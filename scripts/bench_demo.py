"""Build the Acquisition Bench demonstration and write its report to docs/examples.

Runs the same seed the API runs at startup, against a throwaway SQLite database,
then writes the stored benchmark report and the data behind it:

- docs/examples/acquisition-bench-report.md    the report, exactly as stored
- docs/examples/acquisition-bench-data.json    benchmark_data(), for charts

    python scripts/bench_demo.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "examples"

work = Path(tempfile.mkdtemp(prefix="aegis-bench-demo-"))
os.environ["AEGIS_DATABASE_URL"] = f"sqlite:///{work}/demo.db"
os.environ["AEGIS_EVIDENCE_PATH"] = str(work / "evidence")
os.environ["AEGIS_SEED_DEMO"] = "false"
os.environ["AEGIS_SEED_BENCHMARK_DEMO"] = "true"
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import select  # noqa: E402

from aegis.benchmark import benchmark_data  # noqa: E402
from aegis.db import SessionLocal, init_db  # noqa: E402
from aegis.demo_bench import PROJECT_SLUG  # noqa: E402
from aegis.models import Campaign, Project, Report  # noqa: E402
from aegis.seed import bootstrap  # noqa: E402


def main() -> int:
    init_db()
    db = SessionLocal()
    try:
        outcome = bootstrap(db)
        db.commit()
        print("benchmark demo:", outcome.get("benchmark_demo"))
        project = db.execute(select(Project).where(Project.slug == PROJECT_SLUG)).scalar_one()
        report = db.execute(select(Report).where(Report.project_id == project.id)).scalar_one()
        campaigns = list(
            db.execute(
                select(Campaign).where(Campaign.project_id == project.id).order_by(Campaign.created_at)
            ).scalars()
        )
        data = benchmark_data(db, campaigns)
    finally:
        db.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "acquisition-bench-report.md").write_text(report.body)
    (OUT / "acquisition-bench-data.json").write_text(
        json.dumps(data, indent=1, sort_keys=True, default=sorted) + "\n"
    )
    print(f"Report SHA-256 {report.sha256}")
    print(f"Wrote {OUT / 'acquisition-bench-report.md'} and acquisition-bench-data.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
