"""Stage 8 测试：Fleiss' Kappa、样本分类、黄金题、数据回流 + JSONL 导出 + 质量门。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.quality import classify_sample, fleiss_kappa, passes_quality_gate
from backend.app.services import GovernanceService


GAMBLING = {
    "title": "gambling promo",
    "description": "scan the qr to claim your betting bonus at our casino",
    "creator_id": "creator_bet",
}
NEUTRAL = {
    "title": "daily vlog",
    "description": "an ordinary personal update without enough policy context",
    "creator_id": "c",
}


class KappaUnitTest(unittest.TestCase):
    def test_perfect_agreement_kappa_one(self):
        r = fleiss_kappa([["pass", "pass"], ["block", "block"]], categories=["pass", "block"])
        self.assertEqual(r["kappa"], 1.0)
        self.assertTrue(r["meets_threshold"])

    def test_complete_disagreement_negative(self):
        r = fleiss_kappa([["pass", "block"]], categories=["pass", "block"])
        self.assertLess(r["kappa"], 0)

    def test_insufficient_samples(self):
        self.assertIsNone(fleiss_kappa([["pass"]])["kappa"])

    def test_degenerate_single_category_is_undefined_not_perfect(self):
        # 回归：所有裁定同一类别 -> kappa 未定义，不能报 1.0/达标。
        r = fleiss_kappa([["pass", "pass"], ["pass", "pass"]], categories=["pass", "block"])
        self.assertIsNone(r["kappa"])
        self.assertFalse(r["meets_threshold"])

    def test_classify_sample(self):
        self.assertEqual(classify_sample("block", "pass"), ("disagreement", "overkill"))
        self.assertEqual(classify_sample("pass", "block"), ("disagreement", "miss"))
        self.assertEqual(classify_sample("pass", "pass"), ("ground_truth", ""))
        self.assertEqual(classify_sample("uncertain", "block"), ("ground_truth", ""))

    def test_quality_gate(self):
        self.assertTrue(passes_quality_gate("ground_truth", None))
        self.assertTrue(passes_quality_gate("golden", True))
        self.assertFalse(passes_quality_gate("golden", False))


class FlywheelIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env = patch.dict(os.environ, {"LLM_API_KEY": "", "OPENAI_API_KEY": ""})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()

    def _service(self, tmp):
        return GovernanceService(Path(tmp) / "t.sqlite3")

    def _decide(self, service, payload, decision, reviewer="reviewer_a"):
        service.ingest_content(payload)
        service.drain_pipeline()
        task_id = service.list_queue()["items"][0]["task_id"]
        service.claim_task(task_id, reviewer)
        service.decide_task(task_id, {"decision": decision, "reason": "r", "reviewer_id": reviewer})
        return task_id

    def test_disagreement_sample_overkill(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            # 新流程下 block 不进人审；只有 uncertain 内容会产生人审样本。
            self._decide(service, NEUTRAL, "pass")
            samples = service.list_flywheel_samples()["items"]
            self.assertEqual(len(samples), 1)
            self.assertEqual(samples[0]["source_type"], "ground_truth")
            self.assertEqual(samples[0]["source_label"], "人审确认样本")
            self.assertIn("监督样本", samples[0]["source_description"])
            self.assertEqual(samples[0]["error_type"], "")

    def test_ground_truth_sample_on_agreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._decide(service, NEUTRAL, "pass")  # 机审 pass + 人审 pass -> 一致
            samples = service.list_flywheel_samples()["items"]
            self.assertEqual(samples[0]["source_type"], "ground_truth")

    def test_golden_test_sync_evaluation_and_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            service.ingest_content(NEUTRAL)
            service.drain_pipeline()
            task_id = service.list_queue()["items"][0]["task_id"]
            service.mark_golden(task_id, "block")  # 期望 block
            service.claim_task(task_id, "reviewer_a")
            # 审核员答 pass（与期望 block 不符）-> golden 错，质量门不通过。
            result = service.decide_task(
                task_id, {"decision": "pass", "reason": "r", "reviewer_id": "reviewer_a"}
            )
            self.assertTrue(result["golden_test_result"]["is_golden_test"])
            self.assertFalse(result["golden_test_result"]["is_correct"])
            sample = service.list_flywheel_samples(source_type="golden")["items"][0]
            self.assertFalse(sample["quality_gate_passed"])
            stats = service.reviewer_stats("reviewer_a")
            self.assertEqual(stats["golden_total"], 1)
            self.assertEqual(stats["golden_correct"], 0)

    def test_correction_sample_from_appeal_overturn(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._decide(service, NEUTRAL, "block", reviewer="reviewer_a")
            cid = service.list_flywheel_samples()["items"][0]["content_id"]
            appeal_id = service.submit_appeal(cid, "creator_c", "unfair")["appeal_id"]
            service.assign_appeal(appeal_id, "appeal_b")
            service.decide_appeal(appeal_id, "appeal_b", "overturn", "改判")
            corrections = service.list_flywheel_samples(source_type="correction")["items"]
            self.assertEqual(len(corrections), 1)
            self.assertTrue(corrections[0]["is_correction"])
            self.assertEqual(corrections[0]["source_label"], "申诉改判样本")
            self.assertEqual(corrections[0]["final_decision"], "pass")

    def test_quality_summary_and_jsonl_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._decide(service, NEUTRAL, "pass")
            self._decide(
                service,
                {"title": "daily vlog two", "description": "another ordinary update", "creator_id": "c"},
                "block",
            )
            summary = service.quality_summary()
            self.assertEqual(summary["total_samples"], 2)
            self.assertEqual(summary["human_override_rate"], 0.0)
            jsonl = service.export_flywheel_jsonl(only_passed=True)
            self.assertEqual(len(jsonl.strip().splitlines()), 2)

    def test_irr_over_appeal_multirater(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = self._service(tmp)
            self._decide(service, NEUTRAL, "block", reviewer="reviewer_a")
            cid = service.list_flywheel_samples()["items"][0]["content_id"]
            appeal_id = service.submit_appeal(cid, "creator_c", "x")["appeal_id"]
            service.assign_appeal(appeal_id, "appeal_b")
            service.decide_appeal(appeal_id, "appeal_b", "overturn", "改判")
            irr = service.compute_irr()
            # 一个内容有 [block, pass] 两个评审 -> 可算 kappa。
            self.assertEqual(irr["items"], 1)
            self.assertIsNotNone(irr["kappa"])


if __name__ == "__main__":
    unittest.main()
