"""Format the maintained architecture boundary; --check is used in CI.

Expand these lists when migrating another legacy module. Vendor files are excluded.
"""

import subprocess
import sys
from pathlib import Path

import jsbeautifier

ROOT = Path(__file__).resolve().parents[1]
PYTHON = [
    "app/main.py",
    "app/leisure.py",
    "app/plan_changes.py",
    "app/recommendation_service.py",
    "app/planning_outcomes.py",
    "app/operating_evidence.py",
    "app/operating_import.py",
    "app/route_providers.py",
    "app/request_usage.py",
    "app/feedback_preferences.py",
    "app/execution.py",
    "app/plan_jobs.py",
    "app/database.py",
    "app/store.py",
    "app/migrations",
    "scripts/operations_report.py",
    "scripts/operations_check.py",
    "scripts/rehearse_operations.py",
    "scripts/import_operating_data.py",
    "scripts/format_sources.py",
    "tests/test_architecture.py",
]
JAVASCRIPT = [
    "app.js",
    "place-dialog.js",
    "plan-actions.js",
    "leisure.js",
    "experience.js",
    "price-controls.js",
    "plan-detail.js",
    "reviews.js",
    "execution-summary.js",
    "planning-outcomes.js",
]


def main():
    check = "--check" in sys.argv
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", *(["--check"] if check else []), *PYTHON],
        cwd=ROOT,
        check=False,
    )
    failed = result.returncode != 0
    options = jsbeautifier.default_options()
    options.indent_size = 2
    for name in JAVASCRIPT:
        path = ROOT / "static" / name
        source = path.read_text(encoding="utf-8")
        formatted = jsbeautifier.beautify(source, options) + "\n"
        if source != formatted:
            if check:
                print(f"Needs formatting: static/{name}")
                failed = True
            else:
                path.write_text(formatted, encoding="utf-8")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
