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

    def test_celery_chain_processes_pipeline_eagerly(self) -> None:
        from backend.app import tasks as tasks_module

        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "test.sqlite3")
            tasks_module.set_service(service)
            try:
                queued = service.ingest_content(
                    {
                        "title": "Celery cooking clip",
                        "description": "A normal recipe tutorial.",
                        "creator_id": "creator_celery",
                    }
                )
                # 无 broker：ingest 不派发，队列此刻应为空。
                self.assertEqual(service.list_queue()["total"], 0)

                # 通过 Celery chain（eager 同步）驱动整条流水线。
                tasks_module.dispatch_pipeline(queued["job_id"])

                self.assertEqual(service.list_queue()["total"], 1)
                audit = service.get_audit(content_id=queued["content_id"])
                self.assertEqual(
                    [item["action"] for item in audit["items"]],
                    [
                        "content_queued",
                        "pipeline_started",
                        "evidence_extracted",
                        "machine_review_completed",
                        "human_review_task_created",
                    ],
                )
            finally:
                tasks_module.set_service(None)

    def test_pipeline_failure_records_dead_letter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = GovernanceService(Path(tmp) / "test.sqlite3")
            queued = service.ingest_content(
                {"title": "Broken clip", "description": "Neutral content", "creator_id": "creator_x"}
            )
            with patch("backend.app.services.EvidenceExtractor") as extractor_cls:
                extractor_cls.return_value.extract.side_effect = RuntimeError("extractor down")
                service.drain_pipeline()

            jobs = service.list_pipeline_jobs()
            self.assertEqual(jobs["items"][0]["status"], "failed")
            dead_letters = service.list_dead_letters()
            self.assertEqual(dead_letters["total"], 1)
            self.assertEqual(dead_letters["items"][0]["exception_type"], "RuntimeError")
            self.assertEqual(dead_letters["items"][0]["content_id"], queued["content_id"])

    def test_rate_limiter_blocks_after_limit(self) -> None:
        import fakeredis

        from backend.app.rate_limiter import RateLimiter, RateLimitRule

        limiter = RateLimiter(fakeredis.FakeStrictRedis(decode_responses=True))
        rule = RateLimitRule(max_requests=2, window_seconds=60)
        self.assertTrue(limiter.check("op", "user_a", rule))
        self.assertTrue(limiter.check("op", "user_a", rule))
        self.assertFalse(limiter.check("op", "user_a", rule))  # 第 3 次超限
        self.assertTrue(limiter.check("op", "user_b", rule))  # 不同身份独立计数
        # 无 Redis -> 优雅降级放行
        self.assertTrue(RateLimiter(None).check("op", "user_a", rule))

    def test_rate_limited_endpoint_returns_429(self) -> None:
        import fakeredis
        from fastapi.testclient import TestClient

        from backend.app.api import create_app
        from backend.app.rate_limiter import RateLimiter

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(db_path=Path(tmp) / "test.sqlite3")
            with TestClient(app) as client:
                # 注入 fakeredis 后端的限流器（默认无 Redis 会降级放行）。
                app.state.rate_limiter = RateLimiter(fakeredis.FakeStrictRedis(decode_responses=True))
                payload = {"title": "T", "description": "D", "creator_id": "c"}
                statuses = [
                    client.post("/api/v1/content/upload", json=payload).status_code for _ in range(11)
                ]
            self.assertEqual(statuses[:10], [200] * 10)  # content.upload 限额 10/60s
            self.assertEqual(statuses[10], 429)

    def test_circuit_breaker_opens_and_recovers(self) -> None:
        import fakeredis

        from backend.app.circuit_breaker import CircuitBreaker

        clock = {"t": 1000.0}
        breaker = CircuitBreaker(
            fakeredis.FakeStrictRedis(decode_responses=True),
            name="t",
            failure_rate_threshold=0.5,
            minimum_calls=4,
            window_seconds=60,
            recovery_timeout=30,
            time_fn=lambda: clock["t"],
        )
        for _ in range(3):  # 未达 minimum_calls：保持闭合
            breaker.record_failure()
        self.assertTrue(breaker.allow())
        breaker.record_failure()  # 达到最小样本且失败率超阈值 -> 打开
        self.assertFalse(breaker.allow())
        clock["t"] += 10  # 未到恢复期仍打开
        self.assertFalse(breaker.allow())
        clock["t"] += 30  # 到恢复期 -> 半开放行一次试探
        self.assertTrue(breaker.allow())
        breaker.record_success()  # 试探成功 -> 闭合
        self.assertEqual(breaker.state(), "closed")

    def test_circuit_breaker_call_wraps_failures(self) -> None:
        import fakeredis

        from backend.app.circuit_breaker import CircuitBreaker, CircuitOpenError

        breaker = CircuitBreaker(
            fakeredis.FakeStrictRedis(decode_responses=True),
            name="call",
            failure_rate_threshold=0.5,
            minimum_calls=3,
            window_seconds=60,
            recovery_timeout=60,
        )

        def boom():
            raise TimeoutError("down")

        for _ in range(3):
            with self.assertRaises(TimeoutError):
                breaker.call(boom)
        with self.assertRaises(CircuitOpenError):  # 打开后直接短路
            breaker.call(lambda: "ok")
        self.assertTrue(CircuitBreaker(None).allow())  # 无 Redis -> 恒放行

    def test_llm_review_failures_open_breaker(self) -> None:
        import fakeredis

        from backend.app.circuit_breaker import CircuitBreaker
        from backend.app.llm_review import review_with_configured_llm

        breaker = CircuitBreaker(
            fakeredis.FakeStrictRedis(decode_responses=True),
            name="llm_it",
            failure_rate_threshold=0.5,
            minimum_calls=2,
            window_seconds=60,
            recovery_timeout=60,
        )
        env = {
            "LLM_API_KEY": "test-key",
            "OPENAI_API_KEY": "test-key",
            "LLM_BASE_URL": "http://127.0.0.1:1/v1",  # 连接立即被拒
            "LLM_TIMEOUT_SECONDS": "1",
        }
        with patch.dict(os.environ, env):
            for _ in range(2):
                self.assertIsNone(review_with_configured_llm({"metadata": {}}, breaker=breaker))
            self.assertFalse(breaker.allow())  # 连续失败 -> 打开
            # 打开后直接短路返回 None（不再发网络）
            self.assertIsNone(review_with_configured_llm({"metadata": {}}, breaker=breaker))

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
