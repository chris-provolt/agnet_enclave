"""Redis Streams message bus.

Streams:
  enclave:log            append-only log of every event (recorder consumes it)
  enclave:inbox:<role>   task and message delivery per role (consumer group per role)
  enclave:control        dashboard -> coordinator commands

Every inbox or control write is mirrored to enclave:log, so the log alone is a
complete, replayable record of the run.
"""
from __future__ import annotations

from typing import Iterator, Optional

import redis

from .events import Event

LOG_STREAM = "enclave:log"
CONTROL_STREAM = "enclave:control"
INBOX_PREFIX = "enclave:inbox:"
LOG_MAXLEN = 2_000_000


def inbox_stream(role: str) -> str:
    return f"{INBOX_PREFIX}{role}"


def connect(url: str) -> redis.Redis:
    # redis-py 8 defaults socket_timeout to 5s, which collides with 5s blocking reads.
    return redis.Redis.from_url(url, decode_responses=True, socket_keepalive=True, health_check_interval=30,
                                socket_timeout=30, socket_connect_timeout=10)


class Bus:
    def __init__(self, client: redis.Redis, log_stream: str = LOG_STREAM, maxlen: int = LOG_MAXLEN) -> None:
        self.r = client
        self.log_stream = log_stream
        self.maxlen = maxlen

    # ----- writes -------------------------------------------------------
    def log(self, event: Event) -> str:
        """Append to the global log only (thoughts, tool calls, usage, artifacts)."""
        event_id = self.r.xadd(self.log_stream, event.to_fields(), maxlen=self.maxlen, approximate=True)
        event.event_id = event_id
        return event_id

    def send(self, event: Event) -> str:
        """Deliver to the recipient's inbox and mirror to the log. Returns the log id."""
        if not event.recipient or event.recipient == "*":
            raise ValueError("send() needs a concrete recipient role")
        log_id = self.log(event)
        fields = event.to_fields()
        fields["log_id"] = log_id
        self.r.xadd(inbox_stream(event.recipient), fields, maxlen=100_000, approximate=True)
        return log_id

    def control(self, event: Event) -> str:
        log_id = self.log(event)
        fields = event.to_fields()
        fields["log_id"] = log_id
        self.r.xadd(CONTROL_STREAM, fields, maxlen=10_000, approximate=True)
        return log_id

    # ----- consumer groups ---------------------------------------------
    def ensure_group(self, stream: str, group: str) -> None:
        try:
            self.r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def read_group(
        self, streams: list[str], group: str, consumer: str, block_ms: int = 5000, count: int = 10
    ) -> list[tuple[str, Event, str]]:
        """XREADGROUP across streams. Returns (stream, event, stream_entry_id)."""
        out: list[tuple[str, Event, str]] = []
        resp = self.r.xreadgroup(group, consumer, {s: ">" for s in streams}, count=count, block=block_ms)
        for stream, entries in resp or []:
            for entry_id, fields in entries:
                ev = Event.from_fields(fields.get("log_id") or entry_id, fields)
                out.append((stream, ev, entry_id))
        return out

    def pending_for_consumer(
        self, stream: str, group: str, consumer: str, count: int = 50
    ) -> list[tuple[str, Event, str]]:
        """Entries this consumer read but never acked (crash recovery)."""
        out: list[tuple[str, Event, str]] = []
        resp = self.r.xreadgroup(group, consumer, {stream: "0"}, count=count)
        for s, entries in resp or []:
            for entry_id, fields in entries:
                ev = Event.from_fields(fields.get("log_id") or entry_id, fields)
                out.append((s, ev, entry_id))
        return out

    def ack(self, stream: str, group: str, *entry_ids: str) -> None:
        if entry_ids:
            self.r.xack(stream, group, *entry_ids)

    # ----- replay / tail -------------------------------------------------
    def replay(
        self, run_id: Optional[str] = None, start: str = "-", end: str = "+", page: int = 500
    ) -> Iterator[Event]:
        """Iterate the log in order via XRANGE pages, optionally filtered to one run."""
        cursor = start
        while True:
            rows = self.r.xrange(self.log_stream, min=cursor, max=end, count=page)
            if not rows:
                return
            for entry_id, fields in rows:
                if run_id is None or fields.get("run_id") == run_id:
                    yield Event.from_fields(entry_id, fields)
            last = rows[-1][0]
            if len(rows) < page:
                return
            cursor = "(" + last

    def tail(self, last_id: str = "$", block_ms: int = 5000, count: int = 100) -> tuple[str, list[Event]]:
        """Live follow of the log. Returns (new_last_id, events)."""
        resp = self.r.xread({self.log_stream: last_id}, count=count, block=block_ms)
        events: list[Event] = []
        for _stream, entries in resp or []:
            for entry_id, fields in entries:
                events.append(Event.from_fields(entry_id, fields))
                last_id = entry_id
        return last_id, events

    # ----- run bookkeeping ----------------------------------------------
    def add_cost(self, run_id: str, usd: float) -> float:
        return float(self.r.incrbyfloat(f"enclave:run:{run_id}:cost_usd", usd))

    def get_cost(self, run_id: str) -> float:
        raw = self.r.get(f"enclave:run:{run_id}:cost_usd")
        return float(raw) if raw else 0.0

    def set_state(self, key: str, value: str) -> None:
        self.r.set(f"enclave:state:{key}", value)

    def get_state(self, key: str) -> Optional[str]:
        return self.r.get(f"enclave:state:{key}")
