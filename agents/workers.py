"""The five worker roles. Each handles one task type and returns a dict."""
from __future__ import annotations

from enclave.agent import BaseAgent
from enclave.events import Event
from enclave.schemas import AnalystResult, Critique, Plan, Report, ScoutResult


class Scout(BaseAgent):
    role = "scout"
    uses_web = True

    def handle_task(self, ev: Event) -> dict:
        brief = ev.payload["brief"]
        prompt = (
            "Find passive-income candidates for the brief below. Pursue every search angle, "
            "verify numbers against at least one source, and return a ScoutResult JSON with 5 to 15 opportunities.\n\n"
            + self.block("Your brief", brief)
        )
        res = self.think(ev.run_id, prompt, ScoutResult, context={"brief_name": brief.get("name")})
        self.artifact("opportunities", f"scout:{brief.get('name')}", res.parsed)
        return res.parsed.model_dump(mode="json")


class Analyst(BaseAgent):
    role = "analyst"
    uses_web = True

    def handle_task(self, ev: Event) -> dict:
        p = ev.payload
        prompt = (
            f"Deduplicate and score every candidate below, then choose exactly {p['finalists']} finalists "
            "(fewer only if fewer candidates survive). Return an AnalystResult JSON.\n\n"
            + self.block("Candidates from all scouts", p["candidates"])
            + self.block("Scout dead ends (for context)", p.get("dead_ends", []))
        )
        res = self.think(ev.run_id, prompt, AnalystResult)
        self.artifact("scores", "analyst", res.parsed)
        return res.parsed.model_dump(mode="json")


class Planner(BaseAgent):
    role = "planner"
    uses_web = False

    def handle_task(self, ev: Event) -> dict:
        p = ev.payload
        rnd = int(p.get("round", 0))
        prompt = f"Write an execution plan for the opportunity below (revision round {rnd}). Return a Plan JSON.\n\n"
        prompt += self.block("Opportunity", p["opportunity"])
        prompt += self.block("Analyst scoring", p.get("score", {}))
        if p.get("previous_plan"):
            prompt += self.block("Your previous plan", p["previous_plan"])
        if p.get("critique"):
            prompt += self.block("Critique to address", p["critique"])
        res = self.think(ev.run_id, prompt, Plan, context={"opportunity_id": p["opportunity"]["id"], "round": rnd})
        self.artifact("plan", f"plan:{p['opportunity']['id']}:r{rnd}", res.parsed)
        return res.parsed.model_dump(mode="json")


class Critic(BaseAgent):
    role = "critic"
    uses_web = True

    def handle_task(self, ev: Event) -> dict:
        p = ev.payload
        rnd = int(p.get("round", 0))
        prompt = f"Red-team the plan below (revision round {rnd}). Verify the numbers that matter. Return a Critique JSON.\n\n"
        prompt += self.block("Plan", p["plan"])
        prompt += self.block("Opportunity", p["opportunity"])
        if p.get("previous_critique"):
            prompt += self.block("Your previous critique", p["previous_critique"])
        res = self.think(ev.run_id, prompt, Critique, context={"opportunity_id": p["opportunity"]["id"], "round": rnd})
        self.artifact("critique", f"critique:{p['opportunity']['id']}:r{rnd}", res.parsed)
        return res.parsed.model_dump(mode="json")


class Reporter(BaseAgent):
    role = "reporter"
    uses_web = False

    def handle_task(self, ev: Event) -> dict:
        p = ev.payload
        partial = bool(p.get("partial"))
        prompt = "Write the approval report. Return a Report JSON with the full Markdown in `markdown`.\n\n"
        if partial:
            prompt += f"IMPORTANT: this run was halted early ({p.get('halt_reason', 'budget')}). Say so at the top and report only on finished work.\n\n"
        prompt += self.block("Run facts", {"run_id": ev.run_id, "claude_spend_usd": p.get("cost_usd"), "candidates": p.get("candidate_count"), "finalists": p.get("finalist_ids")})
        prompt += self.block("Analyst result", p.get("analysis", {}))
        prompt += self.block("Final plans", p.get("plans", {}))
        prompt += self.block("Final critiques", p.get("critiques", {}))
        prompt += self.block("Scout dead ends", p.get("dead_ends", []))
        res = self.think(ev.run_id, prompt, Report, context={"cost_usd": p.get("cost_usd", 0.0), "partial": partial})
        art = self.artifact("report", "approval-report", res.parsed)
        out = res.parsed.model_dump(mode="json")
        out["artifact_event_id"] = art.event_id
        return out
