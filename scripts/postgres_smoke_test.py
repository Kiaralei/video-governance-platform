from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from backend.app.services import GovernanceService


def cleanup(service: GovernanceService, content_id: str) -> None:
    with service.engine.begin() as conn:
        for table in (
            "audit_logs",
            "human_review_tasks",
            "machine_reviews",
            "evidence_packages",
            "media_assets",
            "pipeline_jobs",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE content_id = :cid"), {"cid": content_id})
        conn.execute(text("DELETE FROM content_items WHERE id = :cid"), {"cid": content_id})


def main() -> None:
    if not os.environ.get("DATABASE_URL", "").startswith(("postgresql://", "postgres://")):
        raise SystemExit("DATABASE_URL must point to PostgreSQL")

    service = GovernanceService()
    queued = service.ingest_content(
        {
            "title": "PostgreSQL smoke test",
            "description": "Temporary test content for PostgreSQL integration.",
            "creator_id": "postgres_smoke",
        }
    )
    content_id = queued["content_id"]
    try:
        processed = service.drain_pipeline()
        queue = service.list_queue()
        if processed < 1 or queue["total"] < 1:
            raise RuntimeError("pipeline did not create a human review task")
        task_id = queue["items"][0]["task_id"]
        decision = service.decide_task(
            task_id,
            {"decision": "pass", "reason": "PostgreSQL smoke accepted.", "reviewer_id": "postgres_smoke"},
        )
        summary = service.summary()
        assert decision["decision"] == "pass"
        assert summary["total_content"] >= 1
        print("POSTGRES SMOKE PASS")
    finally:
        cleanup(service, content_id)


if __name__ == "__main__":
    main()
