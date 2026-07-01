from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from .appeals import (
    APPEALABLE_DECISIONS,
    OVERTURN_TARGET,
    AppealStatus,
    can_transition as appeal_can_transition,
)
from .config import settings
from .database import create_db_engine, init_db, is_postgres_enabled, make_session_factory
from .decision_engine import DecisionEngineService, StrategyRegistry
from .decision_engine.types import VALID_STATUS_TRANSITIONS, DimensionStatus
from .evidence import EvidenceExtractor
from .llm_review import is_llm_configured
from .quality import FlywheelSource, classify_sample, fleiss_kappa, passes_quality_gate
from .realtime import hub
from .sor import SOR_TEMPLATE_ID, render_sor
from .review_workflow import DECISION_PRIORITY, QueuePriority, ReviewStatus, can_transition
from .auth import hash_password, verify_password
from .models import (
    AppealCase,
    AuditLog,
    ContentItem,
    DeadLetterTask,
    DimensionRegistry,
    EvidencePackage,
    FlywheelSample,
    HumanReviewTask,
    MachineReview,
    MediaAsset,
    PipelineJob,
    PolicyVersion,
    User,
)


PASS = "pass"
BLOCK = "block"
PENDING = "pending"
DECIDED = "decided"
JOB_QUEUED = "queued"
JOB_PROCESSING = "processing"
JOB_COMPLETED = "completed"
JOB_FAILED = "failed"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def loads(data: str) -> Any:
    return json.loads(data)


class ValidationError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


class ConflictError(RuntimeError):
    pass


class GovernanceService:
    """Single-tenant, global-jurisdiction MVP workflow service."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path
        self.engine = create_db_engine(db_path)
        init_db(self.engine)
        self._session_factory = make_session_factory(self.engine)
        # Stage 4：每个服务实例持有自己的注册表（隔离不同 DB），策略类是进程级共享。
        self._registry = StrategyRegistry()
        self._decision_engine = DecisionEngineService(self._registry)
        self._seed_decision_registry()
        self.reload_strategies()

    def reset(self) -> dict[str, Any]:
        # 按外键依赖倒序删除，避免约束冲突。
        with self._session_factory.begin() as session:
            for model in (
                DeadLetterTask,
                AuditLog,
                FlywheelSample,
                AppealCase,
                HumanReviewTask,
                MachineReview,
                EvidencePackage,
                MediaAsset,
                PipelineJob,
                ContentItem,
                User,
            ):
                session.execute(delete(model))
        return {"status": "reset"}

    def seed(self) -> dict[str, Any]:
        examples = [
            {
                "title": "低风险做饭教程",
                "description": "创作者展示家常菜做法，并提到一家家庭餐厅。",
                "creator_id": "creator_alina",
                "poi": "global",
                "video_url": "https://example.local/videos/cooking-demo.mp4",
            },
            {
                "title": "高风险博彩引流",
                "description": "视频文字引导用户扫码领取 betting bonus。",
                "creator_id": "creator_bento",
                "poi": "global",
                "video_url": "https://example.local/videos/betting-promo.mp4",
            },
        ]
        created = [self.ingest_content(item) for item in examples]
        return {"items": created}

    def seed_demo_cases(self) -> dict[str, Any]:
        """Create a stable demo batch that exercises the production routing paths."""
        batch_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        examples = [
            {
                "scenario": "critical_gambling_block",
                "expected_policy_decision": "critical_escalate",
                "title": f"DEMO critical gambling {batch_id}",
                "description": "Casino betting bonus. Scan QR to join invite group for odds reward.",
                "creator_id": "demo_creator_gambling_critical",
                "poi": "global",
                "video_url": "https://example.local/videos/demo-critical-gambling.mp4",
            },
            {
                "scenario": "gambling_auto_block",
                "expected_policy_decision": "auto_block",
                "title": f"DEMO gambling auto block {batch_id}",
                "description": "Casino betting lottery wager odds casino betting lottery odds.",
                "creator_id": "demo_creator_gambling",
                "poi": "global",
                "video_url": "https://example.local/videos/demo-gambling-auto-block.mp4",
            },
            {
                "scenario": "drug_violence_auto_block",
                "expected_policy_decision": "auto_block",
                "title": f"DEMO drug violence auto block {batch_id}",
                "description": "Weapon gun knife violence blood scene shown in a dangerous clip.",
                "creator_id": "demo_creator_safety",
                "poi": "global",
                "video_url": "https://example.local/videos/demo-drug-violence-auto-block.mp4",
            },
            {
                "scenario": "marketing_needs_human_review",
                "expected_policy_decision": "needs_human_review",
                "title": f"DEMO marketing needs human review {batch_id}",
                "description": "Creator mentions discount coupon for handmade stickers in a lifestyle vlog.",
                "creator_id": "demo_creator_marketing",
                "poi": "global",
                "video_url": "https://example.local/videos/demo-marketing-review.mp4",
            },
            {
                "scenario": "cooking_auto_pass",
                "expected_policy_decision": "auto_pass",
                "title": f"DEMO cooking auto pass {batch_id}",
                "description": "Family cooking recipe lesson with tomato soup and calm narration.",
                "creator_id": "demo_creator_cooking",
                "poi": "global",
                "video_url": "https://example.local/videos/demo-cooking-pass.mp4",
            },
        ]
        created: list[dict[str, Any]] = []
        for item in examples:
            scenario = item.pop("scenario")
            expected = item.pop("expected_policy_decision")
            job = self.ingest_content(item)
            self._run_pipeline_for_demo(job["job_id"], job["content_id"])
            review = self.get_machine_review(job["content_id"])
            created.append(
                {
                    "scenario": scenario,
                    "expected_policy_decision": expected,
                    "content_id": job["content_id"],
                    "job_id": job["job_id"],
                    "title": item["title"],
                    "recommendation": review["recommendation"],
                    "final_decision": review["final_decision"],
                    "content_status": review["content_status"],
                    "task_id": review["task_id"],
                    "task_status": review["task_status"],
                    "policy_decision": review["decision_summary"]["final_decision"],
                    "risk_score": review["confidence"],
                    "triggered_rules": review["decision_summary"].get("triggered_rules", []),
                }
            )
        return {"batch_id": batch_id, "total": len(created), "items": created}

    def _run_pipeline_for_demo(self, job_id: str, content_id: str) -> None:
        try:
            self.claim_pipeline_job(job_id)
            self.extract_evidence_stage(job_id)
            self.run_machine_review_stage(job_id)
        except Exception as exc:
            self._mark_pipeline_failed(job_id, content_id, exc)
            raise

    def ingest_content(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = str(payload.get("title", "")).strip()
        description = str(payload.get("description", "")).strip()
        creator_id = str(payload.get("creator_id", "anonymous")).strip() or "anonymous"
        if not title:
            raise ValidationError("标题不能为空")
        if not description:
            raise ValidationError("描述不能为空")

        content_id = new_id("cnt")
        job_id = new_id("job")
        timestamp = now_iso()

        with self._session_factory.begin() as session:
            backlog = session.execute(
                select(func.count())
                .select_from(PipelineJob)
                .where(PipelineJob.status.in_([JOB_QUEUED, JOB_PROCESSING]))
            ).scalar_one()
            if backlog >= settings.max_pipeline_backlog:
                raise ConflictError("机审队列已满，请稍后重试")

            session.add(
                ContentItem(
                    id=content_id,
                    tenant_id=settings.tenant_id,
                    jurisdiction=settings.jurisdiction,
                    title=title,
                    description=description,
                    creator_id=creator_id,
                    poi=payload.get("poi", "global"),
                    video_url=payload.get("video_url", ""),
                    status="machine_queued",
                    final_decision=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            session.add(
                PipelineJob(
                    id=job_id,
                    content_id=content_id,
                    status=JOB_QUEUED,
                    stage="queued",
                    attempts=0,
                    max_attempts=3,
                    error=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                    started_at=None,
                    finished_at=None,
                )
            )
            self._append_audit(
                session,
                content_id=content_id,
                task_id=None,
                actor="system",
                action="content_queued",
                detail={
                    "job_id": job_id,
                    "routing": "machine_pipeline",
                    "csam_enabled": False,
                    "critical_detection_enabled": False,
                },
            )

        self._dispatch_pipeline(job_id)
        return self.get_pipeline_job(job_id)

    def _dispatch_pipeline(self, job_id: str) -> None:
        """配置了 Celery broker 时派发异步 chain；否则不派发，交给 drain / 线程 worker。

        测试与本地无 broker 环境下保持“先入队、后 drain”的语义不变。
        """
        if not settings.celery_broker_url:
            return
        from .tasks import dispatch_pipeline  # 延迟导入，避免与 tasks 循环依赖

        dispatch_pipeline(job_id)

    def ingest_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValidationError("批量摄取请求必须包含 items 数组")
        if not items:
            raise ValidationError("items 不能为空")
        if len(items) > settings.max_batch_ingest_items:
            raise ValidationError(f"单次批量摄取最多允许 {settings.max_batch_ingest_items} 条")

        created: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append({"index": index, "error": "条目必须是 JSON 对象"})
                continue
            try:
                created.append(self.ingest_content(item))
            except (ValidationError, ConflictError) as exc:
                errors.append({"index": index, "error": str(exc)})

        return {
            "accepted": len(created),
            "failed": len(errors),
            "total": len(items),
            "items": created,
            "errors": errors,
        }

    def get_pipeline_job(self, job_id: str) -> dict[str, Any]:
        sql = text(
            """
            SELECT j.*, c.title, c.description, c.creator_id, c.status AS content_status,
                   c.final_decision,
                   e.id AS evidence_package_id,
                   m.id AS machine_review_id, m.recommendation, m.confidence, m.rationale,
                   t.id AS task_id, t.status AS task_status
            FROM pipeline_jobs j
            JOIN content_items c ON c.id = j.content_id
            LEFT JOIN evidence_packages e ON e.content_id = c.id
            LEFT JOIN machine_reviews m ON m.content_id = c.id
            LEFT JOIN human_review_tasks t ON t.content_id = c.id
            WHERE j.id = :job_id
            """
        )
        with self._session_factory() as session:
            row = session.execute(sql, {"job_id": job_id}).mappings().first()
        if row is None:
            raise NotFoundError("流水线任务不存在")
        return self._pipeline_job_summary(dict(row))

    def list_pipeline_jobs(self, offset: int = 0, limit: int = 50, status: str | None = None) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        where = ""
        params: dict[str, Any] = {}
        if status:
            where = "WHERE j.status = :status"
            params["status"] = status
        with self._session_factory() as session:
            total = session.execute(
                text(f"SELECT COUNT(*) AS c FROM pipeline_jobs j {where}"),
                params,
            ).scalar_one()
            rows = session.execute(
                text(
                    f"""
                    SELECT j.*, c.title, c.description, c.creator_id, c.status AS content_status,
                           c.final_decision,
                           e.id AS evidence_package_id,
                           m.id AS machine_review_id, m.recommendation, m.confidence, m.rationale,
                           t.id AS task_id, t.status AS task_status
                    FROM pipeline_jobs j
                    JOIN content_items c ON c.id = j.content_id
                    LEFT JOIN evidence_packages e ON e.content_id = c.id
                    LEFT JOIN machine_reviews m ON m.content_id = c.id
                    LEFT JOIN human_review_tasks t ON t.content_id = c.id
                    {where}
                    ORDER BY j.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {**params, "limit": limit, "offset": offset},
            ).mappings().all()
        items = [self._pipeline_job_summary(dict(row)) for row in rows]
        next_offset = offset + limit if offset + limit < total else None
        return {"items": items, "total": total, "offset": offset, "limit": limit, "next_offset": next_offset}

    def process_next_pipeline_job(self) -> bool:
        # PostgreSQL 下用 FOR UPDATE SKIP LOCKED 让多 worker 并发领取不打架；SQLite 无此语义。
        lock_clause = " FOR UPDATE SKIP LOCKED" if is_postgres_enabled() else ""
        with self._session_factory.begin() as session:
            row = session.execute(
                text(
                    f"""
                    SELECT j.*, c.title, c.description, c.creator_id, c.poi, c.video_url
                    FROM pipeline_jobs j
                    JOIN content_items c ON c.id = j.content_id
                    WHERE j.status = :status AND j.attempts < j.max_attempts
                    ORDER BY j.created_at ASC
                    LIMIT 1
                    {lock_clause}
                    """
                ),
                {"status": JOB_QUEUED},
            ).mappings().first()
            if row is None:
                return False
            job = dict(row)
            timestamp = now_iso()

            pipeline_job = session.get(PipelineJob, job["id"])
            pipeline_job.status = JOB_PROCESSING
            pipeline_job.stage = "evidence_extraction"
            pipeline_job.attempts = pipeline_job.attempts + 1
            pipeline_job.started_at = pipeline_job.started_at or timestamp
            pipeline_job.updated_at = timestamp
            pipeline_job.error = None

            content = session.get(ContentItem, job["content_id"])
            content.status = "machine_processing"
            content.updated_at = timestamp

            self._append_audit(
                session,
                content_id=job["content_id"],
                task_id=None,
                actor="pipeline_worker",
                action="pipeline_started",
                detail={"job_id": job["id"]},
            )

        try:
            self._run_pipeline_job(job)
        except Exception as exc:  # pragma: no cover - defensive worker boundary
            self._mark_pipeline_failed(job["id"], job["content_id"], exc)
        return True

    def drain_pipeline(self, limit: int | None = None) -> int:
        processed = 0
        while limit is None or processed < limit:
            if not self.process_next_pipeline_job():
                break
            processed += 1
        return processed

    def _run_pipeline_job(self, job: dict[str, Any]) -> None:
        """线程/drain 路径：调用方已领取任务，这里顺序执行两个阶段。

        阶段方法是幂等的，与 Celery chain 复用同一套逻辑（见 app/tasks.py）。
        """
        self.extract_evidence_stage(job["id"])
        self.run_machine_review_stage(job["id"])

    def claim_pipeline_job(self, job_id: str) -> None:
        """把指定 job 从 queued 领取为 processing（幂等：非 queued 直接跳过）。

        线程路径在 process_next_pipeline_job 里用 SKIP LOCKED 原子领取；Celery 路径
        每个 job 只派发一次，这里按 id 领取即可。
        """
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            job = session.get(PipelineJob, job_id)
            if job is None:
                raise NotFoundError("流水线任务不存在")
            if job.status != JOB_QUEUED:
                return
            job.status = JOB_PROCESSING
            job.stage = "evidence_extraction"
            job.attempts = job.attempts + 1
            job.started_at = job.started_at or timestamp
            job.updated_at = timestamp
            job.error = None
            content = session.get(ContentItem, job.content_id)
            content.status = "machine_processing"
            content.updated_at = timestamp
            self._append_audit(
                session,
                content_id=job.content_id,
                task_id=None,
                actor="pipeline_worker",
                action="pipeline_started",
                detail={"job_id": job_id},
            )

    def extract_evidence_stage(self, job_id: str) -> None:
        """阶段1：抽证据。幂等 —— 证据包已存在则直接返回，重试不会重复生成。"""
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            job = session.get(PipelineJob, job_id)
            if job is None:
                raise NotFoundError("流水线任务不存在")
            content = session.get(ContentItem, job.content_id)
            existing = session.execute(
                select(EvidencePackage.id).where(EvidencePackage.content_id == job.content_id)
            ).scalar()
            if existing is not None:
                return
            evidence_id = new_id("ep")
            text_blob = f"{content.title} {content.description}".lower()
            evidence = self._build_evidence_package(
                evidence_id=evidence_id,
                content_id=job.content_id,
                title=content.title,
                description=content.description,
                creator_id=content.creator_id,
                poi=str(content.poi or "global"),
                video_url=str(content.video_url or ""),
                text=text_blob,
            )
            job.stage = "machine_review"
            job.updated_at = timestamp
            session.add(
                EvidencePackage(
                    id=evidence_id,
                    content_id=job.content_id,
                    package_json=dumps(evidence),
                    created_at=timestamp,
                )
            )
            self._persist_media_asset(session, evidence["media_asset"], timestamp)
            self._append_audit(
                session,
                content_id=job.content_id,
                task_id=None,
                actor="pipeline_worker",
                action="evidence_extracted",
                detail={
                    "job_id": job_id,
                    "evidence_package_id": evidence_id,
                    "media_asset_id": evidence["media_asset"]["asset_id"],
                    "media_asset_status": evidence["media_asset"]["status"],
                },
            )

    def run_machine_review_stage(self, job_id: str) -> None:
        """阶段2：机审分流。机审明确通过/拦截直接终结，只有不确定才进入人审。"""
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            job = session.get(PipelineJob, job_id)
            if job is None:
                raise NotFoundError("流水线任务不存在")
            content = session.get(ContentItem, job.content_id)
            existing_review = session.execute(
                select(MachineReview.id).where(MachineReview.content_id == job.content_id)
            ).scalar()
            if existing_review is not None:
                return
            evidence_row = session.execute(
                select(EvidencePackage).where(EvidencePackage.content_id == job.content_id)
            ).scalar_one()
            evidence = loads(evidence_row.package_json)
            text_blob = f"{content.title} {content.description}".lower()
            machine_review_id = new_id("mr")
            policy_version = self._active_policy_version(session)
            machine = self._run_machine_review(
                machine_review_id, job.content_id, evidence, text_blob, policy_version
            )
            # _run_machine_review 会往 evidence 里补 llm_verdicts / decision_summary / machine_review_source。
            evidence_row.package_json = dumps(evidence)

            session.add(
                MachineReview(
                    id=machine["id"],
                    content_id=job.content_id,
                    recommendation=machine["recommendation"],
                    confidence=machine["confidence"],
                    rationale=machine["rationale"],
                    verdicts_json=dumps(machine["verdicts"]),
                    decision_summary_json=dumps(machine["decision_summary"]),
                    created_at=timestamp,
                )
            )
            self._append_audit(
                session,
                content_id=job.content_id,
                task_id=None,
                actor="pipeline_worker",
                action="machine_review_completed",
                detail={
                    "job_id": job_id,
                    "machine_review_id": machine["id"],
                    "recommendation": machine["recommendation"],
                    "final_decision": machine["decision_summary"].get("final_decision"),
                },
            )

            summary = machine["decision_summary"]
            final_decision = summary.get("final_decision", "needs_human_review")
            action = summary.get("action", {})
            route_to_human = bool(action.get("route_to_human_review"))

            if route_to_human:
                task_id = new_id("task")
                sla_deadline = (
                    _parse_iso(timestamp) + timedelta(seconds=settings.sla_default_seconds)
                ).isoformat()
                priority = DECISION_PRIORITY.get(final_decision, QueuePriority.NORMAL.value)
                is_sensitive = final_decision == "critical_escalate" or any(
                    v.get("severity_suggestion") == "critical" for v in machine["verdicts"]
                )
                session.add(
                    HumanReviewTask(
                        id=task_id,
                        content_id=job.content_id,
                        evidence_package_id=evidence_row.id,
                        status=PENDING,
                        assigned_to=None,
                        decision=None,
                        reason=None,
                        decided_at=None,
                        locked_at=None,
                        lock_expires_at=None,
                        sla_deadline=sla_deadline,
                        sla_warned=False,
                        priority=priority,
                        is_sensitive=is_sensitive,
                        jurisdiction=str(content.jurisdiction or "global"),
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
                job.stage = "human_review_queued"
                content.status = "human_review"
                self._append_audit(
                    session,
                    content_id=job.content_id,
                    task_id=task_id,
                    actor="pipeline_worker",
                    action="human_review_task_created",
                    detail={"job_id": job_id, "task_id": task_id, "final_decision": final_decision},
                )
            else:
                final = PASS if machine["recommendation"] == PASS else BLOCK
                content.status = f"final_{final}"
                content.final_decision = final
                job.stage = "machine_auto_decided"
                self._append_audit(
                    session,
                    content_id=job.content_id,
                    task_id=None,
                    actor="pipeline_worker",
                    action="machine_auto_decided",
                    detail={
                        "job_id": job_id,
                        "machine_review_id": machine["id"],
                        "final_decision": final,
                        "policy_decision": final_decision,
                    },
                )

            job.status = JOB_COMPLETED
            job.updated_at = timestamp
            job.finished_at = timestamp
            content.updated_at = timestamp

    def _mark_pipeline_failed(self, job_id: str, content_id: str, exc: Exception) -> None:
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            pipeline_job = session.get(PipelineJob, job_id)
            if pipeline_job is not None:
                pipeline_job.status = JOB_FAILED
                pipeline_job.stage = "failed"
                pipeline_job.error = str(exc)
                pipeline_job.updated_at = timestamp
                pipeline_job.finished_at = timestamp

            content = session.get(ContentItem, content_id)
            if content is not None:
                content.status = "machine_failed"
                content.updated_at = timestamp

            self._append_audit(
                session,
                content_id=content_id,
                task_id=None,
                actor="pipeline_worker",
                action="pipeline_failed",
                detail={"job_id": job_id, "error": str(exc)},
            )

            # 线程路径失败即终态（不重试），记入死信队列供运维排查/重放。
            session.add(
                DeadLetterTask(
                    task_name="pipeline",
                    celery_task_id=None,
                    job_id=job_id,
                    content_id=content_id,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                    traceback="",
                    retry_count=pipeline_job.attempts if pipeline_job is not None else 0,
                    status="pending",
                    created_at=timestamp,
                )
            )

    def list_queue(self, offset: int = 0, limit: int = 20, status: str = PENDING) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        with self._session_factory() as session:
            total = session.execute(
                select(func.count())
                .select_from(HumanReviewTask)
                .where(HumanReviewTask.status == status)
            ).scalar_one()
            rows = session.execute(
                text(
                    """
                    SELECT t.*, c.title, c.description, c.creator_id, c.poi, c.video_url,
                           m.recommendation, m.confidence, m.rationale
                    FROM human_review_tasks t
                    JOIN content_items c ON c.id = t.content_id
                    JOIN machine_reviews m ON m.content_id = c.id
                    WHERE t.status = :status
                    ORDER BY t.priority ASC,
                             CASE WHEN t.sla_deadline IS NULL THEN 1 ELSE 0 END ASC,
                             t.sla_deadline ASC,
                             t.created_at ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"status": status, "limit": limit, "offset": offset},
            ).mappings().all()
        items = [self._task_summary(dict(row)) for row in rows]
        next_offset = offset + limit if offset + limit < total else None
        return {"items": items, "total": total, "offset": offset, "limit": limit, "next_offset": next_offset}

    def list_machine_reviews(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        with self._session_factory() as session:
            total = session.execute(select(func.count()).select_from(MachineReview)).scalar_one()
            rows = session.execute(
                text(
                    """
                    SELECT m.*, c.title, c.description, c.creator_id, c.status, c.final_decision,
                           e.id AS evidence_package_id, t.id AS task_id, t.status AS task_status
                    FROM machine_reviews m
                    JOIN content_items c ON c.id = m.content_id
                    JOIN evidence_packages e ON e.content_id = c.id
                    LEFT JOIN human_review_tasks t ON t.content_id = c.id
                    ORDER BY m.created_at DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"limit": limit, "offset": offset},
            ).mappings().all()
        items = [self._machine_review_summary(dict(row)) for row in rows]
        next_offset = offset + limit if offset + limit < total else None
        return {"items": items, "total": total, "offset": offset, "limit": limit, "next_offset": next_offset}

    def get_machine_review(self, content_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.execute(
                text(
                    """
                    SELECT m.*, c.title, c.description, c.creator_id, c.status, c.final_decision,
                           e.id AS evidence_package_id, e.package_json,
                           t.id AS task_id, t.status AS task_status
                    FROM machine_reviews m
                    JOIN content_items c ON c.id = m.content_id
                    JOIN evidence_packages e ON e.content_id = c.id
                    LEFT JOIN human_review_tasks t ON t.content_id = c.id
                    WHERE m.content_id = :content_id
                    """
                ),
                {"content_id": content_id},
            ).mappings().first()
        if row is None:
            raise NotFoundError("机审记录不存在")
        data = dict(row)
        summary = self._machine_review_summary(data)
        return {**summary, "evidence": loads(data["package_json"])}

    def get_case(self, task_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            row = session.execute(
                text(
                    """
                    SELECT t.*, c.title, c.description, c.creator_id, c.poi, c.video_url,
                           c.tenant_id, c.jurisdiction, c.final_decision,
                           e.package_json,
                           m.recommendation, m.confidence, m.rationale, m.verdicts_json
                    FROM human_review_tasks t
                    JOIN content_items c ON c.id = t.content_id
                    JOIN evidence_packages e ON e.id = t.evidence_package_id
                    JOIN machine_reviews m ON m.content_id = c.id
                    WHERE t.id = :task_id
                    """
                ),
                {"task_id": task_id},
            ).mappings().first()
        if row is None:
            raise NotFoundError("任务不存在")
        data = dict(row)
        return {
            "task": self._task_summary(data),
            "content": {
                "id": data["content_id"],
                "title": data["title"],
                "description": data["description"],
                "creator_id": data["creator_id"],
                "poi": data["poi"],
                "video_url": data["video_url"],
                "tenant_id": data["tenant_id"],
                "jurisdiction": data["jurisdiction"],
                "final_decision": data["final_decision"],
            },
            "evidence": loads(data["package_json"]),
            "machine_review": {
                "recommendation": data["recommendation"],
                "confidence": data["confidence"],
                "rationale": data["rationale"],
                "verdicts": loads(data["verdicts_json"]),
            },
        }

    def get_evidence(self, evidence_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            package = session.get(EvidencePackage, evidence_id)
        if package is None:
            raise NotFoundError("证据包不存在")
        return loads(package.package_json)

    def claim_task(self, task_id: str, reviewer_id: str) -> dict[str, Any]:
        """领取即加案件锁（Stage 5）。锁未过期时他人不能抢；本人可幂等续租；锁过期可接管。"""
        reviewer_id = reviewer_id.strip() or "reviewer_demo"
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        prev_holder: str | None = None
        with self._session_factory.begin() as session:
            # 行锁（Postgres FOR UPDATE；SQLite 忽略但有文件级写锁）消除领取竞态。
            task = session.get(HumanReviewTask, task_id, with_for_update=True)
            if task is None:
                raise NotFoundError("任务不存在")
            if task.status == DECIDED:
                raise ConflictError("任务已完成裁定")
            lock_expiry = _parse_iso(task.lock_expires_at)
            locked_active = lock_expiry is not None and lock_expiry > now
            if locked_active and task.assigned_to and task.assigned_to != reviewer_id:
                raise ConflictError(f"案件已被 {task.assigned_to} 锁定")
            prev_holder = task.assigned_to if task.assigned_to != reviewer_id else None
            task.assigned_to = reviewer_id
            task.status = ReviewStatus.IN_REVIEW.value  # pending/in_review -> in_review
            task.locked_at = timestamp
            task.lock_expires_at = (
                now + timedelta(seconds=settings.case_lock_ttl_seconds)
            ).isoformat()
            task.updated_at = timestamp
            self._append_audit(
                session,
                content_id=task.content_id,
                task_id=task_id,
                actor=reviewer_id,
                action="task_claimed",
                detail={"reviewer_id": reviewer_id, "lock_expires_at": task.lock_expires_at},
            )
            lock_expires_at = task.lock_expires_at
        # 抢占了他人的过期锁 -> 通知原持有者其锁已失效。
        if prev_holder:
            hub.publish_to_user(prev_holder, "task_reassigned", {"task_id": task_id, "new_holder": reviewer_id})
        hub.publish_to_user(reviewer_id, "task_lock_renewed", {"task_id": task_id, "lock_expires_at": lock_expires_at})
        return self.get_case(task_id)

    def heartbeat_task(self, task_id: str, reviewer_id: str) -> dict[str, Any]:
        """心跳续租锁（Stage 5）。仅持锁人可续。"""
        now = datetime.now(timezone.utc)
        with self._session_factory.begin() as session:
            task = session.get(HumanReviewTask, task_id, with_for_update=True)
            if task is None:
                raise NotFoundError("任务不存在")
            if task.status == DECIDED:
                raise ConflictError("任务已完成裁定")
            if task.assigned_to != reviewer_id:
                raise ConflictError("只有持锁人可以续租")
            lock_expiry = _parse_iso(task.lock_expires_at)
            if lock_expiry is None or lock_expiry <= now:
                raise ConflictError("锁已过期，请重新领取")
            new_expiry = (now + timedelta(seconds=settings.case_lock_ttl_seconds)).isoformat()
            task.lock_expires_at = new_expiry
            task.updated_at = now.isoformat()
        hub.publish_to_user(reviewer_id, "task_lock_renewed", {"task_id": task_id, "lock_expires_at": new_expiry})
        return {"task_id": task_id, "lock_expires_at": new_expiry}

    def release_task(self, task_id: str, reviewer_id: str) -> dict[str, Any]:
        """主动释放锁（Stage 5）。"""
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            task = session.get(HumanReviewTask, task_id, with_for_update=True)
            if task is None:
                raise NotFoundError("任务不存在")
            if task.status == DECIDED:
                raise ConflictError("任务已完成裁定，不能释放")  # 禁止 decided->pending 复活
            if task.assigned_to != reviewer_id:
                raise ConflictError("只有持锁人可以释放")
            task.assigned_to = None
            task.status = ReviewStatus.PENDING.value  # 回到待分配
            task.locked_at = None
            task.lock_expires_at = None
            task.updated_at = timestamp
            self._append_audit(
                session, content_id=task.content_id, task_id=task_id, actor=reviewer_id,
                action="task_released", detail={"reviewer_id": reviewer_id},
            )
        return {"task_id": task_id, "status": "released"}

    def sweep_locks_and_sla(self) -> dict[str, Any]:
        """周期扫描：释放过期锁 + 推送 SLA 临期告警。由后台 sweeper 定时调用。"""
        now = datetime.now(timezone.utc)
        warn_before = now + timedelta(seconds=settings.sla_warning_seconds)
        expired: list[tuple[str, str]] = []
        warnings: list[tuple[str, str, str]] = []
        with self._session_factory.begin() as session:
            rows = session.execute(
                select(HumanReviewTask).where(HumanReviewTask.status != DECIDED)
            ).scalars().all()
            for task in rows:
                lock_expiry = _parse_iso(task.lock_expires_at)
                if task.assigned_to and lock_expiry is not None and lock_expiry <= now:
                    holder = task.assigned_to
                    task.assigned_to = None
                    task.status = ReviewStatus.PENDING.value  # 超时释放回待分配
                    task.locked_at = None
                    task.lock_expires_at = None
                    task.updated_at = now.isoformat()
                    expired.append((task.id, holder))
                sla = _parse_iso(task.sla_deadline)
                if sla is not None and not task.sla_warned and now < sla <= warn_before:
                    task.sla_warned = True
                    task.updated_at = now.isoformat()
                    warnings.append((task.id, task.assigned_to or "", task.sla_deadline))
        for task_id, holder in expired:
            hub.publish_to_user(holder, "task_lock_expired", {"task_id": task_id})
        for task_id, holder, deadline in warnings:
            payload = {"task_id": task_id, "sla_deadline": deadline}
            if holder:
                hub.publish_to_user(holder, "sla_warning", payload)
            hub.publish_to_role("senior_reviewer", "sla_warning", payload)
        return {"expired_locks": len(expired), "sla_warnings": len(warnings)}

    # --- Stage 6：优先级队列 + 分配 + 反疲劳 + 独立性 -------------------------

    def fetch_next(
        self, reviewer_id: str, jurisdiction: str | None = None
    ) -> dict[str, Any]:
        """领取下一个待审案件。优先级 (priority, sla_deadline, created_at) 三级排序，
        原子领取（Postgres FOR UPDATE SKIP LOCKED），并施加独立性 + 反疲劳约束。"""
        reviewer_id = reviewer_id.strip()
        if not reviewer_id:
            raise ValidationError("reviewer_id 不能为空")
        now = datetime.now(timezone.utc)
        now_iso_str = now.isoformat()

        # 反疲劳：强制休息 —— 近 1 小时裁定量超阈值则暂不派单。
        recent = self._recent_decision_count(reviewer_id, settings.forced_break_window_seconds, now)
        if recent >= settings.forced_break_after:
            hub.publish_to_user(reviewer_id, "break_reminder", {"decided_recent": recent})
            return {"task": None, "status": "break_required", "decided_recent": recent}

        over_csam = self._csam_over_limit(reviewer_id, now)
        lock_clause = " FOR UPDATE SKIP LOCKED" if is_postgres_enabled() else ""

        params: dict[str, Any] = {"reviewer_id": reviewer_id, "now": now_iso_str}
        clauses = [
            "t.status <> 'decided'",
            "(t.assigned_to IS NULL OR t.lock_expires_at < :now)",
            # 独立性：排除该审核员已裁定过的同一 content（申诉二审排除原审核员）。
            "NOT EXISTS (SELECT 1 FROM human_review_tasks p "
            "WHERE p.content_id = t.content_id AND p.assigned_to = :reviewer_id "
            "AND p.status = 'decided')",
        ]
        if jurisdiction:
            clauses.append("t.jurisdiction = :jurisdiction")
            params["jurisdiction"] = jurisdiction
        if over_csam:
            # 反疲劳：CSAM/敏感曝光超限 -> 只派非敏感任务。
            # 用绑定参数传布尔，避免 "is_sensitive = 0" 在 Postgres 上 boolean=integer 报错。
            clauses.append("t.is_sensitive = :not_sensitive")
            params["not_sensitive"] = False
        where = " AND ".join(clauses)

        with self._session_factory.begin() as session:
            row = session.execute(
                text(
                    f"""
                    SELECT t.id
                    FROM human_review_tasks t
                    WHERE {where}
                    ORDER BY t.priority ASC,
                             CASE WHEN t.sla_deadline IS NULL THEN 1 ELSE 0 END ASC,
                             t.sla_deadline ASC,
                             t.created_at ASC
                    LIMIT 1
                    {lock_clause}
                    """
                ),
                params,
            ).mappings().first()
            if row is None:
                return {"task": None, "status": "empty"}
            task = session.get(HumanReviewTask, row["id"])
            task.assigned_to = reviewer_id
            task.status = ReviewStatus.IN_REVIEW.value
            task.locked_at = now_iso_str
            task.lock_expires_at = (
                now + timedelta(seconds=settings.case_lock_ttl_seconds)
            ).isoformat()
            task.updated_at = now_iso_str
            task_id = task.id
            self._append_audit(
                session, content_id=task.content_id, task_id=task_id, actor=reviewer_id,
                action="task_assigned", detail={"reviewer_id": reviewer_id, "priority": task.priority},
            )
            lock_expires_at = task.lock_expires_at
        hub.publish_to_user(reviewer_id, "task_lock_renewed", {"task_id": task_id, "lock_expires_at": lock_expires_at})
        return {"status": "assigned", **self.get_case(task_id)}

    def _recent_decision_count(self, reviewer_id: str, window_seconds: int, now: datetime) -> int:
        cutoff = (now - timedelta(seconds=window_seconds)).isoformat()
        with self._session_factory() as session:
            return session.execute(
                select(func.count())
                .select_from(HumanReviewTask)
                .where(
                    HumanReviewTask.assigned_to == reviewer_id,
                    HumanReviewTask.status == DECIDED,
                    HumanReviewTask.decided_at >= cutoff,
                )
            ).scalar_one()

    def _csam_exposure_count(self, reviewer_id: str, window_seconds: int, now: datetime) -> int:
        cutoff = (now - timedelta(seconds=window_seconds)).isoformat()
        with self._session_factory() as session:
            return session.execute(
                select(func.count())
                .select_from(HumanReviewTask)
                .where(
                    HumanReviewTask.assigned_to == reviewer_id,
                    HumanReviewTask.status == DECIDED,
                    HumanReviewTask.is_sensitive.is_(True),
                    HumanReviewTask.decided_at >= cutoff,
                )
            ).scalar_one()

    def _csam_over_limit(self, reviewer_id: str, now: datetime) -> bool:
        shift = self._csam_exposure_count(reviewer_id, settings.shift_window_seconds, now)
        if shift >= settings.csam_per_shift_limit:
            return True
        week = self._csam_exposure_count(reviewer_id, settings.week_window_seconds, now)
        return week >= settings.csam_per_week_limit

    def reviewer_stats(self, reviewer_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        with self._session_factory() as session:
            total_decided = session.execute(
                select(func.count()).select_from(HumanReviewTask).where(
                    HumanReviewTask.assigned_to == reviewer_id, HumanReviewTask.status == DECIDED
                )
            ).scalar_one()
            in_progress = session.execute(
                select(func.count()).select_from(HumanReviewTask).where(
                    HumanReviewTask.assigned_to == reviewer_id,
                    HumanReviewTask.status == ReviewStatus.IN_REVIEW.value,
                )
            ).scalar_one()
            golden_total = session.execute(
                select(func.count()).select_from(HumanReviewTask).where(
                    HumanReviewTask.assigned_to == reviewer_id,
                    HumanReviewTask.status == DECIDED,
                    HumanReviewTask.is_golden.is_(True),
                )
            ).scalar_one()
            golden_correct = session.execute(
                select(func.count()).select_from(HumanReviewTask).where(
                    HumanReviewTask.assigned_to == reviewer_id,
                    HumanReviewTask.status == DECIDED,
                    HumanReviewTask.is_golden.is_(True),
                    HumanReviewTask.decision == HumanReviewTask.golden_expected_decision,
                )
            ).scalar_one()
        return {
            "reviewer_id": reviewer_id,
            "total_decided": total_decided,
            "in_progress": in_progress,
            "golden_total": golden_total,
            "golden_correct": golden_correct,
            "golden_accuracy": round(golden_correct / golden_total, 4) if golden_total else None,
            "csam_exposure_shift": self._csam_exposure_count(reviewer_id, settings.shift_window_seconds, now),
            "csam_exposure_week": self._csam_exposure_count(reviewer_id, settings.week_window_seconds, now),
            "decided_last_hour": self._recent_decision_count(reviewer_id, settings.forced_break_window_seconds, now),
            "csam_per_shift_limit": settings.csam_per_shift_limit,
            "forced_break_after": settings.forced_break_after,
        }

    def decide_task(self, task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        decision = str(payload.get("decision", "")).lower()
        if decision not in {PASS, BLOCK}:
            raise ValidationError("裁定只能是 pass 或 block")
        reason = str(payload.get("reason", "")).strip()
        if not reason:
            raise ValidationError("裁定理由不能为空")
        reviewer_id = str(payload.get("reviewer_id", "reviewer_demo")).strip() or "reviewer_demo"
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()

        with self._session_factory.begin() as session:
            task = session.get(HumanReviewTask, task_id, with_for_update=True)
            if task is None:
                raise NotFoundError("任务不存在")
            if task.status == DECIDED:
                raise ConflictError("任务已经完成裁定")
            # 案件锁排他性：他人持有效锁时不得裁定（终态操作也必须尊重锁）。
            lock_expiry = _parse_iso(task.lock_expires_at)
            if lock_expiry is not None and lock_expiry > now and task.assigned_to and task.assigned_to != reviewer_id:
                raise ConflictError(f"案件已被 {task.assigned_to} 锁定，无法裁定")

            task.status = DECIDED
            # 归属给实际裁定人（锁守卫已确保无他人持有效锁）；避免把裁定与曝光计数
            # 错记到过期未清的旧持锁人头上。
            task.assigned_to = reviewer_id
            task.decision = decision
            task.reason = reason
            task.decided_at = timestamp
            # 裁定即结案，释放案件锁。
            task.locked_at = None
            task.lock_expires_at = None
            task.updated_at = timestamp
            content_id = task.content_id

            content = session.get(ContentItem, task.content_id)
            content.status = f"final_{decision}"
            content.final_decision = decision
            content.updated_at = timestamp

            self._append_audit(
                session,
                content_id=task.content_id,
                task_id=task_id,
                actor=reviewer_id,
                action="human_decision_submitted",
                detail={"decision": decision, "reason": reason},
            )

            # Stage 8：黄金题同步评估 + 数据回流样本落库。
            machine = session.execute(
                select(MachineReview).where(MachineReview.content_id == content_id)
            ).scalar_one_or_none()
            machine_rec = machine.recommendation if machine else ""
            policy_version, rule_version = self._decision_versions(machine)
            golden_result = self._evaluate_and_record_golden(
                session, task, decision, timestamp
            )
            self._record_flywheel_sample(
                session, content_id, machine_rec, decision, golden_result,
                policy_version, rule_version, timestamp,
            )
        hub.publish_to_role(
            "senior_reviewer",
            "task_decided",
            {"task_id": task_id, "content_id": content_id, "decision": decision},
        )
        result = {"task_id": task_id, "status": DECIDED, "decision": decision}
        if golden_result is not None:
            result["golden_test_result"] = golden_result
        return result

    @staticmethod
    def _decision_versions(machine: MachineReview | None) -> tuple[str, str]:
        if machine is None or not machine.decision_summary_json:
            return "", ""
        try:
            summary = loads(machine.decision_summary_json)
        except (ValueError, TypeError):
            return "", ""
        return summary.get("policy_version", ""), summary.get("rule_version", "")

    def _evaluate_and_record_golden(
        self, session: Session, task: HumanReviewTask, decision: str, timestamp: str
    ) -> dict[str, Any] | None:
        if not task.is_golden:
            return None
        expected = task.golden_expected_decision
        is_correct = decision == expected
        self._append_audit(
            session, content_id=task.content_id, task_id=task.id, actor="system",
            action="golden_test_evaluated",
            detail={"expected": expected, "actual": decision, "is_correct": is_correct},
        )
        return {
            "is_golden_test": True,
            "is_correct": is_correct,
            "expected_decision": expected,
            "reviewer_decision": decision,
        }

    def _record_flywheel_sample(
        self,
        session: Session,
        content_id: str,
        machine_rec: str,
        human_decision: str,
        golden_result: dict[str, Any] | None,
        policy_version: str,
        rule_version: str,
        timestamp: str,
        *,
        source_override: str | None = None,
        is_correction: bool = False,
    ) -> None:
        if golden_result is not None:
            source_type = FlywheelSource.GOLDEN.value
            error_type = ""
            gate = passes_quality_gate(source_type, golden_result["is_correct"])
        elif source_override is not None:
            source_type = source_override
            error_type = ""
            gate = passes_quality_gate(source_type, None)
        else:
            source_type, error_type = classify_sample(machine_rec, human_decision)
            gate = passes_quality_gate(source_type, None)
        session.add(
            FlywheelSample(
                id=new_id("fw"),
                source_type=source_type,
                content_id=content_id,
                dimension_id="overall",
                machine_decision=machine_rec or "",
                human_decision=human_decision or "",
                final_decision=human_decision or "",
                error_type=error_type,
                policy_version=policy_version,
                rule_version=rule_version,
                quality_gate_passed=gate,
                is_correction=is_correction,
                created_at=timestamp,
            )
        )

    def record_dead_letter(
        self,
        task_name: str,
        celery_task_id: str | None,
        job_id: str | None,
        exc: Exception,
        traceback_str: str = "",
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """记录一条死信（Celery 任务重试耗尽后调用）。"""
        timestamp = now_iso()
        content_id: str | None = None
        with self._session_factory.begin() as session:
            if job_id:
                job = session.get(PipelineJob, job_id)
                content_id = job.content_id if job is not None else None
            session.add(
                DeadLetterTask(
                    task_name=task_name,
                    celery_task_id=celery_task_id,
                    job_id=job_id,
                    content_id=content_id,
                    exception_type=type(exc).__name__,
                    exception_message=str(exc),
                    traceback=traceback_str,
                    retry_count=retry_count,
                    status="pending",
                    created_at=timestamp,
                )
            )
        return {"status": "recorded"}

    def list_dead_letters(self, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        with self._session_factory() as session:
            total = session.execute(select(func.count()).select_from(DeadLetterTask)).scalar_one()
            rows = session.execute(
                select(DeadLetterTask).order_by(DeadLetterTask.id.desc()).limit(limit).offset(offset)
            ).scalars().all()
        items = [self._dead_letter_summary(row) for row in rows]
        next_offset = offset + limit if offset + limit < total else None
        return {"items": items, "total": total, "offset": offset, "limit": limit, "next_offset": next_offset}

    def _dead_letter_summary(self, row: DeadLetterTask) -> dict[str, Any]:
        return {
            "id": row.id,
            "task_name": row.task_name,
            "celery_task_id": row.celery_task_id,
            "job_id": row.job_id,
            "content_id": row.content_id,
            "exception_type": row.exception_type,
            "exception_message": row.exception_message,
            "retry_count": row.retry_count,
            "status": row.status,
            "created_at": row.created_at,
        }

    # --- Stage 7：申诉闭环 ---------------------------------------------------

    def submit_appeal(self, content_id: str, appellant_id: str, reason: str) -> dict[str, Any]:
        """提交申诉。仅对 BLOCK 处置可申诉（申诉通道不可加重到 BLOCK）。"""
        appellant_id = appellant_id.strip() or "appellant"
        reason = reason.strip()
        if not reason:
            raise ValidationError("申诉理由不能为空")
        appeal_id = new_id("appeal")
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        with self._session_factory.begin() as session:
            # 锁内容行：串行化同一内容的并发申诉提交，避免重复活动申诉（会导致恢复连锁重复触发）。
            content = session.get(ContentItem, content_id, with_for_update=True)
            if content is None:
                raise NotFoundError("内容不存在")
            if content.final_decision not in APPEALABLE_DECISIONS:
                raise ConflictError("仅对已 BLOCK 的内容可发起申诉")
            # 一个内容同一时刻只允许一个进行中的申诉。
            open_exists = session.execute(
                select(AppealCase.id).where(
                    AppealCase.content_id == content_id,
                    AppealCase.status.in_([AppealStatus.OPEN.value, AppealStatus.IN_REVIEW.value]),
                )
            ).scalar()
            if open_exists is not None:
                raise ConflictError("该内容已有进行中的申诉")
            # 取原裁定任务，锁定原审核员用于独立性排除。
            task = session.execute(
                select(HumanReviewTask)
                .where(HumanReviewTask.content_id == content_id, HumanReviewTask.status == DECIDED)
                .order_by(HumanReviewTask.decided_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            original_reviewer = task.assigned_to if task else None
            original_task_id = task.id if task else None
            snapshot = {
                "content_status": content.status,
                "final_decision": content.final_decision,
            }
            session.add(
                AppealCase(
                    id=appeal_id,
                    content_id=content_id,
                    appellant_id=appellant_id,
                    appeal_reason=reason,
                    original_decision=content.final_decision,
                    original_reviewer_id=original_reviewer,
                    original_task_id=original_task_id,
                    pre_disposition_snapshot=dumps(snapshot),
                    status=AppealStatus.OPEN.value,
                    assigned_reviewer_id=None,
                    resolved_decision=None,
                    resolution_reason=None,
                    sla_deadline=(now + timedelta(seconds=settings.sla_default_seconds)).isoformat(),
                    created_at=timestamp,
                    updated_at=timestamp,
                    resolved_at=None,
                )
            )
            self._append_audit(
                session, content_id=content_id, task_id=None, actor=appellant_id,
                action="appeal_submitted",
                detail={"appeal_id": appeal_id, "original_decision": content.final_decision},
            )
        return {"appeal_id": appeal_id, "status": AppealStatus.OPEN.value}

    def list_appeals(self, status: str | None = None, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 100)
        with self._session_factory() as session:
            stmt = select(AppealCase)
            count_stmt = select(func.count()).select_from(AppealCase)
            if status:
                stmt = stmt.where(AppealCase.status == status)
                count_stmt = count_stmt.where(AppealCase.status == status)
            total = session.execute(count_stmt).scalar_one()
            rows = session.execute(
                stmt.order_by(AppealCase.created_at.asc()).limit(limit).offset(offset)
            ).scalars().all()
        return {"items": [self._appeal_summary(r) for r in rows], "total": total, "offset": offset, "limit": limit}

    def get_appeal(self, appeal_id: str) -> dict[str, Any]:
        with self._session_factory() as session:
            appeal = session.get(AppealCase, appeal_id)
            if appeal is None:
                raise NotFoundError("申诉不存在")
            return self._appeal_summary(appeal)

    def assign_appeal(self, appeal_id: str, reviewer_id: str) -> dict[str, Any]:
        """二审领取。独立性：二审员不能是原审核员。open→in_review。"""
        reviewer_id = reviewer_id.strip()
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            appeal = session.get(AppealCase, appeal_id, with_for_update=True)
            if appeal is None:
                raise NotFoundError("申诉不存在")
            if not appeal_can_transition(appeal.status, AppealStatus.IN_REVIEW.value):
                raise ConflictError(f"申诉状态 {appeal.status} 不可领取")
            if appeal.original_reviewer_id and reviewer_id == appeal.original_reviewer_id:
                raise ConflictError("独立性约束：二审员不能是原审核员")
            if reviewer_id == appeal.appellant_id:
                raise ConflictError("独立性约束：申诉人不能自审自批")
            appeal.assigned_reviewer_id = reviewer_id
            appeal.status = AppealStatus.IN_REVIEW.value
            appeal.updated_at = timestamp
            self._append_audit(
                session, content_id=appeal.content_id, task_id=None, actor=reviewer_id,
                action="appeal_claimed", detail={"appeal_id": appeal_id},
            )
        return self.get_appeal(appeal_id)

    def decide_appeal(
        self, appeal_id: str, reviewer_id: str, outcome: str, reason: str
    ) -> dict[str, Any]:
        """二审裁决。outcome ∈ {overturn, reject}。改判触发恢复连锁四链。"""
        reviewer_id = reviewer_id.strip()
        outcome = str(outcome).lower().strip()
        reason = str(reason).strip()
        if outcome not in {"overturn", "reject"}:
            raise ValidationError("outcome 只能是 overturn 或 reject")
        if not reason:
            raise ValidationError("裁决理由不能为空")
        target_status = (
            AppealStatus.OVERTURNED.value if outcome == "overturn" else AppealStatus.REJECTED.value
        )
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        recovery: dict[str, Any] = {}
        content_id: str | None = None
        with self._session_factory.begin() as session:
            appeal = session.get(AppealCase, appeal_id, with_for_update=True)
            if appeal is None:
                raise NotFoundError("申诉不存在")
            if not appeal_can_transition(appeal.status, target_status):
                raise ConflictError(f"申诉状态 {appeal.status} 不可裁决为 {target_status}")
            # 独立性：二审员必须与原审核员、申诉人都不同，且应为领取该申诉的人。
            if appeal.original_reviewer_id and reviewer_id == appeal.original_reviewer_id:
                raise ConflictError("独立性约束：二审员不能是原审核员")
            if reviewer_id == appeal.appellant_id:
                raise ConflictError("独立性约束：申诉人不能自审自批")
            if appeal.assigned_reviewer_id and appeal.assigned_reviewer_id != reviewer_id:
                raise ConflictError("只有领取该申诉的二审员可裁决")
            content_id = appeal.content_id
            appeal.status = target_status
            appeal.resolution_reason = reason
            appeal.updated_at = timestamp
            appeal.resolved_at = timestamp

            if outcome == "overturn":
                # 硬约束：不可加重 —— 只允许 block -> pass。
                new_decision = OVERTURN_TARGET.get(appeal.original_decision)
                if new_decision is None:
                    raise ConflictError("该原处置不支持在申诉通道内改判（不可加重处置）")
                appeal.resolved_decision = new_decision
                content = session.get(ContentItem, content_id)
                # 恢复连锁 ①恢复可见性：内容处置回滚到较轻处置。
                content.final_decision = new_decision
                content.status = f"final_{new_decision}"
                content.updated_at = timestamp
                self._append_audit(
                    session, content_id=content_id, task_id=None, actor=reviewer_id,
                    action="appeal_overturned",
                    detail={"appeal_id": appeal_id, "from": appeal.original_decision, "to": new_decision, "reason": reason},
                )
                # 恢复连锁 ②账号处罚回滚 ③质检负反馈 ④改判样本回流（Stage 8 消费）。
                for chain_action, chain_detail in (
                    ("visibility_restored", {"final_decision": new_decision}),
                    ("penalty_rolled_back", {"creator_id": content.creator_id}),
                    ("qa_negative_feedback", {"original_reviewer_id": appeal.original_reviewer_id}),
                    ("correction_sample_queued", {"content_id": content_id, "corrected_to": new_decision}),
                ):
                    self._append_audit(
                        session, content_id=content_id, task_id=None, actor="system",
                        action=chain_action, detail={"appeal_id": appeal_id, **chain_detail},
                    )
                # 恢复连锁 ④改判样本回流：落一条 correction 样本供数据飞轮消费。
                machine = session.execute(
                    select(MachineReview).where(MachineReview.content_id == content_id)
                ).scalar_one_or_none()
                policy_version, rule_version = self._decision_versions(machine)
                self._record_flywheel_sample(
                    session, content_id, machine.recommendation if machine else "",
                    new_decision, None, policy_version, rule_version, timestamp,
                    source_override="correction", is_correction=True,
                )
                recovery = {
                    "visibility_restored": True,
                    "penalty_rolled_back": True,
                    "qa_negative_feedback": True,
                    "correction_sample_queued": True,
                    "new_decision": new_decision,
                }
            else:
                appeal.resolved_decision = appeal.original_decision  # 维持
                self._append_audit(
                    session, content_id=content_id, task_id=None, actor=reviewer_id,
                    action="appeal_rejected", detail={"appeal_id": appeal_id, "reason": reason},
                )
        # 恢复连锁事件广播（异步最终一致的占位：这里直接推 WS）。
        if outcome == "overturn":
            hub.publish_to_role("compliance_auditor", "appeal_overturned", {"appeal_id": appeal_id, "content_id": content_id})
        return {"appeal_id": appeal_id, "status": target_status, "outcome": outcome, "recovery_chain": recovery}

    def _appeal_summary(self, appeal: AppealCase) -> dict[str, Any]:
        return {
            "appeal_id": appeal.id,
            "content_id": appeal.content_id,
            "appellant_id": appeal.appellant_id,
            "appeal_reason": appeal.appeal_reason,
            "original_decision": appeal.original_decision,
            "original_reviewer_id": appeal.original_reviewer_id,
            "status": appeal.status,
            "assigned_reviewer_id": appeal.assigned_reviewer_id,
            "resolved_decision": appeal.resolved_decision,
            "resolution_reason": appeal.resolution_reason,
            "sla_deadline": appeal.sla_deadline,
            "created_at": appeal.created_at,
            "resolved_at": appeal.resolved_at,
        }

    # --- Stage 4：策略注册表 + 决策引擎 --------------------------------------

    def reload_strategies(self) -> dict[str, Any]:
        """从 dimension_registry 表热加载策略配置（copy-on-write 原子替换）。"""
        with self._session_factory() as session:
            count = self._registry.reload(session)
        return {"status": "reloaded", "loaded": count}

    def _active_policy_version(self, session: Session) -> str:
        row = session.execute(
            select(PolicyVersion.version_id)
            .where(PolicyVersion.status == "active")
            .order_by(PolicyVersion.activated_at.desc())
            .limit(1)
        ).first()
        return row[0] if row else "pv_0"

    def _seed_decision_registry(self) -> None:
        """首次启动时落地默认维度 + 默认策略版本（幂等：非空则跳过）。"""
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            has_dims = session.execute(
                select(func.count()).select_from(DimensionRegistry)
            ).scalar_one()
            if not has_dims:
                for spec in _DEFAULT_DIMENSIONS:
                    session.add(
                        DimensionRegistry(
                            dimension_id=spec["dimension_id"],
                            dimension_name=spec["dimension_name"],
                            dimension_axis=spec["dimension_axis"],
                            enabled=True,
                            llm_review_enabled=spec.get("llm_review_enabled", True),
                            auto_block_threshold=spec.get("auto_block_threshold", 0.90),
                            human_review_threshold=spec.get("human_review_threshold", 0.50),
                            prompt_template_id=spec.get("prompt_template_id", ""),
                            severity_tiers=dumps(spec.get("severity_tiers", {})),
                            jurisdiction_overrides=dumps({}),
                            sor_template_id=spec.get("sor_template_id", ""),
                            status=DimensionStatus.ACTIVE.value,
                            version=1,
                            created_by="system",
                            approved_by="system",
                            created_at=timestamp,
                            updated_at=timestamp,
                        )
                    )
            has_policy = session.execute(
                select(func.count()).select_from(PolicyVersion)
            ).scalar_one()
            if not has_policy:
                session.add(
                    PolicyVersion(
                        version_id="pv_1",
                        title="默认策略版本",
                        status="active",
                        notes="系统初始化",
                        created_by="system",
                        created_at=timestamp,
                        activated_at=timestamp,
                    )
                )

    def list_dimensions(self) -> dict[str, Any]:
        with self._session_factory() as session:
            rows = session.execute(
                select(DimensionRegistry).order_by(DimensionRegistry.dimension_id.asc())
            ).scalars().all()
        return {"items": [self._dimension_summary(r) for r in rows]}

    def create_dimension(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        dimension_id = str(payload.get("dimension_id", "")).strip()
        dimension_name = str(payload.get("dimension_name", "")).strip()
        dimension_axis = str(payload.get("dimension_axis", "safety")).strip()
        if not dimension_id:
            raise ValidationError("dimension_id 不能为空")
        if not dimension_name:
            raise ValidationError("dimension_name 不能为空")
        if dimension_axis not in {"safety", "quality", "business"}:
            raise ValidationError("dimension_axis 只能是 safety / quality / business")
        if dimension_id not in StrategyRegistry.registered_dimension_ids():
            raise ValidationError(
                f"未找到 {dimension_id} 的策略实现类，请先在代码中用 @StrategyRegistry.register 注册"
            )
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            exists = session.execute(
                select(DimensionRegistry.id).where(DimensionRegistry.dimension_id == dimension_id)
            ).scalar()
            if exists is not None:
                raise ConflictError("该维度已存在")
            session.add(
                DimensionRegistry(
                    dimension_id=dimension_id,
                    dimension_name=dimension_name,
                    dimension_axis=dimension_axis,
                    enabled=bool(payload.get("enabled", False)),
                    llm_review_enabled=bool(payload.get("llm_review_enabled", True)),
                    auto_block_threshold=float(payload.get("auto_block_threshold", 0.90)),
                    human_review_threshold=float(payload.get("human_review_threshold", 0.50)),
                    prompt_template_id=str(payload.get("prompt_template_id", "")),
                    severity_tiers=dumps(payload.get("severity_tiers", {})),
                    jurisdiction_overrides=dumps(payload.get("jurisdiction_overrides", {})),
                    sor_template_id=str(payload.get("sor_template_id", "")),
                    status=DimensionStatus.DRAFT.value,  # 新维度一律从 draft 起
                    version=1,
                    created_by=actor,
                    approved_by=None,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            self._append_audit(
                session, content_id=None, task_id=None, actor=actor,
                action="dimension_created", detail={"dimension_id": dimension_id, "status": "draft"},
            )
        self.reload_strategies()
        return {"dimension_id": dimension_id, "status": DimensionStatus.DRAFT.value}

    # 治理敏感字段：改动它们等于改变一个维度的判罚强度，必须重新走 Checker 审批。
    _SENSITIVE_DIMENSION_FIELDS = {
        "enabled", "llm_review_enabled", "auto_block_threshold", "human_review_threshold",
    }

    def update_dimension(self, dimension_id: str, patch: dict[str, Any], actor: str) -> dict[str, Any]:
        timestamp = now_iso()
        allowed = {
            "dimension_name", "enabled", "llm_review_enabled", "auto_block_threshold",
            "human_review_threshold", "prompt_template_id", "sor_template_id",
        }
        touches_sensitive = bool(self._SENSITIVE_DIMENSION_FIELDS & set(patch.keys()))
        with self._session_factory.begin() as session:
            row = session.get(DimensionRegistry, self._dimension_pk(session, dimension_id))
            if row is None:
                raise NotFoundError("维度不存在")
            # 独立性/四眼原则：active 维度的治理配置被冻结，必须先转 shadow/draft 再改，
            # 否则单人即可在生产悄悄削弱一个已上线的安全维度（绕过 Maker-Checker）。
            if row.status == DimensionStatus.ACTIVE.value and touches_sensitive:
                raise ConflictError("active 维度的治理配置已冻结，请先 transition 到 shadow 再修改")
            changed: dict[str, Any] = {}
            for key, value in patch.items():
                if key not in allowed:
                    continue
                setattr(row, key, value)
                changed[key] = value
            if "auto_block_threshold" in changed and not (0 <= float(row.auto_block_threshold) <= 1):
                raise ValidationError("auto_block_threshold 必须在 [0,1]")
            if "human_review_threshold" in changed and not (0 <= float(row.human_review_threshold) <= 1):
                raise ValidationError("human_review_threshold 必须在 [0,1]")
            # 敏感字段一旦改动，作废旧审批 —— 重新上线到 active 前需 Checker 再次签核。
            if touches_sensitive:
                row.approved_by = None
            row.version = int(row.version) + 1
            row.updated_at = timestamp
            self._append_audit(
                session, content_id=None, task_id=None, actor=actor,
                action="dimension_updated",
                detail={"dimension_id": dimension_id, "changed": changed, "approval_reset": touches_sensitive},
            )
        self.reload_strategies()
        return {"dimension_id": dimension_id, "changed": True}

    def transition_dimension(self, dimension_id: str, target_status: str, actor: str) -> dict[str, Any]:
        target_status = str(target_status).strip()
        if target_status not in {s.value for s in DimensionStatus}:
            raise ValidationError(f"非法目标状态: {target_status}")
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            row = session.get(DimensionRegistry, self._dimension_pk(session, dimension_id))
            if row is None:
                raise NotFoundError("维度不存在")
            current = row.status
            if target_status not in VALID_STATUS_TRANSITIONS.get(current, set()):
                raise ConflictError(f"非法状态转移: {current} -> {target_status}")
            # active 需 Maker-Checker：进 active 要求已有 approved_by。
            if target_status == DimensionStatus.ACTIVE.value and not row.approved_by:
                raise ConflictError("上线到 active 前需先经审批人签核 (approve)")
            # 离开 active（active->shadow 回退）作废旧审批：再次上线必须重新签核，
            # 防止基于陈旧批准反复 active<->shadow 横跳。
            if row.status == DimensionStatus.ACTIVE.value and target_status != DimensionStatus.ACTIVE.value:
                row.approved_by = None
            row.status = target_status
            row.updated_at = timestamp
            self._append_audit(
                session, content_id=None, task_id=None, actor=actor,
                action="dimension_transitioned",
                detail={"dimension_id": dimension_id, "from": current, "to": target_status},
            )
        self.reload_strategies()
        return {"dimension_id": dimension_id, "status": target_status}

    def approve_dimension(self, dimension_id: str, actor: str) -> dict[str, Any]:
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            row = session.get(DimensionRegistry, self._dimension_pk(session, dimension_id))
            if row is None:
                raise NotFoundError("维度不存在")
            if row.created_by == actor:
                raise ConflictError("独立性约束：审批人不能是创建人 (Maker-Checker)")
            row.approved_by = actor
            row.updated_at = timestamp
            self._append_audit(
                session, content_id=None, task_id=None, actor=actor,
                action="dimension_approved", detail={"dimension_id": dimension_id},
            )
        return {"dimension_id": dimension_id, "approved_by": actor}

    def _dimension_pk(self, session: Session, dimension_id: str) -> Any:
        return session.execute(
            select(DimensionRegistry.id).where(DimensionRegistry.dimension_id == dimension_id)
        ).scalar()

    def _dimension_summary(self, row: DimensionRegistry) -> dict[str, Any]:
        return {
            "dimension_id": row.dimension_id,
            "dimension_name": row.dimension_name,
            "dimension_axis": row.dimension_axis,
            "enabled": row.enabled,
            "llm_review_enabled": row.llm_review_enabled,
            "auto_block_threshold": row.auto_block_threshold,
            "human_review_threshold": row.human_review_threshold,
            "status": row.status,
            "version": row.version,
            "created_by": row.created_by,
            "approved_by": row.approved_by,
            "has_strategy_class": row.dimension_id in StrategyRegistry.registered_dimension_ids(),
            "updated_at": row.updated_at,
        }

    def list_policy_versions(self) -> dict[str, Any]:
        with self._session_factory() as session:
            rows = session.execute(
                select(PolicyVersion).order_by(PolicyVersion.id.desc())
            ).scalars().all()
        return {
            "items": [
                {
                    "version_id": r.version_id,
                    "title": r.title,
                    "status": r.status,
                    "notes": r.notes,
                    "created_by": r.created_by,
                    "created_at": r.created_at,
                    "activated_at": r.activated_at,
                }
                for r in rows
            ]
        }

    def create_policy_version(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        title = str(payload.get("title", "")).strip()
        if not title:
            raise ValidationError("title 不能为空")
        version_id = new_id("pv")
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            session.add(
                PolicyVersion(
                    version_id=version_id,
                    title=title,
                    status="draft",
                    notes=str(payload.get("notes", "")),
                    created_by=actor,
                    created_at=timestamp,
                    activated_at=None,
                )
            )
            self._append_audit(
                session, content_id=None, task_id=None, actor=actor,
                action="policy_version_created", detail={"version_id": version_id},
            )
        return {"version_id": version_id, "status": "draft"}

    def activate_policy_version(self, version_id: str, actor: str) -> dict[str, Any]:
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            row = session.execute(
                select(PolicyVersion).where(PolicyVersion.version_id == version_id)
            ).scalar_one_or_none()
            if row is None:
                raise NotFoundError("策略版本不存在")
            # 归档当前 active，激活目标版本。
            current = session.execute(
                select(PolicyVersion).where(PolicyVersion.status == "active")
            ).scalars().all()
            for active in current:
                if active.version_id != version_id:
                    active.status = "archived"
            row.status = "active"
            row.activated_at = timestamp
            self._append_audit(
                session, content_id=None, task_id=None, actor=actor,
                action="policy_version_activated", detail={"version_id": version_id},
            )
        return {"version_id": version_id, "status": "active"}

    # --- Stage 9：可观测性 + 审计完整性 + SoR --------------------------------

    def verify_audit_integrity(self) -> dict[str, Any]:
        """重算审计哈希链，检测篡改 / 断链。对齐设计 §12.3。"""
        prev = "GENESIS"
        checked = 0
        with self._session_factory() as session:
            rows = session.execute(select(AuditLog).order_by(AuditLog.id.asc())).scalars().all()
        for row in rows:
            checked += 1
            payload = dumps(
                {
                    "content_id": row.content_id,
                    "task_id": row.task_id,
                    "actor": row.actor,
                    "action": row.action,
                    "detail": loads(row.detail_json),
                    "prev_hash": row.prev_hash,
                    "created_at": row.created_at,
                }
            )
            recomputed = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if row.prev_hash != prev:
                return {"valid": False, "checked": checked,
                        "break_point": {"id": row.id, "reason": "chain_linkage_broken"}}
            if recomputed != row.entry_hash:
                return {"valid": False, "checked": checked,
                        "break_point": {"id": row.id, "reason": "entry_hash_mismatch"}}
            prev = row.entry_hash
        return {"valid": True, "checked": checked, "break_point": None}

    def metrics_snapshot(self) -> dict[str, Any]:
        """业务指标快照（供 Prometheus 渲染）。对齐设计 §9.4。"""
        now_str = now_iso()
        with self._session_factory() as session:
            decisions = {
                (fd or "none"): c
                for fd, c in session.execute(
                    select(ContentItem.final_decision, func.count()).group_by(ContentItem.final_decision)
                ).all()
            }
            jobs = {
                status: c
                for status, c in session.execute(
                    select(PipelineJob.status, func.count()).group_by(PipelineJob.status)
                ).all()
            }
            queue_size = session.execute(
                select(func.count()).select_from(HumanReviewTask).where(HumanReviewTask.status == PENDING)
            ).scalar_one()
            sla_violations = session.execute(
                select(func.count()).select_from(HumanReviewTask).where(
                    HumanReviewTask.status != DECIDED,
                    HumanReviewTask.sla_deadline.isnot(None),
                    HumanReviewTask.sla_deadline < now_str,
                )
            ).scalar_one()
            dead_letters = session.execute(select(func.count()).select_from(DeadLetterTask)).scalar_one()
            flywheel = session.execute(select(func.count()).select_from(FlywheelSample)).scalar_one()
            appeals_total = session.execute(select(func.count()).select_from(AppealCase)).scalar_one()
            overturned = session.execute(
                select(func.count()).select_from(AppealCase).where(
                    AppealCase.status == AppealStatus.OVERTURNED.value
                )
            ).scalar_one()
            golden_total = session.execute(
                select(func.count()).select_from(FlywheelSample).where(
                    FlywheelSample.source_type == FlywheelSource.GOLDEN.value
                )
            ).scalar_one()
            golden_correct = session.execute(
                select(func.count()).select_from(FlywheelSample).where(
                    FlywheelSample.source_type == FlywheelSource.GOLDEN.value,
                    FlywheelSample.quality_gate_passed.is_(True),
                )
            ).scalar_one()
        return {
            "pipeline_decision_total": decisions,
            "pipeline_jobs": jobs,
            "human_review_queue_size": queue_size,
            "human_review_sla_violations_total": sla_violations,
            "dead_letter_tasks_total": dead_letters,
            "flywheel_samples_total": flywheel,
            "appeal_overturn_rate": round(overturned / appeals_total, 4) if appeals_total else 0.0,
            "golden_test_accuracy": round(golden_correct / golden_total, 4) if golden_total else 0.0,
        }

    def generate_sor(self, content_id: str) -> dict[str, Any]:
        """生成对外 SoR（与内部理由物理分离，不含内部笔记/阈值）。"""
        with self._session_factory() as session:
            content = session.get(ContentItem, content_id)
            if content is None:
                raise NotFoundError("内容不存在")
            machine = session.execute(
                select(MachineReview).where(MachineReview.content_id == content_id)
            ).scalar_one_or_none()
        decision = content.final_decision or "pending"
        triggered_dims: list[str] = []
        if machine is not None:
            for verdict in loads(machine.verdicts_json):
                if verdict.get("decision") == "VIOLATION":
                    triggered_dims.append(verdict.get("dimension_id", ""))
        sor_text = render_sor(decision, content.title, triggered_dims)
        return {
            "content_id": content_id,
            "decision": decision,
            "sor_text": sor_text,
            "template_id": SOR_TEMPLATE_ID,
            "triggered_dimensions": triggered_dims,
            "contains_internal_reason": False,
        }

    # --- Stage 8：质检 + 数据回流 --------------------------------------------

    def mark_golden(self, task_id: str, expected_decision: str) -> dict[str, Any]:
        """把一个待审任务注入为黄金题（已知答案，用于校准审核员）。"""
        expected_decision = str(expected_decision).lower().strip()
        if expected_decision not in {PASS, BLOCK}:
            raise ValidationError("黄金题答案只能是 pass 或 block")
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            task = session.get(HumanReviewTask, task_id, with_for_update=True)
            if task is None:
                raise NotFoundError("任务不存在")
            if task.status == DECIDED:
                raise ConflictError("已裁定任务不能再注入黄金题")
            task.is_golden = True
            task.golden_expected_decision = expected_decision
            task.updated_at = timestamp
        return {"task_id": task_id, "is_golden": True, "expected_decision": expected_decision}

    def list_flywheel_samples(
        self, source_type: str | None = None, only_passed: bool = False,
        offset: int = 0, limit: int = 50,
    ) -> dict[str, Any]:
        offset = max(0, offset)
        limit = min(max(1, limit), 500)
        with self._session_factory() as session:
            stmt = select(FlywheelSample)
            count_stmt = select(func.count()).select_from(FlywheelSample)
            if source_type:
                stmt = stmt.where(FlywheelSample.source_type == source_type)
                count_stmt = count_stmt.where(FlywheelSample.source_type == source_type)
            if only_passed:
                stmt = stmt.where(FlywheelSample.quality_gate_passed.is_(True))
                count_stmt = count_stmt.where(FlywheelSample.quality_gate_passed.is_(True))
            total = session.execute(count_stmt).scalar_one()
            rows = session.execute(
                stmt.order_by(FlywheelSample.created_at.asc()).limit(limit).offset(offset)
            ).scalars().all()
        return {"items": [self._flywheel_summary(r) for r in rows], "total": total, "offset": offset, "limit": limit}

    def export_flywheel_jsonl(self, only_passed: bool = True) -> str:
        """导出回流样本为 JSONL（每行一个 JSON 对象）。默认只导出过质量门的样本。"""
        with self._session_factory() as session:
            stmt = select(FlywheelSample).order_by(FlywheelSample.created_at.asc())
            if only_passed:
                stmt = stmt.where(FlywheelSample.quality_gate_passed.is_(True))
            rows = session.execute(stmt).scalars().all()
        return "\n".join(dumps(self._flywheel_summary(r)) for r in rows)

    def quality_summary(self) -> dict[str, Any]:
        with self._session_factory() as session:
            source_counts = {
                src: cnt
                for src, cnt in session.execute(
                    select(FlywheelSample.source_type, func.count()).group_by(FlywheelSample.source_type)
                ).all()
            }
            total_samples = session.execute(select(func.count()).select_from(FlywheelSample)).scalar_one()
            passed_samples = session.execute(
                select(func.count()).select_from(FlywheelSample).where(
                    FlywheelSample.quality_gate_passed.is_(True)
                )
            ).scalar_one()
            golden_total = source_counts.get(FlywheelSource.GOLDEN.value, 0)
            golden_correct = session.execute(
                select(func.count()).select_from(FlywheelSample).where(
                    FlywheelSample.source_type == FlywheelSource.GOLDEN.value,
                    FlywheelSample.quality_gate_passed.is_(True),
                )
            ).scalar_one()
            disagreements = source_counts.get(FlywheelSource.DISAGREEMENT.value, 0)
            appeals_total = session.execute(select(func.count()).select_from(AppealCase)).scalar_one()
            overturned = session.execute(
                select(func.count()).select_from(AppealCase).where(
                    AppealCase.status == AppealStatus.OVERTURNED.value
                )
            ).scalar_one()
        # 推翻率分母只取经 classify_sample 分类的样本（ground_truth + disagreement），
        # 与分子口径一致 —— 排除 golden/correction，避免系统性偏低。
        classified = disagreements + source_counts.get(FlywheelSource.GROUND_TRUTH.value, 0)
        override_rate = round(disagreements / classified, 4) if classified else 0.0
        overturn_rate = round(overturned / appeals_total, 4) if appeals_total else 0.0
        golden_accuracy = round(golden_correct / golden_total, 4) if golden_total else None
        return {
            "flywheel_by_source": source_counts,
            "total_samples": total_samples,
            "passed_quality_gate": passed_samples,
            "golden": {"total": golden_total, "correct": golden_correct, "accuracy": golden_accuracy},
            "human_override_rate": override_rate,
            "appeal_overturn_rate": overturn_rate,
            "irr": self.compute_irr(),
        }

    def compute_irr(self) -> dict[str, Any]:
        """评估者间信度：按 content 汇总多方裁定（人审 + 申诉改判）计算 Fleiss' Kappa。"""
        ratings_by_content: dict[str, list[str]] = {}
        with self._session_factory() as session:
            for content_id, decision in session.execute(
                select(HumanReviewTask.content_id, HumanReviewTask.decision).where(
                    HumanReviewTask.status == DECIDED, HumanReviewTask.decision.isnot(None)
                )
            ).all():
                ratings_by_content.setdefault(content_id, []).append(decision)
            for content_id, resolved in session.execute(
                select(AppealCase.content_id, AppealCase.resolved_decision).where(
                    AppealCase.resolved_decision.isnot(None)
                )
            ).all():
                ratings_by_content.setdefault(content_id, []).append(resolved)
        return fleiss_kappa(list(ratings_by_content.values()), categories=[PASS, BLOCK])

    def _flywheel_summary(self, row: FlywheelSample) -> dict[str, Any]:
        return {
            "sample_id": row.id,
            "source_type": row.source_type,
            "content_id": row.content_id,
            "dimension_id": row.dimension_id,
            "machine_decision": row.machine_decision,
            "human_decision": row.human_decision,
            "final_decision": row.final_decision,
            "error_type": row.error_type,
            "policy_version": row.policy_version,
            "rule_version": row.rule_version,
            "quality_gate_passed": row.quality_gate_passed,
            "is_correction": row.is_correction,
            "created_at": row.created_at,
        }

    # --- 用户 / 认证 ---------------------------------------------------------

    def register_user(self, username: str, password: str, roles: list[str]) -> dict[str, Any]:
        username = username.strip()
        if not username:
            raise ValidationError("用户名不能为空")
        if not password:
            raise ValidationError("密码不能为空")
        if not roles:
            raise ValidationError("角色不能为空")
        user_id = new_id("user")
        timestamp = now_iso()
        with self._session_factory.begin() as session:
            exists = session.execute(
                select(User.id).where(User.username == username)
            ).scalar()
            if exists is not None:
                raise ConflictError("用户名已存在")
            session.add(
                User(
                    id=user_id,
                    username=username,
                    password_hash=hash_password(password),
                    roles_json=dumps(roles),
                    is_active=True,
                    created_at=timestamp,
                )
            )
        return {"user_id": user_id, "username": username, "roles": roles}

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            user = session.execute(
                select(User).where(User.username == username.strip())
            ).scalar_one_or_none()
            if user is None or not user.is_active:
                return None
            if not verify_password(password, user.password_hash):
                return None
            return {"user_id": user.id, "username": user.username, "roles": loads(user.roles_json)}

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            user = session.get(User, user_id)
            if user is None or not user.is_active:
                return None
            return {"user_id": user.id, "username": user.username, "roles": loads(user.roles_json)}

    def seed_users(self) -> dict[str, Any]:
        """创建一组演示账号（幂等：已存在则跳过）。密码统一为 demo-pass。"""
        demo = [
            ("reviewer_demo", ["reviewer_t1"]),
            ("senior_demo", ["senior_reviewer"]),
            ("ops_demo", ["ops_admin"]),
            ("policy_pm_demo", ["policy_pm"]),
            ("policy_approver_demo", ["policy_approver"]),
            ("appeal_demo", ["appeal_reviewer"]),
            ("qa_demo", ["qa_reviewer"]),
        ]
        created: list[dict[str, Any]] = []
        for username, roles in demo:
            if self.authenticate(username, "demo-pass") is not None:
                continue
            try:
                created.append(self.register_user(username, "demo-pass", roles))
            except ConflictError:
                continue
        return {"password": "demo-pass", "users": created}

    def get_audit(self, content_id: str | None = None) -> dict[str, Any]:
        with self._session_factory() as session:
            stmt = select(AuditLog).order_by(AuditLog.id.asc())
            if content_id:
                stmt = stmt.where(AuditLog.content_id == content_id)
            else:
                stmt = stmt.limit(100)
            rows = session.execute(stmt).scalars().all()
        return {"items": [self._audit_row(self._audit_orm_to_row(row)) for row in rows]}

    def summary(self) -> dict[str, Any]:
        with self._session_factory() as session:
            counts = {
                status: count
                for status, count in session.execute(
                    select(HumanReviewTask.status, func.count()).group_by(HumanReviewTask.status)
                ).all()
            }
            decisions = {
                (final_decision or "none"): count
                for final_decision, count in session.execute(
                    select(ContentItem.final_decision, func.count()).group_by(ContentItem.final_decision)
                ).all()
            }
            total = session.execute(select(func.count()).select_from(ContentItem)).scalar_one()
            pipeline = {
                status: count
                for status, count in session.execute(
                    select(PipelineJob.status, func.count()).group_by(PipelineJob.status)
                ).all()
            }
        return {
            "tenant_id": settings.tenant_id,
            "jurisdiction": settings.jurisdiction,
            "total_content": total,
            "queue": {"pending": counts.get(PENDING, 0), "decided": counts.get(DECIDED, 0)},
            "pipeline": {
                "queued": pipeline.get(JOB_QUEUED, 0),
                "processing": pipeline.get(JOB_PROCESSING, 0),
                "completed": pipeline.get(JOB_COMPLETED, 0),
                "failed": pipeline.get(JOB_FAILED, 0),
            },
            "decisions": {"pass": decisions.get(PASS, 0), "block": decisions.get(BLOCK, 0)},
            "feature_flags": feature_flags(),
        }

    def _build_evidence_package(
        self,
        evidence_id: str,
        content_id: str,
        title: str,
        description: str,
        creator_id: str,
        poi: str,
        video_url: str,
        text: str,
    ) -> dict[str, Any]:
        risky_terms = ["gambling", "bet", "bonus", "qr", "scan", "violence", "weapon", "hate"]
        matched = [term for term in risky_terms if term in text]
        extracted = EvidenceExtractor().extract(
            video_url=video_url,
            content_id=content_id,
            title=title,
            description=description,
        )
        return {
            "ep_id": evidence_id,
            "schema_version": "mvp-1.0",
            "content_id": content_id,
            "tenant_id": settings.tenant_id,
            "jurisdiction": settings.jurisdiction,
            "media_asset": extracted["media_asset"],
            "video_meta": extracted["video_meta"],
            "frames": extracted["frames"] or [
                {"frame_id": "frame_001", "timestamp_ms": 0, "thumbnail": "", "caption": title},
                {"frame_id": "frame_002", "timestamp_ms": 45000, "thumbnail": "", "caption": description[:80]},
            ],
            "asr_transcript": extracted["asr_transcript"],
            "ocr_results": extracted["ocr_results"],
            "object_detections": extracted["object_detections"],
            "scene_tags": extracted["scene_tags"],
            "metadata": {"title": title, "description": description, "creator_id": creator_id, "poi": poi},
            "pre_filter_results": {
                "rule_hits": [{"rule_id": f"keyword:{term}", "term": term} for term in matched],
                "cloud_api_hits": [],
                "dedup_reuse": None,
                "skip_llm_review": False,
                "skip_reason": None,
            },
            "llm_verdicts": [],
            "modality_model_invocations": extracted["modality_model_invocations"],
            "modality_availability": extracted["modality_availability"],
            "extraction_notes": extracted["extraction_notes"],
            "truncated_modalities": [],
            "access_policy": {"readable_roles": ["reviewer", "admin"], "retention_days": 90},
            "token_budget_used": len(text.split()),
            "token_budget_limit": 8000,
        }

    def _run_machine_review(
        self,
        review_id: str,
        content_id: str,
        evidence: dict[str, Any],
        text: str,
        policy_version: str,
    ) -> dict[str, Any]:
        """Stage 4：走决策引擎 —— 多维度并行执行 + 规则引擎取严链聚合。"""
        evidence["policy_version"] = policy_version
        summary = self._decision_engine.run(
            evidence,
            policy_version=policy_version,
            rule_version=policy_version,
            jurisdiction=str(evidence.get("jurisdiction") or settings.jurisdiction),
        )
        verdict_dicts = [v.to_dict() for v in summary.dimension_verdicts]
        summary_dict = summary.to_dict()
        summary_dict["dimension_verdicts"] = verdict_dicts

        evidence["llm_verdicts"] = verdict_dicts
        evidence["decision_summary"] = summary_dict
        evidence["machine_review_source"] = "decision_engine"

        source = "llm" if any(v["source"] == "llm" for v in verdict_dicts) else "local_rules"
        evidence["machine_review_llm_used"] = source == "llm"

        return {
            "id": review_id,
            "content_id": content_id,
            "recommendation": summary.machine_recommendation,
            "confidence": summary.risk_score,
            "rationale": self._summary_rationale(summary),
            "verdicts": verdict_dicts,
            "decision_summary": summary_dict,
        }

    @staticmethod
    def _summary_rationale(summary: Any) -> str:
        triggered = summary.triggered_rules
        if not triggered:
            return "各审核维度均未命中违规，机审建议放行。"
        return (
            f"机审最终决策 {summary.final_decision.value}（风险分 {summary.risk_score:.2f}）；"
            f"命中规则: {', '.join(triggered)}。"
        )

    def _append_audit(
        self,
        session: Session,
        content_id: str | None,
        task_id: str | None,
        actor: str,
        action: str,
        detail: dict[str, Any],
    ) -> None:
        # autoflush 会在这条 SELECT 前把同一事务里已 add 的前序审计行刷入，
        # 因此拿到的始终是最新一条 —— 哈希链在事务内也能正确串联。
        prev_hash = session.execute(
            select(AuditLog.entry_hash).order_by(AuditLog.id.desc()).limit(1)
        ).scalar()
        prev_hash = prev_hash if prev_hash else "GENESIS"
        timestamp = now_iso()
        payload = dumps(
            {
                "content_id": content_id,
                "task_id": task_id,
                "actor": actor,
                "action": action,
                "detail": detail,
                "prev_hash": prev_hash,
                "created_at": timestamp,
            }
        )
        entry_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        session.add(
            AuditLog(
                content_id=content_id,
                task_id=task_id,
                actor=actor,
                action=action,
                detail_json=dumps(detail),
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                created_at=timestamp,
            )
        )

    def _persist_media_asset(self, session: Session, asset: dict[str, Any], timestamp: str) -> None:
        session.add(
            MediaAsset(
                id=asset["asset_id"],
                content_id=asset["content_id"],
                source=asset.get("source"),
                source_type=asset["source_type"],
                status=asset["status"],
                storage_backend=asset["storage_backend"],
                storage_uri=asset.get("storage_uri"),
                local_path=asset.get("local_path"),
                sha256=asset.get("sha256"),
                file_size_bytes=asset.get("file_size_bytes"),
                mime_type=asset.get("mime_type"),
                extension=asset.get("extension"),
                error=asset.get("error"),
                asset_json=dumps(asset),
                created_at=timestamp,
            )
        )

    def _task_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "task_id": row["id"],
            "content_id": row["content_id"],
            "evidence_package_id": row["evidence_package_id"],
            "status": row["status"],
            "assigned_to": row["assigned_to"],
            "decision": row["decision"],
            "reason": row["reason"],
            "locked_at": row.get("locked_at"),
            "lock_expires_at": row.get("lock_expires_at"),
            "sla_deadline": row.get("sla_deadline"),
            "priority": row.get("priority"),
            "is_sensitive": row.get("is_sensitive"),
            "jurisdiction": row.get("jurisdiction"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "title": row.get("title"),
            "creator_id": row.get("creator_id"),
            "machine_recommendation": row.get("recommendation"),
            "machine_confidence": row.get("confidence"),
            "machine_rationale": row.get("rationale"),
        }

    def _machine_review_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "review_id": row["id"],
            "content_id": row["content_id"],
            "task_id": row["task_id"],
            "evidence_package_id": row["evidence_package_id"],
            "title": row["title"],
            "description": row["description"],
            "creator_id": row["creator_id"],
            "content_status": row["status"],
            "task_status": row["task_status"],
            "final_decision": row["final_decision"],
            "recommendation": row["recommendation"],
            "confidence": row["confidence"],
            "rationale": row["rationale"],
            "verdicts": loads(row["verdicts_json"]),
            "decision_summary": (
                loads(row["decision_summary_json"]) if row.get("decision_summary_json") else None
            ),
            "created_at": row["created_at"],
        }

    def _pipeline_job_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": row["id"],
            "content_id": row["content_id"],
            "title": row["title"],
            "description": row["description"],
            "creator_id": row["creator_id"],
            "content_status": row["content_status"],
            "status": row["status"],
            "stage": row["stage"],
            "attempts": row["attempts"],
            "max_attempts": row["max_attempts"],
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "evidence_package_id": row.get("evidence_package_id"),
            "machine_review_id": row.get("machine_review_id"),
            "recommendation": row.get("recommendation"),
            "confidence": row.get("confidence"),
            "rationale": row.get("rationale"),
            "task_id": row.get("task_id"),
            "task_status": row.get("task_status"),
            "final_decision": row.get("final_decision"),
        }

    def _audit_orm_to_row(self, row: AuditLog) -> dict[str, Any]:
        return {
            "id": row.id,
            "content_id": row.content_id,
            "task_id": row.task_id,
            "actor": row.actor,
            "action": row.action,
            "detail_json": row.detail_json,
            "prev_hash": row.prev_hash,
            "entry_hash": row.entry_hash,
            "created_at": row.created_at,
        }

    def _audit_row(self, row: dict[str, Any]) -> dict[str, Any]:
        row["detail"] = loads(row.pop("detail_json"))
        return row


# Stage 4：默认维度集合（首次启动播种为 active）。dimension_id 必须有对应策略实现类。
_DEFAULT_DIMENSIONS: list[dict[str, Any]] = [
    {
        "dimension_id": "dim_general_policy",
        "dimension_name": "通用策略",
        "dimension_axis": "safety",
        "llm_review_enabled": True,
        "auto_block_threshold": 0.90,
        "human_review_threshold": 0.50,
    },
    {
        "dimension_id": "dim_gambling",
        "dimension_name": "博彩/彩票",
        "dimension_axis": "safety",
        "auto_block_threshold": 0.90,
        "human_review_threshold": 0.50,
    },
    {
        "dimension_id": "dim_drug_violence",
        "dimension_name": "毒品/暴力",
        "dimension_axis": "safety",
        "auto_block_threshold": 0.90,
        "human_review_threshold": 0.50,
    },
    {
        "dimension_id": "dim_minor_compliance",
        "dimension_name": "未成年合规",
        "dimension_axis": "safety",
        "auto_block_threshold": 0.90,
        "human_review_threshold": 0.50,
    },
    {
        "dimension_id": "dim_marketing_review",
        "dimension_name": "营销属性/画风",
        "dimension_axis": "quality",
        "auto_block_threshold": 0.85,
        "human_review_threshold": 0.50,
    },
    {
        "dimension_id": "dim_poi_match",
        "dimension_name": "内容与信息匹配",
        "dimension_axis": "quality",
        "auto_block_threshold": 0.80,
        "human_review_threshold": 0.50,
    },
]


def feature_flags() -> dict[str, bool]:
    return {
        "enable_csam_detection": False,
        "enable_critical_detection": False,
        "enable_full_disposition_matrix": False,
        "enable_need_more_context": False,
        "single_tenant": True,
        "global_jurisdiction": True,
    }


def config_payload() -> dict[str, Any]:
    return {
        "tenant_id": settings.tenant_id,
        "jurisdiction": settings.jurisdiction,
        "database_backend": "postgresql" if is_postgres_enabled() else "sqlite",
        "machine_review": {
            "llm_configured": is_llm_configured(),
            "fallback": "local_rules",
        },
        "media_ingestion": {
            "storage_backend": "local_fs",
            "max_media_bytes": settings.max_media_bytes,
            "copy_local_media": settings.copy_local_media,
            "remote_download_enabled": settings.enable_remote_download,
            "max_batch_ingest_items": settings.max_batch_ingest_items,
        },
        "modality_models": {
            "asr_configured": bool(settings.asr_model_url),
            "ocr_configured": bool(settings.ocr_model_url),
            "vision_configured": bool(settings.vision_model_url),
            "timeout_seconds": settings.model_timeout_seconds,
        },
        "allowed_human_decisions": [PASS, BLOCK],
        "feature_flags": feature_flags(),
    }
