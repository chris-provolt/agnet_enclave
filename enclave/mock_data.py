"""Canned outputs for LLM_MODE=mock. Keep consistent ids across roles.

Framing: the AI workforce executes, the operator approves and funds. Hours are
HUMAN hours. Video is an angle because agents can generate it.
"""
from __future__ import annotations

OPPS = [
    {
        "id": "ai-shorts-channel", "title": "Faceless AI short-form video channel (Shorts, TikTok, Reels)", "category": "AI-generated short-form video channels",
        "summary": "Agents pick a niche, write scripts, generate visuals and synthetic voiceover, assemble 30-60s videos with ffmpeg, and auto-publish daily across three platforms. Earns via platform ad revenue and affiliate links once eligibility thresholds are met.",
        "startup_cost_usd_low": 100, "startup_cost_usd_high": 400, "time_to_first_dollar_days": 75, "setup_hours_per_week": 1.5, "ongoing_hours_per_week": 0.5,
        "recurring_cost_usd_per_month": 120, "autonomy_notes": "Workforce runs scripting, generation, editing, publishing, analytics. Operator opens the channel accounts, passes identity checks, and approves the niche.",
        "monthly_income_usd_low": 100, "monthly_income_usd_high": 1500, "risk": "medium", "legality_notes": "Disclose AI generation where platforms require it; avoid copyrighted music and real-person likenesses.",
        "sources": ["https://example.com/shorts-monetization-2026", "https://example.com/ai-video-pipeline-costs"], "fit_rationale": "Every production step is API-driven; human time is account setup and weekly approval only.", "is_estimate": True,
    },
    {
        "id": "financial-data-api", "title": "Cleaned market-data API on RapidAPI", "category": "Software and SaaS micro-products, APIs, and data products",
        "summary": "Package the existing price-history and sentiment pipelines as a metered API. Earns per-call and via tiered subscriptions.",
        "startup_cost_usd_low": 100, "startup_cost_usd_high": 600, "time_to_first_dollar_days": 60, "setup_hours_per_week": 1, "ongoing_hours_per_week": 0.5,
        "recurring_cost_usd_per_month": 40, "autonomy_notes": "Workforce builds, deploys, documents, and supports the API. Operator creates the marketplace seller account and payout details.",
        "monthly_income_usd_low": 100, "monthly_income_usd_high": 1500, "risk": "medium", "legality_notes": "Check upstream data licences for redistribution rights.",
        "sources": ["https://example.com/rapidapi-finance-category"], "fit_rationale": "Reuses existing assets directly.", "is_estimate": True,
    },
    {
        "id": "ai-niche-newsletter", "title": "AI-written niche newsletter with paid tier", "category": "AI-written niche newsletters and content sites",
        "summary": "Agents monitor sources, write a twice-weekly briefing, publish via Substack or Beehiiv API, and grow via SEO posts and cross-promotion. Earns via sponsorships and a paid tier.",
        "startup_cost_usd_low": 0, "startup_cost_usd_high": 150, "time_to_first_dollar_days": 90, "setup_hours_per_week": 1, "ongoing_hours_per_week": 0.5,
        "recurring_cost_usd_per_month": 60, "autonomy_notes": "Fully autonomous after the operator opens the publication and payment account.",
        "sources": ["https://example.com/newsletter-benchmarks"], "monthly_income_usd_low": 50, "monthly_income_usd_high": 800, "risk": "low", "legality_notes": "Disclose AI authorship; CAN-SPAM compliance via the platform.",
        "fit_rationale": "Writing and research are core workforce strengths; slow ramp is the main cost.", "is_estimate": True,
    },
    {
        "id": "pod-ai-designs", "title": "Print-on-demand store with AI-generated designs", "category": "Print-on-demand with AI-generated designs",
        "summary": "Agents generate designs, mock them onto products, write listings, and publish to a POD marketplace that handles fulfilment. Earns per sale.",
        "startup_cost_usd_low": 0, "startup_cost_usd_high": 100, "time_to_first_dollar_days": 45, "setup_hours_per_week": 1, "ongoing_hours_per_week": 0.25,
        "recurring_cost_usd_per_month": 30, "autonomy_notes": "Marketplace handles printing and shipping, so the workforce only manages designs and listings. Operator opens the seller account.",
        "monthly_income_usd_low": 30, "monthly_income_usd_high": 400, "risk": "low", "legality_notes": "Trademark screening on every design; no real-person likenesses.",
        "sources": ["https://example.com/pod-ai-income-report"], "fit_rationale": "Low cost, fast first dollar, very low human time.", "is_estimate": True,
    },
    {
        "id": "local-service-leadgen", "title": "Local service lead-generation sites sold to contractors", "category": "Automated marketplace or affiliate sites",
        "summary": "Rank small sites for local service keywords and sell the leads to contractors.",
        "startup_cost_usd_low": 200, "startup_cost_usd_high": 800, "time_to_first_dollar_days": 150, "setup_hours_per_week": 3, "ongoing_hours_per_week": 3,
        "recurring_cost_usd_per_month": 80, "autonomy_notes": "Site building is autonomous but selling leads requires phone calls to contractors, which the workforce cannot do.",
        "monthly_income_usd_low": 0, "monthly_income_usd_high": 1200, "risk": "medium", "legality_notes": "Lead-sale disclosures vary by state.",
        "sources": ["https://example.com/leadgen-case-study"], "fit_rationale": "Needs human phone sales; exceeds oversight hours.", "is_estimate": True,
    },
]

BRIEFS = {
    "rationale": "Spread briefs across generated video, generated content, digital products, and software so scouts do not overlap, and lean into what the workforce can run without a human.",
    "briefs": [
        {"name": "ai-video", "slice": "Faceless short-form and long-form video channels produced entirely by generation APIs", "search_angles": ["faceless YouTube Shorts automation income 2026", "TikTok AI generated channel monetization requirements", "AI voiceover video pipeline costs per video"], "hard_filters": ["no real person on camera", "must disclose AI where required", "recurring API spend under $300/month"]},
        {"name": "ai-content", "slice": "AI-written newsletters, niche sites, and ebooks", "search_angles": ["AI newsletter paid tier benchmarks", "programmatic SEO niche site revenue 2026", "Amazon KDP AI-assisted nonfiction earnings"], "hard_filters": ["first dollar inside 120 days", "disclose AI authorship"]},
        {"name": "digital-products", "slice": "Templates, prompt packs, print-on-demand designs sold on marketplaces", "search_angles": ["Etsy digital download AI designs revenue", "Gumroad prompt pack sales", "print on demand AI art store case study"], "hard_filters": ["trademark-safe designs", "marketplace handles fulfilment"]},
        {"name": "software-data", "slice": "APIs, micro-SaaS, and data products built and operated by agents", "search_angles": ["RapidAPI top earning finance APIs", "micro-SaaS ideas developer tools 2026", "sell market data API licensing rules"], "hard_filters": ["must be legal to redistribute data", "support handled by email or chat only"]},
    ],
}


def _scout_output(brief_name: str) -> dict:
    by_brief = {
        "ai-video": [OPPS[0]],
        "ai-content": [OPPS[2]],
        "digital-products": [OPPS[3]],
        "software-data": [OPPS[1], OPPS[4]],
    }
    opps = by_brief.get(brief_name) or [OPPS[0], OPPS[3]]
    return {"brief_name": brief_name, "opportunities": opps, "dead_ends": ["Live-streaming channels: need a real person on camera.", "Crypto airdrop farming: excluded by profile keywords.", "Engagement-pod growth services: violate platform terms."]}


ANALYST = {
    "merges": ["Merged 'faceless Shorts automation' and 'AI TikTok channel' into ai-shorts-channel."],
    "scored": [
        {"opportunity_id": "ai-shorts-channel", "title": OPPS[0]["title"], "scores": {"cost_fit": 8, "speed": 6, "effort_fit": 9, "ceiling": 8, "risk": 6, "skill_fit": 10}, "total": 8.1, "rationale": "Fully automatable pipeline with the highest ceiling; platform-policy risk is the main drag.", "is_finalist": True, "drop_reason": ""},
        {"opportunity_id": "pod-ai-designs", "title": OPPS[3]["title"], "scores": {"cost_fit": 10, "speed": 8, "effort_fit": 10, "ceiling": 4, "risk": 8, "skill_fit": 10}, "total": 8.0, "rationale": "Cheapest and fastest; modest ceiling.", "is_finalist": True, "drop_reason": ""},
        {"opportunity_id": "financial-data-api", "title": OPPS[1]["title"], "scores": {"cost_fit": 8, "speed": 6, "effort_fit": 8, "ceiling": 8, "risk": 5, "skill_fit": 10}, "total": 7.4, "rationale": "Reuses existing assets; data licensing is a real risk.", "is_finalist": True, "drop_reason": ""},
        {"opportunity_id": "ai-niche-newsletter", "title": OPPS[2]["title"], "scores": {"cost_fit": 9, "speed": 4, "effort_fit": 9, "ceiling": 6, "risk": 8, "skill_fit": 10}, "total": 7.0, "rationale": "Autonomous but slow to monetise.", "is_finalist": False, "drop_reason": "Ramp near the 120-day limit; keep as a later add-on to the video channel."},
        {"opportunity_id": "local-service-leadgen", "title": OPPS[4]["title"], "scores": {"cost_fit": 7, "speed": 2, "effort_fit": 2, "ceiling": 7, "risk": 6, "skill_fit": 4}, "total": 4.3, "rationale": "Selling leads needs human phone calls.", "is_finalist": False, "drop_reason": "Exceeds operator oversight hours; workforce cannot make calls."},
    ],
    "finalist_ids": ["ai-shorts-channel", "pod-ai-designs", "financial-data-api"],
    "weighting_note": "Weights: skill_fit (autonomy) 25%, effort_fit 20%, speed 15%, cost_fit 15%, risk 15%, ceiling 10%.",
}


def _plan(opp_id: str, round_no: int) -> dict:
    opp = next((o for o in OPPS if o["id"] == opp_id), OPPS[0])
    return {
        "opportunity_id": opp_id, "title": f"Plan: {opp['title']}",
        "objective": f"Reach ${int(opp['monthly_income_usd_low']) + 100}/month within {max(6, opp['time_to_first_dollar_days'] // 7)} weeks of launch with under {opp['ongoing_hours_per_week']} operator hours/week.",
        "steps": [
            {"order": 1, "title": "Operator opens accounts", "detail": "Create platform and payout accounts, pass identity checks, hand API credentials to the workforce.", "est_hours": 1.5, "est_cost_usd": 0, "depends_on": [], "performed_by": "operator"},
            {"order": 2, "title": "Niche validation", "detail": "Workforce researches 20 niches, scores demand and competition, proposes the top 3 for operator approval.", "est_hours": 0.5, "est_cost_usd": 15, "depends_on": [], "performed_by": "workforce"},
            {"order": 3, "title": "Build the production pipeline", "detail": "Scripts, generation, assembly, captioning, scheduling, and analytics as scheduled Docker jobs.", "est_hours": 0, "est_cost_usd": 80, "depends_on": [1, 2], "performed_by": "workforce"},
            {"order": 4, "title": "Launch and iterate", "detail": "Publish daily, A/B test hooks and thumbnails, kill underperforming formats weekly, send the operator a weekly digest.", "est_hours": 0.25, "est_cost_usd": 100, "depends_on": [3], "performed_by": "workforce"},
        ],
        "total_cost_usd": float(opp["startup_cost_usd_low"]) + 195, "timeline_weeks": 10,
        "tooling": ["Python", "Docker", "ffmpeg", "image and voice generation APIs", "platform publishing APIs", "Stripe"],
        "kpis": [{"name": "Videos or listings published per week", "target": "21", "check_week": 2}, {"name": "Monetisation eligibility reached", "target": "yes", "check_week": 8}, {"name": "Operator hours/week", "target": "<= 0.5", "check_week": 4}],
        "kill_criteria": ["Under 10k total views after 6 weeks of daily posting", "Any platform strike for policy violation", "Recurring API spend above $300/month without revenue"],
        "assumptions": ["Platforms continue to monetise AI-generated content with disclosure", "Generation API pricing stays within 20% of today"],
        "open_questions": ["Which niche does the operator want to avoid for brand reasons?", "Is a synthetic voice acceptable or should captions-only be used?"],
        "revision_notes": "" if round_no == 0 else "Round %d: added a licence and platform-policy confirmation gate before build spend, per critic." % round_no,
    }


def _critique(opp_id: str, round_no: int) -> dict:
    verdict = "revise" if round_no == 0 and opp_id == "financial-data-api" else "approve"
    return {
        "opportunity_id": opp_id, "verdict": verdict, "confidence": 0.55 if verdict == "revise" else 0.7,
        "issues": [
            {"severity": "high" if verdict == "revise" else "medium", "title": "Third-party terms not confirmed", "detail": "Data redistribution or AI-content monetisation terms could change or forbid the model.", "suggested_fix": "Add a gate step that confirms terms before any build spend."},
            {"severity": "low", "title": "API spend underestimated", "detail": "Generation costs scale with daily volume; budget assumes current pricing.", "suggested_fix": "Cap daily output and alert at 80% of the monthly burn tolerance."},
        ],
        "strengths": ["Almost zero human hours after setup", "Clear kill criteria"],
        "summary": "Solid plan; main exposure is platform or licence terms." if verdict == "approve" else "Do not proceed until licensing is confirmed.",
    }


def _report(ctx: dict) -> dict:
    cost = ctx.get("cost_usd", 0.0)
    recs = [
        {"opportunity_id": "ai-shorts-channel", "title": OPPS[0]["title"], "decision_requested": "Approve a 10-week build; operator opens channel accounts in week one", "startup_cost_usd": "$100-$400 plus ~$120/month APIs", "time_to_first_dollar": "about 11 weeks", "hours_per_week": "1.5 operator hours during setup, 0.5 after", "monthly_income_range": "$100-$1500", "plan_summary": "Agents script, generate, assemble, and publish daily videos across three platforms; weekly digest to the operator.", "critic_confidence": 0.7, "top_risks": ["Platform policy on AI content", "Generation API costs"], "week_one_actions": ["Operator opens YouTube, TikTok, and Instagram accounts", "Workforce proposes three niches for approval"]},
        {"opportunity_id": "pod-ai-designs", "title": OPPS[3]["title"], "decision_requested": "Approve a 4-week launch", "startup_cost_usd": "$0-$100 plus ~$30/month", "time_to_first_dollar": "about 6 weeks", "hours_per_week": "1 operator hour during setup, 0.25 after", "monthly_income_range": "$30-$400", "plan_summary": "Agents generate trademark-screened designs and listings; the marketplace prints and ships.", "critic_confidence": 0.7, "top_risks": ["Low ceiling", "Marketplace saturation"], "week_one_actions": ["Operator opens the seller account", "Workforce publishes the first 50 designs"]},
    ]
    md = "# Enclave approval report\n\n**Decision requested:** approve two of three finalists for execution; hold the data API until licensing is confirmed.\n\n" + "".join(
        f"## {r['title']}\n\n| Metric | Value |\n|---|---|\n| Startup cost | {r['startup_cost_usd']} |\n| Time to first dollar | {r['time_to_first_dollar']} |\n| Operator hours | {r['hours_per_week']} |\n| Monthly income | {r['monthly_income_range']} |\n| Critic confidence | {r['critic_confidence']} |\n\n{r['plan_summary']}\n\n" for r in recs
    ) + "## Dropped\n\n- AI niche newsletter: ramp too slow; revisit as an add-on.\n- Local lead-gen sites: needs human phone sales.\n\n## Methodology\n\n4 scouts, 5 candidates, 3 finalists, 2 critic rounds. Claude spend: $%.2f (mock run).\n" % cost
    return {
        "title": "Enclave approval report (mock run)", "executive_summary": "Two fully automatable products fit the workforce and the operator's limits and are ready for approval; the data API needs licence confirmation first.",
        "recommendations": recs,
        "dropped": [{"title": OPPS[2]["title"], "reason": "Ramp near the 120-day limit; revisit later"}, {"title": OPPS[4]["title"], "reason": "Needs human phone sales; exceeds oversight hours"}, {"title": OPPS[1]["title"], "reason": "Held: confirm data licensing before approval"}],
        "methodology": "Four scout briefs, five candidates, analyst scoring weighted for autonomy, planner/critic rounds, reporter synthesis.",
        "markdown": md,
    }


def script_for(role: str, ctx: dict) -> dict:
    """Return {'steps': [...], 'output': dict} for the mock."""
    brief = ctx.get("brief_name", "ai-video")
    opp = ctx.get("opportunity_id", "ai-shorts-channel")
    rnd = int(ctx.get("round", 0))
    if role == "coordinator":
        return {"steps": [
            {"kind": "thought", "text": "The workforce can generate video, voice, and text through APIs and publish via platform APIs, so faceless video and generated content are first-class angles. Four disjoint briefs: AI video, AI content, digital products, software and data."},
            {"kind": "tool", "tool": "log_finding", "input": {"text": "Keeping briefs disjoint so scouts do not duplicate research; operator hours, not agent hours, are the scarce resource."}},
        ], "output": BRIEFS}
    if role == "scout":
        return {"steps": [
            {"kind": "thought", "text": f"Brief '{brief}'. Start broad, then verify monetisation rules and API costs on two sources before keeping a candidate."},
            {"kind": "web_search", "query": f"{brief} passive income AI automation 2026", "results": [{"title": "Shorts monetization requirements 2026", "url": "https://example.com/shorts-monetization-2026", "page_age": "2 months ago"}, {"title": "AI video pipeline cost breakdown", "url": "https://example.com/ai-video-pipeline-costs", "page_age": "3 months ago"}]},
            {"kind": "thought", "text": "Candidates substantiated. Dropping anything that needs a real person on camera or on the phone."},
            {"kind": "tool", "tool": "log_finding", "input": {"text": "Dead end: live-streaming channels need a human host."}},
            {"kind": "tool", "tool": "send_message", "input": {"to": "analyst", "text": f"Scout on brief {brief}: hours reported are operator hours; income numbers are estimates from secondary sources."}},
        ], "output": _scout_output(brief)}
    if role == "analyst":
        return {"steps": [
            {"kind": "thought", "text": "Five candidates after merging duplicates. Weight autonomy and operator hours highest per the profile's scoring hint."},
            {"kind": "web_search", "query": "RapidAPI finance API average revenue individual publisher", "results": [{"title": "RapidAPI publisher earnings", "url": "https://example.com/rapidapi-finance-category", "page_age": "4 months ago"}]},
            {"kind": "tool", "tool": "log_finding", "input": {"text": "Lead-gen fails the autonomy test (phone sales); newsletter fails the speed test."}},
        ], "output": ANALYST}
    if role == "planner":
        return {"steps": [
            {"kind": "thought", "text": f"Planning {opp}, round {rnd}. Operator steps limited to account setup and approvals; everything else is workforce."},
            {"kind": "tool", "tool": "log_finding", "input": {"text": "Recurring API spend kept under the $300/month burn tolerance."}},
        ] + ([{"kind": "tool", "tool": "send_message", "input": {"to": "critic", "text": f"Revised plan for {opp}: added a terms-confirmation gate before any build spend."}}] if rnd > 0 else []), "output": _plan(opp, rnd)}
    if role == "critic":
        return {"steps": [
            {"kind": "thought", "text": f"Reviewing {opp}. Check for hidden human steps and platform-terms exposure."},
            {"kind": "web_search", "query": f"{opp} platform terms AI generated content monetization", "results": [{"title": "Platform policy on synthetic media", "url": "https://example.com/platform-ai-policy", "page_age": "1 month ago"}]},
            {"kind": "tool", "tool": "log_finding", "input": {"text": "Third-party terms are the only high-severity item."}},
        ], "output": _critique(opp, rnd)}
    if role == "reporter":
        return {"steps": [
            {"kind": "thought", "text": "Lead with the decision. Two approvals, one hold, two drops. Hours shown are operator hours."},
            {"kind": "tool", "tool": "log_finding", "input": {"text": "Report kept under 2500 words."}},
        ], "output": _report(ctx)}
    return {"steps": [], "output": {}}
