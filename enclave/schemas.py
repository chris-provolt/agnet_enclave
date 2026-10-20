"""Pydantic models the agents must return (structured outputs).

Every field is required and every object forbids extra keys, which is what the
API's json_schema output format expects. Keep descriptions short; they are
sent to the model on every call.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- coordinator -> scouts ------------------------------------------
class ScoutBrief(Strict):
    name: str = Field(description="Short slug-like name for this slice")
    slice: str = Field(description="What part of the opportunity space this brief covers")
    search_angles: list[str] = Field(description="3-6 concrete queries or questions to pursue")
    hard_filters: list[str] = Field(description="Constraints from the profile that apply to this slice")


class ScoutBriefs(Strict):
    rationale: str
    briefs: list[ScoutBrief]


# ---------- scouts -> analyst ------------------------------------------------
class Opportunity(Strict):
    id: str = Field(description="kebab-case unique id")
    title: str
    category: str
    summary: str = Field(description="2-4 sentences: what it is and how it earns")
    startup_cost_usd_low: float
    startup_cost_usd_high: float
    time_to_first_dollar_days: int
    setup_hours_per_week: float = Field(description="HUMAN operator hours per week during setup")
    ongoing_hours_per_week: float = Field(description="HUMAN operator hours per week after launch")
    recurring_cost_usd_per_month: float = Field(description="API, hosting, and tool spend the operator carries monthly")
    autonomy_notes: str = Field(description="What the workforce runs by itself vs what needs the operator")
    monthly_income_usd_low: float
    monthly_income_usd_high: float
    risk: Literal["low", "medium", "high"]
    legality_notes: str
    sources: list[str] = Field(description="URLs that substantiate the numbers")
    fit_rationale: str = Field(description="Why this fits (or strains) the workforce capabilities and operator limits")
    is_estimate: bool = Field(description="True if numbers are inferred rather than sourced")


class ScoutResult(Strict):
    brief_name: str
    opportunities: list[Opportunity]
    dead_ends: list[str] = Field(description="Angles pursued that produced nothing usable, and why")


# ---------- analyst -> coordinator -------------------------------------------
class Scores(Strict):
    cost_fit: float
    speed: float
    effort_fit: float
    ceiling: float
    risk: float = Field(description="10 = lowest risk")
    skill_fit: float = Field(description="How fully the workforce can execute autonomously")


class ScoredOpportunity(Strict):
    opportunity_id: str
    title: str
    scores: Scores
    total: float = Field(description="Weighted 0-10")
    rationale: str
    is_finalist: bool
    drop_reason: str = Field(description="Empty string if finalist")


class AnalystResult(Strict):
    merges: list[str] = Field(description="Which candidates were merged and why")
    scored: list[ScoredOpportunity]
    finalist_ids: list[str]
    weighting_note: str


# ---------- planner --------------------------------------------------------------
class PlanStep(Strict):
    order: int
    title: str
    detail: str
    performed_by: Literal["workforce", "operator"]
    est_hours: float
    est_cost_usd: float
    depends_on: list[int] = Field(description="Order numbers this step waits on")


class KPI(Strict):
    name: str
    target: str
    check_week: int


class Plan(Strict):
    opportunity_id: str
    title: str
    objective: str = Field(description="Measurable target with a date")
    steps: list[PlanStep]
    total_cost_usd: float
    timeline_weeks: int
    tooling: list[str]
    kpis: list[KPI]
    kill_criteria: list[str]
    assumptions: list[str]
    open_questions: list[str]
    revision_notes: str = Field(description="How critic issues were addressed; empty on round 0")


# ---------- critic --------------------------------------------------------------
class Issue(Strict):
    severity: Literal["high", "medium", "low"]
    title: str
    detail: str
    suggested_fix: str


class Critique(Strict):
    opportunity_id: str
    verdict: Literal["approve", "revise", "reject"]
    confidence: float = Field(description="0-1 that the plan as written reaches its objective")
    issues: list[Issue]
    strengths: list[str]
    summary: str


# ---------- reporter --------------------------------------------------------------
class Recommendation(Strict):
    opportunity_id: str
    title: str
    decision_requested: str
    startup_cost_usd: str
    time_to_first_dollar: str
    hours_per_week: str
    monthly_income_range: str
    plan_summary: str
    critic_confidence: float
    top_risks: list[str]
    week_one_actions: list[str]


class Dropped(Strict):
    title: str
    reason: str


class Report(Strict):
    title: str
    executive_summary: str
    recommendations: list[Recommendation]
    dropped: list[Dropped]
    methodology: str
    markdown: str = Field(description="The full report as Markdown")


SCHEMAS: dict[str, type[Strict]] = {
    "ScoutBriefs": ScoutBriefs,
    "ScoutResult": ScoutResult,
    "AnalystResult": AnalystResult,
    "Plan": Plan,
    "Critique": Critique,
    "Report": Report,
}


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    """API-ready JSON schema. Uses the SDK's transformer when available."""
    try:
        from anthropic.lib._parse._transform import transform_schema  # type: ignore
        return transform_schema(model)
    except Exception:  # pragma: no cover - fallback if SDK internals move
        schema = model.model_json_schema()
        _force_strict(schema)
        return schema


def _force_strict(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object":
            node.setdefault("additionalProperties", False)
            props = node.get("properties") or {}
            node["required"] = list(props.keys())
        for v in node.values():
            _force_strict(v)
    elif isinstance(node, list):
        for v in node:
            _force_strict(v)
