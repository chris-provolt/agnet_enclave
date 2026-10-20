"""Coordinator: owns the run state machine.

Stages: briefing -> scouting -> analysis -> planning -> reporting -> done.
Plan/critique rounds interleave per finalist inside the planning stage.
State is mirrored to Redis after every change so a restart resumes the run.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from enclave.agent import BaseAgent
from enclave.bus import CONTROL_STREAM, inbox_stream
from enclave.events import Event, Kind
from enclave.llm import BudgetExceeded
from enclave.schemas import ScoutBriefs

STATE_KEY = "coordinator"


@dataclass
class RunState:
    run_id: str
    stage: str = "briefing"
    started_at: str = ""
    stage_started_at: float = field(default_factory=time.time)
    halted: bool = False
    halt_reason: str = ""
    briefs: list[dict] = field(default_factory=list)
    pending: dict[str, dict] = field(default_factory=dict)        # task_id -> {type, role, opp_id, round}
    candidates: list[dict] = field(default_factory=list)
    dead_ends: list[str] = field(default_factory=list)
    analysis: dict = field(default_factory=dict)
    finalist_ids: list[str] = field(default_factory=list)
    rounds: dict[str, int] = field(default_factory=dict)          # opp_id -> current revision round
    plans: dict[str, dict] = field(default_factory=dict)          # opp_id -> latest plan
    critiques: dict[str, dict] = field(default_factory=dict)      # opp_id -> latest critique
    final: dict[str, bool] = field(default_factory=dict)          # opp_id -> frozen
    report: Optional[dict] = None


class Coordinator(BaseAgent):
    role = "coordinator"
    uses_web = False

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.state: Optional[RunState] = self._load_state()
        if self.state:
            self.current_run = self.state.run_id
            self.log.info("resumed run", extra={"extra_fields": {"run_id": self.state.run_id, "stage": self.state.stage}})

    def streams(self) -> list[str]:
        return [inbox_stream(self.role), CONTROL_STREAM]

    # ----- persistence ---------------------------------------------------
    def _save(self) -> None:
        self.bus.set_state(STATE_KEY, json.dumps(asdict(self.state)) if self.state else "")

    def _load_state(self) -> Optional[RunState]:
        raw = self.bus.get_state(STATE_KEY)
        if not raw:
            return None
        try:
            return RunState(**json.loads(raw))
        except Exception:
            self.log.exception("could not load saved state; starting clean")
            return None

    # ----- event routing ---------------------------------------------------
    def on_event(self, ev: Event) -> None:
        if ev.kind == Kind.CONTROL:
            self._on_control(ev)
        elif ev.kind == Kind.TASK_RESULT:
            self._on_result(ev)

    def idle_tick(self) -> None:
        st = self.state
        if not st or not st.pending:
            return
        if time.time() - st.stage_started_at > self.settings.stage_timeout_s:
            lost = list(st.pending.keys())
            self.emit(Kind.ERROR, {"where": "stage_timeout", "stage": st.stage, "lost_tasks": lost})
            for tid in lost:
                self._task_failed(tid, "stage timeout")
            self._save()
            self._advance()

    def _on_control(self, ev: Event) -> None:
        cmd = ev.payload.get("command")
        if cmd == "start_run":
            if self.state:
                self.emit(Kind.STATUS, {"state": "run.busy", "active_run": self.state.run_id}, run_id=ev.run_id)
                return
            self._start_run(ev.payload)
        elif cmd == "cancel_run":
            if self.state and (not ev.payload.get("run_id") or ev.payload["run_id"] == self.state.run_id):
                self._finish("halted", reason="cancelled by operator")
        else:
            self.emit(Kind.STATUS, {"state": "control.unknown", "command": cmd}, run_id=ev.run_id)

    # ----- helpers -----------------------------------------------------------
    def _stage(self, name: str) -> None:
        assert self.state
        self.state.stage = name
        self.state.stage_started_at = time.time()
        self.emit(Kind.STAGE, {"stage": name, "cost_usd": round(self.bus.get_cost(self.state.run_id), 4)})
        self._save()

    def _assign(self, role: str, task_type: str, payload: dict, **meta: Any) -> str:
        assert self.state
        task_id = f"{task_type}-{uuid.uuid4().hex[:8]}"
        self.state.pending[task_id] = {"type": task_type, "role": role, **meta}
        self.state.stage_started_at = time.time()
        self.emit(Kind.TASK_ASSIGNED, {"task_id": task_id, "task_type": task_type, **payload}, recipient=role)
        self._save()
        return task_id

    def _opp(self, opp_id: str) -> dict:
        assert self.state
        return next((c for c in self.state.candidates if c.get("id") == opp_id), {"id": opp_id, "title": opp_id})

    def _plan_payload(self, opp_id: str, critique: Optional[dict]) -> dict:
        st = self.state
        assert st
        score = next((s for s in st.analysis.get("scored", []) if s.get("opportunity_id") == opp_id), {})
        return {"opportunity": self._opp(opp_id), "score": score, "round": st.rounds.get(opp_id, 0),
                "previous_plan": st.plans.get(opp_id), "critique": critique}

    # ----- run start -----------------------------------------------------------
    def _start_run(self, payload: dict) -> None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.state = RunState(run_id=run_id, started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        self.current_run = run_id
        self.seq = 0
        self._profile_cache = None  # re-read profile.yaml each run
        self.emit(Kind.RUN_STARTED, {
            "profile": self.profile(),
            "settings": {"model": self.settings.llm_model, "mode": self.settings.llm_mode, "effort": self.settings.llm_effort,
                          "max_run_usd": self.settings.max_run_usd, "scout_briefs": self.settings.scout_briefs,
                          "finalists": self.settings.finalists, "max_revision_rounds": self.settings.max_revision_rounds},
            "requested_by": payload.get("requested_by", "dashboard"),
            "note": payload.get("note", ""),
        })
        self._stage("briefing")
        try:
            prompt = (
                f"Produce exactly {self.settings.scout_briefs} scout briefs covering disjoint slices of the opportunity space. "
                "Return a ScoutBriefs JSON."
            )
            if payload.get("note"):
                prompt += "\n\nOperator note for this run: " + str(payload["note"])
            res = self.think(run_id, prompt, ScoutBriefs)
        except BudgetExceeded as exc:
            self._finish("halted", reason=str(exc))
            return
        except Exception as exc:
            self.log.exception("briefing failed")
            self._finish("failed", reason=f"briefing: {exc}")
            return
        self.state.briefs = [b.model_dump(mode="json") for b in res.parsed.briefs]
        self.artifact("briefs", "scout-briefs", res.parsed)
        self._stage("scouting")
        for brief in self.state.briefs:
            self._assign("scout", "scout", {"brief": brief}, brief_name=brief["name"])

    # ----- results -------------------------------------------------------------
    def _on_result(self, ev: Event) -> None:
        st = self.state
        if not st or ev.run_id != st.run_id:
            self.emit(Kind.STATUS, {"state": "result.orphan", "task_id": ev.payload.get("task_id")}, run_id=ev.run_id)
            return
        p = ev.payload
        task_id = p.get("task_id")
        meta = st.pending.pop(task_id, None)
        if meta is None:
            self.emit(Kind.STATUS, {"state": "result.unknown_task", "task_id": task_id})
            return
        status = p.get("status")
        if status == "halted":
            st.halted = True
            st.halt_reason = p.get("error") or "budget exceeded"
        elif status != "ok":
            self._task_failed(task_id, p.get("error") or str(status), meta)
        else:
            self._apply_result(meta, p.get("result") or {})
        self._save()
        self._advance()

    def _task_failed(self, task_id: str, reason: str, meta: Optional[dict] = None) -> None:
        st = self.state
        assert st
        meta = meta or st.pending.pop(task_id, {}) or {}
        self.emit(Kind.ERROR, {"where": "task", "task_id": task_id, "task_type": meta.get("type"), "reason": reason})
        if meta.get("type") == "analyze":
            st.halted = True
            st.halt_reason = f"analyst failed: {reason}"
        if meta.get("type") in ("plan", "critique") and meta.get("opp_id"):
            st.final[meta["opp_id"]] = True  # freeze whatever we have for this finalist
        if meta.get("type") == "report":
            st.halted = True
            st.halt_reason = st.halt_reason or f"reporter failed: {reason}"

    def _apply_result(self, meta: dict, result: dict) -> None:
        st = self.state
        assert st
        t = meta["type"]
        if t == "scout":
            st.candidates.extend(result.get("opportunities", []))
            st.dead_ends.extend(result.get("dead_ends", []))
        elif t == "analyze":
            st.analysis = result
            st.finalist_ids = [f for f in result.get("finalist_ids", []) if any(c.get("id") == f for c in st.candidates)]
        elif t == "plan":
            opp_id = meta["opp_id"]
            st.plans[opp_id] = result
            if not st.halted:
                self._assign("critic", "critique", {"plan": result, "opportunity": self._opp(opp_id), "round": st.rounds.get(opp_id, 0),
                                                    "previous_critique": st.critiques.get(opp_id)}, opp_id=opp_id, round=st.rounds.get(opp_id, 0))
        elif t == "critique":
            opp_id = meta["opp_id"]
            st.critiques[opp_id] = result
            rnd = st.rounds.get(opp_id, 0)
            if result.get("verdict") == "revise" and rnd < self.settings.max_revision_rounds and not st.halted:
                st.rounds[opp_id] = rnd + 1
                self._assign("planner", "plan", self._plan_payload(opp_id, result), opp_id=opp_id, round=rnd + 1)
            else:
                st.final[opp_id] = True
        elif t == "report":
            st.report = result

    def _advance(self) -> None:
        """Move the run forward whenever the current stage has nothing pending."""
        st = self.state
        if not st:
            return
        if st.halted and st.stage not in ("reporting", "done"):
            self.emit(Kind.RUN_HALTED, {"reason": st.halt_reason, "stage": st.stage, "cost_usd": round(self.bus.get_cost(st.run_id), 4)})
            st.pending.clear()
            self._start_reporting(partial=True)
            return
        if st.pending:
            return
        if st.stage == "scouting":
            if not st.candidates:
                self._finish("failed", reason="no candidates from scouts")
                return
            self._stage("analysis")
            self._assign("analyst", "analyze", {"candidates": st.candidates, "dead_ends": st.dead_ends, "finalists": self.settings.finalists})
        elif st.stage == "analysis":
            if not st.finalist_ids:
                self._finish("failed", reason="analyst returned no usable finalists")
                return
            self._stage("planning")
            for opp_id in st.finalist_ids:
                st.rounds[opp_id] = 0
                self._assign("planner", "plan", self._plan_payload(opp_id, None), opp_id=opp_id, round=0)
        elif st.stage == "planning":
            if all(st.final.get(o) for o in st.finalist_ids):
                self._start_reporting(partial=False)
        elif st.stage == "reporting":
            self._finish("halted" if st.halted else "finished", reason=st.halt_reason)

    def _start_reporting(self, partial: bool) -> None:
        st = self.state
        assert st
        self._stage("reporting")
        self._assign("reporter", "report", {
            "partial": partial,
            "halt_reason": st.halt_reason,
            "budget_exempt": True,
            "cost_usd": round(self.bus.get_cost(st.run_id), 4),
            "candidate_count": len(st.candidates),
            "finalist_ids": st.finalist_ids,
            "analysis": st.analysis,
            "plans": dict(st.plans),
            "critiques": dict(st.critiques),
            "dead_ends": st.dead_ends,
        })

    def _finish(self, status: str, reason: str = "") -> None:
        st = self.state
        assert st
        cost = round(self.bus.get_cost(st.run_id), 4)
        kind = {"finished": Kind.RUN_FINISHED, "halted": Kind.RUN_HALTED, "failed": Kind.RUN_FAILED}[status]
        payload: dict[str, Any] = {"status": status, "reason": reason, "cost_usd": cost, "candidates": len(st.candidates),
                                   "finalists": st.finalist_ids, "has_report": st.report is not None, "stage": "done"}
        if st.report:
            payload["report_artifact_event_id"] = st.report.get("artifact_event_id")
            payload["report_title"] = st.report.get("title")
        self.emit(kind, payload)
        self.state = None
        self._save()
        self.current_run = None
