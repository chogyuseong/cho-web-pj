"""Read-only operator report. Never prints credentials, addresses or user text."""

import argparse, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import store
from app.config import ROOT, RUNTIME, validate_runtime
from app.operating_evidence import evidence_rows
from app.route_providers import configured


def report():
    checks = {}
    warnings = []
    try:
        validate_runtime()
        checks["configuration"] = True
    except (RuntimeError, ValueError, OSError):
        checks["configuration"] = False
    try:
        with store.connect() as db:
            db.execute("SELECT version FROM schema_migrations LIMIT 1").fetchone()
            checks["database"] = db.execute("SELECT 1 FROM plans LIMIT 1") is not None
    except Exception:
        checks["database"] = False
    try:
        evidence = evidence_rows()
        checks["operating_evidence_file"] = isinstance(evidence, dict)
    except (ValueError, OSError, TypeError):
        checks["operating_evidence_file"] = False
    checks["runtime_free_100mb"] = shutil.disk_usage(RUNTIME).free >= 100 * 1024 * 1024
    for name in ("index.html", "maps.js", "readability.css", "planning-outcomes.js"):
        checks["asset_" + name] = (ROOT / "static" / name).is_file()
    try:
        registry = json.loads((ROOT / "data/provider_registry.json").read_text("utf-8"))
        checks["provider_registry"] = isinstance(registry, list)
    except (ValueError, OSError):
        registry = []
        checks["provider_registry"] = False
    if not configured("walk"):
        warnings.append("도보 API 키 없음: 실제 도보 경로 연결 미완료")
    if not configured("transit"):
        warnings.append("대중교통 API 키 없음: 실제 대중교통 경로 연결 미완료")
    warnings.append("자료·사진·API의 상업 이용 및 양도 범위는 제공처별 증빙 확인 필요")
    return dict(
        ok=all(checks.values()),
        checks=checks,
        warnings=warnings,
        provider_rights=[dict(id=p["id"], status=p["rights_status"]) for p in registry],
        scope="Configuration, local files and database query only; no external API, backup restoration or production load test.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    result = report()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if args.strict and not result["ok"] else 0)
