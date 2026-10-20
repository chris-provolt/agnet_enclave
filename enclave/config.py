"""Environment and file configuration shared by all services."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROLES = ("coordinator", "scout", "analyst", "planner", "critic", "reporter")


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    postgres_dsn: str = os.environ.get("POSTGRES_DSN", "postgresql://enclave:change-me-postgres@localhost:5432/enclave")
    llm_mode: str = os.environ.get("LLM_MODE", "mock")
    llm_model: str = os.environ.get("LLM_MODEL", "claude-opus-5-5")
    llm_effort: str = os.environ.get("LLM_EFFORT", "high")
    llm_max_tokens: int = env_int("LLM_MAX_TOKENS", 16000)
    max_run_usd: float = env_float("MAX_RUN_USD", 5.0)
    scout_briefs: int = env_int("SCOUT_BRIEFS", 4)
    finalists: int = env_int("FINALISTS", 5)
    max_revision_rounds: int = env_int("MAX_REVISION_ROUNDS", 2)
    stage_timeout_s: int = env_int("STAGE_TIMEOUT_S", 1800)
    health_port: int = env_int("HEALTH_PORT", 8000)
    profile_path: str = os.environ.get("PROFILE_PATH", str(Path(__file__).resolve().parent.parent / "config" / "profile.yaml"))
    prompts_dir: str = os.environ.get("PROMPTS_DIR", str(Path(__file__).resolve().parent.parent / "config" / "prompts"))


def load_settings() -> Settings:
    return Settings()


def load_profile(path: str | None = None) -> dict:
    p = Path(path or load_settings().profile_path)
    with p.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_prompt(role: str, prompts_dir: str | None = None) -> str:
    d = Path(prompts_dir or load_settings().prompts_dir)
    shared = (d / "_shared.md").read_text(encoding="utf-8")
    own = (d / f"{role}.md").read_text(encoding="utf-8")
    return shared.strip() + "\n\n" + own.strip()
