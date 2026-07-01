from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import model_gateway as model_gateway_module
from backend.app import database as database_module
from backend.app import modality_models as modality_models_module
from backend.app.models import Base
from backend.app.llm_review import review_with_configured_llm
from backend.app.modality_models import ModalityModelRunner
from backend.app.services import GovernanceService


class MvpFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.llm_env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.llm_env.start()

    def tearDown(self) -> None:
        self.llm_env.stop()

    def test_ingest_review_decide_and_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "test.sqlite3")
            queued = service.ingest_content(
                {
                    "title": "Cooking lesson",
                    "description": "A simple recipe tutorial with family friendly narration.",
                    "creator_id": "creator_1",
                }
            )
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(service.list_queue()["total"], 0)
            self.assertEqual(service.list_pipeline_jobs()["total"], 1)

            self.assertEqual(service.drain_pipeline(), 1)

            queue = service.list_queue()
            self.assertEqual(queue["total"], 1)
            task_id = queue["items"][0]["task_id"]
            self.assertEqual(queue["items"][0]["task_id"], task_id)

            machine_reviews = service.list_machine_reviews()
            self.assertEqual(machine_reviews["total"], 1)
            self.assertEqual(machine_reviews["items"][0]["content_id"], queued["content_id"])
            machine_detail = service.get_machine_review(queued["content_id"])
            self.assertEqual(machine_detail["evidence"]["content_id"], queued["content_id"])
            self.assertEqual(machine_detail["verdicts"][0]["dimension_id"], "mvp_general_policy")

            claimed = service.claim_task(task_id, "reviewer_1")
            self.assertEqual(claimed["task"]["assigned_to"], "reviewer_1")

            result = service.decide_task(
                task_id,
                {"decision": "pass", "reason": "Evidence is low risk.", "reviewer_id": "reviewer_1"},
            )
            self.assertEqual(result["decision"], "pass")

            decided_queue = service.list_queue(status="decided")
            self.assertEqual(decided_queue["total"], 1)

            audit = service.get_audit(content_id=queued["content_id"])
            self.assertEqual([item["action"] for item in audit["items"]], [
                "content_queued",
                "pipeline_started",
                "evidence_extracted",
                "machine_review_completed",
                "human_review_task_created",
                "task_claimed",
                "human_decision_submitted",
            ])

    def test_local_video_reference_generates_file_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "sample.mp4"
            video.write_bytes(b"not-a-real-video-but-a-real-local-file")
            service = GovernanceService(root / "test.sqlite3")

            queued = service.ingest_content(
                {
                    "title": "Local cooking clip",
                    "description": "A normal recipe video stored on disk.",
                    "creator_id": "creator_local",
                    "video_url": str(video),
                }
            )
            self.assertEqual(service.drain_pipeline(), 1)

            machine_detail = service.get_machine_review(queued["content_id"])
            evidence = machine_detail["evidence"]
            meta = evidence["video_meta"]
            self.assertEqual(meta["source_type"], "local_file")
            self.assertEqual(meta["asset_status"], "stored")
            self.assertTrue(meta["storage_uri"].startswith("local://media-assets/"))
            self.assertEqual(meta["file_size_bytes"], video.stat().st_size)
            self.assertEqual(len(meta["sha256"]), 64)
            self.assertEqual(evidence["media_asset"]["status"], "stored")
            self.assertEqual(evidence["modality_availability"]["video_source"]["mode"], "stored_asset")
            self.assertEqual(
                [item["status"] for item in evidence["modality_model_invocations"]],
                ["not_configured", "not_configured", "not_configured"],
            )
            self.assertIn("machine_review_source", evidence)

    def test_batch_ingest_accepts_valid_items_and_reports_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "test.sqlite3")
            result = service.ingest_batch(
                {
                    "items": [
                        {
                            "title": "Batch cooking clip",
                            "description": "A normal recipe tutorial.",
                            "creator_id": "creator_batch_1",
                        },
                        {"title": "", "description": "Missing title should fail."},
                        {
                            "title": "Batch travel clip",
                            "description": "A normal travel video.",
                            "creator_id": "creator_batch_2",
                        },
                    ]
                }
            )

            self.assertEqual(result["accepted"], 2)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(result["errors"][0]["index"], 1)
            self.assertEqual(service.list_pipeline_jobs()["total"], 2)
            self.assertEqual(service.drain_pipeline(), 2)
            self.assertEqual(service.list_queue()["total"], 2)

    def test_external_modality_model_outputs_are_normalized(self) -> None:
        class ModelHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                self.rfile.read(int(self.headers.get("Content-Length", "0")))
                payloads = {
                    "/asr": {
                        "model_version": "asr-test",
                        "segments": [{"start_ms": 100, "end_ms": 900, "text": "spoken words"}],
                    },
                    "/ocr": {
                        "model_version": "ocr-test",
                        "items": [{"frame_id": "frame_001", "text": "visible text", "bbox": [0, 0, 1, 1]}],
                    },
                    "/vision": {
                        "model_version": "vision-test",
                        "objects": [{"frame_id": "frame_001", "label": "cup", "confidence": 0.81}],
                        "scenes": [{"tag": "kitchen", "confidence": 0.72}],
                    },
                }
                raw = json.dumps(payloads[self.path]).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, format: str, *args) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            patched_settings = replace(
                modality_models_module.settings,
                asr_model_url=f"{base_url}/asr",
                ocr_model_url=f"{base_url}/ocr",
                vision_model_url=f"{base_url}/vision",
            )
            with patch.object(modality_models_module, "settings", patched_settings):
                result = ModalityModelRunner().extract(
                    media_asset={"asset_id": "asset_test", "storage_uri": "local://media-assets/test.mp4"},
                    video_meta={"duration_ms": 1000},
                    frames=[{"frame_id": "frame_001", "timestamp_ms": 0}],
                    title="Fallback title",
                    description="Fallback description",
                )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(result["asr_transcript"][0]["text"], "spoken words")
        self.assertEqual(result["ocr_results"][0]["text"], "visible text")
        self.assertEqual(result["object_detections"][0]["label"], "cup")
        self.assertEqual(result["scene_tags"][0]["tag"], "kitchen")
        self.assertEqual(
            [item["status"] for item in result["modality_model_invocations"]],
            ["completed", "completed", "completed"],
        )

    def test_local_model_gateway_outputs_are_normalized(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MODEL_GATEWAY_ASR_PROVIDER": "local",
                "MODEL_GATEWAY_OCR_PROVIDER": "local",
                "MODEL_GATEWAY_VISION_PROVIDER": "local",
            },
        ):
            server = model_gateway_module.create_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_address[1]}"
            patched_settings = replace(
                modality_models_module.settings,
                asr_model_url=f"{base_url}/asr",
                ocr_model_url=f"{base_url}/ocr",
                vision_model_url=f"{base_url}/vision",
            )
            with patch.object(modality_models_module, "settings", patched_settings):
                result = ModalityModelRunner().extract(
                    media_asset={"asset_id": "asset_gateway", "storage_uri": "local://media-assets/test.mp4"},
                    video_meta={"duration_ms": 3000},
                    frames=[{"frame_id": "frame_001", "timestamp_ms": 0, "caption": "Recipe keyframe"}],
                    title="Cooking lesson",
                    description="A recipe tutorial with calm narration.",
                )
        finally:
            server.shutdown()
            server.server_close()

        self.assertIn("recipe tutorial", result["asr_transcript"][0]["text"])
        self.assertEqual(result["ocr_results"][0]["text"], "Cooking lesson")
        self.assertEqual(result["scene_tags"][0]["source"], "external_vision")
        self.assertEqual(
            [item["provider"] for item in result["modality_model_invocations"]],
            ["local_heuristic", "local_heuristic", "local_heuristic"],
        )

    def test_remote_video_defaults_to_reference_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "test.sqlite3")

            queued = service.ingest_content(
                {
                    "title": "Remote clip",
                    "description": "A remote video reference that should not be downloaded by default.",
                    "creator_id": "creator_remote",
                    "video_url": "https://example.local/video.mp4",
                }
            )
            self.assertEqual(service.drain_pipeline(), 1)

            evidence = service.get_machine_review(queued["content_id"])["evidence"]
            self.assertEqual(evidence["media_asset"]["status"], "remote_reference")
            self.assertEqual(evidence["video_meta"]["asset_status"], "remote_reference")
            self.assertEqual(evidence["modality_availability"]["video_source"]["mode"], "remote_reference")

    def test_llm_review_returns_none_without_api_key(self) -> None:
        with patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""}):
            self.assertIsNone(review_with_configured_llm({"metadata": {"title": "Neutral"}}))

    def test_only_pass_or_block_are_valid_final_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "test.sqlite3")
            service.ingest_content({"title": "Clip", "description": "Neutral content"})
            service.drain_pipeline()
            task_id = service.list_queue()["items"][0]["task_id"]
            with self.assertRaises(ValueError):
                service.decide_task(task_id, {"decision": "need_more_context", "reason": "nope"})

    def test_postgres_url_is_normalized_for_psycopg(self) -> None:
        self.assertEqual(
            database_module.normalize_database_url("postgresql://u:p@h:5432/db"),
            "postgresql+psycopg://u:p@h:5432/db",
        )
        self.assertEqual(
            database_module.normalize_database_url("postgres://u:p@h/db"),
            "postgresql+psycopg://u:p@h/db",
        )

    def test_runtime_engine_requires_postgres_url(self) -> None:
        with patch.object(database_module, "settings", replace(database_module.settings, database_url="")):
            with self.assertRaisesRegex(RuntimeError, "PostgreSQL DATABASE_URL is required"):
                database_module.create_db_engine()

    def test_audit_table_uses_autoincrement_identity(self) -> None:
        audit = Base.metadata.tables["audit_logs"]
        self.assertTrue(audit.c.id.primary_key)
        self.assertTrue(audit.c.id.autoincrement)
        self.assertIn("media_assets", Base.metadata.tables)
        index_names = {index.name for index in Base.metadata.tables["pipeline_jobs"].indexes}
        self.assertIn("idx_pipeline_jobs_status_created", index_names)


if __name__ == "__main__":
    unittest.main()
