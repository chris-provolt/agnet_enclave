"""Entrypoint for every agent container. AGENT_ROLE picks the class."""
from __future__ import annotations

import os
import sys

from enclave.bus import Bus, connect
from enclave.config import load_settings
from enclave.health import HealthState, serve_health
from enclave.llm import build_llm
from enclave.logging import setup_logger

from .coordinator import Coordinator
from .workers import Analyst, Critic, Planner, Reporter, Scout

AGENTS = {
    "coordinator": Coordinator,
    "scout": Scout,
    "analyst": Analyst,
    "planner": Planner,
    "critic": Critic,
    "reporter": Reporter,
}


def main() -> None:
    role = os.environ.get("AGENT_ROLE", "").strip().lower()
    if role not in AGENTS:
        print(f"AGENT_ROLE must be one of {sorted(AGENTS)}, got '{role}'", file=sys.stderr)
        sys.exit(2)
    settings = load_settings()
    log = setup_logger(role)
    health = HealthState(role)
    serve_health(health, settings.health_port)
    bus = Bus(connect(settings.redis_url))
    llm = build_llm(settings.llm_mode, settings.llm_model, settings.llm_effort, settings.llm_max_tokens)
    log.info("starting", extra={"extra_fields": {"llm_mode": settings.llm_mode, "model": settings.llm_model}})
    agent = AGENTS[role](settings, bus, llm, health)
    agent.run_forever()


if __name__ == "__main__":
    main()
