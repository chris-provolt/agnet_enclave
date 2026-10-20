"""Print a run's events in order straight from the Redis log.

Usage:
  python -m scripts.replay <run_id> [--kinds thought,msg] [--agents scout,critic] [--speed 0]
  python -m scripts.replay --list

--speed N replays with real inter-event delays divided by N (0 = instant).
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from enclave.bus import Bus, connect
from enclave.events import Event, Kind


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_id", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--kinds", default="")
    ap.add_argument("--agents", default="")
    ap.add_argument("--speed", type=float, default=0.0)
    ap.add_argument("--redis", default=os.environ.get("REDIS_URL", "redis://:change-me-redis@localhost:6379/0"))
    args = ap.parse_args()
    bus = Bus(connect(args.redis))

    if args.list or not args.run_id:
        seen: dict[str, dict] = {}
        for ev in bus.replay():
            if ev.kind == Kind.RUN_STARTED:
                seen[ev.run_id] = {"started": ev.ts, "status": "running"}
            elif ev.kind in (Kind.RUN_FINISHED, Kind.RUN_FAILED) or (ev.kind == Kind.RUN_HALTED and ev.payload.get("status")):
                seen.setdefault(ev.run_id, {})["status"] = ev.payload.get("status", ev.kind.value)
        for rid, info in seen.items():
            print(f"{rid}  {info.get('started', '?')}  {info.get('status', '?')}")
        return

    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()}
    agents = {a.strip() for a in args.agents.split(",") if a.strip()}
    prev = None
    for ev in bus.replay(args.run_id):
        if kinds and ev.kind.value not in kinds:
            continue
        if agents and ev.sender not in agents:
            continue
        if args.speed and prev is not None:
            gap = (ev.ts_dt - prev).total_seconds() / args.speed
            if gap > 0:
                time.sleep(min(gap, 5))
        prev = ev.ts_dt
        print(render(ev))


def render(ev: Event) -> str:
    arrow = f" -> {ev.recipient}" if ev.recipient else ""
    head = f"{ev.ts}  {ev.sender:<11}{arrow:<15} {ev.kind.value}"
    p = ev.payload
    if ev.kind in (Kind.THOUGHT, Kind.TEXT, Kind.MSG):
        body = str(p.get("text", ""))
    elif ev.kind == Kind.TOOL_CALL:
        body = f"{p.get('tool')}({p.get('input')})"
    elif ev.kind == Kind.TOOL_RESULT:
        body = str(p.get("output") or p.get("results") or p.get("error") or p)
    elif ev.kind == Kind.LLM_USAGE:
        body = f"turn {p.get('turn')} {p.get('stop_reason')} ${(ev.usage or {}).get('cost_usd', 0):.4f}"
    elif ev.kind == Kind.TASK_ASSIGNED:
        body = f"{p.get('task_type')} {p.get('task_id')}"
    elif ev.kind == Kind.TASK_RESULT:
        body = f"{p.get('task_type')} {p.get('task_id')} {p.get('status')} {p.get('elapsed_s')}s"
    elif ev.kind == Kind.ARTIFACT:
        body = f"{p.get('artifact_type')} {p.get('name')}"
    else:
        body = str({k: v for k, v in p.items() if k != "profile"})
    body = body.replace("\n", " ")
    if len(body) > 300:
        body = body[:297] + "..."
    return f"{head}\n    {body}"


if __name__ == "__main__":
    sys.exit(main())
