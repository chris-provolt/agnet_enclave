"""Dashboard: start runs, read and approve reports, replay or live-tail any run."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

import markdown as md
import psycopg
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row
from sse_starlette.sse import EventSourceResponse

from enclave.bus import Bus, connect
from enclave.config import load_settings
from enclave.events import Event, Kind
from enclave.logging import setup_logger

os.environ.setdefault("SERVICE_NAME", "dashboard")
log = setup_logger("dashboard")
settings = load_settings()
HERE = Path(__file__).resolve().parent

app = FastAPI(title="Enclave dashboard")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
templates = Jinja2Templates(directory=str(HERE / "templates"))

_bus: Optional[Bus] = None


def bus() -> Bus:
    global _bus
    if _bus is None:
        _bus = Bus(connect(settings.redis_url))
    return _bus


def db() -> psycopg.Connection:
    return psycopg.connect(settings.postgres_dsn, row_factory=dict_row, autocommit=True)


def active_run() -> Optional[dict]:
    raw = bus().get_state("coordinator")
    if not raw:
        return None
    try:
        st = json.loads(raw)
    except Exception:
        return None
    return {"run_id": st.get("run_id"), "stage": st.get("stage"), "pending": len(st.get("pending") or {}),
            "cost_usd": round(bus().get_cost(st.get("run_id", "")), 4), "halted": st.get("halted")}


def _json_safe(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        elif v is not None and type(v).__name__ == "Decimal":
            v = float(v)
        out[k] = v
    return out


# ----- pages ---------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    with db() as conn:
        runs = conn.execute(
            """SELECT r.run_id, r.status, r.started_at, r.finished_at, r.cost_usd, r.summary,
                      (SELECT decision FROM approvals a WHERE a.run_id = r.run_id ORDER BY decided_at DESC LIMIT 1) AS decision,
                      (SELECT count(*) FROM events e WHERE e.run_id = r.run_id) AS event_count
               FROM runs r ORDER BY started_at DESC LIMIT 100"""
        ).fetchall()
    return templates.TemplateResponse(request, "index.html", {"runs": runs, "active": active_run(), "settings": settings})


@app.post("/runs")
def start_run(note: str = Form("")) -> RedirectResponse:
    ev = Event(run_id="control", sender="dashboard", kind=Kind.CONTROL,
               payload={"command": "start_run", "note": note.strip(), "requested_by": "dashboard"})
    bus().control(ev)
    return RedirectResponse("/", status_code=303)


@app.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> RedirectResponse:
    ev = Event(run_id=run_id, sender="dashboard", kind=Kind.CONTROL, payload={"command": "cancel_run", "run_id": run_id})
    bus().control(ev)
    return RedirectResponse("/", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str) -> HTMLResponse:
    with db() as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_id = %s", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "run not found")
        report = conn.execute(
            "SELECT * FROM artifacts WHERE run_id = %s AND artifact_type = 'report' ORDER BY created_at DESC LIMIT 1", (run_id,)
        ).fetchone()
        artifacts = conn.execute(
            "SELECT id, artifact_type, name, created_at FROM artifacts WHERE run_id = %s ORDER BY created_at", (run_id,)
        ).fetchall()
        approvals = conn.execute("SELECT * FROM approvals WHERE run_id = %s ORDER BY decided_at DESC", (run_id,)).fetchall()
        kinds = conn.execute("SELECT kind, count(*) AS n FROM events WHERE run_id = %s GROUP BY kind ORDER BY n DESC", (run_id,)).fetchall()
        agents = conn.execute("SELECT sender, count(*) AS n FROM events WHERE run_id = %s GROUP BY sender ORDER BY n DESC", (run_id,)).fetchall()
    report_html = ""
    if report:
        report_html = md.markdown(report["content"].get("markdown", ""), extensions=["tables", "fenced_code"])
    return templates.TemplateResponse(request, "run.html", {
        "run": run, "report": report, "report_html": report_html, "artifacts": artifacts,
        "approvals": approvals, "kinds": kinds, "agents": agents, "active": active_run(),
    })


@app.post("/runs/{run_id}/decision")
def decide(run_id: str, decision: str = Form(...), notes: str = Form("")) -> RedirectResponse:
    if decision not in ("approve", "reject", "request_changes"):
        raise HTTPException(400, "bad decision")
    ev = Event(run_id=run_id, sender="dashboard", kind=Kind.APPROVAL, payload={"decision": decision, "notes": notes.strip(), "by": "operator"})
    bus().log(ev)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@app.get("/runs/{run_id}/player", response_class=HTMLResponse)
def player(request: Request, run_id: str) -> HTMLResponse:
    with db() as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_id = %s", (run_id,)).fetchone()
    if not run:
        raise HTTPException(404, "run not found")
    return templates.TemplateResponse(request, "player.html", {"run": run})


# ----- API ----------------------------------------------------------------------
@app.get("/api/runs/{run_id}/events")
def api_events(run_id: str, after: Optional[str] = None, limit: int = 20000) -> JSONResponse:
    with db() as conn:
        if after:
            rows = conn.execute(
                "SELECT * FROM events WHERE run_id = %s AND event_id > %s ORDER BY ts, event_id LIMIT %s", (run_id, after, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM events WHERE run_id = %s ORDER BY ts, event_id LIMIT %s", (run_id, limit)).fetchall()
    return JSONResponse([_json_safe(r) for r in rows])


@app.get("/api/runs/{run_id}/live")
async def api_live(request: Request, run_id: str, after: str = "$") -> EventSourceResponse:
    async def gen():
        last = after
        b = bus()
        while not await request.is_disconnected():
            try:
                last, events = await asyncio.to_thread(b.tail, last, 2000, 200)
            except Exception as exc:
                log.warning(f"tail failed: {exc}")
                await asyncio.sleep(2)
                continue
            for ev in events:
                if ev.run_id != run_id:
                    continue
                data = ev.model_dump(mode="json")
                data["kind"] = ev.kind.value
                yield {"event": "ev", "data": json.dumps(data, default=str)}
            if not events:
                yield {"event": "ping", "data": last}

    return EventSourceResponse(gen())


@app.get("/api/runs/{run_id}/report.md")
def api_report_md(run_id: str) -> PlainTextResponse:
    with db() as conn:
        report = conn.execute(
            "SELECT content FROM artifacts WHERE run_id = %s AND artifact_type = 'report' ORDER BY created_at DESC LIMIT 1", (run_id,)
        ).fetchone()
    if not report:
        raise HTTPException(404, "no report yet")
    return PlainTextResponse(report["content"].get("markdown", ""), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="enclave-report-{run_id}.md"'})


@app.get("/api/runs/{run_id}/artifacts/{artifact_id}")
def api_artifact(run_id: str, artifact_id: int) -> JSONResponse:
    with db() as conn:
        art = conn.execute("SELECT * FROM artifacts WHERE run_id = %s AND id = %s", (run_id, artifact_id)).fetchone()
    if not art:
        raise HTTPException(404, "artifact not found")
    return JSONResponse(_json_safe(art))


@app.get("/api/active")
def api_active() -> JSONResponse:
    return JSONResponse(active_run() or {})
