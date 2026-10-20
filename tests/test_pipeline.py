"""End-to-end mock run, in process, on fakeredis.

Instantiates every agent against one fake Redis server and pumps their inboxes
round-robin until the coordinator finishes the run. Asserts the recorded trail
has the shape the dashboard relies on.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from agents.coordinator import Coordinator
from agents.workers import Analyst, Critic, Planner, Reporter, Scout
from enclave.bus import Bus
from enclave.events import Event, Kind
from enclave.health import HealthState
from enclave.llm import MockLLM


def make_team(settings, redis_client):
    bus = Bus(redis_client)
    llm = MockLLM()
    team = []
    for cls in (Coordinator, Scout, Scout, Analyst, Planner, Critic, Reporter):
        agent = cls(settings, bus, llm, HealthState(cls.role))
        for s in agent.streams():
            bus.ensure_group(s, agent.group)
        team.append(agent)
    # two scouts in one consumer group need distinct consumer names
    team[1].consumer, team[2].consumer = "scout-a", "scout-b"
    return bus, team


def pump(bus: Bus, team, max_cycles: int = 400) -> int:
    """Deliver pending inbox entries to agents until nothing moves."""
    coordinator = team[0]
    cycles = 0
    while cycles < max_cycles:
        moved = False
        for agent in team:
            batch = bus.read_group(agent.streams(), agent.group, agent.consumer, block_ms=None, count=3)
            for stream, ev, entry_id in batch:
                agent._dispatch(stream, ev, entry_id)
                moved = True
        cycles += 1
        if moved:
            continue
        if coordinator.state is None:
            break
        # nothing in flight and nothing moved: give the coordinator a chance to advance or time out
        coordinator.idle_tick()
        if coordinator.state is not None and not coordinator.state.pending:
            coordinator._advance()
        if coordinator.state is None:
            break
    return cycles


def start(bus: Bus, note: str = "") -> None:
    bus.control(Event(run_id="control", sender="dashboard", kind=Kind.CONTROL, payload={"command": "start_run", "note": note, "requested_by": "test"}))


def events_of(bus: Bus, run_id: str) -> list[Event]:
    return list(bus.replay(run_id))


def find_run_id(bus: Bus) -> str:
    for ev in bus.replay():
        if ev.kind == Kind.RUN_STARTED:
            return ev.run_id
    raise AssertionError("no run started")


def test_full_mock_run_produces_report_and_trail(settings, redis_client):
    bus, team = make_team(settings, redis_client)
    start(bus, note="focus on software")
    pump(bus, team)
    coordinator = team[0]
    assert coordinator.state is None, "run should be finished"

    run_id = find_run_id(bus)
    evs = events_of(bus, run_id)
    kinds = [e.kind for e in evs]
    assert kinds[0] == Kind.RUN_STARTED
    assert kinds[-1] == Kind.RUN_FINISHED
    final = evs[-1].payload
    assert final["status"] == "finished"
    assert final["has_report"] is True

    # stages happened in order
    stages = [e.payload["stage"] for e in evs if e.kind == Kind.STAGE]
    assert stages == ["briefing", "scouting", "analysis", "planning", "reporting"]

    # every task got a result and all were ok
    assigned = {e.payload["task_id"] for e in evs if e.kind == Kind.TASK_ASSIGNED}
    results = {e.payload["task_id"]: e.payload["status"] for e in evs if e.kind == Kind.TASK_RESULT}
    assert assigned == set(results)
    assert set(results.values()) == {"ok"}
    assert sum(1 for e in evs if e.kind == Kind.TASK_ASSIGNED and e.payload["task_type"] == "scout") == settings.scout_briefs

    # the critic asked for one revision (financial-data-api round 0) -> planner round 1 -> critic again
    plan_rounds = [e.payload.get("round", 0) for e in evs if e.kind == Kind.TASK_ASSIGNED and e.payload["task_type"] == "plan"]
    assert plan_rounds.count(1) == 1
    assert plan_rounds.count(0) == settings.finalists

    # thoughts, messages, tool calls and usage are all on the record
    assert any(e.kind == Kind.THOUGHT and e.payload["source"] == "thinking" for e in evs)
    assert any(e.kind == Kind.THOUGHT and e.payload["source"] == "note" for e in evs)
    msgs = [e for e in evs if e.kind == Kind.MSG]
    assert msgs and all(e.recipient for e in msgs)
    assert any(e.sender == "scout" and e.recipient == "analyst" for e in msgs)
    assert any(e.kind == Kind.TOOL_CALL and e.payload["side"] == "server" and e.payload["tool"] == "web_search" for e in evs)
    assert any(e.kind == Kind.TOOL_RESULT and e.payload["tool"] == "web_search" for e in evs)
    usage = [e for e in evs if e.kind == Kind.LLM_USAGE]
    assert usage and all((e.usage or {}).get("cost_usd", 0) > 0 for e in usage)
    assert abs(sum(e.usage["cost_usd"] for e in usage) - bus.get_cost(run_id)) < 1e-6
    assert final["cost_usd"] > 0

    # the analyst received the scout's message in its prompt (mailbox drained)
    analyst = team[3]
    assert analyst.mailbox.get(run_id, []) == []

    # artifacts: briefs, 4 scout results, scores, plans, critiques, report
    arts = [e.payload["artifact_type"] for e in evs if e.kind == Kind.ARTIFACT]
    assert arts.count("briefs") == 1 and arts.count("scores") == 1 and arts.count("report") == 1
    assert arts.count("opportunities") == settings.scout_briefs
    assert arts.count("plan") == settings.finalists + 1 and arts.count("critique") == settings.finalists + 1
    report = next(e for e in evs if e.kind == Kind.ARTIFACT and e.payload["artifact_type"] == "report")
    assert "# " in report.payload["content"]["markdown"]
    assert final["report_artifact_event_id"] == report.event_id

    # timestamps are monotonic in stream order and ids are ordered
    ids = [e.event_id for e in evs]
    assert ids == sorted(ids)
    ts = [e.ts for e in evs]
    assert ts == sorted(ts)

    # every event belongs to the run and no event escaped the log
    assert all(e.run_id == run_id for e in evs)
    assert redis_client.xlen("enclave:log") >= len(evs)


def test_budget_halt_produces_partial_report(settings, redis_client):
    tight = replace(settings, max_run_usd=0.10)  # briefing fits, scouts trip
    bus, team = make_team(tight, redis_client)
    start(bus)
    pump(bus, team)
    run_id = find_run_id(bus)
    evs = events_of(bus, run_id)
    assert team[0].state is None
    assert any(e.kind == Kind.RUN_HALTED for e in evs)
    assert evs[-1].kind == Kind.RUN_HALTED and evs[-1].payload["status"] == "halted"
    halted_tasks = [e for e in evs if e.kind == Kind.TASK_RESULT and e.payload["status"] == "halted"]
    assert halted_tasks, "some worker should have stopped on budget"
    # the reporter is budget-exempt so a partial report still lands
    report_task = next(e for e in evs if e.kind == Kind.TASK_ASSIGNED and e.payload["task_type"] == "report")
    assert report_task.payload["partial"] is True and report_task.payload["budget_exempt"] is True
    assert any(e.kind == Kind.ARTIFACT and e.payload["artifact_type"] == "report" for e in evs)
    assert evs[-1].payload["has_report"] is True


def test_second_start_while_busy_is_refused(settings, redis_client):
    bus, team = make_team(settings, redis_client)
    coordinator = team[0]
    start(bus)
    # deliver only the control message so the run is mid-flight
    batch = bus.read_group(coordinator.streams(), coordinator.group, coordinator.consumer, block_ms=None, count=1)
    for stream, ev, eid in batch:
        coordinator._dispatch(stream, ev, eid)
    assert coordinator.state is not None and coordinator.state.stage == "scouting"
    start(bus)
    batch = bus.read_group(coordinator.streams(), coordinator.group, coordinator.consumer, block_ms=None, count=1)
    for stream, ev, eid in batch:
        coordinator._dispatch(stream, ev, eid)
    busy = [e for e in bus.replay() if e.kind == Kind.STATUS and e.payload.get("state") == "run.busy"]
    assert len(busy) == 1


def test_coordinator_resumes_state_from_redis(settings, redis_client):
    bus, team = make_team(settings, redis_client)
    coordinator = team[0]
    start(bus)
    batch = bus.read_group(coordinator.streams(), coordinator.group, coordinator.consumer, block_ms=None, count=1)
    for stream, ev, eid in batch:
        coordinator._dispatch(stream, ev, eid)
    run_id = coordinator.state.run_id
    # a fresh coordinator process picks the run back up
    fresh = Coordinator(settings, bus, MockLLM(), HealthState("coordinator"))
    assert fresh.state is not None and fresh.state.run_id == run_id and fresh.state.stage == "scouting"
    assert len(fresh.state.pending) == settings.scout_briefs
