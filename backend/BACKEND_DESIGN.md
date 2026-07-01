# 视频治理平台 -- 后端技术方案

> **版本**: MVP v3.0 | **日期**: 2026-07-01 | **状态**: 修订完成 (基于第二轮技术专家评审反馈)

---

## 一、整体系统架构

### 1.1 架构模式选择: 模块化单体 (Modular Monolith)

**选择理由**:

1. **团队规模与阶段匹配**: MVP 阶段团队 3-8 人, 微服务的运维复杂度(服务发现、分布式事务、独立部署流水线)远超团队承载能力。
2. **模块边界已明确**: PRD 已定义 11 个模块的职责边界, 可在单体内通过 Python Package 实现逻辑隔离, 保留后续拆分微服务的可能。
3. **部署简单**: 单一 Docker 镜像 + 独立 Worker 进程, 避免 Kubernetes Service Mesh 的早期复杂度。
4. **数据一致性**: 核心流程(机审 -> 人审 -> 申诉)跨模块数据强依赖, 单体内事务比分布式 Saga 可靠性更高。
5. **演进路径**: 当单个模块(如证据提取层)出现独立扩缩容需求时, 可将其拆为独立服务, 通过消息队列解耦。

### 1.2 服务划分与边界

```
video-governance-platform/
  backend/
    app/
      main.py                          # FastAPI 应用入口
      config.py                        # 全局配置
      database.py                      # 数据库连接
      
      # ---- 核心领域模块 ----
      ingestion/                       # 内容摄取
        router.py                      # 视频上传/接入 API
        service.py                     # 摄取业务逻辑
        schemas.py                     # 请求/响应 Schema
        
      evidence/                        # 证据提取层 (阶段1)
        router.py
        service.py
        extractors/                    # 各模态提取器
          frame_extractor.py           # 抽帧
          asr_extractor.py             # 语音识别
          ocr_extractor.py             # 文字识别
          object_detector.py           # 目标检测
          scene_classifier.py          # 场景识别
          qr_detector.py               # 二维码/联系方式
        schemas.py                     # EvidencePackage Schema
        
      safety_filter/                   # 基础安全初筛 (阶段2)
        router.py
        service.py
        filters/                       # 各类过滤器
          csam_hash_filter.py          # CSAM 哈希比对
          cloud_safety_api.py          # 云 API 内容安全
          keyword_rule_filter.py       # 关键词/规则过滤
          dedup_filter.py              # 重复内容裁决复用
        schemas.py
        
      llm_review/                      # LLM 策略审查 (阶段3)
        router.py
        service.py
        prompt_manager.py              # Prompt 模板管理
        sanitizer.py                   # 输入净化 (防注入)
        output_validator.py            # 输出 Schema 校验
        token_budget.py                # Token 预算管理
        schemas.py
        
      decision_engine/                 # 决策引擎
        router.py
        service.py
        rule_engine.py                 # 规则引擎核心
        strategy_registry.py           # 策略注册表
        strategy_base.py               # 策略抽象基类
        strategies/                    # 具体策略实现
          minor_compliance.py
          marketing_review.py
          poi_match.py
          violence_detection.py
          # ... 新策略通过注册表添加
        schemas.py
        
      human_review/                    # 人审工作台
        router.py
        service.py
        queue_manager.py               # 任务队列管理
        assignment.py                  # 任务分配策略
        lock_manager.py                # 案件锁管理
        fatigue_manager.py             # 反疲劳管理
        schemas.py
        
      appeal/                          # 申诉闭环
        router.py
        service.py
        state_machine.py               # 申诉状态机
        schemas.py
        
      quality_check/                   # 质检与审核质量
        router.py
        service.py
        golden_test_service.py         # 黄金题管理服务
        schemas.py
        
      flywheel/                        # 数据回流
        router.py
        service.py
        quality_gate.py                # 质量门控
        shadow_runner.py               # Shadow 模式运行器
        schemas.py

      sor/                             # SoR 模板管理模块
        router.py
        service.py
        schemas.py
        
      audit/                           # 审计日志
        service.py
        schemas.py

      system/                          # 系统健康与告警模块
        router.py
        service.py
        schemas.py
        
      # ---- 基础设施层 ----
      common/
        auth.py                        # 认证授权 (JWT + RBAC)
        middleware.py                   # 全局中间件
        exceptions.py                  # 统一异常处理
        events.py                      # 领域事件定义
        circuit_breaker.py             #【修订】滑动窗口 Redis 分布式熔断器
        retry.py                       # 重试机制
        idempotency.py                 # 基于客户端幂等键的幂等性
        rate_limiter.py                # 令牌桶限流器
        websocket.py                   #【修订】Redis Pub/Sub 分布式 WebSocket (双协议心跳)
        health.py                      #【修订】异步健康检查探针
        pagination.py                  #【修订】统一分页响应 (双模式兼容)
        dead_letter.py                 #【修订】死信队列处理器
        
      models/                          # SQLAlchemy 模型
        base.py
        video.py
        evidence.py
        review.py
        decision.py
        appeal.py
        audit.py
        flywheel.py
        sor.py                         # SoR 模板模型
        
      tasks/                           # 异步任务 (Celery Workers)
        evidence_tasks.py              # 阶段1 独立 Celery 任务
        safety_filter_tasks.py         # 阶段2 独立 Celery 任务
        llm_review_tasks.py            # 阶段3 独立 Celery 任务
        decision_tasks.py              # 阶段4 独立 Celery 任务
        review_tasks.py                # 流水线编排 (Celery chain)
        flywheel_tasks.py              # 数据回流任务
        shadow_tasks.py                # Shadow 评估任务
```

### 1.3 服务间通信模式

| 通信场景 | 模式 | 技术选择 | 理由 |
|---------|------|---------|------|
| API 请求/响应 | 同步 REST | FastAPI + httpx | 前端交互、管理操作 |
| 视频处理流水线 | 异步消息 | Redis Streams / Kafka | 长耗时任务解耦, 削峰填谷 |
| 实时状态推送 | WebSocket | FastAPI WebSocket + **Redis Pub/Sub** | 案件锁状态、SLA 倒计时, 跨实例广播 |
| 模块间调用 | 进程内直调 | Python 函数调用 | 模块化单体内, 无网络开销 |
| 定时任务 | Cron | Celery Beat | Shadow 报告、数据回流批处理 |

### 1.4 部署架构

```
                    ┌─────────────────┐
                    │   Nginx / ALB   │
                    │   (反向代理+SSL) │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
     │  FastAPI App   │ │ FastAPI  │ │  FastAPI    │
     │  (实例 1)      │ │ (实例 2) │ │ (实例 N)   │
     │  REST+WS       │ │ REST+WS  │ │ REST+WS    │
     └───┬──────┬─────┘ └──┬───┬──┘ └──┬───┬─────┘
         │      │          │   │       │   │
    ┌────▼──────▼──────────▼───▼───────▼───▼──┐
    │  Redis Cluster                           │
    │  ├── 缓存/锁/限流                        │
    │  ├── Pub/Sub (WebSocket 跨实例广播)       │
    │  ├── Streams (消息队列)                   │
    │  └── 熔断器状态 (滑动窗口分布式)           │  【修订】
    └───┬─────────────────────────────────────┘
        │
    ┌───▼──────────────────────────────────┐
    │     PostgreSQL (主)                   │
    │     + Read Replicas                   │
    └──────────────────────────────────────┘
        │
   ┌────▼──────────────────────────────────┐
   │  Celery Workers (可独立扩缩容)         │
   │  ├── evidence_worker  (CPU密集, 抽帧) │
   │  ├── review_worker    (调LLM API)     │
   │  ├── flywheel_worker  (数据回流)      │
   │  └── shadow_worker    (Shadow评估)    │
   └───────────────────────────────────────┘
        │
   ┌────▼─────────────┐
   │  MinIO / S3       │
   │  (对象存储)       │
   │  ├── uploads/     │
   │  ├── evidence/    │
   │  ├── csam-vault/  │  (独立加密桶)
   │  └── flywheel/    │
   └───────────────────┘
```

---

## 二、机审系统 (Machine Review System)

### 2.1 视频处理流水线

视频从上传到产出机审裁决包, 经过四阶段漏斗:

```
视频上传 → 摄取校验 → [阶段1]证据提取 → [阶段2]基础安全初筛 
         → [阶段3]LLM策略审查 → [阶段4]规则引擎聚合决策 → 裁决包产出
```

#### 流水线编排 (Pipeline Orchestrator)

将原先单一同步 Celery 任务拆分为 Celery chain, 每阶段独立任务、独立重试, 已完成阶段不会因后续失败而重新执行。

```python
# backend/app/tasks/review_tasks.py

from celery import chain, chord
from app.tasks.evidence_tasks import extract_evidence
from app.tasks.safety_filter_tasks import run_safety_filter
from app.tasks.llm_review_tasks import run_llm_review
from app.tasks.decision_tasks import run_decision_aggregation


def run_machine_review_pipeline(video_id: str) -> None:
    """
    机审流水线主编排 -- 使用 Celery chain 替代单一同步任务。
    
    改进说明:
      原方案将四阶段全部放在一个 Celery 任务中同步执行。如果阶段1 (证据提取)
      耗时 60s 后阶段3 (LLM 调用) 超时, 重试会重新执行已完成的阶段1, 浪费算力。
      现在每阶段独立任务, 独立重试策略, 已完成阶段的结果通过 evidence_package_id
      持久化, 不会重复执行。
      
    链路:
      extract_evidence -> run_safety_filter -> run_llm_review -> run_decision_aggregation
      
    短路:
      - CSAM 哈希命中: safety_filter 阶段直接路由 critical pipeline, 中断链路
      - 高置信 critical/high: safety_filter 阶段跳过 LLM, 直接进 decision
    """
    pipeline = chain(
        extract_evidence.s(video_id),
        run_safety_filter.s(),
        run_llm_review.s(),
        run_decision_aggregation.s(),
    )
    pipeline.apply_async(
        link_error=on_pipeline_failure.s(video_id),  #【修订】死信回调
    )


# backend/app/tasks/evidence_tasks.py

@celery_app.task(
    bind=True, max_retries=3, default_retry_delay=30,
    autoretry_for=(IOError, TimeoutError),
    retry_backoff=True, retry_jitter=True,
)
def extract_evidence(self, video_id: str) -> dict:
    """
    阶段1: 证据提取 (独立任务, 独立重试)。
    
    输出: evidence_package_id, 持久化到数据库。
    后续阶段通过 evidence_package_id 加载, 不重复提取。
    """
    from app.evidence.service import EvidenceService
    
    service = EvidenceService()
    evidence_package = service.extract(video_id)
    service.persist(evidence_package)
    
    return {
        "video_id": video_id,
        "evidence_package_id": evidence_package.ep_id,
    }


# backend/app/tasks/safety_filter_tasks.py

@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=10,
    autoretry_for=(ConnectionError,),
    retry_backoff=True, retry_jitter=True,
)
def run_safety_filter(self, prev_result: dict) -> dict:
    """
    阶段2: 基础安全初筛 (独立任务)。
    
    短路逻辑:
      - CSAM 哈希命中 -> 标记 short_circuit='csam', 后续阶段据此跳过
      - 高置信 critical/high 命中 -> 标记 short_circuit='high_confidence'
    """
    from app.safety_filter.service import SafetyFilterService
    from app.evidence.service import EvidenceService
    
    video_id = prev_result["video_id"]
    ep_id = prev_result["evidence_package_id"]
    
    evidence_package = EvidenceService().load(ep_id)
    filter_service = SafetyFilterService()
    pre_filter_result = filter_service.screen(evidence_package)
    
    # 持久化初筛结果
    filter_service.persist_result(ep_id, pre_filter_result)
    
    result = {
        "video_id": video_id,
        "evidence_package_id": ep_id,
        "short_circuit": None,
    }
    
    if pre_filter_result.csam_hash_hit:
        result["short_circuit"] = "csam"
        _handle_csam_critical(video_id, evidence_package)
    elif pre_filter_result.skip_llm_review:
        result["short_circuit"] = "high_confidence"
    
    return result


# backend/app/tasks/llm_review_tasks.py

@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=15,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True, retry_jitter=True,
    soft_time_limit=120, time_limit=150,
)
def run_llm_review(self, prev_result: dict) -> dict:
    """
    阶段3: LLM 策略审查 (独立任务, 独立超时)。
    
    如果阶段2已短路, 直接透传结果, 不调用 LLM。
    """
    if prev_result.get("short_circuit"):
        return prev_result
    
    from app.llm_review.service import LLMReviewService
    from app.evidence.service import EvidenceService
    
    ep_id = prev_result["evidence_package_id"]
    evidence_package = EvidenceService().load(ep_id)
    
    llm_service = LLMReviewService()
    llm_verdicts = llm_service.review(evidence_package)
    
    # 持久化 LLM 审查结果
    llm_service.persist_verdicts(ep_id, llm_verdicts)
    
    prev_result["llm_completed"] = True
    return prev_result


# backend/app/tasks/decision_tasks.py

@celery_app.task(bind=True, max_retries=1)
def run_decision_aggregation(self, prev_result: dict) -> dict:
    """
    阶段4: 规则引擎聚合决策 (独立任务)。
    
    如果 CSAM 短路, 已在阶段2处理, 本阶段直接返回。
    """
    if prev_result.get("short_circuit") == "csam":
        return {"final_decision": "critical_escalate", "video_id": prev_result["video_id"]}
    
    from app.decision_engine.service import DecisionEngineService
    from app.evidence.service import EvidenceService
    from app.database import get_db_session
    
    ep_id = prev_result["evidence_package_id"]
    video_id = prev_result["video_id"]
    
    evidence_package = EvidenceService().load(ep_id)
    
    #【修订】在调用方创建 DB session, 传递给 aggregate(), 避免内部二次创建连接
    db = get_db_session()
    try:
        decision_service = DecisionEngineService()
        decision = decision_service.aggregate(evidence_package, db=db)
        
        # 持久化裁决
        decision_service.persist(db, video_id, decision)
        
        # 路由: PASS / BLOCK / NEEDS_REVIEW
        _route_decision(video_id, decision)
        
        db.commit()
    finally:
        db.close()
    
    return decision.model_dump()


#【修订】死信回调 -- 流水线任务永久失败时记录到死信表
@celery_app.task(bind=True)
def on_pipeline_failure(self, request, exc, traceback, video_id: str):
    """
    【修订】流水线死信处理器。
    
    当 Celery chain 中任何阶段耗尽所有重试后, 此回调被触发。
    将失败信息写入 dead_letter_tasks 表, 供运维人员人工调查和重试。
    
    原方案问题: 无 on_failure 处理, 任务默默失败, 无人知晓。
    """
    from app.common.dead_letter import DeadLetterService
    from app.database import get_db_session
    
    db = get_db_session()
    try:
        dl_service = DeadLetterService()
        dl_service.record_failure(
            db=db,
            task_name=request.task,
            task_id=request.id,
            video_id=video_id,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            traceback=traceback,
            retry_count=request.retries,
        )
        db.commit()
    finally:
        db.close()
```

### 2.2 AI/ML 模型集成层 -- 策略模式

#### 2.2.1 策略抽象基类

```python
# backend/app/decision_engine/strategy_base.py

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DimensionDecision(str, Enum):
    """L1: LLM 维度判断层枚举 (PRD S1.E.2)"""
    VIOLATION = "VIOLATION"
    NO_VIOLATION = "NO_VIOLATION"
    UNCERTAIN = "UNCERTAIN"


class SeveritySuggestion(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceRef(BaseModel):
    ref_type: str          # "frame" | "asr_segment" | "ocr_region" | "detection"
    frame_id: Optional[str] = None
    timestamp_ms: Optional[int] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    text_excerpt: Optional[str] = None
    description: str


class DimensionVerdict(BaseModel):
    """
    LLM 对单个策略维度的结构化输出 (PRD S1.C)。
    LLM 只做理解归因, 不做处置决策。
    """
    dimension_id: str
    dimension_name: str
    decision: DimensionDecision
    confidence: float = Field(ge=0.0, le=1.0)
    severity_suggestion: Optional[SeveritySuggestion] = None
    reason: str = Field(max_length=500)
    evidence_refs: list[EvidenceRef] = []
    policy_version: str
    model_version: str
    llm_unavailable: bool = False


class StrategyConfig(BaseModel):
    """策略维度配置, 从维度注册表加载"""
    dimension_id: str
    dimension_name: str
    dimension_axis: str          # "safety" | "quality" | "business"
    enabled: bool = True
    llm_review_enabled: bool = True
    auto_block_threshold: float = 0.90
    human_review_threshold: float = 0.50
    prompt_template_id: str = ""
    jurisdiction_overrides: dict = {}
    severity_tiers: dict = {}


class BaseReviewStrategy(ABC):
    """
    审核策略抽象基类。
    所有审核维度(未成年合规、营销、POI 匹配等)均须实现此接口。
    新增审核维度时, 只需:
      1. 继承 BaseReviewStrategy
      2. 实现 review() 方法
      3. 在维度注册表中注册
    无需修改决策引擎、人审工作台、申诉闭环等核心代码。
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.dimension_id = config.dimension_id
        self.dimension_name = config.dimension_name

    @abstractmethod
    async def review(
        self,
        evidence_package: "EvidencePackage",
        policy_version: str,
    ) -> DimensionVerdict:
        """
        对证据包执行该维度的策略审查。
        
        Args:
            evidence_package: 标准化证据包
            policy_version: 当前生效的策略版本号
            
        Returns:
            DimensionVerdict: 该维度的结构化判断结果
            
        注意:
            - 只输出理解与归因, 不输出处置动作
            - decision 字段只能是 VIOLATION/NO_VIOLATION/UNCERTAIN
            - severity_suggestion 仅为建议, 规则引擎有最终决定权
        """
        ...

    @abstractmethod
    def build_prompt(
        self,
        evidence_package: "EvidencePackage",
    ) -> str:
        """
        构建该维度的 LLM Prompt。
        从 Prompt 模板库加载模板, 填充证据内容。
        必须使用 system/user 角色分离, 用户内容必须用分隔符隔离。
        """
        ...

    def get_jurisdiction_config(self, jurisdiction: str) -> dict:
        """获取法域特定配置覆盖"""
        return self.config.jurisdiction_overrides.get(
            jurisdiction, {}
        )

    def is_enabled_for_jurisdiction(self, jurisdiction: str) -> bool:
        """检查该维度是否在指定法域启用"""
        override = self.get_jurisdiction_config(jurisdiction)
        return override.get("enabled", self.config.enabled)
```

#### 2.2.2 策略注册表 (Registry Pattern)

```python
# backend/app/decision_engine/strategy_registry.py

import asyncio
import copy
import importlib
import logging
from typing import Type
from app.decision_engine.strategy_base import BaseReviewStrategy, StrategyConfig

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    【修订】策略注册表 -- 维度注册表的运行时实现。
    
    设计目标 (PRD S11.A):
      - 新增审核策略维度零改造: 注册新策略不修改五层核心代码
      - 注册表驱动: 所有策略通过配置发现和加载
      - 版本化: 策略配置与 policy 版本绑定
      
    使用方式:
      1. 数据库驱动: 从 dimension_registry 表加载已注册维度
      2. 代码注册: 通过装饰器 @register_strategy 注册策略类
      3. 热加载: 策略配置变更时重新加载, 无需重启
    
    v3.0 修订:
      原方案使用类级别 (class-level) 可变属性 _strategies/_configs 作为单例状态。
      这导致两个问题:
        1. 单元测试脆弱: 状态在测试间泄漏, 必须手动清理
        2. 热加载竞态: 并发请求读 _configs 时, load_from_database 正在写 _configs,
           可能读到半更新的状态
      
      修订为实例单例 + 读写锁模式:
        - _strategies 类级别 (注册时写, 启动后只读) 不变
        - _configs 改为实例属性, 热加载时原子替换引用 (copy-on-write)
        - 提供 reset() 方法用于测试清理
    """

    # 类级别: 代码注册的策略类映射 (启动时写, 运行时只读)
    _strategies: dict[str, Type[BaseReviewStrategy]] = {}
    
    _instance = None
    _lock = asyncio.Lock()

    def __init__(self):
        # 实例级别: 从数据库加载的配置 (可热加载)
        self._configs: dict[str, StrategyConfig] = {}
        self._initialized: bool = False

    @classmethod
    def get_instance(cls) -> "StrategyRegistry":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """
        【修订】重置单例 -- 仅用于测试环境。
        清除实例状态, 防止测试间状态泄漏。
        """
        cls._instance = None

    @classmethod
    def register(cls, dimension_id: str):
        """
        装饰器: 注册策略类到注册表。
        
        用法:
            @StrategyRegistry.register("dim_minor_compliance")
            class MinorComplianceStrategy(BaseReviewStrategy):
                ...
        """
        def decorator(strategy_class: Type[BaseReviewStrategy]):
            if not issubclass(strategy_class, BaseReviewStrategy):
                raise TypeError(
                    f"{strategy_class.__name__} 必须继承 BaseReviewStrategy"
                )
            cls._strategies[dimension_id] = strategy_class
            logger.info(
                f"策略已注册: {dimension_id} -> {strategy_class.__name__}"
            )
            return strategy_class
        return decorator

    async def load_from_database(self, db_session) -> None:
        """
        【修订】从数据库维度注册表加载所有已注册且启用的策略配置。
        
        使用 copy-on-write 模式: 构建新的 configs 字典, 然后原子替换引用。
        并发读请求要么看到旧的完整 configs, 要么看到新的完整 configs,
        不会看到半更新的状态。
        """
        from app.models.decision import DimensionRegistryModel
        
        async with self._lock:
            rows = db_session.query(DimensionRegistryModel).filter(
                DimensionRegistryModel.enabled == True,
                DimensionRegistryModel.status == "active",
            ).all()
            
            # 构建新配置 (copy-on-write)
            new_configs = {}
            for row in rows:
                config = StrategyConfig(
                    dimension_id=row.dimension_id,
                    dimension_name=row.dimension_name,
                    dimension_axis=row.dimension_axis,
                    enabled=row.enabled,
                    llm_review_enabled=row.llm_review_enabled,
                    auto_block_threshold=row.auto_block_threshold,
                    human_review_threshold=row.human_review_threshold,
                    prompt_template_id=row.prompt_template_id,
                    jurisdiction_overrides=row.jurisdiction_overrides or {},
                    severity_tiers=row.severity_tiers or {},
                )
                new_configs[row.dimension_id] = config
            
            # 原子替换引用
            self._configs = new_configs
            self._initialized = True
            
            logger.info(f"已加载 {len(self._configs)} 个策略维度配置")

    def get_strategy(self, dimension_id: str) -> BaseReviewStrategy:
        """获取已注册的策略实例"""
        if dimension_id not in self._strategies:
            raise KeyError(
                f"策略 {dimension_id} 未注册。"
                f"请确认策略类已用 @StrategyRegistry.register 装饰。"
            )
        if dimension_id not in self._configs:
            raise KeyError(
                f"策略 {dimension_id} 无配置。"
                f"请确认维度注册表中已添加该维度。"
            )
        strategy_class = self._strategies[dimension_id]
        config = self._configs[dimension_id]
        return strategy_class(config)

    def get_configs_snapshot(self) -> dict[str, StrategyConfig]:
        """
        【修订】获取当前配置的只读快照。
        外部模块 (如 RuleEngine) 通过此方法获取配置,
        而非直接访问内部 _configs, 避免竞态。
        """
        return self._configs  # 引用是原子的, copy-on-write 保证一致性

    def get_all_enabled(self, jurisdiction: str = "global") -> list[BaseReviewStrategy]:
        """获取指定法域下所有已启用的策略实例"""
        strategies = []
        for dim_id, config in self._configs.items():
            if not config.enabled:
                continue
            if dim_id not in self._strategies:
                logger.warning(f"维度 {dim_id} 已注册配置但无策略实现, 跳过")
                continue
            strategy = self.get_strategy(dim_id)
            if strategy.is_enabled_for_jurisdiction(jurisdiction):
                strategies.append(strategy)
        return strategies

    def get_llm_enabled(self, jurisdiction: str = "global") -> list[BaseReviewStrategy]:
        """获取需要 LLM 审查的策略列表"""
        return [
            s for s in self.get_all_enabled(jurisdiction)
            if s.config.llm_review_enabled
        ]
```

#### 2.2.3 具体策略实现示例

```python
# backend/app/decision_engine/strategies/minor_compliance.py

from app.decision_engine.strategy_base import (
    BaseReviewStrategy, DimensionVerdict, DimensionDecision,
    SeveritySuggestion, EvidenceRef, StrategyConfig,
)
from app.decision_engine.strategy_registry import StrategyRegistry
from app.evidence.schemas import EvidencePackage
from app.llm_review.service import LLMReviewService


@StrategyRegistry.register("dim_minor_compliance")
class MinorComplianceStrategy(BaseReviewStrategy):
    """
    未成年合规策略。
    
    审查要点:
      - 是否正常亲子/教育/家庭场景
      - 是否存在危险、性化、诱导、导流行为
      - 是否利用未成年人进行营销
      
    偏保守策略:
      疑似未成年 + 任何高风险线索 -> 至少 UNCERTAIN, 强制路由人审
    """

    def build_prompt(self, evidence_package: EvidencePackage) -> str:
        """构建未成年合规审查的 LLM Prompt"""
        # 从 Prompt 模板库加载 (版本化)
        template = self._load_prompt_template()
        
        # 构建证据摘要 (用户内容隔离)
        evidence_summary = self._build_evidence_summary(evidence_package)
        
        return template.format(
            evidence_summary=evidence_summary,
            policy_rules=self._get_policy_rules(),
        )

    async def review(
        self,
        evidence_package: EvidencePackage,
        policy_version: str,
    ) -> DimensionVerdict:
        """执行未成年合规策略审查"""
        
        # 检查证据包中是否有未成年相关信号
        minor_signals = self._extract_minor_signals(evidence_package)
        
        if not minor_signals.has_minor_indicators:
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.NO_VIOLATION,
                confidence=0.95,
                severity_suggestion=None,
                reason="未检测到未成年人相关信号。",
                evidence_refs=[],
                policy_version=policy_version,
                model_version="",
                llm_unavailable=False,
            )
        
        # 有未成年信号, 调用 LLM 深度审查
        prompt = self.build_prompt(evidence_package)
        
        try:
            llm_service = LLMReviewService()
            llm_result = await llm_service.call_llm(
                prompt=prompt,
                evidence_package=evidence_package,
                dimension_id=self.dimension_id,
            )
            
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=llm_result.decision,
                confidence=llm_result.confidence,
                severity_suggestion=llm_result.severity_suggestion,
                reason=llm_result.reason,
                evidence_refs=llm_result.evidence_refs,
                policy_version=policy_version,
                model_version=llm_result.model_version,
                llm_unavailable=False,
            )
        except Exception:
            # LLM 不可用时: UNCERTAIN + 路由人审 (PRD S1.A.3)
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.UNCERTAIN,
                confidence=0.0,
                severity_suggestion=None,
                reason="LLM 服务不可用, 需人工审核。",
                evidence_refs=[],
                policy_version=policy_version,
                model_version="",
                llm_unavailable=True,
            )

    def _extract_minor_signals(self, ep: EvidencePackage) -> "MinorSignals":
        """从证据包提取未成年相关信号"""
        from dataclasses import dataclass
        
        @dataclass
        class MinorSignals:
            has_minor_indicators: bool = False
            minor_frame_refs: list = None
            risk_keywords: list = None
            
            def __post_init__(self):
                self.minor_frame_refs = self.minor_frame_refs or []
                self.risk_keywords = self.risk_keywords or []
        
        signals = MinorSignals()
        
        # 检查目标检测结果
        for det in ep.object_detections:
            if det.label in ("minor_suspected", "child", "infant", "teenager"):
                signals.has_minor_indicators = True
                signals.minor_frame_refs.append(
                    EvidenceRef(
                        ref_type="detection",
                        frame_id=det.frame_id,
                        timestamp_ms=det.frame_ts,
                        description=f"检测到疑似未成年: {det.label}, 置信度 {det.score}",
                    )
                )
        
        # 检查场景标签
        for tag in ep.scene_tags:
            if tag.label in ("school", "playground", "nursery", "children_activity"):
                signals.has_minor_indicators = True
        
        return signals

    def _load_prompt_template(self) -> str:
        """加载 Prompt 模板 (简化版, 生产环境从数据库/配置中心加载)"""
        return """你是一个内容合规审查专家。请分析以下视频证据, 判断是否存在未成年合规问题。

审查要点:
1. 视频中是否出现未成年人?
2. 如果出现, 场景是否为正常的亲子/教育/家庭场景?
3. 是否存在以下风险: 危险行为、性化内容、诱导消费、导流行为、利用未成年人营销?

策略规则:
{policy_rules}

请基于以下证据进行判断:
<user_content>
{evidence_summary}
</user_content>

请以 JSON 格式输出判断结果, 包含 decision, confidence, reason, evidence_refs 字段。
decision 只能是 VIOLATION / NO_VIOLATION / UNCERTAIN 之一。
不要输出任何处置动作 (如 REMOVE/BLOCK/PASS)。"""

    def _get_policy_rules(self) -> str:
        return (
            "- 疑似未成年 + 性化内容: 判定 VIOLATION\n"
            "- 疑似未成年 + 危险行为: 判定 VIOLATION\n"
            "- 疑似未成年 + 诱导消费/导流: 判定 VIOLATION\n"
            "- 疑似未成年 + 营销线索: 判定 UNCERTAIN (需人审确认)\n"
            "- 正常亲子/教育场景, 无风险信号: 判定 NO_VIOLATION"
        )

    def _build_evidence_summary(self, ep: EvidencePackage) -> str:
        parts = []
        parts.append(f"视频时长: {ep.video_meta.duration_ms / 1000:.1f}秒")
        
        if ep.frames:
            parts.append("关键帧:")
            for f in ep.frames[:10]:
                parts.append(f"  - {f.timestamp_ms}ms: 场景={f.scene_tag or '未知'}")
        
        if ep.object_detections:
            parts.append("目标检测:")
            for d in ep.object_detections:
                parts.append(f"  - {d.frame_ts}ms: {d.label} (置信度 {d.score:.2f})")
        
        if ep.asr_transcript:
            parts.append("语音转录:")
            for seg in ep.asr_transcript:
                parts.append(f"  - [{seg.start_ms}-{seg.end_ms}ms]: {seg.text}")
        
        if ep.ocr_results:
            parts.append("OCR 识别:")
            for ocr in ep.ocr_results:
                parts.append(f"  - {ocr.frame_ts}ms: {ocr.text}")
        
        return "\n".join(parts)
```

#### 2.2.4 策略链/组合模式 (Pipeline Pattern)

```python
# backend/app/decision_engine/service.py

import asyncio
import logging
from datetime import datetime, timezone
from app.decision_engine.strategy_registry import StrategyRegistry
from app.decision_engine.strategy_base import (
    DimensionVerdict, DimensionDecision,
)
from app.decision_engine.rule_engine import RuleEngine
from app.evidence.schemas import EvidencePackage

logger = logging.getLogger(__name__)


class DecisionEngineService:
    """
    决策引擎服务。
    
    核心职责:
      - 编排所有已注册策略的执行
      - 调用规则引擎聚合 DimensionVerdict 为最终决策
      - 绑定 policy 版本, 保证 100% 可溯源
      
    设计红线 (PRD S1.D):
      - LLM 只做理解归因, 规则引擎是处置决策的唯一责任主体
      - 规则引擎配置走 Maker-Checker + 版本化
    """

    def __init__(self):
        self.registry = StrategyRegistry.get_instance()
        self.rule_engine = RuleEngine()

    async def run_all_strategies(
        self,
        evidence_package: EvidencePackage,
        policy_version: str,
        jurisdiction: str = "global",
    ) -> list[DimensionVerdict]:
        """
        并行执行所有已启用且需要 LLM 审查的策略。
        
        每个策略独立执行, 互不干扰。
        单个策略失败不影响其他策略, 失败策略返回 UNCERTAIN。
        """
        strategies = self.registry.get_llm_enabled(jurisdiction)
        
        if not strategies:
            logger.warning(f"法域 {jurisdiction} 无已启用的 LLM 策略")
            return []
        
        # 并行执行所有策略
        tasks = [
            self._safe_execute_strategy(strategy, evidence_package, policy_version)
            for strategy in strategies
        ]
        verdicts = await asyncio.gather(*tasks)
        
        return [v for v in verdicts if v is not None]

    async def _safe_execute_strategy(
        self,
        strategy,
        evidence_package: EvidencePackage,
        policy_version: str,
    ) -> DimensionVerdict:
        """安全执行单个策略, 捕获异常并降级"""
        try:
            return await asyncio.wait_for(
                strategy.review(evidence_package, policy_version),
                timeout=25.0,  # 单策略超时 25 秒
            )
        except asyncio.TimeoutError:
            logger.error(f"策略 {strategy.dimension_id} 超时")
            return DimensionVerdict(
                dimension_id=strategy.dimension_id,
                dimension_name=strategy.dimension_name,
                decision=DimensionDecision.UNCERTAIN,
                confidence=0.0,
                reason="策略执行超时, 需人工审核。",
                evidence_refs=[],
                policy_version=policy_version,
                model_version="",
                llm_unavailable=True,
            )
        except Exception as e:
            logger.error(f"策略 {strategy.dimension_id} 执行失败: {e}")
            return DimensionVerdict(
                dimension_id=strategy.dimension_id,
                dimension_name=strategy.dimension_name,
                decision=DimensionDecision.UNCERTAIN,
                confidence=0.0,
                reason=f"策略执行异常: {type(e).__name__}",
                evidence_refs=[],
                policy_version=policy_version,
                model_version="",
                llm_unavailable=True,
            )

    def aggregate(
        self,
        evidence_package: EvidencePackage,
        db=None,
    ) -> "DecisionSummary":
        """
        【修订】规则引擎聚合决策 (PRD S1.A.4)。
        
        v3.0 修订: 接受外部传入的 db session, 避免内部创建新连接。
        
        聚合规则 (按优先级):
          1. CSAM 哈希命中 -> 强制 REMOVE_AND_ESCALATE
          2. 阶段2 高置信 critical/high -> 按初筛结论映射
          3. DimensionVerdict 命中 -> 按阈值计算, 取严链合并
          4. 全部低风险 -> PASS
        """
        return self.rule_engine.aggregate(evidence_package, db=db)
```

#### 2.2.5 规则引擎核心

```python
# backend/app/decision_engine/rule_engine.py

import logging
from enum import Enum
from pydantic import BaseModel
from app.decision_engine.strategy_base import DimensionDecision, DimensionVerdict
from app.evidence.schemas import EvidencePackage

logger = logging.getLogger(__name__)


class PolicyDecision(str, Enum):
    """L2: 规则引擎决策层枚举 (PRD S1.E.2)"""
    AUTO_PASS = "auto_pass"
    AUTO_BLOCK = "auto_block"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    CRITICAL_ESCALATE = "critical_escalate"


class DecisionSummary(BaseModel):
    final_decision: PolicyDecision
    risk_score: float
    triggered_rules: list[str]
    dimension_verdicts_summary: list[dict]
    action: dict  # {"publish": bool, "route_to_human_review": bool, "priority": str}
    policy_version: str
    rule_version: str
    #【修订】新增: 机审推荐, 用于前端展示 (needs_human_review 时为 "uncertain")
    machine_recommendation: str = ""


class RuleEngine:
    """
    规则引擎 -- 处置决策的唯一责任主体 (PRD S1.D)。
    
    职责:
      - 聚合阶段2初筛 + 阶段3 DimensionVerdict
      - 对照策略版本阈值和法域配置
      - 产出最终 PolicyDecision 与路由决策
      
    禁止事项:
      - 不接受 LLM 直接输出的处置动作
      - 不让 severity_suggestion 直接作为最终严重度
    """

    # 取严链: critical_escalate > auto_block > needs_human_review > auto_pass
    _SEVERITY_ORDER = {
        PolicyDecision.CRITICAL_ESCALATE: 4,
        PolicyDecision.AUTO_BLOCK: 3,
        PolicyDecision.NEEDS_HUMAN_REVIEW: 2,
        PolicyDecision.AUTO_PASS: 1,
    }

    def aggregate(
        self,
        evidence_package: EvidencePackage,
        db=None,
    ) -> DecisionSummary:
        """
        【修订】聚合所有信号, 产出最终决策。
        
        v3.0 修订: db session 由调用方传入, 不再内部创建。
        """
        triggered_rules = []
        dimension_decisions = []
        
        pre_filter = evidence_package.pre_filter_results
        llm_verdicts = evidence_package.llm_verdicts or []
        
        # 获取规则版本 (使用传入的 session)
        rule_version = self._get_rule_version(db=db)
        
        # 规则 1: CSAM 哈希命中 -> 强制 CRITICAL_ESCALATE
        if pre_filter and pre_filter.csam_hash_hit:
            return DecisionSummary(
                final_decision=PolicyDecision.CRITICAL_ESCALATE,
                risk_score=1.0,
                triggered_rules=["csam_hash_hit"],
                dimension_verdicts_summary=[],
                action={
                    "publish": False,
                    "route_to_human_review": False,
                    "route_to_critical_pipeline": True,
                    "priority": "critical",
                },
                policy_version=evidence_package.policy_version or "",
                rule_version=rule_version,
                machine_recommendation="block",
            )
        
        # 规则 2: 阶段2 高置信 critical/high 命中
        if pre_filter and pre_filter.cloud_api_hits:
            for hit in pre_filter.cloud_api_hits:
                if hit.severity in ("critical", "high") and hit.confidence >= 0.90:
                    triggered_rules.append(
                        f"pre_filter_{hit.category}_{hit.severity}"
                    )
                    if hit.severity == "critical":
                        dimension_decisions.append(PolicyDecision.CRITICAL_ESCALATE)
                    else:
                        dimension_decisions.append(PolicyDecision.AUTO_BLOCK)
        
        # 规则 3: 逐维度处理 DimensionVerdict
        for verdict in llm_verdicts:
            per_dim_decision = self._evaluate_verdict(verdict)
            dimension_decisions.append(per_dim_decision)
            
            if per_dim_decision != PolicyDecision.AUTO_PASS:
                triggered_rules.append(
                    f"{verdict.dimension_id}_{verdict.decision.value}"
                )
        
        # 取严链合并: 取最严决策
        if not dimension_decisions:
            final = PolicyDecision.AUTO_PASS
        else:
            final = max(
                dimension_decisions,
                key=lambda d: self._SEVERITY_ORDER[d],
            )
        
        # 计算风险分
        risk_score = self._compute_risk_score(llm_verdicts, pre_filter)
        
        #【修订】计算机审推荐 -- needs_human_review 时输出 "uncertain" 而非 "block"
        machine_recommendation = self._compute_machine_recommendation(final)
        
        return DecisionSummary(
            final_decision=final,
            risk_score=risk_score,
            triggered_rules=triggered_rules,
            dimension_verdicts_summary=[
                {"dimension_id": v.dimension_id, "decision": v.decision.value,
                 "confidence": v.confidence}
                for v in llm_verdicts
            ],
            action=self._build_action(final),
            policy_version=evidence_package.policy_version or "",
            rule_version=rule_version,
            machine_recommendation=machine_recommendation,
        )

    def _compute_machine_recommendation(self, decision: PolicyDecision) -> str:
        """
        【修订】计算机审推荐, 供前端展示。
        
        关键变更: needs_human_review 映射为 "uncertain", 而非 "block"。
        
        原方案问题 (关键问题 #4):
          前端 mapMachineDecisionToMVP 将 needs_human_review 映射为 "block"
          作为给审核员的机审推荐, 这会系统性地偏向拦截, 当机审实际上只是不确定时,
          审核员会误以为机审建议拦截, 从而拉高拦截率。
          
        修订: 后端显式返回 machine_recommendation 字段:
          - auto_pass     -> "pass"
          - auto_block    -> "block"  
          - needs_human_review -> "uncertain"  (不偏向任何方向)
          - critical_escalate  -> "block"
        """
        mapping = {
            PolicyDecision.AUTO_PASS: "pass",
            PolicyDecision.AUTO_BLOCK: "block",
            PolicyDecision.NEEDS_HUMAN_REVIEW: "uncertain",
            PolicyDecision.CRITICAL_ESCALATE: "block",
        }
        return mapping.get(decision, "uncertain")

    def _evaluate_verdict(self, verdict: DimensionVerdict) -> PolicyDecision:
        """
        评估单个 DimensionVerdict, 映射到 PolicyDecision。
        
        映射规则 (PRD S1.E.2):
          VIOLATION + confidence >= auto_block_threshold -> AUTO_BLOCK
          VIOLATION + confidence >= human_review_threshold -> NEEDS_HUMAN_REVIEW
          UNCERTAIN -> NEEDS_HUMAN_REVIEW
          NO_VIOLATION + high confidence -> AUTO_PASS
        """
        config = self._get_dimension_config(verdict.dimension_id)
        auto_threshold = config.get("auto_block_threshold", 0.90)
        review_threshold = config.get("human_review_threshold", 0.50)
        
        if verdict.llm_unavailable:
            return PolicyDecision.NEEDS_HUMAN_REVIEW
        
        if verdict.decision == DimensionDecision.UNCERTAIN:
            return PolicyDecision.NEEDS_HUMAN_REVIEW
        
        if verdict.decision == DimensionDecision.VIOLATION:
            # critical 严重度 + 高置信 -> CRITICAL_ESCALATE
            if (verdict.severity_suggestion == "critical"
                    and verdict.confidence >= auto_threshold):
                return PolicyDecision.CRITICAL_ESCALATE
            
            # 高置信 VIOLATION -> AUTO_BLOCK
            if verdict.confidence >= auto_threshold:
                return PolicyDecision.AUTO_BLOCK
            
            # 中置信 VIOLATION -> NEEDS_HUMAN_REVIEW
            if verdict.confidence >= review_threshold:
                return PolicyDecision.NEEDS_HUMAN_REVIEW
            
            # 低置信 VIOLATION -> 也路由人审 (保守策略)
            return PolicyDecision.NEEDS_HUMAN_REVIEW
        
        # NO_VIOLATION
        return PolicyDecision.AUTO_PASS

    def _build_action(self, decision: PolicyDecision) -> dict:
        """构建路由动作"""
        actions = {
            PolicyDecision.AUTO_PASS: {
                "publish": True,
                "route_to_human_review": False,
                "priority": "none",
            },
            PolicyDecision.AUTO_BLOCK: {
                "publish": False,
                "route_to_human_review": False,
                "priority": "none",
            },
            PolicyDecision.NEEDS_HUMAN_REVIEW: {
                "publish": False,
                "route_to_human_review": True,
                "priority": "normal",
            },
            PolicyDecision.CRITICAL_ESCALATE: {
                "publish": False,
                "route_to_human_review": False,
                "route_to_critical_pipeline": True,
                "priority": "critical",
            },
        }
        return actions.get(decision, actions[PolicyDecision.NEEDS_HUMAN_REVIEW])

    def _get_dimension_config(self, dimension_id: str) -> dict:
        """
        【修订】从注册表获取维度配置 -- 使用 get_configs_snapshot() 安全访问。
        """
        from app.decision_engine.strategy_registry import StrategyRegistry
        configs = StrategyRegistry.get_instance().get_configs_snapshot()
        if dimension_id in configs:
            cfg = configs[dimension_id]
            return {
                "auto_block_threshold": cfg.auto_block_threshold,
                "human_review_threshold": cfg.human_review_threshold,
            }
        # 兜底: 保守阈值
        return {"auto_block_threshold": 0.95, "human_review_threshold": 0.40}

    def _compute_risk_score(self, verdicts, pre_filter) -> float:
        """计算综合风险分 (0.0 ~ 1.0)"""
        if not verdicts and (not pre_filter or not pre_filter.cloud_api_hits):
            return 0.0
        
        scores = []
        for v in verdicts:
            if v.decision == DimensionDecision.VIOLATION:
                scores.append(v.confidence)
            elif v.decision == DimensionDecision.UNCERTAIN:
                scores.append(v.confidence * 0.5)
        
        if pre_filter and pre_filter.cloud_api_hits:
            for hit in pre_filter.cloud_api_hits:
                scores.append(hit.confidence)
        
        return max(scores) if scores else 0.0

    def _get_rule_version(self, db=None) -> str:
        """
        【修订】获取当前生效的规则版本标识。
        
        v2.0 修订: 从 date.today() 改为 policy_versions 表单调递增 version_id。
        
        v3.0 修订: 不再内部创建 DB session。
        
        原方案问题 (关键问题 -- 专家评审):
          _get_rule_version() 通过 get_db_session() 在方法内部打开新的 DB 连接。
          当 aggregate() 已经在某个 session 上下文内被调用时 (如 Celery 任务或
          API handler), 这会从连接池中取出第二个连接。高负载下多个 Celery worker
          并发调用, 连接池耗尽导致 "connection pool exhausted" 错误。
          
        修订: db session 由调用方传入; 如果未传入, 使用缓存版本或兜底值。
        """
        if db is None:
            # 无 session 时返回兜底值, 不创建新连接
            logger.warning("_get_rule_version 未收到 db session, 返回兜底版本")
            return "rv_0"
        
        from app.models.decision import PolicyVersionModel
        
        active_version = (
            db.query(PolicyVersionModel)
            .filter(PolicyVersionModel.status == "active")
            .order_by(PolicyVersionModel.activated_at.desc())
            .first()
        )
        if active_version:
            return active_version.version_id
        return "rv_0"
```

### 2.3 新增策略的完整流程示例

以新增 "毒品/暴力检测" 维度为例:

**步骤 1: 编写策略类**

```python
# backend/app/decision_engine/strategies/drug_violence.py

from app.decision_engine.strategy_base import (
    BaseReviewStrategy, DimensionVerdict, DimensionDecision,
    EvidenceRef, StrategyConfig,
)
from app.decision_engine.strategy_registry import StrategyRegistry
from app.evidence.schemas import EvidencePackage
from app.llm_review.service import LLMReviewService


@StrategyRegistry.register("dim_drug_violence")
class DrugViolenceStrategy(BaseReviewStrategy):
    """毒品/暴力内容检测策略"""

    def build_prompt(self, evidence_package: EvidencePackage) -> str:
        template = """你是一个内容安全审查专家。请分析以下视频证据, 
判断是否存在毒品展示/推广或暴力行为。

<user_content>
{evidence}
</user_content>

请以 JSON 输出 decision/confidence/reason/evidence_refs。"""
        return template.format(
            evidence=self._build_evidence_summary(evidence_package)
        )

    async def review(
        self, evidence_package: EvidencePackage, policy_version: str,
    ) -> DimensionVerdict:
        # 先检查目标检测中是否有相关物体
        drug_signals = [
            d for d in evidence_package.object_detections
            if d.label in ("drug", "weapon", "knife", "gun", "syringe")
        ]
        
        if not drug_signals:
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.NO_VIOLATION,
                confidence=0.92,
                reason="未检测到毒品或暴力相关物体。",
                evidence_refs=[],
                policy_version=policy_version,
                model_version="",
            )
        
        # 有信号, 调 LLM 深度审查
        prompt = self.build_prompt(evidence_package)
        llm_service = LLMReviewService()
        try:
            result = await llm_service.call_llm(
                prompt=prompt,
                evidence_package=evidence_package,
                dimension_id=self.dimension_id,
            )
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=result.decision,
                confidence=result.confidence,
                severity_suggestion=result.severity_suggestion,
                reason=result.reason,
                evidence_refs=result.evidence_refs,
                policy_version=policy_version,
                model_version=result.model_version,
            )
        except Exception:
            return DimensionVerdict(
                dimension_id=self.dimension_id,
                dimension_name=self.dimension_name,
                decision=DimensionDecision.UNCERTAIN,
                confidence=0.0,
                reason="LLM 不可用",
                evidence_refs=[],
                policy_version=policy_version,
                model_version="",
                llm_unavailable=True,
            )
```

**步骤 2: 在数据库维度注册表插入配置**

```sql
INSERT INTO dimension_registry (
    dimension_id, dimension_name, dimension_axis,
    enabled, llm_review_enabled,
    auto_block_threshold, human_review_threshold,
    prompt_template_id, severity_tiers,
    status, version, created_by
) VALUES (
    'dim_drug_violence', '毒品/暴力内容', 'safety',
    false,  -- 初始为 Shadow 模式, 不启用
    true,
    0.90, 0.50,
    'prompt_drug_violence_v1',
    '{"critical": {"min_score": 90}, "high": {"min_score": 70}, 
      "medium": {"min_score": 40}, "low": {"min_score": 0}}',
    'shadow', 1, 'policy_pm_001'
);
```

**步骤 3: Shadow 验证 -> 灰度放量 -> 全量上线**

整个过程无需修改决策引擎、人审工作台、申诉闭环、审计日志、策略层的任何核心代码。

---

## 三、人审系统 (Human Review System)

### 3.1 任务队列设计

```python
# backend/app/human_review/queue_manager.py

import logging
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import exists

logger = logging.getLogger(__name__)


class QueuePriority(int, Enum):
    """队列优先级 (数值越小优先级越高)"""
    CRITICAL = 1          # CSAM/暴力等高危
    LEGAL_DEADLINE = 2    # 有法定时限的案件
    HIGH = 3              # 高风险
    NORMAL = 5            # 常规 NEEDS_REVIEW
    LOW = 8               # 低风险/低置信
    BACKFILL = 10         # 回扫/补审


class ReviewTask(BaseModel):
    task_id: str
    video_id: str
    content_id: str
    priority: QueuePriority
    dimension_ids: list[str]         # 需要审核的维度列表
    jurisdiction: str
    created_at: datetime
    sla_deadline: Optional[datetime] = None
    assigned_to: Optional[str] = None
    locked_at: Optional[datetime] = None
    lock_expires_at: Optional[datetime] = None
    status: str = "pending"          # pending/locked/in_review/completed
    evidence_package_id: str = ""
    machine_decision_summary: dict = {}
    is_golden_test: bool = False     # 标记是否为黄金题


class QueueManager:
    """
    人审任务队列管理器。
    
    设计要点:
      1. 优先级队列: 按 (priority, sla_deadline, created_at) 三级排序
      2. 法定时限优先: SLA 即将到期的案件自动提升优先级
      3. 领取即锁定: 防止并发审核同一案件
      4. 心跳超时释放: 锁定超时自动释放, 防止案件卡死
    """

    # 锁定超时时间 (分钟)
    LOCK_TIMEOUT_MINUTES = 30
    # SLA 紧急提升阈值
    SLA_URGENT_THRESHOLD_MINUTES = 15
    # 独立性排除时间窗口 (天) -- 只查最近 N 天, 避免大 IN 查询
    INDEPENDENCE_LOOKBACK_DAYS = 90

    async def enqueue(
        self, db: Session, task: ReviewTask,
    ) -> ReviewTask:
        """将案件加入人审队列"""
        from app.models.review import HumanReviewTaskModel
        
        model = HumanReviewTaskModel(
            task_id=task.task_id,
            video_id=task.video_id,
            content_id=task.content_id,
            priority=task.priority.value,
            dimension_ids=task.dimension_ids,
            jurisdiction=task.jurisdiction,
            sla_deadline=task.sla_deadline,
            evidence_package_id=task.evidence_package_id,
            machine_decision_summary=task.machine_decision_summary,
            status="pending",
            is_golden_test=task.is_golden_test,
        )
        db.add(model)
        db.commit()
        
        logger.info(
            f"案件入队: task={task.task_id}, priority={task.priority.name}, "
            f"jurisdiction={task.jurisdiction}"
        )
        return task

    async def fetch_next(
        self,
        db: Session,
        reviewer_id: str,
        reviewer_skills: list[str],
        reviewer_jurisdiction: list[str],
    ) -> Optional[ReviewTask]:
        """
        获取下一个待审案件。
        
        分配逻辑:
          1. 过滤: 只返回审核员有权限的法域和维度
          2. 排除: 排除审核员已审过的案件 (二审不等于原审)
          3. 排序: priority ASC, sla_deadline ASC NULLS LAST, created_at ASC
          4. 锁定: 原子性领取并锁定
        """
        from app.models.review import HumanReviewTaskModel, HumanReviewDecisionModel
        
        now = datetime.now(timezone.utc)
        
        # 先释放过期锁
        await self._release_expired_locks(db, now)
        
        #【修订】使用 EXISTS 子查询替代 IN, 避免物化大列表
        cutoff = now - timedelta(days=self.INDEPENDENCE_LOOKBACK_DAYS)
        handled_exists = (
            exists()
            .where(HumanReviewDecisionModel.video_id == HumanReviewTaskModel.video_id)
            .where(HumanReviewDecisionModel.reviewer_id == reviewer_id)
            .where(HumanReviewDecisionModel.decided_at >= cutoff)
        )
        
        # 查询可分配的任务
        task_model = (
            db.query(HumanReviewTaskModel)
            .filter(
                HumanReviewTaskModel.status == "pending",
                HumanReviewTaskModel.jurisdiction.in_(reviewer_jurisdiction),
                # 排除审核员近 N 天已处理过的视频 (独立性约束)
                ~handled_exists,
            )
            .order_by(
                HumanReviewTaskModel.priority.asc(),
                HumanReviewTaskModel.sla_deadline.asc().nullslast(),
                HumanReviewTaskModel.created_at.asc(),
            )
            .with_for_update(skip_locked=True)  # 跳过已被其他事务锁定的行
            .first()
        )
        
        if not task_model:
            return None
        
        # 原子性锁定
        task_model.status = "locked"
        task_model.assigned_to = reviewer_id
        task_model.locked_at = now
        task_model.lock_expires_at = now + timedelta(
            minutes=self.LOCK_TIMEOUT_MINUTES
        )
        db.commit()
        
        return self._model_to_task(task_model)

    async def _release_expired_locks(self, db: Session, now: datetime):
        """释放过期的案件锁"""
        from app.models.review import HumanReviewTaskModel
        
        expired = (
            db.query(HumanReviewTaskModel)
            .filter(
                HumanReviewTaskModel.status == "locked",
                HumanReviewTaskModel.lock_expires_at < now,
            )
            .all()
        )
        
        for task in expired:
            task.status = "pending"
            task.assigned_to = None
            task.locked_at = None
            task.lock_expires_at = None
            logger.warning(f"锁超时释放: task={task.task_id}")
        
        if expired:
            db.commit()

    def _model_to_task(self, model) -> ReviewTask:
        return ReviewTask(
            task_id=model.task_id,
            video_id=model.video_id,
            content_id=model.content_id,
            priority=QueuePriority(model.priority),
            dimension_ids=model.dimension_ids or [],
            jurisdiction=model.jurisdiction,
            created_at=model.created_at,
            sla_deadline=model.sla_deadline,
            assigned_to=model.assigned_to,
            locked_at=model.locked_at,
            lock_expires_at=model.lock_expires_at,
            status=model.status,
            evidence_package_id=model.evidence_package_id or "",
            machine_decision_summary=model.machine_decision_summary or {},
            is_golden_test=model.is_golden_test or False,
        )
```

### 3.2 审核工作流引擎 (状态机)

```python
# backend/app/human_review/service.py

from enum import Enum
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel


class ReviewStatus(str, Enum):
    """人审案件状态 (PRD S8.2)"""
    PENDING = "pending"               # 待分配
    LOCKED = "locked"                 # 已领取/已锁定
    IN_REVIEW = "in_review"           # 审核中
    AWAITING_SECOND_REVIEW = "awaiting_second_review"  # 待二审
    DECIDED = "decided"               # 已判定
    DELIVERY_PENDING = "delivery_pending"   # 待交付
    DELIVERY_FAILED = "delivery_failed"     # 交付失败
    CLOSED = "closed"                 # 已结案


# 合法状态转移矩阵
VALID_TRANSITIONS = {
    ReviewStatus.PENDING: {ReviewStatus.LOCKED},
    ReviewStatus.LOCKED: {ReviewStatus.IN_REVIEW, ReviewStatus.PENDING},  # 可释放回 PENDING
    ReviewStatus.IN_REVIEW: {
        ReviewStatus.DECIDED,
        ReviewStatus.AWAITING_SECOND_REVIEW,
        ReviewStatus.PENDING,          # 退回重新分配
    },
    ReviewStatus.AWAITING_SECOND_REVIEW: {ReviewStatus.IN_REVIEW},
    ReviewStatus.DECIDED: {ReviewStatus.DELIVERY_PENDING, ReviewStatus.IN_REVIEW},
    ReviewStatus.DELIVERY_PENDING: {ReviewStatus.CLOSED, ReviewStatus.DELIVERY_FAILED},
    ReviewStatus.DELIVERY_FAILED: {ReviewStatus.DELIVERY_PENDING},
    ReviewStatus.CLOSED: set(),  # 终态
}


class HumanReviewService:
    """人审工作流服务"""

    async def submit_decision(
        self,
        db,
        task_id: str,
        reviewer_id: str,
        decision: str,           # "pass" | "block" (MVP 仅支持两种)
        reason_category: str,    # 结构化理由分类
        reason_detail: str,      # 可选补充说明
        internal_notes: str,     # 内部理由 (不对外)
        dimension_overrides: dict,  # 按维度的判定覆盖
    ) -> dict:
        """
        提交人审决策。
        
        MVP 阶段 decision 字段仅接受 "pass" 或 "block" 两种值。
        PRD 明确将 7 级处置矩阵 (PASS/DEMOTE/LABEL/AGE_GATE/GEO_BLOCK/REMOVE/
        REMOVE_AND_ESCALATE) 推迟到 post-MVP 实现。前端 DispositionPanel 必须
        限制为这两种状态, 提交非法值会被校验拒绝。
        
        【修订】v3.0: 黄金题同步评估, 结果随响应返回。
        
        要求:
          - 决策必填, 仅允许 "pass" 或 "block"
          - 结构化理由分类必填
          - 内部理由与对外 SoR 物理分离
        """
        from app.models.review import HumanReviewTaskModel, HumanReviewDecisionModel
        from app.audit.service import AuditService
        
        # 严格校验 decision 值
        ALLOWED_DECISIONS = {"pass", "block"}
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(
                f"decision 必须为 {ALLOWED_DECISIONS} 之一, "
                f"收到: '{decision}'。7 级处置矩阵为 post-MVP 功能。"
            )
        
        task = db.query(HumanReviewTaskModel).filter(
            HumanReviewTaskModel.task_id == task_id
        ).first()
        
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        
        # 校验: 只有持锁审核员可以提交
        if task.assigned_to != reviewer_id:
            raise PermissionError(
                f"审核员 {reviewer_id} 未持有任务 {task_id} 的锁"
            )
        
        # 校验状态转移合法性
        current = ReviewStatus(task.status)
        if ReviewStatus.DECIDED not in VALID_TRANSITIONS.get(current, set()):
            raise ValueError(
                f"非法状态转移: {current} -> {ReviewStatus.DECIDED}"
            )
        
        # 黄金题处理: 记录结果但不影响正式统计
        is_golden = task.is_golden_test
        
        # 记录决策
        decision_model = HumanReviewDecisionModel(
            task_id=task_id,
            video_id=task.video_id,
            reviewer_id=reviewer_id,
            decision=decision,
            reason_category=reason_category,
            reason_detail=reason_detail,
            internal_notes=internal_notes,
            dimension_overrides=dimension_overrides,
            decided_at=datetime.now(timezone.utc),
            is_golden_test=is_golden,
        )
        db.add(decision_model)
        
        # 更新任务状态
        task.status = ReviewStatus.DECIDED.value
        
        # 审计日志
        audit = AuditService()
        await audit.log(
            db=db,
            video_id=task.video_id,
            action="human_review_decided",
            actor=reviewer_id,
            details={
                "task_id": task_id,
                "decision": decision,
                "reason_category": reason_category,
                "is_golden_test": is_golden,
            },
        )
        
        db.commit()
        
        #【修订】构建响应 -- 包含 success 字段和黄金题同步评估结果
        response = {
            "success": True,
            "task_id": task_id,
            "status": "decided",
            "decision": decision,
        }
        
        #【修订】黄金题: 同步评估, 结果包含在响应中
        if is_golden:
            from app.quality_check.golden_test_service import GoldenTestService
            golden_svc = GoldenTestService()
            golden_result = golden_svc.evaluate_golden_result_sync(
                db=db,
                task_id=task_id,
                reviewer_id=reviewer_id,
                reviewer_decision=decision,
            )
            response["golden_test_result"] = golden_result
        else:
            # 触发数据回流 (异步)
            from app.tasks.flywheel_tasks import trigger_flywheel_sample
            trigger_flywheel_sample.delay(task_id, "human_review_confirmed")
        
        return response

    async def batch_decide(
        self,
        db,
        reviewer_id: str,
        decisions: list[dict],
    ) -> dict:
        """
        批量提交人审决策。
        
        前端批量审核功能所需。对每条决策独立校验、独立提交,
        部分失败不影响其他成功的决策。
        
        Args:
            decisions: [{"task_id": "...", "decision": "pass"|"block",
                        "reason_category": "...", ...}, ...]
        
        Returns:
            {"succeeded": [...], "failed": [...]}
        """
        succeeded = []
        failed = []
        
        for dec in decisions:
            try:
                result = await self.submit_decision(
                    db=db,
                    task_id=dec["task_id"],
                    reviewer_id=reviewer_id,
                    decision=dec["decision"],
                    reason_category=dec["reason_category"],
                    reason_detail=dec.get("reason_detail", ""),
                    internal_notes=dec.get("internal_notes", ""),
                    dimension_overrides=dec.get("dimension_overrides", {}),
                )
                succeeded.append(result)
            except Exception as e:
                failed.append({
                    "task_id": dec.get("task_id"),
                    "error": str(e),
                })
        
        return {"succeeded": succeeded, "failed": failed}
```

### 3.3 任务分配策略

```python
# backend/app/human_review/assignment.py

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ReviewerProfile:
    reviewer_id: str
    tier: int                        # 1=普通, 2=高级, 3=专家
    skills: list[str]                # 擅长维度
    jurisdictions: list[str]         # 可处理法域
    current_load: int                # 当前待办数
    max_load: int                    # 最大并行数
    csam_exposure_count: int         # 当班 CSAM 曝光计数
    csam_weekly_count: int           # 本周 CSAM 累计
    consecutive_critical_count: int  # 连续 critical 处理数
    is_on_break: bool                # 是否在强制休息中
    handled_video_ids: set           # 已处理视频 (排除用)


class AssignmentStrategy:
    """
    任务分配策略。
    
    分配算法:
      1. 资格过滤: 法域权限、维度技能、独立性排除
      2. 反疲劳过滤: CSAM 曝光上限、强制休息、负载上限
      3. 优先匹配: 技能匹配度优先, 同等技能取负载最低
    """

    # 反疲劳参数 (PRD S5.A)
    CSAM_PER_SHIFT_LIMIT = 10
    CSAM_PER_WEEK_LIMIT = 30
    FORCED_BREAK_3_CONSECUTIVE = 5 * 60   # 3 条连续 critical 后休息 5 分钟
    FORCED_BREAK_5_CONSECUTIVE = 15 * 60  # 5 条连续 critical 后休息 15 分钟

    def select_reviewer(
        self,
        task,
        available_reviewers: list[ReviewerProfile],
    ) -> ReviewerProfile | None:
        """为任务选择最合适的审核员"""
        
        candidates = []
        
        for reviewer in available_reviewers:
            # 1. 资格过滤
            if not self._check_qualification(reviewer, task):
                continue
            
            # 2. 独立性排除 (二审不等于原审)
            if task.video_id in reviewer.handled_video_ids:
                continue
            
            # 3. 反疲劳过滤
            if not self._check_fatigue(reviewer, task):
                continue
            
            # 4. 负载过滤
            if reviewer.current_load >= reviewer.max_load:
                continue
            
            candidates.append(reviewer)
        
        if not candidates:
            return None
        
        # 5. 排序: 技能匹配度 -> 负载均衡
        candidates.sort(key=lambda r: (
            -self._skill_match_score(r, task),  # 技能匹配度高优先
            r.current_load,                      # 负载低优先
        ))
        
        return candidates[0]

    def _check_qualification(self, reviewer, task) -> bool:
        """检查审核员资格"""
        # 法域权限
        if task.jurisdiction not in reviewer.jurisdictions:
            return False
        # Tier 权限: critical 需要 Tier 2+
        if task.priority.value <= 2 and reviewer.tier < 2:
            return False
        return True

    def _check_fatigue(self, reviewer, task) -> bool:
        """反疲劳检查 (PRD S5.A)"""
        if reviewer.is_on_break:
            return False
        
        is_csam = "csam" in [d.lower() for d in task.dimension_ids]
        
        if is_csam:
            # 单班 CSAM 曝光上限
            if reviewer.csam_exposure_count >= self.CSAM_PER_SHIFT_LIMIT:
                return False
            # 周 CSAM 累积上限
            if reviewer.csam_weekly_count >= self.CSAM_PER_WEEK_LIMIT:
                return False
        
        return True

    def _skill_match_score(self, reviewer, task) -> float:
        """计算技能匹配度"""
        if not task.dimension_ids:
            return 0.5
        matched = len(set(reviewer.skills) & set(task.dimension_ids))
        return matched / len(task.dimension_ids)
```

### 3.4 质量保证机制

```python
# backend/app/quality_check/service.py

import random
from datetime import datetime, timezone
from enum import Enum
from collections import Counter


class SamplingType(str, Enum):
    RANDOM = "random"          # 随机抽检
    TARGETED = "targeted"      # 定向抽检 (特定维度/审核员)
    GOLDEN = "golden"          # 黄金题 (已知标准答案)


class QualityCheckService:
    """
    质检与审核质量服务。
    
    机制:
      1. 随机抽检: 按配置比例随机抽取已完成案件
      2. 定向抽检: 针对特定维度/审核员/高推翻率场景
      3. 黄金题注入: 注入已知答案的测试案件, 校准审核员
      4. IRR (评估者间信度): 多人对同一案件独立判定, 计算 Fleiss' Kappa 系数
    """

    RANDOM_SAMPLE_RATE = 0.05   # 随机抽检比例 5%
    GOLDEN_INJECT_RATE = 0.02   # 黄金题注入比例 2%
    KAPPA_THRESHOLD = 0.80      # Kappa 系数最低要求

    async def should_sample(self, task_id: str) -> tuple[bool, SamplingType | None]:
        """判断是否需要抽检"""
        # 随机抽检
        if random.random() < self.RANDOM_SAMPLE_RATE:
            return True, SamplingType.RANDOM
        return False, None

    async def inject_golden_test(
        self, db, reviewer_id: str,
    ) -> dict | None:
        """注入黄金题"""
        if random.random() >= self.GOLDEN_INJECT_RATE:
            return None
        
        # 从黄金集获取一个测试案件
        from app.models.flywheel import GoldenSetModel
        golden = (
            db.query(GoldenSetModel)
            .filter(GoldenSetModel.status == "active")
            .order_by(GoldenSetModel.last_used_at.asc().nullslast())
            .first()
        )
        
        if golden:
            golden.last_used_at = datetime.now(timezone.utc)
            db.commit()
            return {
                "golden_id": golden.sample_id,
                "expected_decision": golden.final_decision,
                "dimension_id": golden.dimension_id,
            }
        return None

    async def evaluate_consistency(
        self, db, task_id: str, decisions: list[dict],
    ) -> dict:
        """
        评估多人判定一致性 -- 使用 Fleiss' Kappa 系数。
        
        Cohen's Kappa 公式: kappa = (Po - Pe) / (1 - Pe)
          Po = 观察一致率 (实际一致的比例)
          Pe = 期望一致率 (随机情况下预期的一致比例)
        
        对于二分类 (pass/block), 如果分布不平衡 (如 90% pass),
        简单一致率可能达到 90%+, 但 Kappa 可能只有 0.3,
        说明审核员的一致性并不真正高于随机预期。
        """
        if len(decisions) < 2:
            return {"irr_applicable": False}
        
        # 提取所有决策值
        all_decisions = [d["decision"] for d in decisions]
        unique_labels = sorted(set(all_decisions))
        
        if len(unique_labels) < 2:
            # 所有人决策完全一致 -- Kappa 定义退化, 返回完美一致
            return {
                "irr_applicable": True,
                "kappa": 1.0,
                "observed_agreement": 1.0,
                "expected_agreement": None,
                "meets_threshold": True,
                "decisions_count": len(decisions),
                "note": "所有评估者决策完全一致, Kappa 退化为 1.0",
            }
        
        #【修订】直接调用 Fleiss' Kappa, 移除无用的 pairwise 循环
        kappa, po, pe = self._compute_fleiss_kappa(all_decisions, unique_labels)
        
        return {
            "irr_applicable": True,
            "kappa": round(kappa, 4),
            "observed_agreement": round(po, 4),
            "expected_agreement": round(pe, 4),
            "meets_threshold": kappa >= self.KAPPA_THRESHOLD,
            "decisions_count": len(decisions),
        }
    
    def _compute_fleiss_kappa(
        self,
        decisions: list[str],
        labels: list[str],
    ) -> tuple[float, float, float]:
        """
        计算 Fleiss' Kappa (适用于多于 2 个评估者)。
        
        对于 N 个评估者对同一案件的判定:
          Po = 观察一致率
          Pe = 各类别边际概率的平方和 (期望一致率)
          Kappa = (Po - Pe) / (1 - Pe)
        """
        n = len(decisions)
        if n < 2:
            return (1.0, 1.0, 0.0)
        
        # 计算各标签的频率
        counter = Counter(decisions)
        
        # Po: pairwise agreement proportion
        # = sum(n_k * (n_k - 1)) / (n * (n - 1)) for each label k
        agreements = sum(
            count * (count - 1)
            for count in counter.values()
        )
        total_pairs = n * (n - 1)
        po = agreements / total_pairs if total_pairs > 0 else 1.0
        
        # Pe: expected agreement under independence
        # = sum((n_k / n) ^ 2) for each label k
        pe = sum(
            (count / n) ** 2
            for count in counter.values()
        )
        
        # Kappa
        if pe >= 1.0:
            kappa = 1.0  # 完美一致
        else:
            kappa = (po - pe) / (1.0 - pe)
        
        return (kappa, po, pe)


# backend/app/quality_check/golden_test_service.py

class GoldenTestService:
    """
    黄金题管理服务。
    
    职责:
      1. 注入黄金题到审核队列 (标记 is_golden_test=True)
      2. 审核员提交后同步评估准确率
      3. 黄金题结果不计入审核员正式统计
      4. 提供 API 让 QA 管理员查看黄金题评估结果
    
    【修订】v3.0: 从异步评估改为同步评估。
    
    原方案问题 (关键问题 #3):
      submit_decision 返回 {task_id, status, decision}, 黄金题评估通过
      evaluate_golden_result_async 异步执行。前端 GoldenTestFeedbackModal
      期望在提交响应中直接获取 golden_test_result, 但异步模式下响应中
      不包含此字段, Modal 永远不会被触发。
      
    修订: 黄金题评估改为同步执行。比对逻辑极轻量 (只是字符串比较),
    无需异步化。结果直接包含在 submit_decision 响应中。
    """
    
    def evaluate_golden_result_sync(
        self,
        db,
        task_id: str,
        reviewer_id: str,
        reviewer_decision: str,
    ) -> dict:
        """
        【修订】同步评估黄金题结果。
        
        逻辑:
          1. 从任务记录中查询预期答案 (golden_expected_decision)
          2. 比对审核员决策与预期答案
          3. 更新审核员的黄金题准确率统计
          4. 返回评估结果 (包含是否正确、预期答案)
        """
        from app.models.review import HumanReviewTaskModel, HumanReviewDecisionModel
        from app.models.flywheel import GoldenSetModel
        
        # 查询黄金题的预期答案
        task = db.query(HumanReviewTaskModel).filter(
            HumanReviewTaskModel.task_id == task_id
        ).first()
        
        if not task or not task.is_golden_test:
            return {"is_golden_test": False}
        
        # 从 GoldenSet 查询预期决策
        golden = db.query(GoldenSetModel).filter(
            GoldenSetModel.sample_id == task.golden_set_id,
        ).first()
        
        if not golden:
            return {"is_golden_test": True, "evaluation_error": "golden_set_not_found"}
        
        expected = golden.final_decision
        is_correct = (reviewer_decision == expected)
        
        # 更新决策记录中的预期答案字段
        decision_record = db.query(HumanReviewDecisionModel).filter(
            HumanReviewDecisionModel.task_id == task_id,
            HumanReviewDecisionModel.reviewer_id == reviewer_id,
        ).first()
        
        if decision_record:
            decision_record.golden_expected_decision = expected
        
        db.commit()
        
        return {
            "is_golden_test": True,
            "is_correct": is_correct,
            "expected_decision": expected,
            "reviewer_decision": reviewer_decision,
        }
    
    async def get_reviewer_golden_stats(
        self,
        db,
        reviewer_id: str,
    ) -> dict:
        """
        获取审核员的黄金题准确率统计。
        用于 QA 管理员查看审核员校准情况。
        """
        from app.models.review import HumanReviewDecisionModel, HumanReviewTaskModel
        
        golden_decisions = (
            db.query(HumanReviewDecisionModel)
            .join(HumanReviewTaskModel)
            .filter(
                HumanReviewDecisionModel.reviewer_id == reviewer_id,
                HumanReviewDecisionModel.is_golden_test == True,
            )
            .all()
        )
        
        if not golden_decisions:
            return {
                "reviewer_id": reviewer_id,
                "total_golden_tests": 0,
                "accuracy": None,
            }
        
        correct = sum(
            1 for d in golden_decisions
            if d.golden_expected_decision == d.decision
        )
        
        return {
            "reviewer_id": reviewer_id,
            "total_golden_tests": len(golden_decisions),
            "correct": correct,
            "accuracy": correct / len(golden_decisions),
        }
```

---

## 四、数据模型设计

### 4.1 数据库选型: PostgreSQL

**选择理由**:

1. **JSONB 原生支持**: EvidencePackage、DimensionVerdict、策略配置等复杂嵌套结构, PostgreSQL 的 JSONB 类型支持索引和查询, 无需额外文档数据库。
2. **行级锁 + SKIP LOCKED**: 人审任务队列的并发领取, `SELECT ... FOR UPDATE SKIP LOCKED` 原生支持, 无需外部队列。
3. **分区表**: 审计日志和数据回流表按时间分区, 历史数据归档不影响在线查询。
4. **扩展生态**: pg_trgm (模糊搜索)、pg_cron (定时任务)、pgvector (向量检索, 远期需要)。
5. **事务能力**: ACID 事务保证审核流程的数据一致性, 避免 "裁决已产出但审计日志缺失" 的不一致场景。

### 4.2 核心实体 ER 关系

```
ContentItem (1) ──── (1) EvidencePackage
     │                        │
     │                        ├── (N) FrameEvidence
     │                        ├── (N) ASRSegment
     │                        ├── (N) OCRResult
     │                        ├── (N) ObjectDetection
     │                        └── (N) SceneTag
     │
     ├── (1) MachineReviewResult
     │           │
     │           ├── (N) DimensionVerdictRecord
     │           └── (1) PreFilterResult
     │
     ├── (N) HumanReviewTask
     │           │
     │           └── (N) HumanReviewDecision
     │
     ├── (N) AppealCase
     │           │
     │           └── (N) AppealDecision
     │
     ├── (N) AuditEvent
     │
     └── (N) FlywheelSample

DimensionRegistry (独立, 版本化)
PolicyVersion (独立, 四态生命周期, 单调递增 version_id)
ShadowReport (独立)
ReviewerCSAMExposure (独立)
SoRTemplate (独立)
SystemAlert (独立)
DeadLetterTask (独立)              【修订】新增死信任务表
```

### 4.3 详细表结构

```python
# backend/app/models/video.py

import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Index, Enum as SQLEnum, BigInteger,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class ContentStatus(str, enum.Enum):
    INGESTED = "ingested"
    EVIDENCE_EXTRACTING = "evidence_extracting"
    SAFETY_FILTERING = "safety_filtering"
    LLM_REVIEWING = "llm_reviewing"
    MACHINE_DECIDED = "machine_decided"
    HUMAN_REVIEW_PENDING = "human_review_pending"
    HUMAN_REVIEW_IN_PROGRESS = "human_review_in_progress"
    DECIDED = "decided"
    APPEAL_IN_PROGRESS = "appeal_in_progress"
    CLOSED = "closed"


class VisibilityState(str, enum.Enum):
    """可见性状态 (PRD S8.1)"""
    PUBLISH_GATE = "publish_gate"
    PUBLIC = "public"
    DEMOTED = "demoted"
    AGE_RESTRICTED = "age_restricted"
    GEO_RESTRICTED = "geo_restricted"
    REMOVED = "removed"
    EVIDENCE_HELD = "evidence_held"


class ContentItem(Base):
    """
    内容项 -- 审核系统的核心被审实体。
    从 "视频" 抽象出, 预留多内容形态扩展 (PRD S11: ContentItem 抽象)。
    """
    __tablename__ = "content_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 基础信息
    content_type = Column(String(20), nullable=False, default="video")
    title = Column(String(500), default="")
    description = Column(Text, default="")
    creator_id = Column(String(100), nullable=False, index=True)
    
    # 地理/法域
    region = Column(String(20), default="global")
    jurisdiction = Column(String(20), default="global")
    geo_tag = Column(String(200), default="")
    poi_name = Column(String(200), default="")
    poi_category = Column(String(100), default="")
    
    # 视频元数据
    video_path = Column(String(500), nullable=False)
    thumbnail_path = Column(String(500), default="")
    duration_ms = Column(BigInteger, default=0)
    resolution_width = Column(Integer, default=0)
    resolution_height = Column(Integer, default=0)
    file_size_bytes = Column(BigInteger, default=0)
    codec = Column(String(20), default="")
    
    # 状态
    status = Column(
        SQLEnum(ContentStatus), default=ContentStatus.INGESTED, index=True,
    )
    visibility = Column(
        SQLEnum(VisibilityState), default=VisibilityState.PUBLISH_GATE, index=True,
    )
    
    # 策略绑定
    policy_version = Column(String(50), default="")
    snapshot_id = Column(String(100), default="")   # 提交快照标识
    
    # 创作者信誉 (从外部信用引擎消费)
    creator_trust_tier = Column(String(20), default="medium")
    
    # 多租户预留
    tenant_id = Column(String(50), default="default", index=True)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 乐观锁版本号
    version = Column(Integer, default=1, nullable=False)
    
    # 关系
    evidence_package = relationship(
        "EvidencePackageModel", back_populates="content_item", uselist=False,
    )
    machine_review = relationship(
        "MachineReviewResult", back_populates="content_item", uselist=False,
    )
    review_tasks = relationship("HumanReviewTaskModel", back_populates="content_item")
    appeals = relationship("AppealCase", back_populates="content_item")
    audit_events = relationship("AuditEvent", back_populates="content_item")
    
    __table_args__ = (
        Index("ix_content_status_created", "status", "created_at"),
        Index("ix_content_creator_status", "creator_id", "status"),
        Index("ix_content_jurisdiction", "jurisdiction"),
    )
```

```python
# backend/app/models/evidence.py

class EvidencePackageModel(Base):
    """证据包 (PRD S1.B)"""
    __tablename__ = "evidence_packages"

    ep_id = Column(String(100), primary_key=True)
    schema_version = Column(String(10), nullable=False, default="1.0")
    content_id = Column(
        UUID(as_uuid=True), ForeignKey("content_items.id"), unique=True,
    )
    snapshot_id = Column(String(100), nullable=False)
    
    # 视频元数据
    video_meta = Column(JSONB, default={})
    
    # 各模态可用性
    modality_availability = Column(JSONB, default={
        "video": True, "audio": True, "text_ocr": True, "asr": True,
    })
    
    # 证据数据 (存储为 JSONB, 大量帧数据指针存 S3)
    frames = Column(JSONB, default=[])
    asr_transcript = Column(JSONB, default=[])
    ocr_results = Column(JSONB, default=[])
    object_detections = Column(JSONB, default=[])
    scene_tags = Column(JSONB, default=[])
    
    # 阶段2 初筛结果
    pre_filter_results = Column(JSONB, default={})
    
    # 阶段3 LLM 审查结果
    llm_verdicts = Column(JSONB, default=[])
    
    # 规则引擎聚合结果
    decision_summary = Column(JSONB, nullable=True)
    
    # Token 预算使用情况
    token_budget_used = Column(Integer, default=0)
    token_budget_limit = Column(Integer, default=0)
    truncated_modalities = Column(JSONB, default=[])
    
    # 访问控制
    access_policy = Column(JSONB, default={
        "readable_roles": ["reviewer", "senior_reviewer", "qa_reviewer"],
        "csam_exception": False,
        "retention_days": 365,
    })
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    content_item = relationship("ContentItem", back_populates="evidence_package")
    
    __table_args__ = (
        Index("ix_ep_content_id", "content_id"),
        Index("ix_ep_snapshot_id", "snapshot_id"),
    )
```

```python
# backend/app/models/decision.py

class DimensionRegistryModel(Base):
    """维度注册表 -- 策略可扩展性的核心 (PRD S11.A)"""
    __tablename__ = "dimension_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dimension_id = Column(String(100), unique=True, nullable=False)
    dimension_name = Column(String(200), nullable=False)
    dimension_axis = Column(String(20), nullable=False)   # safety/quality/business
    
    enabled = Column(Boolean, default=False)
    llm_review_enabled = Column(Boolean, default=True)
    
    auto_block_threshold = Column(Float, default=0.90)
    human_review_threshold = Column(Float, default=0.50)
    
    prompt_template_id = Column(String(100), default="")
    severity_tiers = Column(JSONB, default={})
    jurisdiction_overrides = Column(JSONB, default={})
    
    # 人审 UI 配置 (零改造: 人审工作台按此配置动态渲染)
    human_review_ui_config = Column(JSONB, default={})
    
    # SoR 模板 (零改造: 申诉系统按此生成对外理由)
    sor_template_id = Column(String(100), default="")
    
    # 策略四态生命周期
    status = Column(String(20), default="draft")  # draft/shadow/active/archived
    version = Column(Integer, default=1)
    
    created_by = Column(String(100), nullable=False)
    approved_by = Column(String(100), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class MachineReviewResult(Base):
    """机审裁决结果"""
    __tablename__ = "machine_review_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(
        UUID(as_uuid=True), ForeignKey("content_items.id"), unique=True,
    )
    
    # 决策结果 (L2: PolicyDecision)
    final_decision = Column(String(30), nullable=False)
    risk_score = Column(Float, default=0.0)
    triggered_rules = Column(JSONB, default=[])
    
    # 各维度判定摘要
    dimension_verdicts = Column(JSONB, default=[])
    
    # 路由动作
    action = Column(JSONB, default={})
    
    #【修订】机审推荐 (前端展示用, needs_human_review 时为 "uncertain")
    machine_recommendation = Column(String(20), default="")
    
    # 版本绑定 (100% 可溯源)
    policy_version = Column(String(50), nullable=False)
    rule_version = Column(String(50), nullable=False)
    model_version = Column(String(50), default="")
    evidence_package_id = Column(String(100), nullable=False)
    
    processing_ms = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    content_item = relationship("ContentItem", back_populates="machine_review")
    
    __table_args__ = (
        Index("ix_mr_decision", "final_decision"),
        Index("ix_mr_policy_version", "policy_version"),
    )


class PolicyVersionModel(Base):
    """
    策略版本 (四态生命周期, PRD S8.5)。
    
    version_id 为单调递增计数器, 格式 "rv_{N}"。
    不再使用日期字符串, 确保同一天内的多次变更拥有不同版本号。
    """
    __tablename__ = "policy_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(String(50), unique=True, nullable=False)
    
    # 单调递增版本号 (用于生成 version_id)
    version_seq = Column(Integer, nullable=False, unique=True)
    
    # 状态: draft -> shadow -> active -> archived
    status = Column(String(20), default="draft")
    
    # 策略内容
    thresholds = Column(JSONB, nullable=False)      # 各维度阈值配置
    dimension_configs = Column(JSONB, nullable=False)  # 维度启用/禁用
    jurisdiction_rules = Column(JSONB, default={})
    
    # 内容哈希 -- 相同配置内容产生相同哈希, 防止无变更的版本创建
    content_hash = Column(String(64), nullable=False, default="")
    
    # 灰度放量
    rollout_percentage = Column(Integer, default=0)  # 0-100
    
    # Maker-Checker
    created_by = Column(String(100), nullable=False)
    approved_by = Column(String(100), default="")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    activated_at = Column(DateTime(timezone=True), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)
```

```python
# backend/app/models/review.py

class HumanReviewTaskModel(Base):
    """人审任务"""
    __tablename__ = "human_review_tasks"

    task_id = Column(String(100), primary_key=True)
    video_id = Column(String(100), nullable=False, index=True)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"))
    
    # 优先级与分配
    priority = Column(Integer, default=5, index=True)
    dimension_ids = Column(JSONB, default=[])
    jurisdiction = Column(String(20), default="global")
    assigned_to = Column(String(100), default="", index=True)
    
    # 锁机制
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # SLA
    sla_deadline = Column(DateTime(timezone=True), nullable=True)
    
    # 关联
    evidence_package_id = Column(String(100), default="")
    machine_decision_summary = Column(JSONB, default={})
    
    # 状态
    status = Column(String(30), default="pending", index=True)
    
    # 黄金题标记
    is_golden_test = Column(Boolean, default=False)
    golden_set_id = Column(String(100), nullable=True)   #【修订】关联 GoldenSet 的 sample_id
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    content_item = relationship("ContentItem", back_populates="review_tasks")
    decisions = relationship("HumanReviewDecisionModel", back_populates="task")
    
    __table_args__ = (
        Index("ix_task_queue", "status", "priority", "sla_deadline", "created_at"),
    )


class HumanReviewDecisionModel(Base):
    """人审决策记录"""
    __tablename__ = "human_review_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(100), ForeignKey("human_review_tasks.task_id"))
    video_id = Column(String(100), nullable=False)
    
    reviewer_id = Column(String(100), nullable=False, index=True)
    decision = Column(String(20), nullable=False)    # MVP: pass / block
    reason_category = Column(String(100), nullable=False)
    reason_detail = Column(Text, default="")
    
    # 内部理由与对外 SoR 物理分离
    internal_notes = Column(Text, default="")
    sor_text = Column(Text, default="")             # Statement of Reason (对外)
    
    # 维度级覆盖
    dimension_overrides = Column(JSONB, default={})
    
    # 是否推翻机审
    is_override = Column(Boolean, default=False)
    override_reason = Column(Text, default="")
    
    # 黄金题标记与预期答案
    is_golden_test = Column(Boolean, default=False)
    golden_expected_decision = Column(String(20), nullable=True)
    
    decided_at = Column(DateTime(timezone=True), nullable=False)
    
    task = relationship("HumanReviewTaskModel", back_populates="decisions")
    
    __table_args__ = (
        # 为黄金题查询添加索引
        Index("ix_decision_reviewer_golden", "reviewer_id", "is_golden_test"),
    )


class ReviewerCSAMExposure(Base):
    """审核员 CSAM 曝光计数 (PRD S5.A)"""
    __tablename__ = "reviewer_csam_exposure"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reviewer_id = Column(String(100), nullable=False, index=True)
    shift_date = Column(DateTime(timezone=True), nullable=False)
    shift_count = Column(Integer, default=0)
    week_start = Column(DateTime(timezone=True), nullable=False)
    weekly_count = Column(Integer, default=0)
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
```

```python
# backend/app/models/appeal.py

class AppealStatus(str, enum.Enum):
    """申诉状态机 (PRD S8.4)"""
    OPEN = "open"
    REJECTED_INTAKE = "rejected_intake"
    IN_TRIAGE = "in_triage"
    IN_REVIEW = "in_review"
    UPHELD = "upheld"              # 维持 (终态)
    OVERTURNED = "overturned"      # 改判 (终态)
    WITHDRAWN = "withdrawn"        # 撤回
    SUPERSEDED = "superseded"      # 被取代
    EXPIRED = "expired"            # 过期


class AppealCase(Base):
    """申诉案件"""
    __tablename__ = "appeal_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"))
    
    # 创作者信息
    appellant_id = Column(String(100), nullable=False, index=True)
    appeal_reason = Column(Text, nullable=False)
    
    # 原始处置
    original_decision = Column(String(30), nullable=False)
    original_reviewer_id = Column(String(100), default="")
    original_sor = Column(Text, default="")           # 对外说明理由
    
    # 处置前快照 (回滚锚点)
    pre_disposition_snapshot = Column(JSONB, default={})
    
    # 状态
    status = Column(SQLEnum(AppealStatus), default=AppealStatus.OPEN, index=True)
    
    # 二审分配 (排除原审核员)
    assigned_reviewer_id = Column(String(100), default="")
    
    # SLA
    sla_deadline = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    content_item = relationship("ContentItem", back_populates="appeals")
    decisions = relationship("AppealDecision", back_populates="appeal_case")


class AppealDecision(Base):
    """申诉裁决"""
    __tablename__ = "appeal_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appeal_id = Column(UUID(as_uuid=True), ForeignKey("appeal_cases.id"))
    
    reviewer_id = Column(String(100), nullable=False)
    decision = Column(String(20), nullable=False)     # upheld / overturned
    reason = Column(Text, nullable=False)
    
    # 改判类型 (PRD S1A.2)
    overturn_type = Column(String(30), default="")   # wrong_judgment / policy_change
    
    decided_at = Column(DateTime(timezone=True), nullable=False)
    
    appeal_case = relationship("AppealCase", back_populates="decisions")
```

```python
# backend/app/models/audit.py

import hashlib
import json


class AuditEvent(Base):
    """
    审计事件 -- append-only, 不可修改 (PRD S9)。
    链式完整性: 每条事件包含前一条事件的哈希, 篡改可检测。
    """
    __tablename__ = "audit_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(100), unique=True, nullable=False)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), index=True)
    
    action = Column(String(100), nullable=False, index=True)
    actor = Column(String(100), nullable=False, index=True)  # 人或 "system"
    actor_role = Column(String(50), default="")
    
    # 事件详情
    details = Column(JSONB, default={})
    
    # 链式完整性
    previous_event_hash = Column(String(64), default="")
    event_hash = Column(String(64), nullable=False)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    content_item = relationship("ContentItem", back_populates="audit_events")
    
    __table_args__ = (
        Index("ix_audit_action_time", "action", "created_at"),
        Index("ix_audit_actor_time", "actor", "created_at"),
        # 按月分区建议 (生产环境)
    )

    @staticmethod
    def compute_event_hash(
        event_id: str,
        action: str,
        actor: str,
        details: dict,
        previous_hash: str,
        created_at_iso: str,
    ) -> str:
        """
        【修订】计算审计事件的链式哈希。
        
        原方案声明了 previous_event_hash 和 event_hash 字段,
        但未提供实际的哈希计算逻辑。
        
        实现: SHA-256(event_id + action + actor + details_json 
                      + previous_hash + created_at)
        链式保证: 任意一条历史事件被篡改, 后续所有事件的 hash 链断裂,
        可通过 /audit/integrity/verify 端点检测。
        """
        canonical = json.dumps({
            "event_id": event_id,
            "action": action,
            "actor": actor,
            "details": details,
            "previous_event_hash": previous_hash,
            "created_at": created_at_iso,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

```python
#【修订】backend/app/audit/service.py (审计链完整性实现)

class AuditService:
    """
    审计服务 -- 负责写入审计事件并维护链式完整性。
    
    【修订】补充链式完整性的写入逻辑:
      1. 查询该 content_id 下最后一条事件的 event_hash
      2. 将其作为新事件的 previous_event_hash
      3. 计算新事件的 event_hash
      4. 写入数据库
    """
    
    async def log(
        self,
        db,
        video_id: str,
        action: str,
        actor: str,
        details: dict,
    ) -> None:
        import uuid
        from datetime import datetime, timezone
        from app.models.audit import AuditEvent
        
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        
        # 查询该 content 的最后一条事件哈希
        last_event = (
            db.query(AuditEvent.event_hash)
            .filter(AuditEvent.content_id == video_id)
            .order_by(AuditEvent.id.desc())
            .first()
        )
        previous_hash = last_event.event_hash if last_event else ""
        
        # 计算本事件哈希
        event_hash = AuditEvent.compute_event_hash(
            event_id=event_id,
            action=action,
            actor=actor,
            details=details,
            previous_hash=previous_hash,
            created_at_iso=now.isoformat(),
        )
        
        event = AuditEvent(
            event_id=event_id,
            content_id=video_id,
            action=action,
            actor=actor,
            details=details,
            previous_event_hash=previous_hash,
            event_hash=event_hash,
            created_at=now,
        )
        db.add(event)
```

```python
# backend/app/models/flywheel.py

class FlywheelSampleModel(Base):
    """数据回流样本 (PRD S12)"""
    __tablename__ = "flywheel_samples"

    sample_id = Column(String(100), primary_key=True)
    source_type = Column(String(50), nullable=False)  # ground_truth/disagreement/golden/relabel
    
    content_id = Column(String(100), nullable=False, index=True)
    snapshot_id = Column(String(100), nullable=False)
    ep_id = Column(String(100), nullable=False)
    dimension_id = Column(String(100), nullable=False, index=True)
    
    # 决策链
    machine_decision = Column(String(30), default="")
    machine_confidence = Column(Float, default=0.0)
    human_decision = Column(String(30), default="")
    final_decision = Column(String(30), nullable=False)
    final_severity = Column(String(20), default="")
    
    # 不一致分析
    disagreement_type = Column(String(30), default="")  # machine_wrong/machine_right
    error_type = Column(String(30), default="")          # overkill/miss
    
    # 版本绑定
    policy_version = Column(String(50), default="")
    model_version = Column(String(50), default="")
    prompt_version = Column(String(50), default="")
    rule_version = Column(String(50), default="")
    
    # 质量门控
    quality_gate_passed = Column(Boolean, default=False)
    annotator_tier = Column(String(20), default="")
    is_correction = Column(Boolean, default=False)
    is_shadow = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index("ix_flywheel_source_dim", "source_type", "dimension_id"),
        Index("ix_flywheel_quality_gate", "quality_gate_passed"),
    )


class ShadowReportModel(Base):
    """Shadow 验证报告 (PRD S1.E.6)"""
    __tablename__ = "shadow_reports"

    report_id = Column(String(100), primary_key=True)
    policy_version_new = Column(String(50), nullable=False)
    policy_version_old = Column(String(50), nullable=False)
    
    report_period_start_ms = Column(BigInteger, nullable=False)
    report_period_end_ms = Column(BigInteger, nullable=False)
    generated_at_ms = Column(BigInteger, nullable=False)
    
    status = Column(String(20), default="generating")  # generating/ready/archived
    summary_json = Column(JSONB, default={})
    drift_alerts_json = Column(JSONB, default=[])
    
    created_by = Column(String(50), default="system_shadow_cron")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

```python
# backend/app/models/sor.py

class SoRTemplateModel(Base):
    """
    Statement of Reason 模板。
    
    前端 SoRPreview 组件和 ExternalReasonForm 依赖此表。
    每个维度可关联一个或多个 SoR 模板, 支持按法域和语言切换。
    """
    __tablename__ = "sor_templates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    template_id = Column(String(100), unique=True, nullable=False)
    dimension_id = Column(String(100), nullable=False, index=True)
    
    # 模板内容
    template_name = Column(String(200), nullable=False)
    template_body = Column(Text, nullable=False)          # 支持 {placeholder} 变量
    
    # 法域和语言
    jurisdiction = Column(String(20), default="global")
    language = Column(String(10), default="zh")
    
    # 版本
    version = Column(Integer, default=1)
    status = Column(String(20), default="active")         # active / archived
    
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        Index("ix_sor_dim_jurisdiction", "dimension_id", "jurisdiction"),
    )
```

```python
# backend/app/models/system.py

class SystemAlertModel(Base):
    """
    系统告警记录。
    
    前端 Dashboard 的 getSystemHealth / getRecentAlerts / acknowledgeAlert
    端点依赖此表。告警由 Prometheus AlertManager webhook 或业务逻辑写入。
    """
    __tablename__ = "system_alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(100), unique=True, nullable=False)
    
    # 告警信息
    alert_name = Column(String(200), nullable=False)
    severity = Column(String(20), nullable=False)        # critical / high / medium / low
    category = Column(String(50), nullable=False)        # pipeline / queue / sla / system
    message = Column(Text, nullable=False)
    details = Column(JSONB, default={})
    
    # 状态
    status = Column(String(20), default="active")        # active / acknowledged / resolved
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index("ix_alert_status_severity", "status", "severity"),
        Index("ix_alert_created", "created_at"),
    )


class DeadLetterTaskModel(Base):
    """
    【修订】死信任务表。
    
    记录 Celery 任务耗尽重试后的失败信息, 供运维人员人工调查和重试。
    """
    __tablename__ = "dead_letter_tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_name = Column(String(200), nullable=False, index=True)
    celery_task_id = Column(String(100), nullable=False)
    video_id = Column(String(100), nullable=True, index=True)
    
    exception_type = Column(String(200), nullable=False)
    exception_message = Column(Text, nullable=False)
    traceback = Column(Text, default="")
    retry_count = Column(Integer, default=0)
    
    # 处理状态: pending / investigating / retried / abandoned
    status = Column(String(20), default="pending", index=True)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

---

## 五、API 设计

### 5.1 RESTful API 列表

#### 5.1.0【修订】统一分页响应格式 (双模式兼容)

```python
# backend/app/common/pagination.py

from pydantic import BaseModel
from typing import TypeVar, Generic, Optional

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    【修订】统一分页响应 Schema -- 同时兼容 page-based 和 offset-based 查询。
    
    v3.0 修订 (关键问题 #1 -- 分页协议矛盾):
    
    原方案问题:
      后端声明 offset-based 分页 (期望 ?offset=N&limit=M),
      前端发送 page-based 参数 (?page=N&page_size=M),
      后端返回 {items, offset, limit, next_offset},
      前端期望读取 {tasks, page, page_size} 字段。
      参数不兼容 + 字段不兼容 = 所有分页 API 调用失败。
    
    修订方案:
      1. 后端同时接受两种参数模式:
         - offset-based: ?offset=0&limit=20 (原生)
         - page-based:   ?page=1&page_size=20 (兼容前端)
         page-based 会被内部转换为 offset = (page - 1) * page_size
      
      2. 响应同时包含两套字段:
         - items: 数据列表 (标准字段名)
         - total/offset/limit/next_offset: offset-based 字段
         - page/page_size/total_pages: page-based 兼容字段
      
      3. 前端可以直接读取 items (不再需要 'tasks' 别名),
         也可以通过 page/page_size 做页码计算。
    """
    items: list[T]
    total: int
    offset: int
    limit: int
    next_offset: Optional[int] = None  # null = 没有更多数据
    # 【修订】page-based 兼容字段
    page: int = 1
    page_size: int = 20
    total_pages: int = 1


def parse_pagination_params(
    offset: Optional[int] = None,
    limit: Optional[int] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> tuple[int, int]:
    """
    【修订】解析分页参数 -- 同时支持 offset-based 和 page-based。
    
    优先级:
      1. 如果提供了 offset/limit, 直接使用
      2. 如果提供了 page/page_size, 转换为 offset/limit
      3. 都未提供, 使用默认值 offset=0, limit=20
    """
    if offset is not None and limit is not None:
        return max(0, offset), min(max(1, limit), 100)
    
    if page is not None and page_size is not None:
        actual_page = max(1, page)
        actual_size = min(max(1, page_size), 100)
        return (actual_page - 1) * actual_size, actual_size
    
    if offset is not None:
        return max(0, offset), limit or 20
    
    if page is not None:
        actual_page = max(1, page)
        actual_size = page_size or 20
        return (actual_page - 1) * actual_size, min(actual_size, 100)
    
    return 0, 20


def build_paginated_response(
    items: list,
    total: int,
    offset: int,
    limit: int,
) -> dict:
    """
    【修订】构建兼容两种模式的分页响应。
    """
    next_offset = offset + limit if offset + limit < total else None
    page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset,
        "page": page,
        "page_size": limit,
        "total_pages": total_pages,
    }
```

#### 内容摄取

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/content/upload` | POST | 创作者上传视频 | multipart/form-data: video, title, description, region, poi | `{content_id, status, snapshot_id}` |
| `/api/v1/content/batch` | POST | 批量接入 | `{items: [{video_url, meta}]}` | `{batch_id, accepted: N, rejected: N}` |
| `/api/v1/content/{id}` | GET | 获取内容详情 | - | `{content_id, status, visibility, ...}` |
| `/api/v1/content/{id}/status` | GET | 获取审核状态 (创作者侧) | - | `{status, visibility, sor_text}` |

#### 证据与机审

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/evidence/{ep_id}` | GET | 获取证据包 (含全部字段) | - | EvidencePackageResponse |
| `/api/v1/evidence/{ep_id}/frames` | GET | 获取证据帧 (CSAM 受限) | - | `{frames: [...]}` |
| `/api/v1/review/machine/{content_id}` | GET | 获取机审结果 | - | MachineReviewResult |
| `/api/v1/review/machine/{content_id}/retry` | POST | 重试机审 | - | `{status: "retrying"}` |

证据包响应 Schema:

```python
# backend/app/evidence/schemas.py

class EvidencePackageResponse(BaseModel):
    """
    GET /api/v1/evidence/{ep_id} 的完整响应 Schema。
    
    明确列出所有返回字段, 包括 truncated_modalities 和 modality_availability,
    这些字段存储为 JSONB, 前端 EvidencePackage 类型依赖它们。
    """
    ep_id: str
    schema_version: str
    content_id: str
    snapshot_id: str
    video_meta: dict
    modality_availability: dict        # 各模态是否可用
    frames: list[dict]
    asr_transcript: list[dict]
    ocr_results: list[dict]
    object_detections: list[dict]
    scene_tags: list[dict]
    pre_filter_results: dict
    llm_verdicts: list[dict]
    decision_summary: dict | None
    token_budget_used: int
    token_budget_limit: int
    truncated_modalities: list[str]    # 被截断的模态列表
    access_policy: dict
    created_at: datetime
```

#### 人审工作台

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/review/human/queue` | GET | 获取待审队列 | `?offset=0&limit=20` 或 `?page=1&page_size=20`【修订】 | `PaginatedResponse[ReviewTask]`【修订】 |
| `/api/v1/review/human/next` | POST | 领取下一个任务 | `{reviewer_id}` | ReviewTask |
| `/api/v1/review/human/{task_id}` | GET | 获取任务详情 (含证据包) | - | `{task, evidence, machine_result}` |
| `/api/v1/review/human/{task_id}/decide` | POST | 提交决策 | `{decision, reason_category, reason_detail, internal_notes}` | `{success, task_id, status, decision, golden_test_result?}`【修订】 |
| `/api/v1/review/human/{task_id}/release` | POST | 释放任务锁 | - | `{status: "released"}` |
| `/api/v1/review/human/{task_id}/heartbeat` | POST | 续租锁 (心跳) | - | `{lock_expires_at}` |
| `/api/v1/review/human/{task_id}/escalate` | POST | 升级到高级审核 | `{reason}` | `{status: "escalated"}` |
| `/api/v1/review/human/batch-decide` | POST | 批量提交决策 | `{decisions: [{task_id, decision, ...}]}` | `{succeeded: [...], failed: [...]}` |

#### 申诉

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/appeal/submit` | POST | 创作者提交申诉 | `{content_id, reason}` | `{appeal_id, status}` |
| `/api/v1/appeal/{id}` | GET | 获取申诉详情 | - | AppealCase |
| `/api/v1/appeal/{id}/decide` | POST | 二审裁决 | `{decision, reason, overturn_type}` | `{status}` |
| `/api/v1/appeal/my` | GET | 创作者查看自己的申诉 | `?status=open` | `{appeals: [...]}` |

#### 策略管理

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/policy/versions` | GET | 获取策略版本列表 | `?status=active` | `{versions: [...]}` |
| `/api/v1/policy/versions` | POST | 创建新策略版本 (草稿) | PolicyVersion | `{version_id}` |
| `/api/v1/policy/versions/{id}/approve` | POST | 审批策略版本 | `{approver_id}` | `{status}` |
| `/api/v1/policy/versions/{id}/activate` | POST | 激活 (需已 Shadow) | - | `{status}` |
| `/api/v1/policy/versions/{id}/rollback` | POST | 回滚 | `{reason}` | `{status}` |
| `/api/v1/policy/dimensions` | GET | 获取维度注册表 | - | `{dimensions: [...]}` |
| `/api/v1/policy/dimensions` | POST | 注册新维度 | DimensionConfig | `{dimension_id}` |
| `/api/v1/policy/dispositions` | GET | 获取当前可用处置选项 | `?jurisdiction=global` | `{dispositions: ["pass", "block"]}` |

#### Shadow 与数据回流

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/shadow/reports` | GET | Shadow 报告列表 | `?offset=0&limit=20` 或 `?page=1&page_size=20` | `PaginatedResponse[ShadowReport]` |
| `/api/v1/shadow/reports/{id}` | GET | Shadow 报告详情 | - | ShadowReport |
| `/api/v1/shadow/reports/latest` | GET | 最新 Shadow 报告 | - | ShadowReport |
| `/api/v1/flywheel/samples` | GET | 回流样本列表 | `?source_type=disagreement` | `PaginatedResponse[FlywheelSample]` |
| `/api/v1/flywheel/export` | POST | 导出 JSONL | `{date_range, source_type}` | 文件下载 |

#### 审计

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/audit/events` | GET | 审计事件查询 | `?content_id=xxx&action=xxx&offset=0&limit=20` | `PaginatedResponse[AuditEvent]` |
| `/api/v1/audit/integrity/verify` | POST | 链式完整性校验 | `{start_id, end_id}` | `{valid, break_point}` |

#### SoR 模板

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/sor/templates` | GET | 获取 SoR 模板列表 | `?dimension_id=xxx&jurisdiction=global` | `{templates: [...]}` |
| `/api/v1/sor/templates/{id}` | GET | 获取单个 SoR 模板 | - | SoRTemplate |
| `/api/v1/sor/templates` | POST | 创建 SoR 模板 | `{dimension_id, template_body, jurisdiction, language}` | `{template_id}` |
| `/api/v1/sor/templates/{id}` | PUT | 更新 SoR 模板 | `{template_body, ...}` | `{status: "updated"}` |
| `/api/v1/sor/render` | POST | 渲染 SoR 文本预览 | `{template_id, variables: {...}}` | `{rendered_text}` |

#### 系统健康与告警

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/system/health` | GET | 系统健康状态 | - | `{status, components: {...}}` |
| `/api/v1/system/ready` | GET | 就绪探针 | - | `{ready: true}` |
| `/api/v1/system/alerts` | GET | 最近告警列表 | `?status=active&limit=20` | `{alerts: [...]}` |
| `/api/v1/system/alerts/{id}/acknowledge` | POST | 确认告警 | `{acknowledged_by}` | `{status: "acknowledged"}` |
|【修订】`/api/v1/system/dead-letters` | GET | 死信任务列表 | `?status=pending` | `PaginatedResponse[DeadLetterTask]` |
|【修订】`/api/v1/system/dead-letters/{id}/retry` | POST | 重试死信任务 | - | `{status: "retrying"}` |

#### 认证

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/auth/login` | POST | 用户登录 | `{username, password}` | `{access_token, refresh_token}` |
| `/api/v1/auth/refresh` | POST | 刷新令牌 | `{refresh_token}` | `{access_token}` |
| `/api/v1/auth/ws-token` | POST | 获取 WebSocket 短期令牌 | - (依赖 Bearer Token) | `{ws_token, expires_at}` |

#### 审核员管理

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/reviewers` | GET | 审核员列表 | `?tier=2&jurisdiction=US` | `{reviewers: [...]}` |
| `/api/v1/reviewers/{id}` | GET | 审核员详情 | - | ReviewerProfile |
| `/api/v1/reviewers/{id}/stats` | GET | 审核员统计 | `?period=weekly` | `{completed, accuracy, override_rate, ...}` |
| `/api/v1/reviewers/{id}/golden-stats` | GET | 黄金题统计 | - | `{total, correct, accuracy}` |

#### 质检

| 端点 | 方法 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/api/v1/quality/golden-results` | GET | 黄金题评估结果 | `?reviewer_id=xxx` | `{results: [...]}` |
| `/api/v1/quality/irr-report` | GET | IRR 一致性报告 | `?period=weekly` | `{kappa, dimensions: [...]}` |

### 5.2 WebSocket 接口 (PRD S1.E.4)

使用 Redis Pub/Sub 作为跨实例广播层, 解决 WebSocketManager 进程局部问题。

```python
# backend/app/common/websocket.py

import json
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect, Depends
from redis.asyncio import Redis as AsyncRedis
from app.common.auth import verify_ws_token

logger = logging.getLogger(__name__)

# Redis Pub/Sub 频道
WS_CHANNEL_BROADCAST = "ws:broadcast"
WS_CHANNEL_REVIEWER = "ws:reviewer:{reviewer_id}"
WS_CHANNEL_ROLE = "ws:role:{role}"

# 事件持久化 -- 用于断线重连补发
WS_EVENT_STREAM = "ws:events:{reviewer_id}"
WS_EVENT_STREAM_MAX_LEN = 200
WS_EVENT_STREAM_TTL_SECONDS = 3600  # 1 小时


class WebSocketManager:
    """
    分布式 WebSocket 连接管理器。
    
    设计:
      1. 每个 FastAPI 实例维护自己的 active_connections (本地 WebSocket 对象)
      2. 事件发布到 Redis Pub/Sub 频道, 所有实例订阅
      3. 每个实例收到 Redis 消息后, 转发给自己管理的本地连接
      4. 断线重连: 事件同时写入 Redis Stream, 客户端发送 RECONNECT_SYNC 时
         从 Stream 补发 lastSeenTimestamp 之后的事件
    """

    def __init__(self, redis: AsyncRedis):
        self.redis = redis
        self.active_connections: dict[str, WebSocket] = {}
        self.reviewer_roles: dict[str, list[str]] = {}
        self._subscriber_task: asyncio.Task | None = None

    async def start_subscriber(self):
        """
        启动 Redis Pub/Sub 订阅者协程。
        在 FastAPI 的 startup 事件中调用。
        """
        self._subscriber_task = asyncio.create_task(self._subscribe_loop())
        logger.info("WebSocket Redis Pub/Sub 订阅者已启动")

    async def stop_subscriber(self):
        """在 FastAPI 的 shutdown 事件中调用"""
        if self._subscriber_task:
            self._subscriber_task.cancel()

    async def _subscribe_loop(self):
        """
        持续监听 Redis Pub/Sub, 将消息转发到本实例的本地连接。
        """
        pubsub = self.redis.pubsub()
        await pubsub.psubscribe("ws:*")
        
        try:
            async for raw_message in pubsub.listen():
                if raw_message["type"] not in ("pmessage",):
                    continue
                
                channel = raw_message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                
                data = raw_message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    continue
                
                await self._dispatch_to_local(channel, message)
        except asyncio.CancelledError:
            await pubsub.unsubscribe()

    async def _dispatch_to_local(self, channel: str, message: dict):
        """将 Redis 消息分发到本实例的本地 WebSocket 连接"""
        
        if channel == WS_CHANNEL_BROADCAST:
            # 广播给所有本地连接
            for reviewer_id, ws in list(self.active_connections.items()):
                await self._safe_send(ws, reviewer_id, message)
        
        elif channel.startswith("ws:reviewer:"):
            # 定向推送
            target_reviewer = channel.split(":")[-1]
            if target_reviewer in self.active_connections:
                ws = self.active_connections[target_reviewer]
                await self._safe_send(ws, target_reviewer, message)
        
        elif channel.startswith("ws:role:"):
            # 角色广播
            target_role = channel.split(":")[-1]
            for reviewer_id, ws in list(self.active_connections.items()):
                if target_role in self.reviewer_roles.get(reviewer_id, []):
                    await self._safe_send(ws, reviewer_id, message)

    async def _safe_send(self, ws: WebSocket, reviewer_id: str, message: dict):
        """安全发送, 捕获连接断开异常"""
        try:
            await ws.send_json(message)
        except Exception:
            self.active_connections.pop(reviewer_id, None)
            self.reviewer_roles.pop(reviewer_id, None)

    async def connect(self, websocket: WebSocket, reviewer_id: str, roles: list[str]):
        await websocket.accept()
        self.active_connections[reviewer_id] = websocket
        self.reviewer_roles[reviewer_id] = roles

    async def disconnect(self, reviewer_id: str):
        self.active_connections.pop(reviewer_id, None)
        self.reviewer_roles.pop(reviewer_id, None)

    async def handle_reconnect_sync(
        self, reviewer_id: str, last_seen_timestamp_ms: int,
    ):
        """
        处理前端 RECONNECT_SYNC 消息。
        
        前端断线重连时发送 RECONNECT_SYNC, 携带 lastSeenTimestamp。
        从 Redis Stream 中读取该时间戳之后的所有事件, 逐条补发。
        """
        stream_key = WS_EVENT_STREAM.format(reviewer_id=reviewer_id)
        
        # Redis Stream ID 格式: {timestamp_ms}-{seq}
        min_id = f"{last_seen_timestamp_ms + 1}-0"
        
        events = await self.redis.xrange(stream_key, min=min_id, max="+")
        
        ws = self.active_connections.get(reviewer_id)
        if not ws:
            return
        
        for event_id, event_data in events:
            try:
                message = json.loads(event_data.get(b"data", b"{}"))
                await ws.send_json(message)
            except Exception:
                break
        
        logger.info(
            f"RECONNECT_SYNC: reviewer={reviewer_id}, "
            f"补发 {len(events)} 条事件 (since {last_seen_timestamp_ms})"
        )

    # ---- 事件发布方法 (发到 Redis, 不直接发本地) ----

    async def publish_case_lock_acquired(self, case_id: str, locked_by: str):
        """广播案件锁定事件"""
        message = {
            "ws_message_version": "1.0",
            "type": "CASE_LOCK_ACQUIRED",
            "timestamp_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            "payload": {
                "case_id": case_id,
                "locked_by_reviewer_id": locked_by,
            },
        }
        await self._publish_and_persist(WS_CHANNEL_BROADCAST, message, locked_by)

    async def publish_case_sla_tick(
        self, case_id: str, reviewer_id: str, remaining_ms: int,
    ):
        """定向推送 SLA 倒计时"""
        message = {
            "ws_message_version": "1.0",
            "type": "CASE_SLA_TICK",
            "timestamp_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            "payload": {
                "case_id": case_id,
                "remaining_sla_ms": remaining_ms,
                "is_warning": remaining_ms < 15 * 60 * 1000,
            },
        }
        channel = WS_CHANNEL_REVIEWER.format(reviewer_id=reviewer_id)
        await self._publish_and_persist(channel, message, reviewer_id)

    async def publish_critical_alert(
        self, content_id: str, category: str, roles: list[str],
    ):
        """角色广播 critical 告警"""
        message = {
            "ws_message_version": "1.0",
            "type": "CRITICAL_ALERT",
            "timestamp_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            "payload": {
                "content_id": content_id,
                "alert_level": "critical",
                "category": category,
            },
        }
        for role in roles:
            channel = WS_CHANNEL_ROLE.format(role=role)
            await self.redis.publish(channel, json.dumps(message))

    async def _publish_and_persist(
        self, channel: str, message: dict, reviewer_id: str,
    ):
        """
        发布到 Pub/Sub + 持久化到 Stream (用于断线重连补发)。
        """
        message_json = json.dumps(message)
        
        # 发布到 Pub/Sub (实时)
        await self.redis.publish(channel, message_json)
        
        # 持久化到 Stream (用于 RECONNECT_SYNC)
        stream_key = WS_EVENT_STREAM.format(reviewer_id=reviewer_id)
        await self.redis.xadd(
            stream_key,
            {"data": message_json},
            maxlen=WS_EVENT_STREAM_MAX_LEN,
        )
        await self.redis.expire(stream_key, WS_EVENT_STREAM_TTL_SECONDS)
```

```python
#【修订】WebSocket 端点处理 -- 双协议心跳 + 双模式认证

# backend/app/main.py (WebSocket 路由部分)

@app.websocket("/ws/review")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str,  # 查询参数传递 token (ws_token 或 login JWT)
):
    """
    【修订】WebSocket 端点 -- 同时支持 ws-token 和登录 JWT 认证。
    
    v3.0 修订 (关键问题 #2 -- WebSocket 认证失败):
    
    原方案问题:
      verify_ws_token() 要求 JWT payload 中 type == 'ws',
      但前端 MVP 阶段复用登录 JWT (不含 type='ws' 字段),
      导致所有 WebSocket 连接被拒绝 (code=4001)。
    
    修订: verify_ws_token() 改为双模式验证:
      1. 优先检查 type='ws' 的专用令牌
      2. 如果 type 字段不存在, 回退为普通登录 JWT 验证
      这样 MVP 阶段前端复用登录 JWT 可以正常连接,
      后续切换到专用 ws-token 也无需修改后端代码。
    
    【修订】心跳双协议 (集成问题 #3):
    
    原方案问题:
      后端处理 'HEARTBEAT' 并回复 'HEARTBEAT_ACK',
      前端发送 'PING' 并期望 'PONG'。消息类型名不匹配。
    
    修订: 后端同时处理 'HEARTBEAT' 和 'PING', 分别回复对应格式。
    """
    # 验证 Token (双模式)
    try:
        claims = verify_ws_token(token)
        reviewer_id = claims["sub"]
        roles = claims.get("roles", [])
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    ws_manager = app.state.ws_manager
    await ws_manager.connect(websocket, reviewer_id, roles)
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "RECONNECT_SYNC":
                # 处理断线重连同步请求
                last_seen = data.get("payload", {}).get("lastSeenTimestamp", 0)
                await ws_manager.handle_reconnect_sync(reviewer_id, last_seen)
            
            elif msg_type == "HEARTBEAT":
                await websocket.send_json({
                    "type": "HEARTBEAT_ACK",
                    "timestamp_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
                })
            
            #【修订】兼容前端 PING 消息
            elif msg_type == "PING":
                await websocket.send_json({
                    "type": "PONG",
                    "timestamp_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
                })
    
    except WebSocketDisconnect:
        await ws_manager.disconnect(reviewer_id)
```

### 5.3 API 版本管理

- 所有 API 路径以 `/api/v1/` 前缀
- 重大不兼容变更时新增 `/api/v2/`, 保持 v1 运行至少 6 个月
- EvidencePackage Schema 版本随 `schema_version` 字段管理, 与 API 版本独立

### 5.4 认证授权 (RBAC)

```python
# backend/app/common/auth.py

import jwt
import time
from enum import Enum
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer


class Role(str, Enum):
    """角色枚举 (PRD S7 角色矩阵子集)"""
    REVIEWER_T1 = "reviewer_t1"
    REVIEWER_T2 = "reviewer_t2"
    REVIEWER_T3 = "reviewer_t3"
    SENIOR_REVIEWER = "senior_reviewer"
    QA_REVIEWER = "qa_reviewer"
    ADJUDICATOR = "adjudicator"
    CRITICAL_SPECIALIST = "critical_specialist"
    APPEAL_TRIAGE = "appeal_triage"
    APPEAL_REVIEWER = "appeal_reviewer"
    POLICY_PM = "policy_pm"
    POLICY_APPROVER = "policy_approver"
    OPS_ADMIN = "ops_admin"
    COMPLIANCE_AUDITOR = "compliance_auditor"
    SYSTEM = "system"


# 端点 -> 允许的角色
ENDPOINT_PERMISSIONS = {
    "review.human.queue": {Role.REVIEWER_T1, Role.REVIEWER_T2, Role.REVIEWER_T3, Role.SENIOR_REVIEWER},
    "review.human.decide": {Role.REVIEWER_T1, Role.REVIEWER_T2, Role.REVIEWER_T3, Role.SENIOR_REVIEWER},
    "review.human.batch_decide": {Role.REVIEWER_T2, Role.REVIEWER_T3, Role.SENIOR_REVIEWER},
    "appeal.decide": {Role.APPEAL_REVIEWER, Role.REVIEWER_T3},
    "policy.create": {Role.POLICY_PM},
    "policy.approve": {Role.POLICY_APPROVER},
    "audit.read": {Role.COMPLIANCE_AUDITOR, Role.POLICY_PM},
    "shadow.read": {Role.POLICY_PM, Role.OPS_ADMIN},
    "evidence.csam_access": {Role.CRITICAL_SPECIALIST, Role.COMPLIANCE_AUDITOR},
    "system.alerts.acknowledge": {Role.OPS_ADMIN},
    "system.dead_letters": {Role.OPS_ADMIN},
    "reviewers.manage": {Role.OPS_ADMIN, Role.SENIOR_REVIEWER},
    "quality.golden_stats": {Role.QA_REVIEWER, Role.OPS_ADMIN},
}


def require_roles(*allowed_roles: Role):
    """角色校验装饰器"""
    async def checker(current_user = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"角色 {current_user.role} 无权执行此操作",
            )
        return current_user
    return checker


def generate_ws_token(user_id: str, roles: list[str], secret: str) -> dict:
    """
    【修订】生成 WebSocket 短期令牌。
    
    v3.0 修订 (集成问题 #7): 有效期从 5 分钟延长到 30 分钟。
    
    原方案问题:
      ws-token 有效期 5 分钟, 仅用于建立连接。但如果审核员在审核过程中
      刷新页面 (如审核一个复杂案件超过 5 分钟), 页面刷新后需要重新获取
      ws-token 才能重连 WebSocket。5 分钟过短, 导致频繁的 ws-token 请求。
      
    修订: 有效期延长到 30 分钟, 覆盖一个完整的案件审核会话。
    token 仅用于握手认证, 连接建立后不再校验 token 有效期 (WebSocket
    连接的活跃性通过心跳维护)。30 分钟足够覆盖页面刷新场景,
    同时不会过长导致安全风险。
    """
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    payload = {
        "sub": user_id,
        "roles": roles,
        "type": "ws",
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, secret, algorithm="HS256")
    return {
        "ws_token": token,
        "expires_at": expires_at.isoformat(),
    }


def verify_ws_token(token: str) -> dict:
    """
    【修订】验证 WebSocket 令牌 -- 双模式: ws-token 或登录 JWT。
    
    v3.0 修订 (关键问题 #2):
    
    原方案: 严格要求 payload.type == 'ws', 拒绝所有不含 type 字段的 JWT。
    前端 MVP 阶段复用登录 JWT (无 type 字段), 所有连接被拒绝。
    
    修订: 双模式验证
      1. 如果 payload 包含 type='ws' -> 按 ws-token 验证 (专用令牌)
      2. 如果 payload 不含 type 字段 -> 按登录 JWT 验证 (MVP 兼容)
      3. 如果 payload.type 存在但不是 'ws' -> 拒绝 (其他类型令牌不接受)
    """
    from app.config import settings
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        
        token_type = payload.get("type")
        
        if token_type == "ws":
            # 模式 1: 专用 ws-token (推荐)
            return payload
        elif token_type is None:
            # 模式 2: 登录 JWT (MVP 兼容, 无 type 字段)
            # 确保包含必要字段
            if "sub" not in payload:
                raise ValueError("Login JWT missing 'sub' field")
            return payload
        else:
            # 其他类型令牌 (如 refresh token 等), 拒绝
            raise ValueError(f"Unsupported token type: {token_type}")
            
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
```

---

## 六、基础设施层

### 6.1 消息队列: Redis Streams (MVP) + Kafka (V2)

**MVP 选择 Redis Streams 的理由**: 团队已引入 Redis 做缓存, Redis Streams 提供消息队列能力, 无需额外运维 Kafka 集群。V2 阶段当日处理量超过 100 万条时迁移 Kafka。

```python
# Topic (Stream) 设计
STREAMS = {
    "video:ingested":           "视频摄取完成, 触发证据提取",
    "evidence:extracted":       "证据包就绪, 触发基础安全初筛",
    "safety:filtered":          "初筛完成, 触发 LLM 审查",
    "llm:reviewed":             "LLM 审查完成, 触发规则聚合",
    "decision:made":            "机审裁决产出, 触发路由",
    "review:human:enqueued":    "案件入人审队列",
    "review:human:decided":     "人审决策完成, 触发回流",
    "appeal:submitted":         "申诉提交, 触发分配",
    "appeal:decided":           "申诉裁决, 触发恢复连锁",
    "flywheel:sample:created":  "回流样本产出",
    "critical:alert":           "高危告警",
}
```

### 6.2 缓存策略 (Redis)

| 缓存场景 | Key 模式 | TTL | 策略 |
|---------|---------|-----|------|
| 策略版本配置 | `policy:active:{jurisdiction}` | 5 分钟 | Write-through, 策略变更时主动失效 |
| 维度注册表 | `dimension:registry:all` | 10 分钟 | 策略热加载时刷新 |
| 审核员会话 | `reviewer:session:{id}` | 1 小时 | JWT 续签时刷新 |
| 案件锁状态 | `lock:case:{task_id}` | 30 分钟 | 分布式锁, 心跳续租 |
| CSAM 曝光计数 | `csam:exposure:{reviewer_id}:{date}` | 24 小时 | 原子 INCR, 持久化到 DB |
| 重复内容指纹 | `dedup:fingerprint:{hash}` | 30 天 | 布隆过滤器 + 精确查询 |
| 限流计数 | `ratelimit:{endpoint}:{user_id}` | 按窗口 | 令牌桶, 滑动窗口 |
| 熔断器状态 | `circuit:{name}:*` | 按配置 | 滑动窗口分布式【修订】|
| WebSocket 事件 | `ws:events:{reviewer_id}` | 1 小时 | Redis Stream, 断线重连补发 |

### 6.3 对象存储 (MinIO / S3)

```
存储桶设计:
├── vgp-uploads/                     # 原始上传视频
│   └── {content_id}/video.mp4
├── vgp-evidence/                    # 证据包存储
│   └── {content_id}/{snapshot_id}/
│       ├── frames/                  # 关键帧图片
│       │   ├── frm_001.jpg
│       │   └── frm_002.jpg
│       ├── evidence_package.json    # 完整证据包
│       └── metadata.json
├── vgp-csam-vault/                  # CSAM 独立加密桶
│   └── (独立加密, 独立访问控制)
│   └── (仅 critical_specialist + compliance_auditor 可访问)
└── vgp-flywheel/                    # 回流训练数据
    └── exports/
        └── {date}/samples.jsonl
```

### 6.4 监控告警 (Prometheus + Grafana)

```python
# 自定义业务指标
METRICS = {
    # 机审流水线
    "vgp_pipeline_duration_seconds":          "机审流水线总耗时",
    "vgp_evidence_extraction_seconds":        "阶段1 证据提取耗时",
    "vgp_safety_filter_seconds":              "阶段2 初筛耗时",
    "vgp_llm_review_seconds":                 "阶段3 LLM 审查耗时",
    "vgp_llm_tokens_used_total":              "LLM Token 消耗总量",
    "vgp_pipeline_decision_total":            "决策分布 (pass/block/review)",
    
    # 人审工作台
    "vgp_human_review_queue_size":            "人审队列深度",
    "vgp_human_review_sla_violations_total":  "SLA 违规次数",
    "vgp_human_review_override_rate":         "人审推翻机审比率",
    "vgp_reviewer_fatigue_breaks_total":      "强制休息触发次数",
    
    # 申诉
    "vgp_appeal_overturn_rate":               "申诉改判率",
    "vgp_appeal_resolution_seconds":          "申诉解决耗时",
    
    # 数据回流
    "vgp_flywheel_samples_total":             "回流样本总数",
    "vgp_flywheel_quality_gate_pass_rate":    "质量门通过率",
    
    # 系统健康
    "vgp_csam_detection_latency_seconds":     "CSAM 检测到上报延迟 (P0 合规)",
    "vgp_ws_connections_active":              "活跃 WebSocket 连接数",
    "vgp_circuit_breaker_state":              "熔断器状态 (0=closed, 1=open, 0.5=half_open)",
    "vgp_rate_limit_rejected_total":          "限流拒绝次数",
    "vgp_golden_test_accuracy":               "黄金题准确率",
    "vgp_irr_kappa_score":                    "IRR Fleiss' Kappa 分数",
    #【修订】
    "vgp_dead_letter_tasks_total":            "死信任务累计数",
    "vgp_circuit_breaker_failure_ratio":      "熔断器窗口内失败比率",
}

# 告警规则
ALERT_RULES = {
    "P0_CSAM_REPORT_OVERDUE": {
        "condition": "vgp_csam_detection_latency_seconds > LEGAL_TBD",
        "severity": "critical",
        "notify": ["compliance_team", "oncall"],
    },
    "P1_PIPELINE_SLA_BREACH": {
        "condition": "vgp_safety_filter_seconds:p95 > 3 for 5m",
        "severity": "high",
        "notify": ["sre_oncall"],
    },
    "P2_QUEUE_BACKLOG": {
        "condition": "vgp_human_review_queue_size > 10000",
        "severity": "medium",
        "notify": ["ops_admin"],
    },
    "P1_CIRCUIT_BREAKER_OPEN": {
        "condition": "vgp_circuit_breaker_state{name='anthropic_llm'} == 1 for 2m",
        "severity": "high",
        "notify": ["sre_oncall"],
    },
    "P2_GOLDEN_TEST_ACCURACY_LOW": {
        "condition": "vgp_golden_test_accuracy < 0.70 for 1h",
        "severity": "medium",
        "notify": ["qa_reviewer", "ops_admin"],
    },
    #【修订】
    "P1_DEAD_LETTER_ACCUMULATION": {
        "condition": "increase(vgp_dead_letter_tasks_total[1h]) > 10",
        "severity": "high",
        "notify": ["sre_oncall", "ops_admin"],
    },
}
```

### 6.5【修订】健康检查探针 (异步)

```python
# backend/app/common/health.py

from datetime import datetime, timezone
from fastapi import APIRouter
from sqlalchemy import text
from redis.asyncio import Redis as AsyncRedis

router = APIRouter()


@router.get("/api/v1/system/health")
async def health_check():
    """
    【修订】系统健康检查端点 -- 全异步实现。
    
    v3.0 修订 (专家评审关键问题 -- 同步 Redis 阻塞事件循环):
    
    原方案问题:
      使用 redis.Redis.from_url() (同步客户端) 在 async def 中调用 r.ping(),
      这是阻塞调用, 会阻塞 asyncio 事件循环, 导致同一事件循环上的所有
      其他协程 (包括正在处理的 HTTP 请求和 WebSocket) 被挂起。
      在高并发场景下, 健康检查本身成为性能瓶颈。
    
    修订: 使用 redis.asyncio.Redis 异步客户端, 所有 IO 操作不阻塞事件循环。
    """
    components = {}
    overall_healthy = True
    
    # 1. PostgreSQL (使用异步 engine)
    try:
        from app.database import async_engine
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        components["postgresql"] = {"status": "healthy"}
    except Exception as e:
        components["postgresql"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False
    
    # 2. Redis (异步客户端)
    try:
        from app.config import settings
        r = AsyncRedis.from_url(settings.REDIS_URL)
        try:
            await r.ping()
            components["redis"] = {"status": "healthy"}
        finally:
            await r.aclose()
    except Exception as e:
        components["redis"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False
    
    # 3. Object Storage
    try:
        from app.config import settings
        import aioboto3
        session = aioboto3.Session()
        async with session.client("s3", endpoint_url=settings.S3_ENDPOINT) as s3:
            await s3.head_bucket(Bucket="vgp-uploads")
        components["object_storage"] = {"status": "healthy"}
    except Exception as e:
        components["object_storage"] = {"status": "degraded", "error": str(e)}
    
    # 4. Celery Workers (通过 Redis 检查)
    try:
        from app.config import settings
        r = AsyncRedis.from_url(settings.REDIS_URL)
        try:
            # 检查 Celery 心跳 key 是否存在
            worker_keys = await r.keys("celery-task-meta-*")
            components["celery_workers"] = {
                "status": "healthy" if worker_keys else "degraded",
            }
        finally:
            await r.aclose()
    except Exception as e:
        components["celery_workers"] = {"status": "unknown", "error": str(e)}
    
    return {
        "status": "healthy" if overall_healthy else "unhealthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
    }


@router.get("/api/v1/system/ready")
async def readiness_check():
    """
    就绪探针 -- 全异步实现。
    
    Kubernetes / ALB 用于判断实例是否可以接收流量。
    只检查最关键的依赖 (PostgreSQL + Redis)。
    """
    try:
        from app.database import async_engine
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        
        from app.config import settings
        r = AsyncRedis.from_url(settings.REDIS_URL)
        try:
            await r.ping()
        finally:
            await r.aclose()
        
        return {"ready": True}
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"ready": False},
        )
```

### 6.6 限流器

```python
# backend/app/common/rate_limiter.py

import time
import logging
from fastapi import Request, HTTPException, status
from redis.asyncio import Redis as AsyncRedis

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    令牌桶限流器。
    
    应用场景:
      - 视频上传: 防止恶意批量上传 (10 次/分钟/用户)
      - 申诉提交: 防止申诉滥用 (5 次/小时/用户)
      - 登录: 防止暴力破解 (10 次/分钟/IP)
      - 人审决策: 防止自动化脚本 (60 次/分钟/用户)
      - WebSocket Token: 防止令牌滥刷 (10 次/分钟/用户)
    """

    # 端点级限流配置
    RATE_LIMITS = {
        "content.upload": {"max_requests": 10, "window_seconds": 60, "by": "user"},
        "appeal.submit": {"max_requests": 5, "window_seconds": 3600, "by": "user"},
        "auth.login": {"max_requests": 10, "window_seconds": 60, "by": "ip"},
        "auth.ws_token": {"max_requests": 10, "window_seconds": 60, "by": "user"},
        "review.human.decide": {"max_requests": 60, "window_seconds": 60, "by": "user"},
        "review.human.batch_decide": {"max_requests": 10, "window_seconds": 60, "by": "user"},
    }

    def __init__(self, redis_client: AsyncRedis):
        self.redis = redis_client

    async def check_rate_limit(
        self,
        endpoint: str,
        user_id: str = "",
        ip_address: str = "",
    ) -> bool:
        """
        检查请求是否超过限流阈值。
        
        Returns:
            True: 允许通过
            
        Raises:
            HTTPException(429): 超过限流
        """
        config = self.RATE_LIMITS.get(endpoint)
        if not config:
            return True
        
        key_identifier = user_id if config["by"] == "user" else ip_address
        if not key_identifier:
            return True
        
        cache_key = f"ratelimit:{endpoint}:{key_identifier}"
        window = config["window_seconds"]
        max_requests = config["max_requests"]
        
        # 滑动窗口计数器
        now = time.time()
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(cache_key, 0, now - window)
        pipe.zadd(cache_key, {str(now): now})
        pipe.zcard(cache_key)
        pipe.expire(cache_key, window)
        results = await pipe.execute()
        
        current_count = results[2]
        
        if current_count > max_requests:
            logger.warning(
                f"限流触发: endpoint={endpoint}, "
                f"identifier={key_identifier}, count={current_count}"
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁, 请 {window} 秒后重试",
                headers={"Retry-After": str(window)},
            )
        
        return True
```

### 6.7【修订】死信队列处理器

```python
# backend/app/common/dead_letter.py

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class DeadLetterService:
    """
    【修订】死信队列服务。
    
    原方案问题 (专家评审次要问题):
      Celery 任务耗尽所有重试后, 默认静默失败。没有 on_failure 处理器
      或死信队列记录失败任务, 导致永久失败的视频无人知晓, 无法人工干预。
    
    修订:
      1. 每个 Celery chain 绑定 link_error 回调, 永久失败时触发
      2. 失败信息写入 dead_letter_tasks 表
      3. 提供 API (/system/dead-letters) 让运维人员查看和重试
      4. 超过阈值时触发告警 (P1_DEAD_LETTER_ACCUMULATION)
    """
    
    def record_failure(
        self,
        db,
        task_name: str,
        task_id: str,
        video_id: str,
        exception_type: str,
        exception_message: str,
        traceback: str,
        retry_count: int,
    ) -> None:
        """记录永久失败的任务"""
        import uuid
        from app.models.system import DeadLetterTaskModel
        
        dl = DeadLetterTaskModel(
            task_name=task_name,
            celery_task_id=task_id,
            video_id=video_id,
            exception_type=exception_type,
            exception_message=exception_message,
            traceback=traceback or "",
            retry_count=retry_count,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        db.add(dl)
        
        logger.error(
            f"死信记录: task={task_name}, video={video_id}, "
            f"error={exception_type}: {exception_message}, "
            f"retries_exhausted={retry_count}"
        )
    
    async def retry_dead_letter(self, db, dead_letter_id: int) -> dict:
        """重试死信任务"""
        from app.models.system import DeadLetterTaskModel
        
        dl = db.query(DeadLetterTaskModel).filter(
            DeadLetterTaskModel.id == dead_letter_id
        ).first()
        
        if not dl:
            raise ValueError(f"死信任务不存在: {dead_letter_id}")
        
        if dl.status != "pending":
            raise ValueError(f"死信任务状态不允许重试: {dl.status}")
        
        # 根据任务类型重新触发
        from app.tasks.review_tasks import run_machine_review_pipeline
        if dl.video_id:
            run_machine_review_pipeline(dl.video_id)
        
        dl.status = "retried"
        dl.resolved_at = datetime.now(timezone.utc)
        db.commit()
        
        return {"status": "retrying", "video_id": dl.video_id}
```

---

## 七、可靠性与容错设计

### 7.1【修订】熔断器 (Circuit Breaker) -- 滑动窗口

```python
# backend/app/common/circuit_breaker.py

import time
import json
import logging
from enum import Enum
from functools import wraps
from typing import Callable
from redis.asyncio import Redis as AsyncRedis

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"         # 正常
    OPEN = "open"             # 熔断
    HALF_OPEN = "half_open"   # 试探


class CircuitBreaker:
    """
    【修订】Redis 分布式滑动窗口熔断器。
    
    v2.0: 引入 Redis 分布式存储, 所有实例共享状态。
    
    v3.0 修订 (专家评审关键问题 -- reset-on-any-success 缺陷):
    
    原方案问题:
      在 CLOSED 状态下, _on_success() 将 failure_count 重置为 0。
      这意味着如果阈值 = 5, 而 4 次失败后夹杂 1 次成功,
      failure_count 被重置为 0, 下一轮又需要连续 5 次失败才能触发熔断。
      即使服务 80% 不可用 (每 5 次调用 4 次失败), 熔断器也永远不会打开。
    
    修订: 采用滑动时间窗口 + 失败率机制替代简单计数器。
      - 在配置的时间窗口内 (如 60 秒), 记录所有调用结果
      - 当窗口内失败率超过阈值 (如 50%) 且最小调用次数满足要求时, 触发熔断
      - 使用 Redis Sorted Set 存储调用时间戳, 自动清理过期记录
      - 成功调用不会重置失败记录, 而是作为正常样本参与失败率计算
    
    应用场景:
      - LLM API 调用 (Anthropic API 不可用时熔断)
      - 云内容安全 API 调用
      - 外部信用引擎查询
      
    熔断后降级策略:
      - LLM 不可用: verdict 置 UNCERTAIN, 路由人审
      - 云 API 不可用: 跳过初筛, 直接进 LLM 审查
      - 信用引擎不可用: 按最严基线机审
    """

    def __init__(
        self,
        redis_client: AsyncRedis,
        failure_rate_threshold: float = 0.50,
        minimum_calls: int = 5,
        window_seconds: int = 60,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
        expected_exception: type = Exception,
        name: str = "default",
    ):
        """
        Args:
            failure_rate_threshold: 窗口内失败率阈值 (0.0 ~ 1.0), 超过则熔断
            minimum_calls: 窗口内最少调用次数, 不足时不计算失败率
            window_seconds: 滑动窗口大小 (秒)
            recovery_timeout: 熔断后等待恢复的超时时间 (秒)
            half_open_max_calls: 半开状态下允许的试探调用次数
            expected_exception: 计入失败的异常类型
            name: 熔断器名称 (用于 Redis key 命名空间)
        """
        self.redis = redis_client
        self.failure_rate_threshold = failure_rate_threshold
        self.minimum_calls = minimum_calls
        self.window_seconds = window_seconds
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exception = expected_exception
        self.name = name
        
        # Redis keys
        self._state_key = f"circuit:{name}:state"
        self._success_key = f"circuit:{name}:success"     # Sorted Set
        self._failure_key = f"circuit:{name}:failure"      # Sorted Set
        self._last_failure_key = f"circuit:{name}:last_failure"
        self._half_open_success_key = f"circuit:{name}:half_open_success"

    async def _get_state(self) -> CircuitState:
        """从 Redis 获取当前熔断状态"""
        raw = await self.redis.get(self._state_key)
        if raw is None:
            return CircuitState.CLOSED
        return CircuitState(raw.decode() if isinstance(raw, bytes) else raw)

    async def _set_state(self, state: CircuitState):
        """设置熔断状态到 Redis"""
        await self.redis.set(self._state_key, state.value)

    def __call__(self, func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            state = await self._get_state()
            
            if state == CircuitState.OPEN:
                last_failure = float(await self.redis.get(self._last_failure_key) or 0)
                if time.time() - last_failure > self.recovery_timeout:
                    await self._set_state(CircuitState.HALF_OPEN)
                    await self.redis.set(self._half_open_success_key, 0)
                    logger.info(f"熔断器 [{self.name}] 进入半开状态")
                else:
                    raise CircuitBreakerOpenError(
                        f"熔断器 [{self.name}] 已开启, 请求被拒绝"
                    )
            
            try:
                result = await func(*args, **kwargs)
                await self._on_success()
                return result
            except self.expected_exception as e:
                await self._on_failure()
                raise e
        
        return wrapper

    async def _on_success(self):
        state = await self._get_state()
        now = time.time()
        
        if state == CircuitState.HALF_OPEN:
            success_count = await self.redis.incr(self._half_open_success_key)
            if success_count >= self.half_open_max_calls:
                await self._set_state(CircuitState.CLOSED)
                # 清理滑动窗口数据, 重新开始统计
                await self.redis.delete(
                    self._success_key, self._failure_key,
                    self._half_open_success_key,
                )
                logger.info(f"熔断器 [{self.name}] 恢复关闭")
        elif state == CircuitState.CLOSED:
            #【修订】成功调用记入滑动窗口, 而非重置失败计数
            await self.redis.zadd(self._success_key, {str(now): now})
            # 清理过期数据
            cutoff = now - self.window_seconds
            await self.redis.zremrangebyscore(self._success_key, 0, cutoff)

    async def _on_failure(self):
        now = time.time()
        await self.redis.set(self._last_failure_key, str(now))
        
        state = await self._get_state()
        
        if state == CircuitState.HALF_OPEN:
            # 半开状态下任何失败立即重新打开
            await self._set_state(CircuitState.OPEN)
            logger.warning(f"熔断器 [{self.name}] 半开失败, 重新打开")
            return
        
        #【修订】记录失败到滑动窗口, 并计算失败率
        await self.redis.zadd(self._failure_key, {str(now): now})
        
        # 清理过期数据
        cutoff = now - self.window_seconds
        await self.redis.zremrangebyscore(self._failure_key, 0, cutoff)
        await self.redis.zremrangebyscore(self._success_key, 0, cutoff)
        
        # 计算窗口内的失败率
        failure_count = await self.redis.zcard(self._failure_key)
        success_count = await self.redis.zcard(self._success_key)
        total_calls = failure_count + success_count
        
        if total_calls < self.minimum_calls:
            # 调用次数不足, 不触发熔断
            return
        
        failure_rate = failure_count / total_calls
        
        if failure_rate >= self.failure_rate_threshold:
            await self._set_state(CircuitState.OPEN)
            logger.warning(
                f"熔断器 [{self.name}] 已开启: "
                f"窗口内失败率 {failure_rate:.1%} "
                f"({failure_count}/{total_calls}), "
                f"阈值 {self.failure_rate_threshold:.1%}"
            )


class CircuitBreakerOpenError(Exception):
    pass


# 使用示例
# redis_client = AsyncRedis.from_url(settings.REDIS_URL)
# llm_circuit = CircuitBreaker(
#     redis_client=redis_client,
#     failure_rate_threshold=0.50,   # 50% 失败率触发熔断
#     minimum_calls=5,               # 窗口内至少 5 次调用才计算
#     window_seconds=60,             # 60 秒滑动窗口
#     recovery_timeout=30,           # 30 秒后尝试恢复
#     name="anthropic_llm",
# )
```

### 7.2 重试机制

```python
# backend/app/common/retry.py

import asyncio
import random
import logging
from functools import wraps
from typing import Callable, Type

logger = logging.getLogger(__name__)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """
    指数退避重试装饰器。
    
    参数:
      max_retries: 最大重试次数
      base_delay: 基础延迟 (秒)
      max_delay: 最大延迟 (秒)
      exponential_base: 指数基数
      jitter: 是否添加随机抖动 (防止雷群效应)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(
                            f"{func.__name__} 重试耗尽 ({max_retries} 次): {e}"
                        )
                        raise
                    
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay,
                    )
                    if jitter:
                        delay = delay * (0.5 + random.random())
                    
                    logger.warning(
                        f"{func.__name__} 第 {attempt + 1} 次重试, "
                        f"等待 {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)
            
            raise last_exception
        
        return wrapper
    return decorator
```

### 7.3 幂等性设计

幂等键生成方式基于客户端提供的 `Idempotency-Key` 请求头, 而非仅由 method+path+user_id 拼接。

```python
# backend/app/common/idempotency.py

import hashlib
import json
from datetime import timedelta
from typing import Optional
from fastapi import Request, HTTPException, status
from redis.asyncio import Redis as AsyncRedis


class IdempotencyManager:
    """
    幂等性管理器。
    
    策略:
      1. 优先使用客户端提供的 Idempotency-Key 请求头 (行业标准)
      2. 如果客户端未提供, 则基于 method + path + user_id + body_hash 生成
      3. 关键写入端点 (upload, decide, appeal) 强制要求 Idempotency-Key 头
    
    应用场景:
      - 视频上传接口: 防止重复上传
      - 人审决策提交: 防止重复提交
      - 申诉提交: 防止重复申诉
      
    实现: Redis + idempotency_key
    """

    # 强制要求 Idempotency-Key 头的端点
    REQUIRED_ENDPOINTS = {
        "/api/v1/content/upload",
        "/api/v1/review/human/{task_id}/decide",
        "/api/v1/review/human/batch-decide",
        "/api/v1/appeal/submit",
    }

    def __init__(self, redis_client: AsyncRedis, ttl: timedelta = timedelta(hours=24)):
        self.redis = redis_client
        self.ttl = ttl

    async def check_and_set(self, idempotency_key: str, response_data: dict) -> dict | None:
        """
        检查幂等键。
        
        返回:
          - None: 首次请求, 已设置幂等键
          - dict: 重复请求, 返回之前的响应
        """
        cache_key = f"idempotency:{idempotency_key}"
        
        existing = await self.redis.get(cache_key)
        if existing:
            return json.loads(existing)
        
        await self.redis.setex(
            cache_key,
            int(self.ttl.total_seconds()),
            json.dumps(response_data),
        )
        return None

    @staticmethod
    async def extract_key(request: Request, user_id: str) -> str:
        """
        从请求中提取或生成幂等键。
        
        优先级:
          1. 客户端提供的 Idempotency-Key 请求头 (推荐, 行业标准)
          2. 自动生成: method + path + user_id + body_hash
          
        强制端点: 对于 REQUIRED_ENDPOINTS 中的端点,
        如果客户端未提供 Idempotency-Key 头, 返回 400 错误。
        """
        client_key = request.headers.get("Idempotency-Key")
        
        if client_key:
            # 使用客户端提供的幂等键 (带用户隔离)
            return hashlib.sha256(
                f"{user_id}:{client_key}".encode()
            ).hexdigest()
        
        # 检查是否为强制要求端点
        path = request.url.path
        # 替换路径参数为通配
        for required in IdempotencyManager.REQUIRED_ENDPOINTS:
            if "{" in required:
                # 简单匹配: 去掉路径参数后比较前缀
                prefix = required.split("{")[0]
                if path.startswith(prefix):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="此端点要求提供 Idempotency-Key 请求头",
                    )
            elif path == required:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="此端点要求提供 Idempotency-Key 请求头",
                )
        
        # 非强制端点: 自动生成 (包含 body hash)
        body = await request.body()
        body_hash = hashlib.sha256(body).hexdigest()[:16] if body else "empty"
        
        content = f"{request.method}:{path}:{user_id}:{body_hash}"
        return hashlib.sha256(content.encode()).hexdigest()
```

### 7.4 数据一致性保证

```
事务策略:
1. 机审裁决 + 审计日志: 同一数据库事务, 原子提交
2. 人审决策 + 状态更新 + 审计日志: 同一事务
3. 申诉改判 + 恢复连锁四链:
   - 改判决策 + 审计日志: 同一事务 (强一致)
   - 恢复可见性 + 账号回滚 + 质检反馈 + 样本回流: 通过消息队列异步执行 (最终一致)
   - 恢复连锁的每一步都有独立重试机制
4. 数据回流: 最终一致性
   - 样本写入 flywheel_staging 暂存区 (事务内)
   - ETL 批处理写入训练集 (异步)

乐观锁:
- ContentItem.version 字段实现乐观锁
- 处置执行时校验版本号, 并发冲突时重试
- critical 短路拥有最高写优先级, 绕过乐观锁直接 CAS
```

### 7.5 优雅降级

| 故障场景 | 降级策略 | 影响 |
|---------|---------|------|
| LLM API 不可用 | 跳过阶段3, 仅用阶段2初筛结果决策; 低置信案件全部路由人审 | 人审队列压力增大, 自动处置率下降 |
| 云安全 API 不可用 | 跳过阶段2, 直接进阶段3 LLM 审查; CSAM 哈希比对走本地库不受影响 | LLM 成本上升 |
| Redis 不可用 | 策略配置回退到数据库直查; 案件锁退化为数据库行锁; 熔断器退化为进程本地 | 性能下降但不中断 |
| 对象存储不可用 | 证据包本地暂存, 恢复后批量上传; 新上传视频排队等待 | 新视频处理延迟 |
| PostgreSQL 主库不可用 | 读请求切到只读副本; 写请求排队等待主库恢复 | 新审核暂停, 查询不受影响 |

---

## 八、前后端集成契约

本章节明确前后端之间所有集成约定, 避免集成时出现不一致。

### 8.1 处置选项对齐

```
MVP 阶段:
  后端 HumanReviewDecisionModel.decision: "pass" | "block" (仅两种)
  前端 DispositionPanel: 限制为 PASS / BLOCK 两个选项
  
  前端调用 GET /api/v1/policy/dispositions?jurisdiction=global 获取当前可用处置选项,
  后端 MVP 返回: {"dispositions": [{"value": "pass", "label": "通过"}, {"value": "block", "label": "拦截"}]}
  
Post-MVP:
  后端扩展 decision 字段, 接受完整 7 级处置矩阵
  前端 DispositionPanel 按后端返回的 dispositions 列表动态渲染
  过渡期保持向后兼容: "pass" 和 "block" 始终有效
```

### 8.2【修订】分页协议 (双模式兼容)

```
【修订】后端同时支持 offset-based 和 page-based 两种分页参数:
  
  请求模式 A (offset-based, 推荐):
    GET /api/v1/xxx?offset=0&limit=20&sort=created_at&order=desc
  
  请求模式 B (page-based, 兼容前端):
    GET /api/v1/xxx?page=1&page_size=20&sort=created_at&order=desc
  
  后端使用 parse_pagination_params() 统一解析, 
  page=1&page_size=20 被内部转换为 offset=0&limit=20。
  
  响应同时包含两套字段:
  {
    "items": [...],
    "total": 150,
    "offset": 0,
    "limit": 20,
    "next_offset": 20,    // null 表示最后一页
    "page": 1,            // 兼容前端 page-based
    "page_size": 20,
    "total_pages": 8
  }
  
  前端对接方式:
    使用 items (不是 tasks) 读取数据列表。
    page-based: 直接读取 page/total_pages
    offset-based: getNextPageParam = (lastPage) => lastPage.next_offset ?? undefined
```

### 8.3【修订】WebSocket 协议 (双协议心跳 + 双模式认证)

```
连接建立 (双模式认证):
  模式 A (推荐, post-MVP):
    1. 前端调用 POST /api/v1/auth/ws-token 获取短期 JWT (30 分钟有效)
    2. 前端连接 ws://host/ws/review?token={ws_token}
    3. 后端验证 token (type='ws'), 接受连接
  
  模式 B (MVP 兼容):
    1. 前端直接使用登录 JWT (无 type 字段)
    2. 前端连接 ws://host/ws/review?token={login_jwt}
    3. 后端验证 token (无 type 字段, 回退为登录 JWT 验证), 接受连接

消息类型 (后端 -> 前端):
  - CASE_LOCK_ACQUIRED: 案件锁广播
  - CASE_LOCK_RELEASED: 案件锁释放
  - CASE_SLA_TICK: SLA 倒计时 (定向推送)
  - CRITICAL_ALERT: critical 告警 (角色广播)
  - SHADOW_REPORT_READY: Shadow 报告就绪
  - HEARTBEAT_ACK: 心跳回复 (对应 HEARTBEAT)
  - PONG: 心跳回复 (对应 PING)          【修订】兼容前端

消息类型 (前端 -> 后端):
  - RECONNECT_SYNC: 断线重连同步 (payload: {lastSeenTimestamp})
  - HEARTBEAT: 心跳 (后端回复 HEARTBEAT_ACK)
  - PING: 心跳 (后端回复 PONG)           【修订】兼容前端
```

### 8.4 证据包 API 字段映射

```
GET /api/v1/evidence/{ep_id} 返回所有 JSONB 字段:

  前端 EvidencePackage.truncated_modalities  <->  后端 EvidencePackageModel.truncated_modalities
  前端 EvidencePackage.modality_availability <->  后端 EvidencePackageModel.modality_availability
  前端 EvidencePackage.frames                <->  后端 EvidencePackageModel.frames
  前端 EvidencePackage.asr_transcript        <->  后端 EvidencePackageModel.asr_transcript
  前端 EvidencePackage.ocr_results           <->  后端 EvidencePackageModel.ocr_results
  
  所有 JSONB 字段在 EvidencePackageResponse Schema 中显式声明,
  不存在 "JSONB 有但 API 不暴露" 的情况。
```

### 8.5 SoR 模板集成

```
前端 SoRPreview / ExternalReasonForm 工作流:
  1. 前端加载维度注册表: GET /api/v1/policy/dimensions
     -> 每个维度包含 sor_template_id
  2. 前端获取 SoR 模板: GET /api/v1/sor/templates/{sor_template_id}
     -> 返回模板内容和占位变量
  3. 审核员填写变量后, 前端预览: POST /api/v1/sor/render
     -> 返回渲染后的 SoR 文本
  4. 审核员确认后, SoR 文本随决策一起提交

【修订】SoR 功能启用里程碑 (集成问题 #6):
  MVP:     前端 enableSoRTemplates = false; 后端 SoR API 已就绪但不强制使用
  MVP+1:   前端开启 enableSoRTemplates = true; 后端 SoR API 进入正式使用
           触发条件: 第一个法域的 SoR 模板通过法务审核
  Post-MVP: 所有法域启用 SoR 模板, sor_text 字段成为决策提交的必填项
```

### 8.6 后果预览 (Consequence Preview)

```
MVP 阶段仅支持 PASS 和 BLOCK 两种处置, 后果是确定性的:
  - PASS: 内容发布, 无后续动作
  - BLOCK: 内容下架, 通知创作者

因此 MVP 不需要独立的 consequence preview API。
前端 ConsequencePreview 组件在 MVP 阶段使用静态文案:
  - PASS -> "内容将正常发布"
  - BLOCK -> "内容将被下架, 创作者将收到通知, 可在 N 天内申诉"

Post-MVP 扩展 7 级处置矩阵时, 新增:
  GET /api/v1/policy/dispositions/{disposition}/consequences?jurisdiction=US
  返回该处置的具体后果列表。
```

### 8.7【修订】黄金题前端集成 (同步反馈)

```
【修订】黄金题对审核员透明, 提交后立即反馈:

  1. 后端在队列中注入黄金题 (is_golden_test=true)
  2. 前端领取任务时不显示黄金题标记 -- API 响应中不包含 is_golden_test 字段
  3. 审核员正常审核并提交决策
  4.【修订】后端同步评估准确率, 结果包含在提交响应中:
     
     POST /api/v1/review/human/{task_id}/decide 响应:
     {
       "success": true,
       "task_id": "xxx",
       "status": "decided",
       "decision": "pass",
       "golden_test_result": {              // 仅黄金题包含此字段
         "is_golden_test": true,
         "is_correct": false,
         "expected_decision": "block",
         "reviewer_decision": "pass"
       }
     }
     
  5. 前端 GoldenTestFeedbackModal 检测到 response.golden_test_result
     即可直接展示反馈, 无需额外轮询或 WebSocket 推送。

QA 管理员侧:
  GET /api/v1/quality/golden-results?reviewer_id=xxx
  返回审核员的黄金题评估结果 (总数、正确数、准确率)
  QA 管理员有权限查看, 普通审核员无权限
```

### 8.8【修订】机审推荐展示 (消除偏差)

```
【修订】解决机审推荐偏向拦截的问题 (关键问题 #4):

后端 MachineReviewResult 新增 machine_recommendation 字段:
  - auto_pass          -> "pass"
  - auto_block         -> "block"
  - needs_human_review -> "uncertain"   (不偏向任何方向)
  - critical_escalate  -> "block"

前端展示:
  - "pass"      -> 绿色标签 "机审建议: 通过"
  - "block"     -> 红色标签 "机审建议: 拦截"
  - "uncertain" -> 灰色标签 "机审: 不确定, 需人工判断"

前端 mapMachineDecisionToMVP 必须使用后端返回的 machine_recommendation 字段,
而非自行映射 final_decision。这避免了将 needs_human_review 硬编码为 "block"
导致的系统性偏差 (拉高拦截率, 削弱人审对边界案件的独立判断)。
```

### 8.9【修订】submit_decision 响应契约

```
【修订】统一 submit_decision 响应格式 (集成问题 #5):

POST /api/v1/review/human/{task_id}/decide 响应:
{
  "success": true,                    // 新增: 前端契约测试依赖此字段
  "task_id": "xxx",
  "status": "decided",
  "decision": "pass",
  "golden_test_result": { ... }       // 仅黄金题时存在
}

此格式满足:
  - 前端 DispositionResponseSchema 期望的 'success' 字段
  - 前端 GoldenTestFeedbackModal 期望的 'golden_test_result' 字段
  - 现有功能期望的 task_id/status/decision 字段
```

---

## 九、技术选型汇总

| 组件 | 选型 | 版本 | 理由 |
|------|------|------|------|
| 语言 | Python | 3.11+ | 团队技术栈, AI/ML 生态 |
| Web 框架 | FastAPI | 0.115+ | 异步性能, 自动文档, 类型校验 |
| ORM | SQLAlchemy | 2.0+ | 成熟稳定, 支持异步 |
| 数据校验 | Pydantic | 2.9+ | FastAPI 原生集成 |
| 数据库 | PostgreSQL | 16+ | JSONB, 分区, 行锁 |
| 缓存 | Redis | 7+ | 缓存 + 消息队列 + 分布式锁 + Pub/Sub + 熔断器 |
| 消息队列 | Redis Streams (MVP) / Kafka (V2) | - | MVP 简单运维, V2 支撑高吞吐 |
| 任务队列 | Celery + Redis | 5.3+ | 异步任务编排 |
| 对象存储 | MinIO (开发) / S3 (生产) | - | S3 兼容协议 |
| AI 模型 | Anthropic Claude API | claude-sonnet-4-6 | 多模态理解, 策略审查 |
| 视频处理 | OpenCV + ffmpeg | - | 抽帧, 转码 |
| ASR | Whisper / FunASR | - | 语音识别 |
| OCR | PaddleOCR / EasyOCR | - | 文字识别 |
| 目标检测 | YOLO / Grounding DINO | - | 人体/物品检测 |
| 容器 | Docker + Docker Compose (MVP) / K8s (V2) | - | MVP 简化部署 |
| 监控 | Prometheus + Grafana | - | 指标采集 + 可视化 |
| 日志 | structlog + ELK (可选) | - | 结构化日志 |
| JWT | PyJWT | 2.8+ | 认证 + WebSocket 短期令牌 |
|【修订】异步 Redis | redis.asyncio | 5.0+ | 健康检查/限流/熔断器 async 客户端 |
|【修订】异步 S3 | aioboto3 | 12+ | 健康检查异步 S3 探测 |

---

## 十、修订变更日志

本节总结相对 v2.0 版本的所有修订, 按修订类型分类。

### 专家评审关键问题修复 (Expert Critical)

| # | 问题 | 修订内容 | 涉及章节 |
|---|------|---------|---------|
| EC1 | _get_rule_version() 内部创建新 DB session, 与外部 session 并存导致连接池耗尽 | db session 由调用方传入; aggregate() 和 _get_rule_version() 均接受 db 参数; 无 session 时返回兜底值不创建新连接 | 2.2.4, 2.2.5, 2.1 |
| EC2 | 熔断器 CLOSED 状态下 _on_success 重置 failure_count, 单次成功即清零, 80% 失败率也不会触发熔断 | 改为滑动时间窗口 + 失败率机制: 记录所有调用 (成功/失败) 到 Redis Sorted Set, 窗口内失败率超阈值且满足最小调用次数才触发, 成功调用不清除失败记录 | 7.1 |
| EC3 | 健康检查 async handler 中使用同步 Redis 客户端 (redis.Redis.from_url + r.ping), 阻塞事件循环 | 全部改用 redis.asyncio.Redis 异步客户端; PostgreSQL 使用 async_engine; S3 使用 aioboto3 | 6.5 |

### 专家评审次要问题修复 (Expert Minor)

| # | 问题 | 修订内容 | 涉及章节 |
|---|------|---------|---------|
| EM1 | _compute_fleiss_kappa 中 pairwise Cohen's Kappa 循环计算后丢弃结果, 属于死代码 | 删除无用的 pairwise 循环, 直接调用 _compute_fleiss_kappa | 3.4 |
| EM2 | Celery 任务耗尽重试后静默失败, 无死信队列 | 新增 on_pipeline_failure 回调 + DeadLetterTaskModel 表 + DeadLetterService + 运维 API (/system/dead-letters) + 告警规则 | 2.1, 4.3, 5.1, 6.4, 6.7 |
| EM3 | StrategyRegistry 类级别可变属性, 测试状态泄漏 + 热加载竞态 | _configs 改为实例属性 + copy-on-write 原子替换; 新增 reset() 测试方法; get_configs_snapshot() 安全访问 | 2.2.2, 2.2.5 |
| EM4 | 审计链完整性字段已声明但无哈希逻辑实现 | 新增 AuditEvent.compute_event_hash() 静态方法 + AuditService.log() 中查询前一事件哈希并计算当前哈希 | 4.3, 新增 audit/service.py |
| EM5 | _get_reviewer_handled_videos 使用 IN 子查询, 活跃审核员可能返回上千 ID | 改为 EXISTS 子查询, 数据库只做存在性检查不物化列表 | 3.1 |

### 前后端集成关键问题修复 (Integration Critical)

| # | 问题 | 修订内容 | 涉及章节 |
|---|------|---------|---------|
| IC1 | 分页协议矛盾: 后端 offset-based (items/offset/limit), 前端 page-based (tasks/page/page_size) | 后端 parse_pagination_params() 同时接受两种参数; 响应同时返回 offset-based + page-based 字段; items 为标准列表字段名 | 5.1.0, 8.2 |
| IC2 | WebSocket 认证失败: verify_ws_token 要求 type='ws', 前端 MVP 复用登录 JWT 无此字段 | verify_ws_token 改为双模式: type='ws' 走 ws-token 路径, type 不存在走登录 JWT 路径 | 5.4, 8.3 |
| IC3 | 黄金题反馈时序不匹配: 前端期望同步响应 golden_test_result, 后端异步处理 | GoldenTestService 改为同步评估 (evaluate_golden_result_sync); 结果包含在 submit_decision 响应中 | 3.2, 3.4, 8.7 |
| IC4 | mapMachineDecisionToMVP 将 needs_human_review 映射为 block, 偏向拦截 | 后端新增 machine_recommendation 字段: needs_human_review 映射为 "uncertain"; 前端必须使用此字段而非自行映射 | 2.2.5, 4.3, 8.8 |

### 前后端集成次要问题修复 (Integration Minor)

| # | 问题 | 修订内容 | 涉及章节 |
|---|------|---------|---------|
| IM1 | 响应字段名不匹配: 后端 items, 前端期望 tasks | 统一使用 items; 前端适配层按 items 读取 | 5.1.0, 8.2 |
| IM2 | 心跳消息类型不匹配: 后端 HEARTBEAT/HEARTBEAT_ACK, 前端 PING/PONG | 后端同时处理 HEARTBEAT 和 PING, 分别回复对应格式 | 5.2, 8.3 |
| IM3 | submit_decision 响应缺少 success 字段, 前端契约测试失败 | 响应新增 success: true 字段 | 3.2, 8.9 |
| IM4 | SoR 功能启用无里程碑计划 | 新增 MVP/MVP+1/Post-MVP 三阶段启用计划文档 | 8.5 |
| IM5 | ws-token 5 分钟有效期过短, 页面刷新后需重新获取 | 延长到 30 分钟, 覆盖完整审核会话 | 5.4, 8.3 |

---

以上方案覆盖了机审四阶段漏斗、人审工作台、申诉闭环、数据回流的完整后端技术设计, 并针对第二轮评审反馈完成了全部修订, 重点保证了以下核心约束:

1. **稳定性**: 滑动窗口分布式熔断器 (解决 reset-on-success 缺陷) + 独立阶段重试 + 死信队列 (DLQ 全闭环) + 优雅降级 + 异步健康探针 (不阻塞事件循环) + 限流
2. **可复用性**: 策略注册表 + 装饰器注册 + 零改造路径, 新审核维度通过配置添加, 不修改核心代码; StrategyRegistry copy-on-write 热加载无竞态
3. **鲁棒性**: 乐观锁 + 客户端幂等键 + 事务 + 最终一致性 + Fleiss' Kappa (清理死代码) + 审计链完整性 (补全哈希实现) + EXISTS 子查询 (替代 IN 大列表)
4. **前后端集成**: 双模式分页协议 (offset + page 双兼容) + 双模式 WebSocket 认证 (ws-token + 登录 JWT) + 双协议心跳 (HEARTBEAT + PING) + 黄金题同步反馈 + machine_recommendation 消除偏差 + 响应 success 字段 + SoR 里程碑
5. **可扩展性**: 模块化单体 + Celery chain 独立阶段 + 熔断器窗口化 + 死信任务运维闭环 + 策略注册表版本化热加载
6. **安全性**: RBAC 端点权限 + JWT + 限流 (全异步 Redis) + 幂等性 + WebSocket 双模式令牌 + 审计链式哈希完整性
7. **完整性**: 补齐死信队列 + 审计哈希实现 + 机审推荐字段 + 分页双模式 + 心跳双协议 + SoR 启用计划 + submit_decision success 字段
