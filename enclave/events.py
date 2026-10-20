"""The one event envelope every stream carries.

Every thought, tool call, message, artifact, and lifecycle change is an Event.
Redis stream IDs are millisecond timestamps, so ordering falls out of the bus.
`ts` is an explicit UTC ISO timestamp so events stay self-describing after
export, and `seq` is a per-sender counter so same-millisecond events keep order.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Kind(str, Enum):
    RUN_STARTED = "run.started"
    RUN_FINISHED = "run.finished"
    RUN_HALTED = "run.halted"
    RUN_FAILED = "run.failed"
    STAGE = "run.stage"               # coordinator moved the run to a new stage
    TASK_ASSIGNED = "task.assigned"
    TASK_RESULT = "task.result"
    MSG = "msg"                       # agent to agent note
    THOUGHT = "thought"               # summarized thinking block or note()
    TEXT = "text"                     # visible assistant text
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    LLM_USAGE = "llm.usage"
    REFUSAL = "llm.refusal"
    ARTIFACT = "artifact"
    APPROVAL = "approval.decision"
    CONTROL = "control"
    STATUS = "agent.status"
    ERROR = "error"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Event(BaseModel):
    event_id: Optional[str] = None       # redis stream id, filled in after XADD
    run_id: str
    ts: str = Field(default_factory=now_iso)
    seq: int = 0
    sender: str
    recipient: Optional[str] = None      # None = thought / log only, "*" = broadcast
    kind: Kind
    payload: dict[str, Any] = Field(default_factory=dict)
    usage: Optional[dict[str, Any]] = None

    def to_fields(self) -> dict[str, str]:
        """Flatten for XADD. Redis stream fields are strings."""
        return {
            "run_id": self.run_id,
            "ts": self.ts,
            "seq": str(self.seq),
            "sender": self.sender,
            "recipient": self.recipient or "",
            "kind": self.kind.value,
            "payload": json.dumps(self.payload, default=str, ensure_ascii=True),
            "usage": json.dumps(self.usage, default=str) if self.usage is not None else "",
        }

    @classmethod
    def from_fields(cls, event_id: str, fields: dict[str, str]) -> "Event":
        return cls(
            event_id=event_id,
            run_id=fields.get("run_id", ""),
            ts=fields.get("ts") or now_iso(),
            seq=int(fields.get("seq") or 0),
            sender=fields.get("sender", "?"),
            recipient=fields.get("recipient") or None,
            kind=Kind(fields.get("kind", Kind.ERROR.value)),
            payload=json.loads(fields.get("payload") or "{}"),
            usage=json.loads(fields["usage"]) if fields.get("usage") else None,
        )

    @property
    def ts_dt(self) -> datetime:
        return datetime.fromisoformat(self.ts)

    @staticmethod
    def stream_id_to_dt(event_id: str) -> datetime:
        ms = int(event_id.split("-")[0])
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
