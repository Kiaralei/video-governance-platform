from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.server import create_server


def request(port: int, method: str, path: str, body: dict | None = None) -> dict:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    raw = json.dumps(body or {}).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, body=raw, headers=headers)
    response = conn.getresponse()
    payload = json.loads(response.read().decode("utf-8"))
    if response.status >= 400:
        raise RuntimeError(f"{method} {path} failed: {response.status} {payload}")
    return payload


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        server = create_server(port=0, db_path=Path(tmp) / "smoke.sqlite3")
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            health = request(port, "GET", "/api/v1/health")
            created = request(
                port,
                "POST",
                "/api/v1/content/upload",
                {
                    "title": "Smoke test clip",
                    "description": "A neutral educational clip for the runnable MVP.",
                    "creator_id": "creator_smoke",
                },
            )
            request(port, "POST", "/api/v1/pipeline/drain", {"limit": 10})
            for _ in range(20):
                queue = request(port, "GET", "/api/v1/review/human/queue")
                if queue["total"] == 1:
                    break
                time.sleep(0.1)
            queue = request(port, "GET", "/api/v1/review/human/queue")
            machine_reviews = request(port, "GET", "/api/v1/machine/reviews")
            pipeline_jobs = request(port, "GET", "/api/v1/pipeline/jobs")
            task_id = queue["items"][0]["task_id"]
            case = request(port, "GET", f"/api/v1/review/human/{task_id}")
            machine_detail = request(port, "GET", f"/api/v1/machine/reviews/{created['content_id']}")
            decision = request(
                port,
                "POST",
                f"/api/v1/review/human/{task_id}/decide",
                {"decision": "pass", "reason": "Smoke test accepted.", "reviewer_id": "reviewer_smoke"},
            )
            audit = request(port, "GET", f"/api/v1/audit?content_id={created['content_id']}")
            summary = request(port, "GET", "/api/v1/dashboard/summary")

            assert health["status"] == "ok"
            assert queue["total"] == 1
            assert machine_reviews["total"] == 1
            assert pipeline_jobs["items"][0]["status"] == "completed"
            assert case["evidence"]["content_id"] == created["content_id"]
            assert "media_asset" in machine_detail["evidence"]
            assert "video_meta" in machine_detail["evidence"]
            assert machine_detail["evidence"]["machine_review_source"] in {"local_rules", "llm"}
            assert machine_detail["verdicts"][0]["dimension_id"] == "mvp_general_policy"
            assert decision["decision"] == "pass"
            assert len(audit["items"]) >= 5
            assert summary["decisions"]["pass"] == 1
            print("SMOKE PASS: ingest -> pipeline queue -> evidence -> machine review -> human decision -> audit")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
