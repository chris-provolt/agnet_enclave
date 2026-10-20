from __future__ import annotations

import os
from pathlib import Path

import fakeredis
import pytest

os.environ.setdefault("MOCK_DELAY_S", "0")

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def redis_client():
    server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server, decode_responses=True)


@pytest.fixture
def settings(tmp_path):
    from enclave.config import Settings

    return Settings(
        redis_url="redis://unused",
        llm_mode="mock",
        max_run_usd=5.0,
        scout_briefs=4,
        finalists=3,
        max_revision_rounds=2,
        stage_timeout_s=60,
        profile_path=str(ROOT / "config" / "profile.yaml"),
        prompts_dir=str(ROOT / "config" / "prompts"),
    )
