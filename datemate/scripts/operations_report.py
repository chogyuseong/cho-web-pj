"""Local-only aggregate report. Never exports addresses, tokens or user text."""

import json
import sys
import time
import math
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
    values = [json.loads(r["payload"]) for r in rows]
    for provider in providers:
        for key in ("calls", "errors"):
            provider[key] = int(provider[key])
        if provider["average_ms"] is not None:
            provider["average_ms"] = float(provider["average_ms"])
    completed = [v for v in values if v.get("status", "complete") == "complete"]
    failed = sum(v.get("status") == "failed" for v in values)
    durations = sorted(v["elapsed_ms"] for v in completed if "elapsed_ms" in v)
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
        "scope": "Recorded attempts only; admission rejections, abrupt process exits, SDK retries, token charges and actual visits are not measured. p95 covers completed attempts. Provider totals use hourly buckets.",
    }


if __name__ == "__main__":
    print(json.dumps(report(), ensure_ascii=False, indent=2))
