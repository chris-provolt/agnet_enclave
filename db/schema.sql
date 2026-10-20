-- Applied once by the postgres container on first start.

CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'running',   -- running | finished | halted | failed
    started_at   TIMESTAMPTZ NOT NULL,
    finished_at  TIMESTAMPTZ,
    profile      JSONB,
    cost_usd     NUMERIC(12,6) NOT NULL DEFAULT 0,
    summary      TEXT
);

CREATE TABLE IF NOT EXISTS events (
    event_id   TEXT PRIMARY KEY,                     -- redis stream id, e.g. 1729300000000-0
    run_id     TEXT NOT NULL,
    ts         TIMESTAMPTZ NOT NULL,
    seq        INTEGER NOT NULL,
    sender     TEXT NOT NULL,
    recipient  TEXT,
    kind       TEXT NOT NULL,
    payload    JSONB NOT NULL DEFAULT '{}'::jsonb,
    usage      JSONB
);
CREATE INDEX IF NOT EXISTS events_run_ts_idx ON events (run_id, ts, event_id);
CREATE INDEX IF NOT EXISTS events_run_kind_idx ON events (run_id, kind);

CREATE TABLE IF NOT EXISTS artifacts (
    id            BIGSERIAL PRIMARY KEY,
    run_id        TEXT NOT NULL,
    event_id      TEXT NOT NULL UNIQUE,
    artifact_type TEXT NOT NULL,                     -- briefs | opportunities | scores | plan | critique | report
    name          TEXT NOT NULL,
    content       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS artifacts_run_idx ON artifacts (run_id, artifact_type);

CREATE TABLE IF NOT EXISTS approvals (
    id          BIGSERIAL PRIMARY KEY,
    run_id      TEXT NOT NULL,
    decision    TEXT NOT NULL,                       -- approve | reject | request_changes
    notes       TEXT,
    decided_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
