# Agent Enclave

A Dockerized team of Claude agents that researches passive-income opportunities,
turns the best ones into execution plans, red-teams those plans, and hands you an
approval report. Nothing is executed without your approval. Every agent thought,
tool call, and inter-agent message is timestamped on a Redis Stream and persisted
to Postgres, so any run can be replayed in the dashboard.

## Team

| Role | What it does | Web access |
|---|---|---|
| coordinator | Owns the run. Splits the search space into scout briefs, dispatches tasks, enforces the budget, drives stages. | no |
| scout (x2) | Searches the web for candidates in its brief. Returns 5-15 opportunities with sourced numbers. | yes |
| analyst | Dedups, scores, and picks finalists. | yes (sparingly) |
| planner | Writes an execution plan per finalist; revises when the critic asks. | no |
| critic | Red-teams each plan, verifies numbers, returns approve / revise / reject. | yes |
| reporter | Writes the approval report (Markdown + JSON). | no |

Plus two services: `recorder` (tails the log stream into Postgres) and
`dashboard` (start runs, read reports, approve or reject, replay or live-tail).

## Quick start

```bash
cp .env.example .env            # set ANTHROPIC_API_KEY; leave LLM_MODE=mock for a free dry run
docker compose up --build -d
docker compose ps               # everything should be healthy within ~30s
```

Open http://localhost:8080, click **Start run**. In mock mode the run finishes in
a few seconds. Open the run, read the report, approve or reject, then click
**Open timeline player** to replay every thought and message.

For a real run, set `LLM_MODE=live`, keep `MAX_RUN_USD` low at first (5 is a
reasonable ceiling), and restart: `docker compose up -d`.

Edit `config/profile.yaml` to describe your capital, time, skills, and
exclusions. It is read at the start of every run; no restart needed.

## How messaging and recording work

- `enclave:log` is a single append-only Redis Stream. Every event goes there.
- `enclave:inbox:<role>` streams deliver tasks and messages to a role. Two scouts
  share one inbox through a consumer group. Every inbox write is mirrored to the log.
- `enclave:control` carries dashboard commands (start, cancel) to the coordinator.
- Event envelope: `run_id, ts (UTC ISO ms), seq, sender, recipient, kind, payload, usage`.
  Redis stream ids are millisecond timestamps, so the log is ordered by construction.
- Agents call Claude through a manual loop (`enclave/llm.py`) so each thinking
  summary, text block, tool call, server web-search result, and usage record
  becomes its own event. Agents talk to each other only via the `send_message`
  tool, which writes to the bus, so there is no off-the-record channel.
- `MAX_RUN_USD` is enforced from the Redis cost counter before every model call.
  When it trips, the run halts and the reporter (budget-exempt) writes a partial
  report.

## Replay without the dashboard

```bash
docker compose exec dashboard python -m scripts.replay --list
docker compose exec dashboard python -m scripts.replay <run_id> --kinds thought,msg --speed 20
```

## Development

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # Windows
.venv/Scripts/python -m pytest -q
```

Tests run a full mock pipeline in-process on fakeredis; no Docker needed.

## Layout

```
agents/        coordinator + worker roles, one entrypoint (AGENT_ROLE)
enclave/       shared library: events, bus, llm, agent base, schemas, pricing
recorder/      log -> postgres
dashboard/     FastAPI UI and JSON/SSE API
config/        profile.yaml and per-role prompts (mounted read-only)
db/schema.sql  runs, events, artifacts, approvals
scripts/       CLI replay
tests/         unit + in-process pipeline tests
```

## Phase 2 (not built)

Executor agents with per-action approval gates, scheduled runs, notifications,
dashboard auth.
