"""LLM access for agents.

AnthropicLLM runs a manual agentic loop against the Claude API so that every
thinking block, text block, tool call, and tool result can be recorded as an
event in order. MockLLM produces schema-valid canned output with a realistic
event trail so the whole pipeline can run with zero spend.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from pydantic import BaseModel

from .events import Kind
from .pricing import usage_to_usd
from .schemas import json_schema_for

OnEvent = Callable[[Kind, dict, Optional[dict]], None]

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 12}
WEB_FETCH_TOOL = {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 12, "max_content_tokens": 20000}


class LLMError(RuntimeError):
    pass


class LLMRefused(LLMError):
    pass


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    fn: Callable[[dict], str]

    def definition(self) -> dict:
        schema = dict(self.input_schema)
        schema.setdefault("additionalProperties", False)
        schema.setdefault("required", list((schema.get("properties") or {}).keys()))
        return {"name": self.name, "description": self.description, "strict": True, "input_schema": schema}


@dataclass
class LLMResult:
    text: str
    parsed: Any = None
    stop_reason: str = "end_turn"
    turns: int = 0
    cost_usd: float = 0.0
    model: str = ""
    raw_usage: list[dict] = field(default_factory=list)


class LLM(Protocol):
    def complete(
        self,
        *,
        role: str,
        system: str,
        user_content: str,
        tools: list[ToolSpec],
        use_web: bool,
        output_schema: Optional[type[BaseModel]],
        on_event: OnEvent,
        budget_check: Callable[[], None],
        context: Optional[dict] = None,
    ) -> LLMResult: ...


def _flatten_usage(usage: Any) -> dict:
    data = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage or {})
    flat = {
        "input_tokens": data.get("input_tokens", 0) or 0,
        "output_tokens": data.get("output_tokens", 0) or 0,
        "cache_creation_input_tokens": data.get("cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": data.get("cache_read_input_tokens", 0) or 0,
    }
    stu = data.get("server_tool_use") or {}
    flat["web_search_requests"] = stu.get("web_search_requests", 0) or 0
    flat["web_fetch_requests"] = stu.get("web_fetch_requests", 0) or 0
    return flat


class AnthropicLLM:
    """Manual loop on client.beta.messages.create (beta is needed for fallbacks)."""

    def __init__(self, model: str, effort: str = "high", max_tokens: int = 16000, max_turns: int = 40, refusal_retries: int = 2) -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self.max_turns = max_turns
        self.refusal_retries = refusal_retries

    def complete(
        self,
        *,
        role: str,
        system: str,
        user_content: str,
        tools: list[ToolSpec],
        use_web: bool,
        output_schema: Optional[type[BaseModel]],
        on_event: OnEvent,
        budget_check: Callable[[], None],
        context: Optional[dict] = None,
    ) -> LLMResult:
        tool_map = {t.name: t for t in tools}
        tool_defs: list[dict] = []
        if use_web:
            tool_defs.extend([WEB_SEARCH_TOOL, WEB_FETCH_TOOL])
        tool_defs.extend(t.definition() for t in tools)

        output_config: dict = {"effort": self.effort}
        if output_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": json_schema_for(output_schema)}

        messages: list[dict] = [{"role": "user", "content": user_content}]
        result = LLMResult(text="", model=self.model)
        refusals = 0
        turn = 0

        while turn < self.max_turns:
            turn += 1
            budget_check()
            kwargs: dict = dict(
                model=self.model,
                max_tokens=self.max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config=output_config,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            if tool_defs:
                kwargs["tools"] = tool_defs
            resp = self.client.beta.messages.create(**kwargs)
            result.turns = turn

            usage = _flatten_usage(resp.usage)
            usage["cost_usd"] = usage_to_usd(self.model, usage)
            result.cost_usd += usage["cost_usd"]
            result.raw_usage.append(usage)
            on_event(Kind.LLM_USAGE, {"turn": turn, "model": resp.model, "stop_reason": resp.stop_reason}, usage)

            for block in resp.content:
                btype = getattr(block, "type", "")
                if btype == "thinking":
                    text = getattr(block, "thinking", "") or ""
                    if text.strip():
                        on_event(Kind.THOUGHT, {"source": "thinking", "text": text}, None)
                elif btype == "text":
                    on_event(Kind.TEXT, {"text": block.text}, None)
                elif btype == "tool_use":
                    on_event(Kind.TOOL_CALL, {"side": "client", "tool": block.name, "tool_use_id": block.id, "input": block.input}, None)
                elif btype == "server_tool_use":
                    on_event(Kind.TOOL_CALL, {"side": "server", "tool": block.name, "tool_use_id": block.id, "input": block.input}, None)
                elif btype == "web_search_tool_result":
                    on_event(Kind.TOOL_RESULT, {"side": "server", "tool": "web_search", "tool_use_id": block.tool_use_id, **_summarize_search(block.content)}, None)
                elif btype == "web_fetch_tool_result":
                    on_event(Kind.TOOL_RESULT, {"side": "server", "tool": "web_fetch", "tool_use_id": block.tool_use_id, **_summarize_fetch(block.content)}, None)
                elif btype == "fallback":
                    on_event(Kind.STATUS, {"event": "fallback", "from": getattr(getattr(block, "from_", None), "model", None), "to": getattr(getattr(block, "to", None), "model", None)}, None)

            stop = resp.stop_reason or "end_turn"
            result.stop_reason = stop

            if stop == "refusal":
                # Safety classifiers are probabilistic; a fresh request usually passes.
                details = getattr(resp, "stop_details", None)
                category = getattr(details, "category", None)
                refusals += 1
                retrying = refusals <= self.refusal_retries
                on_event(Kind.REFUSAL, {"category": category, "explanation": getattr(details, "explanation", None),
                                        "attempt": refusals, "retrying": retrying}, None)
                if not retrying:
                    raise LLMRefused(f"model refused {refusals} times ({category})")
                messages = [{"role": "user", "content": user_content}]  # restart the task from scratch
                time.sleep(2 * refusals)
                continue

            if stop == "pause_turn":
                messages.append({"role": "assistant", "content": resp.content})
                continue

            if stop == "max_tokens":
                raise LLMError("hit max_tokens before finishing; raise LLM_MAX_TOKENS")

            if stop == "tool_use":
                messages.append({"role": "assistant", "content": resp.content})
                results = []
                for block in resp.content:
                    if getattr(block, "type", "") != "tool_use":
                        continue
                    spec = tool_map.get(block.name)
                    is_error = False
                    try:
                        if spec is None:
                            raise KeyError(f"unknown tool {block.name}")
                        inp = block.input if isinstance(block.input, dict) else json.loads(block.input)
                        content = spec.fn(inp)
                    except Exception as exc:  # tool failure goes back to the model, not up the stack
                        is_error = True
                        content = f"tool error: {exc}"
                    on_event(Kind.TOOL_RESULT, {"side": "client", "tool": block.name, "tool_use_id": block.id, "output": content, "is_error": is_error}, None)
                    item: dict = {"type": "tool_result", "tool_use_id": block.id, "content": content}
                    if is_error:
                        item["is_error"] = True
                    results.append(item)
                messages.append({"role": "user", "content": results})
                continue

            # end_turn (or stop_sequence)
            texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            result.text = "\n".join(texts).strip()
            if output_schema is not None:
                result.parsed = output_schema.model_validate_json(texts[-1] if texts else "{}")
            return result

        raise LLMError(f"agent loop exceeded {self.max_turns} turns")


def _summarize_search(content: Any) -> dict:
    if isinstance(content, list):
        items = []
        for r in content:
            items.append({"title": getattr(r, "title", None), "url": getattr(r, "url", None), "page_age": getattr(r, "page_age", None)})
        return {"results": items, "count": len(items)}
    return {"error": getattr(content, "error_code", str(content))}


def _summarize_fetch(content: Any) -> dict:
    if getattr(content, "type", "") == "web_fetch_result":
        doc = getattr(content, "content", None)
        src = getattr(doc, "source", None)
        text = getattr(src, "data", "") or ""
        return {"url": getattr(content, "url", None), "retrieved_at": getattr(content, "retrieved_at", None), "chars": len(text) if isinstance(text, str) else None}
    return {"error": getattr(content, "error_code", str(content))}


class MockLLM:
    """Scripted stand-in. Emits a believable event trail and schema-valid JSON."""

    def __init__(self, model: str = "mock-claude", delay_s: float = 0.15) -> None:
        self.model = model
        self.delay_s = float(os.environ.get("MOCK_DELAY_S", delay_s))

    def complete(
        self,
        *,
        role: str,
        system: str,
        user_content: str,
        tools: list[ToolSpec],
        use_web: bool,
        output_schema: Optional[type[BaseModel]],
        on_event: OnEvent,
        budget_check: Callable[[], None],
        context: Optional[dict] = None,
    ) -> LLMResult:
        from . import mock_data

        context = context or {}
        tool_map = {t.name: t for t in tools}
        script = mock_data.script_for(role, context)
        turn = 0
        total_cost = 0.0

        def usage_event(stop: str) -> None:
            nonlocal turn, total_cost
            turn += 1
            u = {"input_tokens": 2400 + 300 * turn, "output_tokens": 350, "cache_creation_input_tokens": 0 if turn > 1 else 1800,
                 "cache_read_input_tokens": 1800 if turn > 1 else 0, "web_search_requests": 1 if use_web and stop == "tool_use" else 0, "web_fetch_requests": 0}
            u["cost_usd"] = usage_to_usd("claude-opus-5-5", u)
            total_cost += u["cost_usd"]
            on_event(Kind.LLM_USAGE, {"turn": turn, "model": self.model, "stop_reason": stop}, u)

        budget_check()
        usage_event("tool_use")
        for step in script["steps"]:
            time.sleep(self.delay_s)
            kind = step["kind"]
            if kind == "thought":
                on_event(Kind.THOUGHT, {"source": "thinking", "text": step["text"]}, None)
            elif kind == "web_search" and use_web:
                tid = f"srvtoolu_mock_{turn}_{int(time.time()*1000)%100000}"
                on_event(Kind.TOOL_CALL, {"side": "server", "tool": "web_search", "tool_use_id": tid, "input": {"query": step["query"]}}, None)
                time.sleep(self.delay_s)
                on_event(Kind.TOOL_RESULT, {"side": "server", "tool": "web_search", "tool_use_id": tid, "results": step["results"], "count": len(step["results"])}, None)
            elif kind == "tool" and step["tool"] in tool_map:
                tid = f"toolu_mock_{turn}_{int(time.time()*1000)%100000}"
                on_event(Kind.TOOL_CALL, {"side": "client", "tool": step["tool"], "tool_use_id": tid, "input": step["input"]}, None)
                try:
                    out = tool_map[step["tool"]].fn(step["input"])
                    err = False
                except Exception as exc:
                    out, err = f"tool error: {exc}", True
                on_event(Kind.TOOL_RESULT, {"side": "client", "tool": step["tool"], "tool_use_id": tid, "output": out, "is_error": err}, None)
                budget_check()
                usage_event("tool_use")
        time.sleep(self.delay_s)
        budget_check()
        usage_event("end_turn")

        payload = script["output"]
        parsed = None
        if output_schema is not None:
            parsed = output_schema.model_validate(payload)
            text = parsed.model_dump_json()
        else:
            text = payload if isinstance(payload, str) else json.dumps(payload)
        on_event(Kind.TEXT, {"text": text[:4000]}, None)
        return LLMResult(text=text, parsed=parsed, stop_reason="end_turn", turns=turn, cost_usd=total_cost, model=self.model)


def build_llm(mode: str, model: str, effort: str, max_tokens: int) -> LLM:
    if mode == "live":
        return AnthropicLLM(model=model, effort=effort, max_tokens=max_tokens)
    return MockLLM()
