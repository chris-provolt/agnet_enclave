from __future__ import annotations

from enclave.bus import CONTROL_STREAM, LOG_STREAM, Bus, inbox_stream
from enclave.events import Event, Kind
from enclave.pricing import usage_to_usd


def test_event_roundtrip():
    ev = Event(run_id="r1", seq=3, sender="scout", recipient="analyst", kind=Kind.MSG, payload={"text": "hi", "n": [1, 2]}, usage={"cost_usd": 0.01})
    fields = ev.to_fields()
    assert all(isinstance(v, str) for v in fields.values())
    back = Event.from_fields("1700000000000-0", fields)
    assert back.event_id == "1700000000000-0"
    assert back.kind == Kind.MSG
    assert back.payload == {"text": "hi", "n": [1, 2]}
    assert back.usage == {"cost_usd": 0.01}
    assert back.recipient == "analyst"
    assert back.ts == ev.ts


def test_thought_has_no_recipient():
    ev = Event(run_id="r1", sender="critic", kind=Kind.THOUGHT, payload={"text": "hmm"})
    back = Event.from_fields("1-0", ev.to_fields())
    assert back.recipient is None


def test_send_writes_inbox_and_log(redis_client):
    bus = Bus(redis_client)
    ev = Event(run_id="r1", sender="coordinator", recipient="scout", kind=Kind.TASK_ASSIGNED, payload={"task_id": "t1"})
    log_id = bus.send(ev)
    assert redis_client.xlen(LOG_STREAM) == 1
    assert redis_client.xlen(inbox_stream("scout")) == 1
    entry = redis_client.xrange(inbox_stream("scout"))[0][1]
    assert entry["log_id"] == log_id
    assert ev.event_id == log_id


def test_log_only_for_thoughts(redis_client):
    bus = Bus(redis_client)
    bus.log(Event(run_id="r1", sender="scout", kind=Kind.THOUGHT, payload={"text": "x"}))
    assert redis_client.xlen(LOG_STREAM) == 1
    assert redis_client.exists(inbox_stream("scout")) == 0


def test_consumer_group_read_and_ack(redis_client):
    bus = Bus(redis_client)
    stream = inbox_stream("scout")
    bus.ensure_group(stream, "scout")
    bus.ensure_group(stream, "scout")  # idempotent
    for i in range(3):
        bus.send(Event(run_id="r1", sender="coordinator", recipient="scout", kind=Kind.TASK_ASSIGNED, payload={"task_id": f"t{i}"}))
    got = bus.read_group([stream], "scout", "scout-a", block_ms=None, count=2)
    assert [e.payload["task_id"] for _, e, _ in got] == ["t0", "t1"]
    # unacked entries come back for the same consumer on recovery
    pend = bus.pending_for_consumer(stream, "scout", "scout-a")
    assert len(pend) == 2
    bus.ack(stream, "scout", *[eid for _, _, eid in got])
    assert bus.pending_for_consumer(stream, "scout", "scout-a") == []
    rest = bus.read_group([stream], "scout", "scout-b", block_ms=None, count=5)
    assert [e.payload["task_id"] for _, e, _ in rest] == ["t2"]


def test_replay_filters_by_run_and_keeps_order(redis_client):
    bus = Bus(redis_client)
    for i in range(7):
        bus.log(Event(run_id="r1" if i % 2 == 0 else "r2", sender="x", seq=i, kind=Kind.THOUGHT, payload={"i": i}))
    r1 = list(bus.replay("r1", page=2))
    assert [e.payload["i"] for e in r1] == [0, 2, 4, 6]
    everything = list(bus.replay(page=3))
    assert len(everything) == 7
    ids = [e.event_id for e in everything]
    assert ids == sorted(ids)


def test_control_mirrors_to_log(redis_client):
    bus = Bus(redis_client)
    bus.control(Event(run_id="control", sender="dashboard", kind=Kind.CONTROL, payload={"command": "start_run"}))
    assert redis_client.xlen(CONTROL_STREAM) == 1
    assert redis_client.xlen(LOG_STREAM) == 1


def test_cost_accumulates(redis_client):
    bus = Bus(redis_client)
    bus.add_cost("r1", 0.25)
    bus.add_cost("r1", 0.5)
    assert abs(bus.get_cost("r1") - 0.75) < 1e-9
    assert bus.get_cost("other") == 0.0


def test_pricing():
    usd = usage_to_usd("claude-opus-5-5", {"input_tokens": 1_000_000, "output_tokens": 0})
    assert usd == 4.0
    usd = usage_to_usd("claude-opus-5-5", {"input_tokens": 0, "output_tokens": 100_000, "web_search_requests": 2})
    assert abs(usd - (2.0 + 0.02)) < 1e-9
