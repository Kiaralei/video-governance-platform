"""SQLAlchemy ORM 模型 —— 数据库结构的【单一事实源】。

替代原来手工维护的两份 DDL 字符串（SQLITE_SCHEMA + POSTGRES_SCHEMA）。
表结构只在这里定义一次，SQLite（测试）和 PostgreSQL（生产）的方言差异由
SQLAlchemy 处理；结构变更由 Alembic 迁移管理。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    roles_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON 数组，如 ["reviewer"]
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class ContentItem(Base):
    __tablename__ = "content_items"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    creator_id: Mapped[str] = mapped_column(String, nullable=False)
    poi: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    business_context_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String, nullable=False)
    final_decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    content_id: Mapped[str] = mapped_column(String, ForeignKey("content_items.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=3)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    finished_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __table_args__ = (Index("idx_pipeline_jobs_status_created", "status", "created_at"),)


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    content_id: Mapped[str] = mapped_column(String, ForeignKey("content_items.id"), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    storage_backend: Mapped[str] = mapped_column(String, nullable=False)
    storage_uri: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sha256: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    extension: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asset_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("idx_media_assets_content", "content_id"),
        Index("idx_media_assets_sha256", "sha256"),
    )


class EvidencePackage(Base):
    __tablename__ = "evidence_packages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    content_id: Mapped[str] = mapped_column(String, ForeignKey("content_items.id"), nullable=False)
    package_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class MachineReview(Base):
    __tablename__ = "machine_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    content_id: Mapped[str] = mapped_column(String, ForeignKey("content_items.id"), nullable=False)
    recommendation: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    verdicts_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Stage 4：规则引擎聚合的完整决策摘要（final_decision/risk_score/triggered_rules/...）。
    decision_summary_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("idx_machine_reviews_content", "content_id"),)


class DimensionRegistry(Base):
    """维度注册表 —— 策略可扩展性核心。热加载配置 + 四态生命周期。"""

    __tablename__ = "dimension_registry"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    dimension_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    dimension_name: Mapped[str] = mapped_column(String, nullable=False)
    dimension_axis: Mapped[str] = mapped_column(String, nullable=False)  # safety/quality/business
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    llm_review_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_block_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.90)
    human_review_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.50)
    prompt_template_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    severity_tiers: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON
    jurisdiction_overrides: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON
    sor_template_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")  # 四态
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("idx_dimension_registry_status", "status"),)


class PolicyVersion(Base):
    """策略版本快照 —— 提供 rule_version，同样走 draft→shadow→active→archived。"""

    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    version_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    activated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __table_args__ = (Index("idx_policy_versions_status", "status"),)


class HumanReviewTask(Base):
    __tablename__ = "human_review_tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    content_id: Mapped[str] = mapped_column(String, ForeignKey("content_items.id"), nullable=False)
    evidence_package_id: Mapped[str] = mapped_column(
        String, ForeignKey("evidence_packages.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    assigned_to: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Stage 5：案件锁 + SLA。
    locked_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    lock_expires_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sla_deadline: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sla_warned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Stage 6：优先级队列 + 反疲劳 + 独立性。
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    jurisdiction: Mapped[str] = mapped_column(String, nullable=False, default="global")
    # Stage 8：黄金题注入。
    is_golden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    golden_expected_decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("idx_human_review_tasks_status_created", "status", "created_at"),
        Index("idx_human_review_tasks_queue", "status", "priority", "sla_deadline", "created_at"),
    )


class FlywheelSample(Base):
    """数据回流样本（Stage 8）。四类：ground_truth/disagreement/golden/correction。"""

    __tablename__ = "flywheel_samples"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    content_id: Mapped[str] = mapped_column(String, nullable=False)
    dimension_id: Mapped[str] = mapped_column(String, nullable=False, default="overall")
    machine_decision: Mapped[str] = mapped_column(String, nullable=False, default="")
    human_decision: Mapped[str] = mapped_column(String, nullable=False, default="")
    final_decision: Mapped[str] = mapped_column(String, nullable=False)
    error_type: Mapped[str] = mapped_column(String, nullable=False, default="")  # overkill/miss
    policy_version: Mapped[str] = mapped_column(String, nullable=False, default="")
    rule_version: Mapped[str] = mapped_column(String, nullable=False, default="")
    quality_gate_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_correction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("idx_flywheel_source", "source_type"),
        Index("idx_flywheel_content", "content_id"),
    )


class AppealCase(Base):
    """申诉案件（Stage 7）。状态：open→in_review→overturned|rejected。"""

    __tablename__ = "appeal_cases"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    content_id: Mapped[str] = mapped_column(String, ForeignKey("content_items.id"), nullable=False)
    appellant_id: Mapped[str] = mapped_column(String, nullable=False)
    appeal_reason: Mapped[str] = mapped_column(Text, nullable=False)
    original_decision: Mapped[str] = mapped_column(String, nullable=False)
    original_reviewer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    original_task_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pre_disposition_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    assigned_reviewer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    resolved_decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    resolution_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sla_deadline: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    resolved_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    __table_args__ = (Index("idx_appeal_cases_status", "status"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    # 主键需服务端自增：PostgreSQL 用 BIGINT(→BIGSERIAL/IDENTITY)，SQLite 只有
    # INTEGER PRIMARY KEY 才等价于自增 rowid，故用 with_variant 按方言切换。
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    content_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    task_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String, nullable=False)
    entry_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("idx_audit_logs_content_id", "content_id"),)


class DeadLetterTask(Base):
    __tablename__ = "dead_letter_tasks"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    content_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    exception_type: Mapped[str] = mapped_column(String, nullable=False)
    exception_message: Mapped[str] = mapped_column(Text, nullable=False)
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (Index("idx_dead_letter_tasks_status", "status"),)
