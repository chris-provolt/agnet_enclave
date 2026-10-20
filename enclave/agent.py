"""BaseAgent: inbox loop plus automatic recording of everything an agent does.

Subclasses implement handle_task(event) and return a dict result. Everything
else (thinking, tool calls, messages, usage, errors) is recorded as events on
the bus by this class, so no agent can communicate off the record.
"""
from __future__ import annotations

import json
import socket
import time
import traceback
from typing import Any, Optional

import yaml
from pydantic import BaseModel

from .bus import Bus, inbox_stream
from .config import ROLES, Settings, load_profile, load_prompt
from .events import Event, Kind
from .health import HealthState
from .llm import LLM, BudgetExceeded, LLMRefused, LLMResult, ToolSpec
from .logging import setup_logger


class BaseAgent:
    role: str = "base"
    uses_web: bool = False

    def __init__(self, settings: Settings, bus: Bus, llm: LLM, health: HealthState) -> None:
        self.settings = settings
        self.bus = bus
        self.llm = llm
        self.health = health
        self.log = setup_logger(self.role)
        self.consumer = f"{self.role}-{socket.gethostname()}"
        self.group = self.role
        self.seq = 0
        self.current_run: Optional[str] = None
        self.mailbox: dict[str, list[dict]] = {}
        self._profile_cache: Optional[dict] = None
        self._budget_exempt = False

    # ----- streams this agent listens on ---------------------------------
    def streams(self) -> list[str]:
        return [inbox_stream(self.role)]

    # ----- main loop ------------------------------------------------------
    def run_forever(self) -> None:
        for s in self.streams():
            self.bus.ensure_group(s, self.group)
        self.health.beat("ok", consumer=self.consumer)
        self.log.info("agent online", extra={"extra_fields": {"consumer": self.consumer, "streams": self.streams()}})
        # crash recovery: finish anything we read but never acked
        for s in self.streams():
            for stream, ev, entry_id in self.bus.pending_for_consumer(s, self.group, self.consumer):
                self._dispatch(stream, ev, entry_id)
        while True:
            try:
                batch = self.bus.read_group(self.streams(), self.group, self.consumer, block_ms=5000, count=5)
            except Exception:  # redis hiccup: back off and retry
                self.log.exception("read failed; retrying")
                self.health.beat("degraded")
                time.sleep(2)
                continue
            self.health.beat("ok")
            for stream, ev, entry_id in batch:
                self._dispatch(stream, ev, entry_id)
            self.idle_tick()

    def idle_tick(self) -> None:
        """Hook for subclasses (coordinator uses it for stage timeouts)."""

    def _dispatch(self, stream: str, ev: Event, entry_id: str) -> None:
        try:
            if ev.kind == Kind.TASK_ASSIGNED:
                self._run_task(ev)
            elif ev.kind == Kind.MSG:
                self.mailbox.setdefault(ev.run_id, []).append({"from": ev.sender, "ts": ev.ts, "text": ev.payload.get("text", "")})
            else:
                self.on_event(ev)
        except Exception:
            self.log.exception("dispatch failed")
            self.emit(Kind.ERROR, {"where": "dispatch", "kind": ev.kind.value, "trace": traceback.format_exc()[-2000:]}, run_id=ev.run_id)
        finally:
            self.bus.ack(stream, self.group, entry_id)

    def on_event(self, ev: Event) -> None:
        """Non-task, non-message events (coordinator overrides)."""

    def _run_task(self, ev: Event) -> None:
        self.current_run = ev.run_id
        task = ev.payload
        task_id = task.get("task_id", "?")
        self._budget_exempt = bool(task.get("budget_exempt"))
        self.health.beat("busy", task=task.get("task_type"), run_id=ev.run_id)
        self.emit(Kind.STATUS, {"state": "task.start", "task_id": task_id, "task_type": task.get("task_type")})
        started = time.time()
        status, result, error = "ok", None, None
        try:
            result = self.handle_task(ev)
        except BudgetExceeded as exc:
            status, error = "halted", str(exc)
        except LLMRefused as exc:
            status, error = "refused", str(exc)
        except Exception as exc:
            status, error = "error", f"{type(exc).__name__}: {exc}"
            self.log.exception("task failed")
            self.emit(Kind.ERROR, {"where": "handle_task", "task_id": task_id, "trace": traceback.format_exc()[-3000:]})
        payload = {
            "task_id": task_id,
            "task_type": task.get("task_type"),
            "status": status,
            "result": result,
            "error": error,
            "elapsed_s": round(time.time() - started, 2),
            "run_cost_usd": round(self.bus.get_cost(ev.run_id), 4),
        }
        self.emit(Kind.TASK_RESULT, payload, recipient=ev.sender)
        self.emit(Kind.STATUS, {"state": "task.done", "task_id": task_id, "status": status})
        self.health.beat("ok")

    def handle_task(self, ev: Event) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    # ----- recording -----------------------------------------------------
    def emit(self, kind: Kind, payload: dict, recipient: Optional[str] = None, usage: Optional[dict] = None, run_id: Optional[str] = None) -> Event:
        self.seq += 1
        ev = Event(run_id=run_id or self.current_run or "none", seq=self.seq, sender=self.role, recipient=recipient, kind=kind, payload=payload, usage=usage)
        if recipient and recipient != "*":
            self.bus.send(ev)
        else:
            self.bus.log(ev)
        return ev

    def artifact(self, artifact_type: str, name: str, content: Any) -> Event:
        if isinstance(content, BaseModel):
            content = content.model_dump(mode="json")
        return self.emit(Kind.ARTIFACT, {"artifact_type": artifact_type, "name": name, "content": content})

    # ----- LLM access -----------------------------------------------------
    def profile(self) -> dict:
        if self._profile_cache is None:
            self._profile_cache = load_profile(self.settings.profile_path)
        return self._profile_cache

    def system_prompt(self) -> str:
        prompt = load_prompt(self.role, self.settings.prompts_dir)
        profile_yaml = yaml.safe_dump(self.profile(), sort_keys=False)
        return f"{prompt}\n\n# Operator profile (ground truth)\n\n```yaml\n{profile_yaml}```\n"

    def default_tools(self, run_id: str) -> list[ToolSpec]:
        def note(inp: dict) -> str:
            self.emit(Kind.THOUGHT, {"source": "note", "text": inp.get("text", "")}, run_id=run_id)
            return "noted"

        def send_message(inp: dict) -> str:
            to = str(inp.get("to", "")).strip().lower()
            if to not in ROLES:
                return f"unknown recipient '{to}'. Valid: {', '.join(ROLES)}"
            self.emit(Kind.MSG, {"text": inp.get("text", "")}, recipient=to, run_id=run_id)
            return f"delivered to {to}"

        return [
            # Wording matters here: descriptions that mention recording decisions, doubts, or
            # working notes trip the API's reasoning_extraction classifier (verified by probing).
            ToolSpec("log_finding", "Log a fact or finding for the operator, such as a source checked or an option ruled out.",
                     {"type": "object", "properties": {"text": {"type": "string"}}}, note),
            ToolSpec("send_message", "Send a short message to another agent on the team.",
                     {"type": "object", "properties": {"to": {"type": "string", "enum": list(ROLES)}, "text": {"type": "string"}}}, send_message),
        ]

    def think(self, run_id: str, user_content: str, output_schema: Optional[type[BaseModel]] = None,
              use_web: Optional[bool] = None, extra_tools: Optional[list[ToolSpec]] = None, context: Optional[dict] = None) -> LLMResult:
        inbox = self.mailbox.pop(run_id, [])
        if inbox:
            lines = "\n".join(f"- [{m['ts']}] from {m['from']}: {m['text']}" for m in inbox)
            user_content = f"Messages received from other agents since your last task:\n{lines}\n\n---\n\n{user_content}"

        def on_event(kind: Kind, payload: dict, usage: Optional[dict]) -> None:
            self.emit(kind, payload, usage=usage, run_id=run_id)
            if kind == Kind.LLM_USAGE and usage and usage.get("cost_usd"):
                self.bus.add_cost(run_id, float(usage["cost_usd"]))

        def budget_check() -> None:
            if self._budget_exempt:
                return
            spent = self.bus.get_cost(run_id)
            if spent > self.settings.max_run_usd:
                raise BudgetExceeded(f"run spend ${spent:.2f} exceeds MAX_RUN_USD ${self.settings.max_run_usd:.2f}")

        ctx = dict(context or {})
        ctx.setdefault("cost_usd", self.bus.get_cost(run_id))
        return self.llm.complete(
            role=self.role,
            system=self.system_prompt(),
            user_content=user_content,
            tools=self.default_tools(run_id) + list(extra_tools or []),
            use_web=self.uses_web if use_web is None else use_web,
            output_schema=output_schema,
            on_event=on_event,
            budget_check=budget_check,
            context=ctx,
        )

    @staticmethod
    def block(title: str, data: Any) -> str:
        """Render a labelled JSON block for a user prompt."""
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json")
        return f"## {title}\n\n```json\n{json.dumps(data, indent=2, default=str)}\n```\n"
