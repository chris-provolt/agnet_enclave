"""Recorder: tails enclave:log and persists every event to Postgres.

It is the only consumer of the log stream and the single source for playback.
"""
from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from enclave.bus import LOG_STREAM, Bus, connect
from enclave.config import load_settings
from enclave.events import Event, Kind
from enclave.health import HealthState, serve_health
from enclave.logging import setup_logger

GROUP = "recorder"
os.environ.setdefault("SERVICE_NAME", "recorder")
log = setup_logger("recorder")


def pg_connect(dsn: str) -> psycopg.Connection:
    for attempt in range(30):
        try:
            conn = psycopg.connect(dsn, autocommit=False)
            return conn
        except Exception as exc:  # postgres may still be booting
            log.warning(f"postgres not ready ({exc}); retry {attempt + 1}")
            time.sleep(2)
    raise RuntimeError("postgres unreachable")


def persist(conn: psycopg.Connection, ev: Event) -> None:
    ts = datetime.fromisoformat(ev.ts)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO events (event_id, run_id, ts, seq, sender, recipient, kind, payload, usage)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (event_id) DO NOTHING""",
            (ev.event_id, ev.run_id, ts, ev.seq, ev.sender, ev.recipient, ev.kind.value, Jsonb(ev.payload), Jsonb(ev.usage) if ev.usage is not None else None),
        )
        if ev.kind == Kind.RUN_STARTED:
            cur.execute(
                """INSERT INTO runs (run_id, status, started_at, profile) VALUES (%s, 'running', %s, %s)
                   ON CONFLICT (run_id) DO NOTHING""",
                (ev.run_id, ts, Jsonb(ev.payload.get("profile") or {})),
            )
        elif ev.kind in (Kind.RUN_FINISHED, Kind.RUN_HALTED, Kind.RUN_FAILED):
            if ev.kind == Kind.RUN_HALTED and not ev.payload.get("status"):
                # mid-run halt: the coordinator still asks for a partial report, so keep the run open
                cur.execute("UPDATE runs SET summary = %s WHERE run_id = %s",
                            (f"halted during {ev.payload.get('stage')}: {ev.payload.get('reason')}", ev.run_id))
            else:
                status = ev.payload.get("status") or {Kind.RUN_FINISHED: "finished", Kind.RUN_HALTED: "halted", Kind.RUN_FAILED: "failed"}[ev.kind]
                cur.execute(
                    "UPDATE runs SET status = %s, finished_at = %s, summary = COALESCE(NULLIF(%s, ''), summary) WHERE run_id = %s",
                    (status, ts, ev.payload.get("reason") or ev.payload.get("report_title") or "", ev.run_id),
                )
        elif ev.kind == Kind.LLM_USAGE and ev.usage and ev.usage.get("cost_usd"):
            cur.execute("UPDATE runs SET cost_usd = cost_usd + %s WHERE run_id = %s", (float(ev.usage["cost_usd"]), ev.run_id))
        elif ev.kind == Kind.ARTIFACT:
            cur.execute(
                """INSERT INTO artifacts (run_id, event_id, artifact_type, name, content, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (event_id) DO NOTHING""",
                (ev.run_id, ev.event_id, ev.payload.get("artifact_type", "unknown"), ev.payload.get("name", ""), Jsonb(ev.payload.get("content") or {}), ts),
            )
        elif ev.kind == Kind.APPROVAL:
            cur.execute(
                "INSERT INTO approvals (run_id, decision, notes, decided_at) VALUES (%s, %s, %s, %s)",
                (ev.run_id, ev.payload.get("decision", "?"), ev.payload.get("notes"), ts),
            )


def main() -> None:
    settings = load_settings()
    health = HealthState("recorder")
    serve_health(health, settings.health_port)
    bus = Bus(connect(settings.redis_url))
    bus.ensure_group(LOG_STREAM, GROUP)
    consumer = f"recorder-{socket.gethostname()}"
    conn = pg_connect(settings.postgres_dsn)
    health.beat("ok")
    log.info("recorder online")
    written = 0
    while True:
        try:
            batch = bus.read_group([LOG_STREAM], GROUP, consumer, block_ms=5000, count=200)
        except Exception:
            log.exception("redis read failed")
            health.beat("degraded")
            time.sleep(2)
            continue
        if not batch:
            health.beat("ok", written=written)
            continue
        ids = []
        try:
            for _stream, ev, entry_id in batch:
                ev.event_id = entry_id  # log entries carry their own id
                persist(conn, ev)
                ids.append(entry_id)
            conn.commit()
            bus.ack(LOG_STREAM, GROUP, *ids)
            written += len(ids)
            health.beat("ok", written=written)
        except Exception:
            log.exception("persist failed; rolling back batch")
            conn.rollback()
            health.beat("degraded")
            try:
                conn.close()
            except Exception:
                pass
            conn = pg_connect(settings.postgres_dsn)
            time.sleep(1)


if __name__ == "__main__":
    main()
