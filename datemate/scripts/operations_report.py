"""Local-only aggregate report. Never exports addresses, tokens or user text."""

import json
import sys
import time
import math
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import store


def report(since=None):
    since = time.time() - 30 * 86400 if since is None else since
    with store.connect() as db:
        providers = [
            dict(r)
            for r in db.execute(
                "SELECT provider,SUM(calls) calls,SUM(errors) errors,ROUND(SUM(elapsed_ms)*1.0/NULLIF(SUM(calls),0),1) average_ms FROM provider_metrics WHERE hour>=? GROUP BY provider",
                (int(since // 3600),),
            )
        ]
        rows = db.execute(
            "SELECT payload FROM experience_events WHERE kind='recommendation' AND created>=?",
            (since,),
        ).fetchall()
        actions = db.execute(
            "SELECT kind,payload,owner,plan_id,created FROM experience_events WHERE created>=?",
            (since,),
        ).fetchall()
    values = [json.loads(r["payload"]) for r in rows]
    for provider in providers:
        for key in ("calls", "errors"):
            provider[key] = int(provider[key])
        if provider["average_ms"] is not None:
            provider["average_ms"] = float(provider["average_ms"])
    completed = [v for v in values if v.get("status", "complete") == "complete"]
    failed = sum(v.get("status") == "failed" for v in values)
    durations = sorted(v["elapsed_ms"] for v in completed if "elapsed_ms" in v)
    action_counts = {
        kind: len({(r["owner"], r["plan_id"]) for r in actions if r["kind"] == kind})
        for kind in ("selection", "visit", "apply_meal", "apply_agreement")
    }
    visits = [json.loads(r["payload"]) for r in actions if r["kind"] == "visit"]
    usage = [json.loads(r["payload"]) for r in actions if r["kind"] == "model_usage"]
    tokens = {
        k: sum(v.get(k, 0) for v in usage)
        for k in ("input_tokens", "output_tokens", "total_tokens")
    }
    prices = [
        os.getenv("DATEMATE_INPUT_USD_PER_MILLION"),
        os.getenv("DATEMATE_OUTPUT_USD_PER_MILLION"),
    ]
    try:
        estimated_usd = (
            (tokens["input_tokens"] * float(prices[0]) + tokens["output_tokens"] * float(prices[1]))
            / 1000000
            if all(prices)
            else None
        )
    except (ValueError, TypeError):
        estimated_usd = None
    fields = sum(v.get("total_evidence_fields", 0) for v in completed)
    from app.planning_outcomes import study_summary

    usage = [v["external_usage"] for v in values if "external_usage" in v]
    known_http_costs = [
        u["estimated_http_usd"] for u in usage if u.get("estimated_http_usd") is not None
    ]

    return {
        "providers": providers,
        "recommendations": len(values),
        "since": since,
        "completed": len(completed),
        "failed": failed,
        "failure_rate": failed / len(values) if values else None,
        "empty_results": sum(v.get("plans") == 0 for v in completed),
        "best_effort_plans": sum(v.get("best_effort_plans", 0) for v in completed),
        "quality_sample_size": sum("best_effort_plans" in v for v in completed),
        "p95_ms": durations[math.ceil(len(durations) * 0.95) - 1] if durations else None,
        "billing_cost": "not_measured",
        "operating_evidence_coverage": sum(v.get("evidence_fields", 0) for v in completed) / fields
        if fields
        else None,
        "product_actions": action_counts,
        "planning_study": study_summary([dict(r) for r in actions]),
        "recommendation_resources": dict(
            samples=len(usage),
            total_observed_calls=sum(u["total_calls"] for u in usage),
            cache_hits=sum(u["cache_hits"] for u in usage),
            budget_exhausted=sum(u["budget_exhausted"] for u in usage),
            known_http_cost_samples=len(known_http_costs),
            estimated_http_usd=sum(known_http_costs)
            if len(known_http_costs) == len(usage) and usage
            else None,
            scope="Recorded recommendation attempts including failures. HTTP prices must be configured; excludes later photos/menus, SDK tokens/retries and hosting. Missing prices are unknown, not free.",
        ),
        "self_reported_visits": sum(v.get("visited") == "yes" for v in visits),
        "self_reported_reuse_yes": sum(v.get("reuse") == "yes" for v in visits),
        "model_usage": dict(
            tokens,
            samples=len(usage),
            estimated_usd=estimated_usd,
            scope="Provider-reported successful response tokens only; configured unit prices, not an invoice. Mixed models require separate reporting.",
        ),
        "product_scope": "Unique browser/plan actions in the window; not unique people, verified visits or a conversion cohort.",
        "scope": "Recorded attempts only; admission rejections, abrupt process exits, SDK retries, token charges and actual visits are not measured. p95 covers completed attempts. Provider totals use hourly buckets.",
    }


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2))
