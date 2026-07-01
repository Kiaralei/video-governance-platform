# 视频治理平台技术方案

> **版本**: MVP v1.0 | **日期**: 2026-07-01 | **状态**: 评审通过

---

## 1. 项目概述

### 1.1 项目背景与目标

本平台面向海量视频内容的自动化治理场景。核心设计理念：**不让大模型直接对整条视频拍板**。生产级审核应先把视频拆成可追溯证据，再由多模态大模型做策略理解，最后通过规则引擎和人工复核稳定决策。

**核心目标**：

- 通过**机器审核（机审）**对视频进行多维度自动打分与初步决策
- 对机审不确定的内容，流转至**人工审核（人审）**处理
- 提供**申诉通道**供创作者对拒绝决策提出异议
- 所有人审结果与申诉改判自动**回流为训练数据**，持续优化机审模型

**审核全流程**：

| 环节 | 核心问题 | 主要产物 |
|------|---------|---------|
| 视频上传 | 这条视频有哪些上下文信息？ | 视频文件、标题、简介、POI、作者信息 |
| 证据提取 | 视频里出现了什么？ | 关键帧、ASR、OCR、目标检测、场景识别 |
| 基础安全初筛 | 有没有明显基础风险？ | 色情、暴力、低俗、导流等风险标签 |
| LLM 策略审查 | 这些证据按平台策略如何理解？ | 未成年合规、营销属性、画风、地点匹配判断 |
| 决策引擎 | 最终通过、拒绝，还是送人审？ | PASS / BLOCK / NEEDS_REVIEW + 触发规则 |
| 人审工作台 | 边界样本和高风险样本的人工兜底 | 最终 PASS / BLOCK 裁定 |
| 数据回流 | 这次审核如何反哺后续模型和规则？ | 最终标签、改判原因、样本库 |

### 1.2 核心功能概述

**MVP 本期交付**：
- 证据提取层（抽帧 + ASR + OCR + 目标检测）
- 基础安全初筛（规则 + 轻量模型）
- LLM 策略审查（多模态模型判断）
- 决策引擎（阈值配置 + 三态路由）
- 人审工作台（前端界面 + 证据展示 + 队列）
- 申诉流程（提交 + 二审 + 改判）
- 数据回流（四类标注数据 + JSONL 导出）

**本期暂不交付**：处置矩阵（7 档细粒度处置）、高危强制上报（CSAM / NCMEC）、need_more_context 第四态、合规透明度报告、运营健康度看板、多租户 / 多法域支持。

### 1.3 设计原则

**稳定性**：滑动窗口分布式熔断器 + 独立阶段重试 + 死信队列 + 优雅降级 + 异步健康探针 + 限流。

**可复用性**：策略注册表 + 装饰器注册 + 零改造路径。新增审核维度通过配置添加，不修改核心代码。StrategyRegistry copy-on-write 热加载无竞态。

**鲁棒性**：乐观锁 + 客户端幂等键 + 事务 + 最终一致性 + Fleiss' Kappa + 审计链完整性 + EXISTS 子查询。

### 1.4 技术选型总览

**后端技术栈**：

| 组件 | 选型 | 版本 | 理由 |
|------|------|------|------|
| 语言 | Python | 3.11+ | 团队技术栈，AI/ML 生态 |
| Web 框架 | FastAPI | 0.115+ | 异步性能，自动文档，类型校验 |
| ORM | SQLAlchemy | 2.0+ | 成熟稳定，支持异步 |
| 数据校验 | Pydantic | 2.9+ | FastAPI 原生集成 |
| 数据库 | PostgreSQL | 16+ | JSONB，分区，行锁 |
| 缓存/队列 | Redis | 7+ | 缓存 + 消息队列 + 分布式锁 + Pub/Sub + 熔断器 |
| 任务队列 | Celery + Redis | 5.3+ | 异步任务编排 |
| 对象存储 | MinIO (开发) / S3 (生产) | - | S3 兼容协议 |
| AI 模型 | Anthropic Claude API | claude-sonnet-4-6 | 多模态理解，策略审查 |
| 视频处理 | OpenCV + ffmpeg | - | 抽帧，转码 |
| ASR | Whisper / FunASR | - | 语音识别 |
| OCR | PaddleOCR / EasyOCR | - | 文字识别 |
| 目标检测 | YOLO / Grounding DINO | - | 人体/物品检测 |
| 容器 | Docker + Docker Compose (MVP) | - | 简化部署 |
| 监控 | Prometheus + Grafana | - | 指标采集 + 可视化 |
| JWT | PyJWT | 2.8+ | 认证 + WebSocket 短期令牌 |

**前端技术栈**：

| 领域 | 选型 | 版本 | 理由 |
|------|------|------|------|
| 框架 | React | 18.3+ | Concurrent 模式保障高频更新流畅度 |
| 语言 | TypeScript | 5.4+ | 强类型约束，与数据契约一一映射 |
| 构建 | Vite | 6.x | HMR 快，ESBuild 预构建 |
| UI 库 | Ant Design | 5.x | 企业级 B 端组件齐全 |
| 状态管理 | Zustand | 5.x | 轻量，slice 模式 |
| 请求层 | TanStack Query | 5.x | stale-while-revalidate 缓存 |
| 图表 | ECharts | 5.5+ | 大屏渲染性能好 |
| 视频 | xgplayer | 3.x | 国内视频格式兼容好 |
| 路由 | React Router | 7.x | 数据路由模式 |
| 测试 | Vitest + RTL + Playwright | - | 单元/集成/E2E |
| 契约测试 | MSW + Zod | - | Mock Service Worker + Schema 校验 |

---

## 2. 系统架构设计

### 2.1 整体架构

采用**模块化单体 (Modular Monolith)** 架构。

**选择理由**：
1. **团队规模匹配**：MVP 阶段团队 3-8 人，微服务运维复杂度超出承载能力
2. **模块边界明确**：通过 Python Package 实现逻辑隔离，保留拆分微服务的可能
3. **部署简单**：单一 Docker 镜像 + 独立 Worker 进程
4. **数据一致性**：核心流程（机审 -> 人审 -> 申诉）跨模块数据强依赖，单体内事务可靠性更高
5. **演进路径**：当单个模块出现独立扩缩容需求时，可拆为独立服务

### 2.2 服务划分与职责

```
video-governance-platform/
  backend/
    app/
      main.py                          # FastAPI 应用入口
      config.py                        # 全局配置
      database.py                      # 数据库连接
      
      # ---- 核心领域模块 ----
      ingestion/                       # 内容摄取
        router.py / service.py / schemas.py
        
      evidence/                        # 证据提取层 (阶段1)
        router.py / service.py / schemas.py
        extractors/
          frame_extractor.py           # 抽帧
          asr_extractor.py             # 语音识别
          ocr_extractor.py             # 文字识别
          object_detector.py           # 目标检测
          scene_classifier.py          # 场景识别
          qr_detector.py               # 二维码/联系方式
        
      safety_filter/                   # 基础安全初筛 (阶段2)
        router.py / service.py / schemas.py
        filters/
          csam_hash_filter.py
          cloud_safety_api.py
          keyword_rule_filter.py
          dedup_filter.py
        
      llm_review/                      # LLM 策略审查 (阶段3)
        router.py / service.py / schemas.py
        prompt_manager.py              # Prompt 模板管理
        sanitizer.py                   # 输入净化 (防注入)
        output_validator.py            # 输出 Schema 校验
        token_budget.py                # Token 预算管理
        
      decision_engine/                 # 决策引擎
        router.py / service.py / schemas.py
        rule_engine.py                 # 规则引擎核心
        strategy_registry.py           # 策略注册表
        strategy_base.py               # 策略抽象基类
        strategies/                    # 具体策略实现
          minor_compliance.py
          marketing_review.py
          poi_match.py
          violence_detection.py
        
      human_review/                    # 人审工作台
        router.py / service.py / schemas.py
        queue_manager.py               # 任务队列管理
        assignment.py                  # 任务分配策略
        lock_manager.py                # 案件锁管理
        fatigue_manager.py             # 反疲劳管理
        
      appeal/                          # 申诉闭环
        router.py / service.py / schemas.py
        state_machine.py               # 申诉状态机
        
      quality_check/                   # 质检与审核质量
        router.py / service.py / schemas.py
        golden_test_service.py         # 黄金题管理服务
        
      flywheel/                        # 数据回流
        router.py / service.py / schemas.py
        quality_gate.py / shadow_runner.py

      sor/                             # SoR 模板管理
      audit/                           # 审计日志
      system/                          # 系统健康与告警
        
      # ---- 基础设施层 ----
      common/
        auth.py                        # 认证授权 (JWT + RBAC)
        middleware.py                  # 全局中间件
        exceptions.py                  # 统一异常处理
        circuit_breaker.py             # 滑动窗口 Redis 分布式熔断器
        retry.py                       # 重试机制
        idempotency.py                 # 幂等性
        rate_limiter.py                # 令牌桶限流器
        websocket.py                   # Redis Pub/Sub 分布式 WebSocket
        health.py                      # 异步健康检查探针
        pagination.py                  # 统一分页响应 (双模式兼容)
        dead_letter.py                 # 死信队列处理器
        
      models/                          # SQLAlchemy 模型
      tasks/                           # Celery Workers

  frontend/
    src/
      app/                             # 应用壳：路由、权限、Provider
      api/                             # 接口层：REST / WebSocket 封装
        adapters/                      # 前后端契约适配层
        endpoints/                     # 按模块组织的端点
      stores/                          # Zustand 状态切片
      features/                        # 按业务域拆分的页面级模块
        dashboard/ review/ appeal/ policy/ admin/ quality/
      components/                      # 通用业务组件
      hooks/                           # 通用自定义 hooks
      types/                           # 全局 TypeScript 类型定义
      plugins/                         # 插件注册表
```

### 2.3 通信机制（同步 + 异步）

| 通信场景 | 模式 | 技术选择 | 理由 |
|---------|------|---------|------|
| API 请求/响应 | 同步 REST | FastAPI + httpx | 前端交互、管理操作 |
| 视频处理流水线 | 异步消息 | Celery + Redis Streams | 长耗时任务解耦，削峰填谷 |
| 实时状态推送 | WebSocket | FastAPI WS + Redis Pub/Sub | 案件锁状态、SLA 倒计时，跨实例广播 |
| 模块间调用 | 进程内直调 | Python 函数调用 | 模块化单体内，无网络开销 |
| 定时任务 | Cron | Celery Beat | Shadow 报告、数据回流批处理 |

### 2.4 部署架构

```
                    +-------------------+
                    |   Nginx / ALB     |
                    |   (反向代理+SSL)   |
                    +--------+----------+
                             |
              +--------------+--------------+
              |              |              |
     +--------v------+ +----v-----+ +------v------+
     |  FastAPI App   | | FastAPI  | |  FastAPI    |
     |  (实例 1)      | | (实例 2) | | (实例 N)    |
     |  REST+WS       | | REST+WS  | | REST+WS    |
     +---+------+-----+ +--+---+--+ +--+---+-----+
         |      |          |   |       |   |
    +----v------v----------v---v-------v---v--+
    |  Redis Cluster                           |
    |  - 缓存/锁/限流                          |
    |  - Pub/Sub (WebSocket 跨实例广播)         |
    |  - Streams (消息队列)                     |
    |  - 熔断器状态 (滑动窗口分布式)             |
    +---+-------------------------------------+
        |
    +---v--------------------------------------+
    |     PostgreSQL (主) + Read Replicas       |
    +------------------------------------------+
        |
   +----v--------------------------------------+
   |  Celery Workers (可独立扩缩容)             |
   |  - evidence_worker  (CPU密集, 抽帧)       |
   |  - review_worker    (调LLM API)           |
   |  - flywheel_worker  (数据回流)            |
   |  - shadow_worker    (Shadow评估)          |
   +-------------------------------------------+
        |
   +----v-----------------+
   |  MinIO / S3           |
   |  - uploads/           |
   |  - evidence/          |
   |  - csam-vault/        |
   |  - flywheel/          |
   +-----------------------+
```

---

## 3. 机审系统（Machine Review）

### 3.1 视频处理流水线

视频从上传到产出机审裁决包，经过四阶段漏斗：

```
视频上传 -> 摄取校验 -> [阶段1]证据提取 -> [阶段2]基础安全初筛 
         -> [阶段3]LLM策略审查 -> [阶段4]规则引擎聚合决策 -> 裁决包产出
```

使用 Celery chain 编排，每阶段独立任务、独立重试，已完成阶段不因后续失败而重新执行。

```python
# backend/app/tasks/review_tasks.py

from celery import chain
from app.tasks.evidence_tasks import extract_evidence
from app.tasks.safety_filter_tasks import run_safety_filter
from app.tasks.llm_review_tasks import run_llm_review
from app.tasks.decision_tasks import run_decision_aggregation


def run_machine_review_pipeline(video_id: str) -> None:
    """
    机审流水线主编排 -- 使用 Celery chain 替代单一同步任务。
    
    每阶段独立任务、独立重试策略，已完成阶段的结果通过
    evidence_package_id 持久化，不会重复执行。
    """
    pipeline = chain(
        extract_evidence.s(video_id),
        run_safety_filter.s(),
        run_llm_review.s(),
        run_decision_aggregation.s(),
    )
    pipeline.apply_async(
        link_error=on_pipeline_failure.s(video_id),  # 死信回调
    )
```

**各阶段独立任务定义**：

```python
# backend/app/tasks/evidence_tasks.py
@celery_app.task(
    bind=True, max_retries=3, default_retry_delay=30,
    autoretry_for=(IOError, TimeoutError),
    retry_backoff=True, retry_jitter=True,
)
def extract_evidence(self, video_id: str) -> dict:
    """阶段1: 证据提取。输出 evidence_package_id，持久化到数据库。"""
    service = EvidenceService()
    evidence_package = service.extract(video_id)
    service.persist(evidence_package)
    return {"video_id": video_id, "evidence_package_id": evidence_package.ep_id}


# backend/app/tasks/safety_filter_tasks.py
@celery_app.task(
    bind=True, max_retries=2, default_retry_delay=10,
    autoretry_for=(ConnectionError,),
    retry_backoff=True, retry_jitter=True,
)
def run_safety_filter(self, prev_result: dict) -> dict:
    """
    阶段2: 基础安全初筛。
    短路逻辑:
      - CSAM 哈希命中 -> short_circuit='csam'
      - 高置信 critical/high -> short_circuit='high_confidence'
    """
    evidence_package = EvidenceService().load(prev_result["evidence_package_id"])
    pre_filter_result = SafetyFilterService().screen(evidence_package)
    result = {**prev_result, "short_circuit": None}
    if pre_filter_result.csam_hash_hit:
        result["short_circuit"] = "csam"
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
    """阶段3: LLM 策略审查。如果阶段2已短路，直接透传。"""
    if prev_result.get("short_circuit"):
        return prev_result
    evidence_package = EvidenceService().load(prev_result["evidence_package_id"])
    llm_verdicts = LLMReviewService().review(evidence_package)
    LLMReviewService().persist_verdicts(prev_result["evidence_package_id"], llm_verdicts)
    prev_result["llm_completed"] = True
    return prev_result


# backend/app/tasks/decision_tasks.py
@celery_app.task(bind=True, max_retries=1)
def run_decision_aggregation(self, prev_result: dict) -> dict:
    """阶段4: 规则引擎聚合决策。db session 由调用方创建，避免连接池耗尽。"""
    if prev_result.get("short_circuit") == "csam":
        return {"final_decision": "critical_escalate", "video_id": prev_result["video_id"]}
    db = get_db_session()
    try:
        evidence_package = EvidenceService().load(prev_result["evidence_package_id"])
        decision_service = DecisionEngineService()
        decision = decision_service.aggregate(evidence_package, db=db)
        decision_service.persist(db, prev_result["video_id"], decision)
        _route_decision(prev_result["video_id"], decision)
        db.commit()
    finally:
        db.close()
    return decision.model_dump()


# 死信回调 -- 流水线任务永久失败时记录
@celery_app.task(bind=True)
def on_pipeline_failure(self, request, exc, traceback, video_id: str):
    """将失败信息写入 dead_letter_tasks 表，供运维人员人工调查和重试。"""
    db = get_db_session()
    try:
        DeadLetterService().record_failure(
            db=db, task_name=request.task, task_id=request.id,
            video_id=video_id, exception_type=type(exc).__name__,
            exception_message=str(exc), traceback=traceback,
            retry_count=request.retries,
        )
        db.commit()
    finally:
        db.close()
```

**证据包输出示例**：

```json
{
  "video_id": "vid_001",
  "duration": 58.4,
  "meta": { "title": "周末亲子餐厅打卡", "poi_name": "星光亲子餐厅", "city": "上海" },
  "frames": [
    { "timestamp": 5.0, "objects": ["adult", "minor_suspected", "restaurant_table"], "scene": "restaurant" }
  ],
  "asr": [{ "start": 2.1, "end": 6.8, "text": "扫码领取优惠券，今天下单立减二十" }],
  "ocr": [{ "timestamp": 12.0, "text": "扫码领券", "confidence": 0.94 }]
}
```

### 3.2 AI模型集成层

#### 策略抽象基类

```python
# backend/app/decision_engine/strategy_base.py

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DimensionDecision(str, Enum):
    """L1: LLM 维度判断层枚举"""
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
    """LLM 对单个策略维度的结构化输出。LLM 只做理解归因，不做处置决策。"""
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
    """策略维度配置，从维度注册表加载"""
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
    审核策略抽象基类。新增审核维度时，只需:
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
        self, evidence_package: "EvidencePackage", policy_version: str,
    ) -> DimensionVerdict:
        """对证据包执行该维度的策略审查。只输出理解与归因，不输出处置动作。"""
        ...

    @abstractmethod
    def build_prompt(self, evidence_package: "EvidencePackage") -> str:
        """构建该维度的 LLM Prompt。"""
        ...
```

#### 策略执行编排

```python
# backend/app/decision_engine/service.py

class DecisionEngineService:
    """决策引擎服务 -- 编排所有已注册策略的执行，调用规则引擎聚合最终决策。"""

    def __init__(self):
        self.registry = StrategyRegistry.get_instance()
        self.rule_engine = RuleEngine()

    async def run_all_strategies(
        self, evidence_package, policy_version, jurisdiction="global",
    ) -> list[DimensionVerdict]:
        """并行执行所有已启用策略。单个策略失败不影响其他策略，失败返回 UNCERTAIN。"""
        strategies = self.registry.get_llm_enabled(jurisdiction)
        tasks = [
            self._safe_execute_strategy(s, evidence_package, policy_version)
            for s in strategies
        ]
        verdicts = await asyncio.gather(*tasks)
        return [v for v in verdicts if v is not None]

    async def _safe_execute_strategy(self, strategy, evidence_package, policy_version):
        """安全执行单个策略，超时 25 秒，捕获异常降级为 UNCERTAIN。"""
        try:
            return await asyncio.wait_for(
                strategy.review(evidence_package, policy_version), timeout=25.0,
            )
        except (asyncio.TimeoutError, Exception) as e:
            return DimensionVerdict(
                dimension_id=strategy.dimension_id,
                dimension_name=strategy.dimension_name,
                decision=DimensionDecision.UNCERTAIN,
                confidence=0.0,
                reason=f"策略执行异常: {type(e).__name__}",
                evidence_refs=[], policy_version=policy_version,
                model_version="", llm_unavailable=True,
            )
```

### 3.3 策略引擎设计

#### 基础安全初筛能力矩阵

| 风险类型 | 检查项 | 实现方式 |
|---------|--------|---------|
| 图像/视觉风险 | 色情、低俗、暴露、暴力、血腥、危险行为 | 云内容安全 API / 开源模型 |
| 文本风险 | 辱骂、敏感词、联系方式、诈骗、诱导交易 | 关键词规则 + 云 API |
| 导流风险 | 二维码、电话、微信、URL、进群、私信 | OpenCV + pyzbar + 正则 |
| 未成年线索 | 疑似儿童或青少年出现 | 仅作复核线索，不自动定性 |

**未成年策略偏保守**：疑似未成年 + 性化/危险/暴力/诱导消费/联系方式/成人营销等线索，至少强制进入人工复核。

#### LLM 策略审查维度

| 策略维度 | 模型要判断什么 | 典型证据 |
|---------|--------------|---------|
| 未成年合法合规 | 是否正常亲子/教育/家庭场景，是否存在危险、性化、诱导、导流 | 关键帧、人物标签、ASR 话术、OCR 文案 |
| 营销属性/画风 | 是否软广、强营销、导流、带货；画风是否低俗、夸张 | 价格、优惠、扫码、下单、品牌露出 |
| 毒品/暴力 | 是否展示、推广毒品或暴力行为 | 关键帧物体检测、场景识别、ASR |
| 内容与信息匹配 | 视频内容是否和标题、简介、挂载地点一致 | POI 信息、门店名、场景、OCR、ASR |

### 3.4 结果聚合与决策引擎

```python
# backend/app/decision_engine/rule_engine.py

class PolicyDecision(str, Enum):
    """L2: 规则引擎决策层枚举"""
    AUTO_PASS = "auto_pass"
    AUTO_BLOCK = "auto_block"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    CRITICAL_ESCALATE = "critical_escalate"


class RuleEngine:
    """
    规则引擎 -- 处置决策的唯一责任主体。
    大模型负责理解和归因，规则引擎负责最终动作。
    """

    # 取严链: critical_escalate > auto_block > needs_human_review > auto_pass
    _SEVERITY_ORDER = {
        PolicyDecision.CRITICAL_ESCALATE: 4,
        PolicyDecision.AUTO_BLOCK: 3,
        PolicyDecision.NEEDS_HUMAN_REVIEW: 2,
        PolicyDecision.AUTO_PASS: 1,
    }

    def aggregate(self, evidence_package, db=None) -> "DecisionSummary":
        """
        聚合所有信号产出最终决策。db session 由调用方传入，不再内部创建。
        
        决策优先级:
        1. CSAM 哈希命中 -> 强制 CRITICAL_ESCALATE
        2. 阶段2 高置信 critical/high -> 按初筛结论映射
        3. 逐维度处理 DimensionVerdict -> 按阈值计算
        4. 取严链合并 -> 取最严决策
        5. 全部低风险 -> AUTO_PASS
        """
        triggered_rules = []
        dimension_decisions = []
        rule_version = self._get_rule_version(db=db)
        
        # ... 阈值评估逻辑
        
        # 计算机审推荐: needs_human_review -> "uncertain" (不偏向任何方向)
        machine_recommendation = self._compute_machine_recommendation(final)
        
        return DecisionSummary(
            final_decision=final, risk_score=risk_score,
            triggered_rules=triggered_rules,
            machine_recommendation=machine_recommendation,
            policy_version=evidence_package.policy_version or "",
            rule_version=rule_version,
            # ...
        )

    def _compute_machine_recommendation(self, decision: PolicyDecision) -> str:
        """
        机审推荐映射 -- needs_human_review 映射为 "uncertain"，而非 "block"。
        避免系统性偏向拦截，让审核员基于证据独立判断。
        """
        return {
            PolicyDecision.AUTO_PASS: "pass",
            PolicyDecision.AUTO_BLOCK: "block",
            PolicyDecision.NEEDS_HUMAN_REVIEW: "uncertain",
            PolicyDecision.CRITICAL_ESCALATE: "block",
        }.get(decision, "uncertain")

    def _evaluate_verdict(self, verdict: DimensionVerdict) -> PolicyDecision:
        """单维度评估映射规则"""
        config = self._get_dimension_config(verdict.dimension_id)
        auto_threshold = config.get("auto_block_threshold", 0.90)
        review_threshold = config.get("human_review_threshold", 0.50)
        
        if verdict.llm_unavailable or verdict.decision == DimensionDecision.UNCERTAIN:
            return PolicyDecision.NEEDS_HUMAN_REVIEW
        if verdict.decision == DimensionDecision.VIOLATION:
            if verdict.confidence >= auto_threshold:
                return PolicyDecision.AUTO_BLOCK
            return PolicyDecision.NEEDS_HUMAN_REVIEW
        return PolicyDecision.AUTO_PASS

    def _get_rule_version(self, db=None) -> str:
        """获取规则版本。db session 由调用方传入，不再内部创建新连接。"""
        if db is None:
            return "rv_0"
        active_version = (
            db.query(PolicyVersionModel)
            .filter(PolicyVersionModel.status == "active")
            .order_by(PolicyVersionModel.activated_at.desc())
            .first()
        )
        return active_version.version_id if active_version else "rv_0"
```

**决策结果格式**：

```json
{
  "final_decision": "needs_human_review",
  "risk_score": 0.78,
  "machine_recommendation": "uncertain",
  "triggered_rules": ["minor_present_with_marketing_signal", "qr_code_detected"],
  "action": { "publish": false, "route_to_human_review": true, "priority": "high" },
  "policy_version": "rv_12",
  "rule_version": "rv_12"
}
```

**策略配置示例（每类目独立）**：

```json
{
  "category": "minor_compliance",
  "auto_block_threshold": 0.90,
  "human_review_threshold": 0.50,
  "enabled": true
}
```

### 3.5 新增策略流程

以新增 "毒品/暴力检测" 维度为例，完整步骤：

**步骤 1: 编写策略类**

```python
# backend/app/decision_engine/strategies/drug_violence.py

@StrategyRegistry.register("dim_drug_violence")
class DrugViolenceStrategy(BaseReviewStrategy):
    """毒品/暴力内容检测策略"""

    def build_prompt(self, evidence_package):
        template = """你是一个内容安全审查专家。请分析以下视频证据，
判断是否存在毒品展示/推广或暴力行为。

<user_content>
{evidence}
</user_content>

请以 JSON 输出 decision/confidence/reason/evidence_refs。"""
        return template.format(evidence=self._build_evidence_summary(evidence_package))

    async def review(self, evidence_package, policy_version) -> DimensionVerdict:
        drug_signals = [
            d for d in evidence_package.object_detections
            if d.label in ("drug", "weapon", "knife", "gun", "syringe")
        ]
        if not drug_signals:
            return DimensionVerdict(
                dimension_id=self.dimension_id, dimension_name=self.dimension_name,
                decision=DimensionDecision.NO_VIOLATION, confidence=0.92,
                reason="未检测到毒品或暴力相关物体。", evidence_refs=[],
                policy_version=policy_version, model_version="",
            )
        # 有信号，调 LLM 深度审查
        prompt = self.build_prompt(evidence_package)
        try:
            result = await LLMReviewService().call_llm(
                prompt=prompt, evidence_package=evidence_package,
                dimension_id=self.dimension_id,
            )
            return DimensionVerdict(
                dimension_id=self.dimension_id, dimension_name=self.dimension_name,
                decision=result.decision, confidence=result.confidence,
                severity_suggestion=result.severity_suggestion,
                reason=result.reason, evidence_refs=result.evidence_refs,
                policy_version=policy_version, model_version=result.model_version,
            )
        except Exception:
            return DimensionVerdict(
                dimension_id=self.dimension_id, dimension_name=self.dimension_name,
                decision=DimensionDecision.UNCERTAIN, confidence=0.0,
                reason="LLM 不可用", evidence_refs=[],
                policy_version=policy_version, model_version="",
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
    false,   -- 初始为 Shadow 模式
    true, 0.90, 0.50,
    'prompt_drug_violence_v1',
    '{"critical": {"min_score": 90}, "high": {"min_score": 70}}',
    'shadow', 1, 'policy_pm_001'
);
```

**步骤 3**: Shadow 验证 -> 灰度放量 -> 全量上线。整个过程无需修改决策引擎、人审工作台、申诉闭环、审计日志的任何核心代码。

---

## 4. 人审系统（Human Review）

### 4.1 任务队列与分配

```python
# backend/app/human_review/queue_manager.py

class QueuePriority(int, Enum):
    CRITICAL = 1          # CSAM/暴力等高危
    LEGAL_DEADLINE = 2    # 有法定时限的案件
    HIGH = 3              # 高风险
    NORMAL = 5            # 常规 NEEDS_REVIEW
    LOW = 8               # 低风险/低置信
    BACKFILL = 10         # 回扫/补审


class QueueManager:
    """
    人审任务队列管理器。
    1. 优先级队列: 按 (priority, sla_deadline, created_at) 三级排序
    2. 领取即锁定: 防止并发审核同一案件
    3. 心跳超时释放: 锁定超时 30 分钟自动释放
    """
    LOCK_TIMEOUT_MINUTES = 30
    INDEPENDENCE_LOOKBACK_DAYS = 90

    async def fetch_next(self, db, reviewer_id, reviewer_skills, reviewer_jurisdiction):
        """
        获取下一个待审案件。
        使用 EXISTS 子查询排除审核员已审过的案件（避免 IN 物化大列表）。
        使用 SELECT ... FOR UPDATE SKIP LOCKED 实现原子性领取。
        """
        now = datetime.now(timezone.utc)
        await self._release_expired_locks(db, now)
        
        cutoff = now - timedelta(days=self.INDEPENDENCE_LOOKBACK_DAYS)
        handled_exists = (
            exists()
            .where(HumanReviewDecisionModel.video_id == HumanReviewTaskModel.video_id)
            .where(HumanReviewDecisionModel.reviewer_id == reviewer_id)
            .where(HumanReviewDecisionModel.decided_at >= cutoff)
        )
        
        task_model = (
            db.query(HumanReviewTaskModel)
            .filter(
                HumanReviewTaskModel.status == "pending",
                HumanReviewTaskModel.jurisdiction.in_(reviewer_jurisdiction),
                ~handled_exists,
            )
            .order_by(
                HumanReviewTaskModel.priority.asc(),
                HumanReviewTaskModel.sla_deadline.asc().nullslast(),
                HumanReviewTaskModel.created_at.asc(),
            )
            .with_for_update(skip_locked=True)
            .first()
        )
        
        if not task_model:
            return None
        
        task_model.status = "locked"
        task_model.assigned_to = reviewer_id
        task_model.locked_at = now
        task_model.lock_expires_at = now + timedelta(minutes=self.LOCK_TIMEOUT_MINUTES)
        db.commit()
        return self._model_to_task(task_model)
```

**任务分配策略**：

```python
# backend/app/human_review/assignment.py

class AssignmentStrategy:
    """
    分配算法:
      1. 资格过滤: 法域权限、维度技能、独立性排除
      2. 反疲劳过滤: CSAM 曝光上限(10/班, 30/周)、强制休息、负载上限
      3. 优先匹配: 技能匹配度优先，同等技能取负载最低
    """
    CSAM_PER_SHIFT_LIMIT = 10
    CSAM_PER_WEEK_LIMIT = 30
```

### 4.2 工作流引擎（状态机设计）

```python
class ReviewStatus(str, Enum):
    PENDING = "pending"                         # 待分配
    LOCKED = "locked"                           # 已领取/已锁定
    IN_REVIEW = "in_review"                     # 审核中
    AWAITING_SECOND_REVIEW = "awaiting_second_review"
    DECIDED = "decided"                         # 已判定
    DELIVERY_PENDING = "delivery_pending"       # 待交付
    DELIVERY_FAILED = "delivery_failed"         # 交付失败
    CLOSED = "closed"                           # 已结案（终态）

# 合法状态转移矩阵
VALID_TRANSITIONS = {
    ReviewStatus.PENDING: {ReviewStatus.LOCKED},
    ReviewStatus.LOCKED: {ReviewStatus.IN_REVIEW, ReviewStatus.PENDING},
    ReviewStatus.IN_REVIEW: {
        ReviewStatus.DECIDED,
        ReviewStatus.AWAITING_SECOND_REVIEW,
        ReviewStatus.PENDING,
    },
    ReviewStatus.AWAITING_SECOND_REVIEW: {ReviewStatus.IN_REVIEW},
    ReviewStatus.DECIDED: {ReviewStatus.DELIVERY_PENDING, ReviewStatus.IN_REVIEW},
    ReviewStatus.DELIVERY_PENDING: {ReviewStatus.CLOSED, ReviewStatus.DELIVERY_FAILED},
    ReviewStatus.DELIVERY_FAILED: {ReviewStatus.DELIVERY_PENDING},
    ReviewStatus.CLOSED: set(),  # 终态
}
```

**提交决策服务**：

```python
class HumanReviewService:
    async def submit_decision(self, db, task_id, reviewer_id, decision, 
                               reason_category, reason_detail, internal_notes,
                               dimension_overrides) -> dict:
        """
        MVP 阶段 decision 仅接受 "pass" 或 "block"。
        黄金题同步评估，结果随响应返回。
        """
        ALLOWED_DECISIONS = {"pass", "block"}
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"decision 必须为 {ALLOWED_DECISIONS} 之一")
        
        # 校验持锁 + 状态转移合法性
        # 记录决策 + 更新状态 + 审计日志
        
        response = {
            "success": True,
            "task_id": task_id,
            "status": "decided",
            "decision": decision,
        }
        
        if task.is_golden_test:
            golden_result = GoldenTestService().evaluate_golden_result_sync(
                db=db, task_id=task_id, reviewer_id=reviewer_id,
                reviewer_decision=decision,
            )
            response["golden_test_result"] = golden_result
        
        return response
```

### 4.3 质量保证机制

**三重质检机制**：
1. **随机抽检** (5%): 随机抽取已完成案件二审
2. **定向抽检**: 针对特定维度/审核员/高推翻率场景
3. **黄金题注入** (2%): 注入已知答案的测试案件，校准审核员

**IRR (评估者间信度) 计算**：

```python
class QualityCheckService:
    KAPPA_THRESHOLD = 0.80

    def _compute_fleiss_kappa(self, decisions, labels) -> tuple[float, float, float]:
        """
        Fleiss' Kappa: kappa = (Po - Pe) / (1 - Pe)
        Po = 观察一致率, Pe = 期望一致率
        """
        n = len(decisions)
        counter = Counter(decisions)
        agreements = sum(count * (count - 1) for count in counter.values())
        total_pairs = n * (n - 1)
        po = agreements / total_pairs if total_pairs > 0 else 1.0
        pe = sum((count / n) ** 2 for count in counter.values())
        kappa = (po - pe) / (1.0 - pe) if pe < 1.0 else 1.0
        return (kappa, po, pe)
```

**黄金题同步评估**：

```python
class GoldenTestService:
    def evaluate_golden_result_sync(self, db, task_id, reviewer_id, reviewer_decision):
        """同步评估黄金题结果，结果直接包含在 submit_decision 响应中。"""
        golden = db.query(GoldenSetModel).filter(
            GoldenSetModel.sample_id == task.golden_set_id
        ).first()
        expected = golden.final_decision
        is_correct = (reviewer_decision == expected)
        return {
            "is_golden_test": True, "is_correct": is_correct,
            "expected_decision": expected, "reviewer_decision": reviewer_decision,
        }
```

### 4.4 审核员管理

| 功能 | 说明 |
|------|------|
| 审核员列表 | 姓名、角色(T1/T2/T3)、技能标签、当前负载 |
| 技能标签管理 | 语言能力、法域资质、类目专长 |
| CSAM 曝光监控 | 单班/周累计处理量、距上限比例 |
| 反疲劳管理 | 连续 3 条 critical 强制休息 5 分钟，5 条 15 分钟 |
| 独立性约束 | 申诉二审自动排除原审核员 |

---

## 5. 前端架构设计

### 5.1 整体架构与模块划分

**组件分层架构**：

```
  Page Components     -- 路由级容器，数据编排 + 权限校验
        |
  Feature Components  -- 业务组件（ReviewWorkbench, PolicyEditor）
        |
  Common Components   -- 通用业务组件（VideoPlayer, EvidenceViewer）
        |
  Ant Design 5.x      -- 基础 UI 原子
```

**状态管理分层**：

| 状态层 | 存储 | 更新频率 | 示例 |
|--------|------|----------|------|
| 服务端缓存态 | TanStack Query | 按 staleTime | 视频列表、案件详情 |
| 实时推送态 | wsStore | 高频（WebSocket） | 锁状态、SLA tick |
| 会话运行态 | reviewStore | 中频（用户操作） | 当前案件、草稿 |
| 全局配置态 | authStore | 低频（登录/刷新） | 用户角色、Feature Flag |

**错误边界策略**：三层错误边界（全局 -> 路由 -> 面板），确保审核员即使视频播放器崩溃，仍可查看证据包文本并完成处置提交。

### 5.2 机审监控面板

**大屏布局**：

```
+--------------------------------------------------+
| 系统健康状态条 (全宽)                                |
+------------------+------------------+-------------+
| 审核量趋势图      | 违规类型分布      | 策略命中率    |
+------------------+------------------+-------------+
| 三阶段漏斗转化     | 决策分布饼图      | LLM 置信度   |
+------------------+------------------+-------------+
| 实时告警流 (全宽)                                    |
+--------------------------------------------------+
```

**健康指示器**通过 `GET /api/v1/system/health` 获取，展示四阶段 P95 延迟和错误率。通过 feature flag `enableDashboardHealth` 控制显隐。

**策略管理界面**包括策略列表（四态生命周期）、动态参数配置表单、Shadow 效果对比视图。

### 5.3 人审工作台

**一屏完成决策**的布局设计：

```
+------------------------------------------------------------------+
| 顶栏: SLA 倒计时 | 案件 ID | 严重度 Badge | 锁状态 | 快捷键提示    |
+----------------------------+---------+---------------------------+
|                            |         | 机审维度评分面板            |
|   视频播放器                |  时间轴  | - 安全/质量/业务维度分数    |
|   (含命中点标注)            |  标注    | - 触发规则 + LLM 理由      |
+----------------------------+  面板   +---------------------------+
| 证据面板 (Tabs)             |         | 处置操作面板                |
| [ASR][OCR][目标检测]        |         | - 机审建议（明确/需人工判断）|
| [场景识别][初筛结果]         |         | - pass / block 按钮组      |
| 元数据 + 创作者信息          |         | - 理由（结构化 + 自由文本） |
+----------------------------+---------+---------------------------+
| 状态栏: 疲劳指标 | 曝光计数 | 屏蔽模式开关 | Wellness 入口        |
+------------------------------------------------------------------+
```

**机审建议展示修复偏差**：

```typescript
// needs_human_review 返回 null（无建议），展示"需人工判断"
// 避免系统性偏向 block
function mapMachineDecisionToMVP(decision: string): MVPDisposition | null {
  switch (decision) {
    case 'auto_pass': return 'pass';
    case 'auto_block': return 'block';
    case 'critical_escalate': return 'block';
    case 'needs_human_review': return null;  // 不偏向
    default: return null;
  }
}
```

**快捷键系统**：

| 快捷键 | 动作 |
|--------|------|
| `p` | 选择通过 |
| `b` | 选择拒绝 |
| `Ctrl+Enter` | 提交并取下一个 |
| `Space` | 播放/暂停 |
| `,` / `.` | 逐帧后退/前进 |
| `Alt+1~6` | 区域间快速跳转 |
| `h` | 切换创伤屏蔽 |

### 5.4 管理后台

- **RBAC 可视化**：矩阵表格呈现角色权限映射
- **审核员管理**：负载看板、CSAM 曝光监控、排班管理
- **审计日志**：append-only 只读查询，支持按 content_id 全链路追溯
- **质检管理**：QA 管理员可查看金标测试结果和 IRR 一致性报告

### 5.5 组件库设计

| 组件 | 职责 |
|------|------|
| `VideoPlayer` | xgplayer 封装 + 命中点标注 + 逐帧控制 + 创伤屏蔽 |
| `EvidenceViewer` | 多模态证据展示 (ASR/OCR/目标检测/场景标签 Tab) |
| `StatusBadge` | 统一状态标签 (MVP: pass/block + L2 四态) |
| `SLACountdown` | SLA 倒计时，区分法定/运营 |
| `DynamicForm` | Schema 驱动的动态表单生成 |
| `TaskCard` | 队列案件卡片 |
| `TraumaShield` | 创伤屏蔽遮罩层 + 点击解锁 |
| `PanelErrorBoundary` | 面板级错误边界 |

---

## 6. 数据模型设计

### 6.1 核心实体与关系

```
ContentItem (1) ──── (1) EvidencePackage
     |                        |
     |                        +-- (N) FrameEvidence / ASRSegment / OCRResult
     |                        +-- (N) ObjectDetection / SceneTag
     |
     +-- (1) MachineReviewResult
     |         +-- (N) DimensionVerdictRecord
     |         +-- (1) PreFilterResult
     |
     +-- (N) HumanReviewTask
     |         +-- (N) HumanReviewDecision
     |
     +-- (N) AppealCase
     |         +-- (N) AppealDecision
     |
     +-- (N) AuditEvent
     +-- (N) FlywheelSample

DimensionRegistry (独立, 版本化)
PolicyVersion (独立, 四态生命周期)
ShadowReport / SoRTemplate / SystemAlert / DeadLetterTask (独立)
```

### 6.2 数据库表结构设计

#### content_items -- 审核系统核心被审实体

```python
class ContentItem(Base):
    __tablename__ = "content_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_type = Column(String(20), nullable=False, default="video")
    title = Column(String(500), default="")
    description = Column(Text, default="")
    creator_id = Column(String(100), nullable=False, index=True)
    
    # 地理/法域
    region = Column(String(20), default="global")
    jurisdiction = Column(String(20), default="global")
    poi_name = Column(String(200), default="")
    poi_category = Column(String(100), default="")
    
    # 视频元数据
    video_path = Column(String(500), nullable=False)
    duration_ms = Column(BigInteger, default=0)
    file_size_bytes = Column(BigInteger, default=0)
    
    # 状态
    status = Column(SQLEnum(ContentStatus), default=ContentStatus.INGESTED, index=True)
    visibility = Column(SQLEnum(VisibilityState), default=VisibilityState.PUBLISH_GATE, index=True)
    
    # 策略绑定 + 乐观锁
    policy_version = Column(String(50), default="")
    version = Column(Integer, default=1, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("ix_content_status_created", "status", "created_at"),
        Index("ix_content_creator_status", "creator_id", "status"),
    )
```

#### evidence_packages -- 证据包

```python
class EvidencePackageModel(Base):
    __tablename__ = "evidence_packages"

    ep_id = Column(String(100), primary_key=True)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), unique=True)
    schema_version = Column(String(10), nullable=False, default="1.0")
    snapshot_id = Column(String(100), nullable=False)
    video_meta = Column(JSONB, default={})
    modality_availability = Column(JSONB, default={})
    frames = Column(JSONB, default=[])
    asr_transcript = Column(JSONB, default=[])
    ocr_results = Column(JSONB, default=[])
    object_detections = Column(JSONB, default=[])
    scene_tags = Column(JSONB, default=[])
    pre_filter_results = Column(JSONB, default={})
    llm_verdicts = Column(JSONB, default=[])
    decision_summary = Column(JSONB, nullable=True)
    token_budget_used = Column(Integer, default=0)
    token_budget_limit = Column(Integer, default=0)
    truncated_modalities = Column(JSONB, default=[])
    access_policy = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

#### dimension_registry -- 维度注册表（策略可扩展性核心）

```python
class DimensionRegistryModel(Base):
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
    human_review_ui_config = Column(JSONB, default={})
    sor_template_id = Column(String(100), default="")
    status = Column(String(20), default="draft")  # draft/shadow/active/archived
    version = Column(Integer, default=1)
    created_by = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

#### machine_review_results -- 机审裁决结果

```python
class MachineReviewResult(Base):
    __tablename__ = "machine_review_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), unique=True)
    final_decision = Column(String(30), nullable=False)
    risk_score = Column(Float, default=0.0)
    triggered_rules = Column(JSONB, default=[])
    dimension_verdicts = Column(JSONB, default=[])
    action = Column(JSONB, default={})
    machine_recommendation = Column(String(20), default="")  # pass/block/uncertain
    policy_version = Column(String(50), nullable=False)
    rule_version = Column(String(50), nullable=False)
    evidence_package_id = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

#### human_review_tasks + human_review_decisions

```python
class HumanReviewTaskModel(Base):
    __tablename__ = "human_review_tasks"

    task_id = Column(String(100), primary_key=True)
    video_id = Column(String(100), nullable=False, index=True)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"))
    priority = Column(Integer, default=5, index=True)
    dimension_ids = Column(JSONB, default=[])
    jurisdiction = Column(String(20), default="global")
    assigned_to = Column(String(100), default="", index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    lock_expires_at = Column(DateTime(timezone=True), nullable=True)
    sla_deadline = Column(DateTime(timezone=True), nullable=True)
    evidence_package_id = Column(String(100), default="")
    machine_decision_summary = Column(JSONB, default={})
    status = Column(String(30), default="pending", index=True)
    is_golden_test = Column(Boolean, default=False)
    golden_set_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index("ix_task_queue", "status", "priority", "sla_deadline", "created_at"),
    )


class HumanReviewDecisionModel(Base):
    __tablename__ = "human_review_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(100), ForeignKey("human_review_tasks.task_id"))
    video_id = Column(String(100), nullable=False)
    reviewer_id = Column(String(100), nullable=False, index=True)
    decision = Column(String(20), nullable=False)    # MVP: pass / block
    reason_category = Column(String(100), nullable=False)
    reason_detail = Column(Text, default="")
    internal_notes = Column(Text, default="")        # 内部理由（不对外）
    sor_text = Column(Text, default="")              # Statement of Reason（对外）
    dimension_overrides = Column(JSONB, default={})
    is_override = Column(Boolean, default=False)
    is_golden_test = Column(Boolean, default=False)
    golden_expected_decision = Column(String(20), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=False)
```

#### appeal_cases + appeal_decisions

```python
class AppealCase(Base):
    __tablename__ = "appeal_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"))
    appellant_id = Column(String(100), nullable=False, index=True)
    appeal_reason = Column(Text, nullable=False)
    original_decision = Column(String(30), nullable=False)
    original_reviewer_id = Column(String(100), default="")
    original_sor = Column(Text, default="")
    pre_disposition_snapshot = Column(JSONB, default={})
    status = Column(SQLEnum(AppealStatus), default=AppealStatus.OPEN, index=True)
    assigned_reviewer_id = Column(String(100), default="")
    sla_deadline = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

#### policy_versions -- 策略版本（四态生命周期）

```python
class PolicyVersionModel(Base):
    __tablename__ = "policy_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(String(50), unique=True, nullable=False)
    version_seq = Column(Integer, nullable=False, unique=True)
    status = Column(String(20), default="draft")  # draft/shadow/active/archived
    thresholds = Column(JSONB, nullable=False)
    dimension_configs = Column(JSONB, nullable=False)
    content_hash = Column(String(64), nullable=False, default="")
    rollout_percentage = Column(Integer, default=0)
    created_by = Column(String(100), nullable=False)
    approved_by = Column(String(100), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    activated_at = Column(DateTime(timezone=True), nullable=True)
```

#### flywheel_samples -- 数据回流样本

```python
class FlywheelSampleModel(Base):
    __tablename__ = "flywheel_samples"

    sample_id = Column(String(100), primary_key=True)
    source_type = Column(String(50), nullable=False)  # ground_truth/disagreement/golden
    content_id = Column(String(100), nullable=False, index=True)
    dimension_id = Column(String(100), nullable=False, index=True)
    machine_decision = Column(String(30), default="")
    human_decision = Column(String(30), default="")
    final_decision = Column(String(30), nullable=False)
    error_type = Column(String(30), default="")   # overkill/miss
    policy_version = Column(String(50), default="")
    model_version = Column(String(50), default="")
    rule_version = Column(String(50), default="")
    quality_gate_passed = Column(Boolean, default=False)
    is_correction = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

#### dead_letter_tasks -- 死信任务

```python
class DeadLetterTaskModel(Base):
    __tablename__ = "dead_letter_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_name = Column(String(200), nullable=False, index=True)
    celery_task_id = Column(String(100), nullable=False)
    video_id = Column(String(100), nullable=True, index=True)
    exception_type = Column(String(200), nullable=False)
    exception_message = Column(Text, nullable=False)
    traceback = Column(Text, default="")
    retry_count = Column(Integer, default=0)
    status = Column(String(20), default="pending", index=True)  # pending/retried/abandoned
    created_at = Column(DateTime(timezone=True), server_default=func.now())
```

### 6.3 审计日志设计

```python
class AuditEvent(Base):
    """审计事件 -- append-only，不可修改。链式完整性：每条包含前一条的哈希。"""
    __tablename__ = "audit_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(String(100), unique=True, nullable=False)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content_items.id"), index=True)
    action = Column(String(100), nullable=False, index=True)
    actor = Column(String(100), nullable=False, index=True)
    details = Column(JSONB, default={})
    previous_event_hash = Column(String(64), default="")
    event_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @staticmethod
    def compute_event_hash(event_id, action, actor, details, previous_hash, created_at_iso):
        """SHA-256 哈希链。任一历史事件被篡改，后续所有 hash 链断裂。"""
        canonical = json.dumps({
            "event_id": event_id, "action": action, "actor": actor,
            "details": details, "previous_event_hash": previous_hash,
            "created_at": created_at_iso,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

---

## 7. API设计

### 7.1 RESTful API规范

所有 API 以 `/api/v1/` 为前缀。分页响应统一使用双模式兼容格式。

#### 统一分页响应

```python
class PaginatedResponse(BaseModel, Generic[T]):
    """同时兼容 offset-based 和 page-based 查询"""
    items: list[T]
    total: int
    offset: int
    limit: int
    next_offset: Optional[int] = None  # null = 没有更多数据
    page: int = 1                      # page-based 兼容字段
    page_size: int = 20
    total_pages: int = 1
```

#### 内容摄取

| 端点 | 方法 | 说明 | 响应 |
|------|------|------|------|
| `/api/v1/content/upload` | POST | 上传视频 | `{content_id, status, snapshot_id}` |
| `/api/v1/content/{id}` | GET | 获取内容详情 | ContentItem |
| `/api/v1/content/{id}/status` | GET | 审核状态（创作者侧） | `{status, visibility, sor_text}` |

#### 证据与机审

| 端点 | 方法 | 说明 | 响应 |
|------|------|------|------|
| `/api/v1/evidence/{ep_id}` | GET | 获取证据包 | EvidencePackageResponse |
| `/api/v1/review/machine/{content_id}` | GET | 获取机审结果 | MachineReviewResult |
| `/api/v1/review/machine/{content_id}/retry` | POST | 重试机审 | `{status: "retrying"}` |

#### 人审工作台

| 端点 | 方法 | 说明 | 响应 |
|------|------|------|------|
| `/api/v1/review/human/queue` | GET | 待审队列 `?offset=0&limit=20` | `PaginatedResponse[ReviewTask]` |
| `/api/v1/review/human/next` | POST | 领取下一个任务 | ReviewTask |
| `/api/v1/review/human/{task_id}` | GET | 任务详情 | `{task, evidence, machine_result}` |
| `/api/v1/review/human/{task_id}/decide` | POST | 提交决策 | `{success, task_id, status, decision, golden_test_result?}` |
| `/api/v1/review/human/{task_id}/release` | POST | 释放锁 | `{status: "released"}` |
| `/api/v1/review/human/{task_id}/heartbeat` | POST | 续租锁 | `{lock_expires_at}` |
| `/api/v1/review/human/batch-decide` | POST | 批量提交 | `{succeeded: [...], failed: [...]}` |

#### 申诉

| 端点 | 方法 | 说明 | 响应 |
|------|------|------|------|
| `/api/v1/appeal/submit` | POST | 提交申诉 | `{appeal_id, status}` |
| `/api/v1/appeal/{id}` | GET | 申诉详情 | AppealCase |
| `/api/v1/appeal/{id}/decide` | POST | 二审裁决 | `{status}` |

#### 策略管理

| 端点 | 方法 | 说明 | 响应 |
|------|------|------|------|
| `/api/v1/policy/versions` | GET/POST | 版本列表/创建草稿 | versions / `{version_id}` |
| `/api/v1/policy/versions/{id}/activate` | POST | 激活策略 | `{status}` |
| `/api/v1/policy/dimensions` | GET/POST | 维度注册表 | dimensions / `{dimension_id}` |
| `/api/v1/policy/dispositions` | GET | 可用处置选项 | `{dispositions: ["pass","block"]}` |

#### 系统健康与运维

| 端点 | 方法 | 说明 | 响应 |
|------|------|------|------|
| `/api/v1/system/health` | GET | 系统健康 | `{status, components}` |
| `/api/v1/system/ready` | GET | 就绪探针 | `{ready: true}` |
| `/api/v1/system/alerts` | GET | 告警列表 | `{alerts: [...]}` |
| `/api/v1/system/dead-letters` | GET | 死信任务列表 | `PaginatedResponse[DeadLetterTask]` |
| `/api/v1/system/dead-letters/{id}/retry` | POST | 重试死信 | `{status: "retrying"}` |

#### 认证与审核员

| 端点 | 方法 | 说明 | 响应 |
|------|------|------|------|
| `/api/v1/auth/login` | POST | 登录 | `{access_token, refresh_token}` |
| `/api/v1/auth/refresh` | POST | 刷新令牌 | `{access_token}` |
| `/api/v1/auth/ws-token` | POST | 获取 WS 短期令牌 | `{ws_token, expires_at}` |
| `/api/v1/reviewers/{id}/stats` | GET | 审核员统计 | `{completed, accuracy, ...}` |
| `/api/v1/reviewers/{id}/golden-stats` | GET | 黄金题统计 | `{total, correct, accuracy}` |

#### 质检与审计

| 端点 | 方法 | 说明 | 响应 |
|------|------|------|------|
| `/api/v1/quality/golden-results` | GET | 黄金题结果 | `{results: [...]}` |
| `/api/v1/quality/irr-report` | GET | IRR 一致性报告 | `{kappa, dimensions}` |
| `/api/v1/audit/events` | GET | 审计事件查询 | `PaginatedResponse[AuditEvent]` |
| `/api/v1/audit/integrity/verify` | POST | 链式完整性校验 | `{valid, break_point}` |

### 7.2 WebSocket接口

使用 Redis Pub/Sub 作为跨实例广播层。

**连接建立（双模式认证）**：

```
模式 A (推荐): POST /api/v1/auth/ws-token -> ws://host/ws/review?token={ws_token}
模式 B (MVP兼容): 直接使用登录 JWT -> ws://host/ws/review?token={login_jwt}
```

**消息信封格式**：

```json
{
  "type": "<消息类型>",
  "payload": { ... },
  "timestamp": "2026-07-01T12:02:00Z",
  "correlation_id": "uuid-v4"
}
```

**消息类型定义（后端为契约权威）**：

| 方向 | 消息类型 | 说明 |
|------|---------|------|
| 后端->前端 | `task_lock_renewed` | 任务锁续约确认 |
| 后端->前端 | `task_lock_expired` | 任务锁超时 |
| 后端->前端 | `task_reassigned` | 任务被重新分配 |
| 后端->前端 | `sla_warning` | SLA 距截止不足 30 分钟 |
| 后端->前端 | `legal_deadline_warning` | 法定时限告警 |
| 后端->前端 | `kill_switch_activated` | kill-switch 触发 |
| 后端->前端 | `break_reminder` | 强制休息提醒 |
| 后端->前端 | `CRITICAL_ALERT` | 高危告警（角色广播） |
| 后端->前端 | `HEARTBEAT_ACK` | 心跳回复 |
| 前端->后端 | `HEARTBEAT` | 心跳（每 30 秒） |
| 前端->后端 | `RECONNECT_SYNC` | 断线重连同步（V2） |

**心跳双协议兼容**：后端同时处理 `HEARTBEAT` 和 `PING`，分别回复 `HEARTBEAT_ACK` 和 `PONG`。

**断线重连**：
- MVP: 前端重连后 invalidate 所有活跃 TanStack Query
- V2: 前端发送 `RECONNECT_SYNC`，后端从 Redis Stream 补发遗漏事件

### 7.3 认证授权（RBAC）

```python
class Role(str, Enum):
    REVIEWER_T1 = "reviewer_t1"
    REVIEWER_T2 = "reviewer_t2"
    REVIEWER_T3 = "reviewer_t3"
    SENIOR_REVIEWER = "senior_reviewer"
    QA_REVIEWER = "qa_reviewer"
    APPEAL_REVIEWER = "appeal_reviewer"
    POLICY_PM = "policy_pm"
    POLICY_APPROVER = "policy_approver"
    OPS_ADMIN = "ops_admin"
    COMPLIANCE_AUDITOR = "compliance_auditor"
    SYSTEM = "system"

ENDPOINT_PERMISSIONS = {
    "review.human.queue": {Role.REVIEWER_T1, Role.REVIEWER_T2, Role.REVIEWER_T3, Role.SENIOR_REVIEWER},
    "review.human.decide": {Role.REVIEWER_T1, Role.REVIEWER_T2, Role.REVIEWER_T3, Role.SENIOR_REVIEWER},
    "appeal.decide": {Role.APPEAL_REVIEWER, Role.REVIEWER_T3},
    "policy.create": {Role.POLICY_PM},
    "policy.approve": {Role.POLICY_APPROVER},
    "audit.read": {Role.COMPLIANCE_AUDITOR, Role.POLICY_PM},
    "system.dead_letters": {Role.OPS_ADMIN},
    "quality.golden_stats": {Role.QA_REVIEWER, Role.OPS_ADMIN},
}
```

**ws-token 生成**：有效期 30 分钟，仅用于握手认证。前端在到期前 60 秒自动续期。

```python
def generate_ws_token(user_id, roles, secret):
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    payload = {"sub": user_id, "roles": roles, "type": "ws", "exp": int(expires_at.timestamp())}
    token = jwt.encode(payload, secret, algorithm="HS256")
    return {"ws_token": token, "expires_at": expires_at.isoformat()}
```

---

## 8. 策略/插件系统详细设计

### 8.1 策略接口定义

所有审核维度必须实现 `BaseReviewStrategy` 抽象基类（见 3.2 节），提供两个核心方法：

- `review(evidence_package, policy_version) -> DimensionVerdict`：执行策略审查
- `build_prompt(evidence_package) -> str`：构建 LLM Prompt

### 8.2 策略注册机制

```python
# backend/app/decision_engine/strategy_registry.py

class StrategyRegistry:
    """
    实例单例 + copy-on-write 热加载。
    类级别 _strategies（启动时写，运行时只读）不变，
    实例级别 _configs 热加载时原子替换引用。
    """
    _strategies: dict[str, Type[BaseReviewStrategy]] = {}
    _instance = None

    @classmethod
    def register(cls, dimension_id: str):
        """装饰器注册策略类"""
        def decorator(strategy_class):
            if not issubclass(strategy_class, BaseReviewStrategy):
                raise TypeError(f"{strategy_class.__name__} 必须继承 BaseReviewStrategy")
            cls._strategies[dimension_id] = strategy_class
            return strategy_class
        return decorator

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """仅用于测试环境，防止测试间状态泄漏。"""
        cls._instance = None

    async def load_from_database(self, db_session):
        """copy-on-write 模式：构建新 configs 字典，原子替换引用。"""
        async with self._lock:
            rows = db_session.query(DimensionRegistryModel).filter(
                DimensionRegistryModel.enabled == True,
                DimensionRegistryModel.status == "active",
            ).all()
            new_configs = {row.dimension_id: StrategyConfig(...) for row in rows}
            self._configs = new_configs  # 原子替换

    def get_configs_snapshot(self):
        """外部模块通过此方法安全获取配置快照。"""
        return self._configs
```

### 8.3 策略配置管理

策略配置从 `dimension_registry` 表加载，Schema 定义：

```python
class StrategyConfig(BaseModel):
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
```

前端通过 `GET /api/v1/policy/dimensions` 获取配置，`DynamicForm` 组件根据 Schema 自动渲染配置表单。

### 8.4 策略版本控制与回滚

**四态生命周期**：`draft -> shadow -> active -> archived`

**版本管理约束**：
- 策略变更必须创建新版本，不可原地修改
- 每条机审决策记录绑定策略版本号，100% 可溯源
- version_id 为单调递增计数器（格式 `rv_{N}`），同天多次变更有不同版本号
- 相同配置内容产生相同 content_hash，防止无变更的版本创建

**API 流程**：
1. `POST /api/v1/policy/versions` 创建草稿
2. `POST /api/v1/policy/versions/{id}/approve` Policy Approver 审批
3. Shadow 模式并行评估（`GET /api/v1/shadow/reports/latest`）
4. `POST /api/v1/policy/versions/{id}/activate` 激活
5. `POST /api/v1/policy/versions/{id}/rollback` 紧急回滚

### 8.5 新增策略完整示例

见 3.5 节"新增策略流程"，包含完整的代码编写、SQL 配置和上线路径。整个过程零改造核心代码。

**前端扩展**：

```typescript
// 第一级：Schema 驱动默认渲染（零代码变更）
// 后端注册表中定义字段，前端 DynamicForm + DefaultVerdictRenderer 自动渲染

// 第二级：自定义渲染器插件（需代码变更）
pluginRegistry.register({
  dimensionId: 'dim_aigc_disclosure',
  VerdictRenderer: AIGCVerdictRenderer,
  ConfigRenderer: AIGCConfigRenderer,
});
```

---

## 9. 基础设施

### 9.1 消息队列设计

**MVP 使用 Redis Streams**（团队已引入 Redis，无需额外运维 Kafka）。V2 日处理量超 100 万条时迁移 Kafka。

```python
STREAMS = {
    "video:ingested":           "视频摄取完成，触发证据提取",
    "evidence:extracted":       "证据包就绪，触发初筛",
    "safety:filtered":          "初筛完成，触发 LLM 审查",
    "llm:reviewed":             "LLM 审查完成，触发规则聚合",
    "decision:made":            "机审裁决产出，触发路由",
    "review:human:decided":     "人审决策完成，触发回流",
    "appeal:decided":           "申诉裁决，触发恢复连锁",
    "flywheel:sample:created":  "回流样本产出",
    "critical:alert":           "高危告警",
}
```

### 9.2 缓存策略

| 缓存场景 | Key 模式 | TTL | 策略 |
|---------|---------|-----|------|
| 策略版本配置 | `policy:active:{jurisdiction}` | 5 分钟 | Write-through |
| 维度注册表 | `dimension:registry:all` | 10 分钟 | 热加载刷新 |
| 案件锁状态 | `lock:case:{task_id}` | 30 分钟 | 分布式锁，心跳续租 |
| CSAM 曝光计数 | `csam:exposure:{reviewer_id}:{date}` | 24 小时 | 原子 INCR |
| 限流计数 | `ratelimit:{endpoint}:{user_id}` | 按窗口 | 滑动窗口 |
| 熔断器状态 | `circuit:{name}:*` | 按配置 | 滑动窗口分布式 |
| WebSocket 事件 | `ws:events:{reviewer_id}` | 1 小时 | Redis Stream |

### 9.3 存储设计

```
对象存储桶:
+-- vgp-uploads/                     # 原始上传视频
+-- vgp-evidence/                    # 证据包存储（关键帧 + JSON）
+-- vgp-csam-vault/                  # CSAM 独立加密桶（仅 critical_specialist 可访问）
+-- vgp-flywheel/                    # 回流训练数据（JSONL 导出）
```

### 9.4 监控告警体系

**Prometheus 自定义业务指标**：

```python
METRICS = {
    "vgp_pipeline_duration_seconds":          "机审流水线总耗时",
    "vgp_llm_review_seconds":                 "LLM 审查耗时",
    "vgp_llm_tokens_used_total":              "LLM Token 消耗总量",
    "vgp_pipeline_decision_total":            "决策分布 (pass/block/review)",
    "vgp_human_review_queue_size":            "人审队列深度",
    "vgp_human_review_sla_violations_total":  "SLA 违规次数",
    "vgp_human_review_override_rate":         "人审推翻机审比率",
    "vgp_appeal_overturn_rate":               "申诉改判率",
    "vgp_flywheel_samples_total":             "回流样本总数",
    "vgp_dead_letter_tasks_total":            "死信任务累计数",
    "vgp_circuit_breaker_failure_ratio":      "熔断器失败比率",
    "vgp_golden_test_accuracy":               "黄金题准确率",
}
```

**告警规则**：

| 告警名 | 条件 | 严重度 | 通知 |
|--------|------|--------|------|
| P0_CSAM_REPORT_OVERDUE | CSAM 检测到上报延迟超标 | critical | compliance + oncall |
| P1_PIPELINE_SLA_BREACH | 初筛 P95 > 3s 持续 5m | high | sre_oncall |
| P1_CIRCUIT_BREAKER_OPEN | LLM 熔断器打开 > 2m | high | sre_oncall |
| P1_DEAD_LETTER_ACCUMULATION | 1h 内死信 > 10 条 | high | sre + ops |
| P2_QUEUE_BACKLOG | 人审队列 > 10000 | medium | ops_admin |
| P2_GOLDEN_TEST_ACCURACY_LOW | 黄金题准确率 < 70% | medium | qa + ops |

---

## 10. 可靠性与容错设计

### 10.1 熔断与降级

```python
# backend/app/common/circuit_breaker.py

class CircuitBreaker:
    """
    Redis 分布式滑动窗口熔断器。
    
    修复 reset-on-any-success 缺陷：采用滑动时间窗口 + 失败率机制。
    在配置的时间窗口内记录所有调用结果，失败率超阈值触发熔断。
    成功调用不重置失败记录，而是作为正常样本参与失败率计算。
    """

    def __init__(self, redis_client, failure_rate_threshold=0.50,
                 minimum_calls=5, window_seconds=60,
                 recovery_timeout=60, name="default"):
        self.redis = redis_client
        self.failure_rate_threshold = failure_rate_threshold
        self.minimum_calls = minimum_calls
        self.window_seconds = window_seconds
        self.recovery_timeout = recovery_timeout
        self.name = name

    async def _on_failure(self):
        """记录失败到 Redis Sorted Set，计算窗口内失败率。"""
        now = time.time()
        cutoff = now - self.window_seconds
        # 清理过期数据
        await self.redis.zremrangebyscore(self._failure_key, 0, cutoff)
        await self.redis.zremrangebyscore(self._success_key, 0, cutoff)
        # 记录失败
        await self.redis.zadd(self._failure_key, {str(now): now})
        # 计算失败率
        failure_count = await self.redis.zcard(self._failure_key)
        success_count = await self.redis.zcard(self._success_key)
        total_calls = failure_count + success_count
        if total_calls >= self.minimum_calls:
            failure_rate = failure_count / total_calls
            if failure_rate >= self.failure_rate_threshold:
                await self._set_state(CircuitState.OPEN)
```

**降级策略**：

| 故障场景 | 降级策略 | 影响 |
|---------|---------|------|
| LLM API 不可用 | verdict 置 UNCERTAIN，路由人审 | 人审队列压力增大 |
| 云安全 API 不可用 | 跳过初筛，直接进 LLM 审查 | LLM 成本上升 |
| Redis 不可用 | 策略配置回退数据库直查；锁退化为行锁 | 性能下降但不中断 |
| PostgreSQL 主库不可用 | 读请求切只读副本；写请求排队 | 新审核暂停 |

### 10.2 重试机制

```python
def retry_with_backoff(max_retries=3, base_delay=1.0, max_delay=60.0,
                        exponential_base=2.0, jitter=True):
    """指数退避重试装饰器，支持随机抖动防止雷群效应。"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        raise
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)
                    if jitter:
                        delay = delay * (0.5 + random.random())
                    await asyncio.sleep(delay)
        return wrapper
    return decorator
```

**Celery 任务独立重试配置**：
- 证据提取: 3 次重试，30s 延迟
- 安全初筛: 2 次重试，10s 延迟
- LLM 审查: 2 次重试，15s 延迟，独立超时 120s
- 决策聚合: 1 次重试

### 10.3 幂等性设计

```python
class IdempotencyManager:
    """
    优先使用客户端 Idempotency-Key 请求头（行业标准）。
    关键写入端点强制要求：upload, decide, appeal。
    """
    REQUIRED_ENDPOINTS = {
        "/api/v1/content/upload",
        "/api/v1/review/human/{task_id}/decide",
        "/api/v1/appeal/submit",
    }

    async def check_and_set(self, idempotency_key, response_data):
        cache_key = f"idempotency:{idempotency_key}"
        existing = await self.redis.get(cache_key)
        if existing:
            return json.loads(existing)  # 重复请求，返回之前的响应
        await self.redis.setex(cache_key, 86400, json.dumps(response_data))
        return None
```

### 10.4 数据一致性保证

**事务策略**：
1. 机审裁决 + 审计日志：同一数据库事务，原子提交
2. 人审决策 + 状态更新 + 审计日志：同一事务
3. 申诉改判 + 恢复连锁：改判事务强一致，恢复连锁异步最终一致
4. 数据回流：最终一致性（样本先写暂存区，ETL 批处理写训练集）

**乐观锁**：ContentItem.version 字段实现乐观锁，并发冲突时重试。critical 短路拥有最高写优先级。

---

## 11. 性能优化

### 11.1 后端性能优化

| 优化项 | 实现方式 |
|--------|---------|
| 流水线阶段独立化 | Celery chain 替代单一任务，已完成阶段不重复执行 |
| DB 连接池管理 | db session 由调用方传入，避免内部二次创建导致连接池耗尽 |
| EXISTS 替代 IN 子查询 | 审核员已处理视频排除查询，避免物化大列表 |
| SKIP LOCKED | 任务领取使用 `SELECT FOR UPDATE SKIP LOCKED`，并发不阻塞 |
| 异步健康检查 | 使用 `redis.asyncio.Redis`，不阻塞事件循环 |
| 策略并行执行 | `asyncio.gather` 并行执行所有已启用策略，单策略 25s 超时 |
| 短路优化 | CSAM 哈希命中 / 高置信安全风险直接跳过 LLM，节省 API 调用 |

### 11.2 前端性能优化

| 优化项 | 实现方式 |
|--------|---------|
| 视频懒加载 | 仅进入案件时加载视频，队列只加载缩略图 |
| 自适应码率 | HLS/DASH 流，根据网络自动切换 360p/720p/1080p |
| 虚拟滚动 | react-virtuoso，队列/审计日志等长列表 |
| 路由级代码分割 | Vite 自动 chunk + `lazy()` 动态加载 |
| ECharts 按需引入 | 只 import 使用的图表类型 |
| 请求去重 | TanStack Query staleTime=30s，WebSocket 在线时不轮询 |
| 乐观更新 | 提交处置时前端立即更新，失败回滚 |
| Service Worker | StaleWhileRevalidate 缓存证据帧图片 |
| 预加载 | 后台预加载队列中下一条的证据包元数据 |
| 首屏体积控制 | 主 chunk < 200KB gzipped，路由 chunk < 100KB |

---

## 12. 安全设计

### 12.1 认证与授权

- **JWT 认证**：登录获取 access_token + refresh_token
- **RBAC 权限**：端点级角色校验，13 种角色覆盖完整职能
- **WebSocket 专用令牌**：type='ws' 的短期 JWT，30 分钟有效期
- **双模式 WS 认证**：兼容 ws-token 和登录 JWT
- **多标签页同步**：BroadcastChannel 同步登出和 token 刷新

### 12.2 数据安全

- **CSAM 独立加密桶**：独立访问控制，仅 critical_specialist + compliance_auditor 可访问
- **内部理由与对外 SoR 物理分离**：`internal_notes` 与 `sor_text` 独立字段
- **LLM Prompt 净化**：用户内容用 `<user_content>` 分隔符隔离，防止注入
- **限流保护**：令牌桶限流器覆盖上传、登录、决策提交、ws-token 等端点

```python
RATE_LIMITS = {
    "content.upload": {"max_requests": 10, "window_seconds": 60, "by": "user"},
    "appeal.submit": {"max_requests": 5, "window_seconds": 3600, "by": "user"},
    "auth.login": {"max_requests": 10, "window_seconds": 60, "by": "ip"},
    "auth.ws_token": {"max_requests": 10, "window_seconds": 60, "by": "user"},
    "review.human.decide": {"max_requests": 60, "window_seconds": 60, "by": "user"},
}
```

### 12.3 审计追踪

- **append-only 审计日志**：不可修改，SHA-256 链式哈希
- **链式完整性校验**：`POST /api/v1/audit/integrity/verify` 检测篡改
- **全链路追溯**：按 content_id 从摄取 -> 机审 -> 人审 -> 申诉 -> 最终处置
- **版本绑定**：每条决策记录绑定 policy_version + rule_version + model_version
- **申诉硬约束**：申诉通道内不可加重处置，改判只能从 BLOCK -> PASS

---

## 13. 部署方案

### 13.1 容器化部署

```yaml
# docker-compose.yml (MVP 部署)
services:
  api:
    build: ./backend
    ports: ["8000:8000"]
    depends_on: [postgres, redis, minio]
    environment:
      - DATABASE_URL=postgresql+asyncpg://...
      - REDIS_URL=redis://redis:6379
      - S3_ENDPOINT=http://minio:9000

  celery-evidence:
    build: ./backend
    command: celery -A app.tasks worker -Q evidence -c 4
    
  celery-review:
    build: ./backend
    command: celery -A app.tasks worker -Q review -c 2
    
  celery-flywheel:
    build: ./backend
    command: celery -A app.tasks worker -Q flywheel -c 1
    
  celery-beat:
    build: ./backend
    command: celery -A app.tasks beat

  frontend:
    build: ./frontend
    ports: ["3000:80"]

  postgres:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]
    
  redis:
    image: redis:7-alpine
    
  minio:
    image: minio/minio
    command: server /data
```

### 13.2 CI/CD流水线

```
代码提交 -> Lint/Type Check -> 单元测试 -> 契约测试 (MSW + Zod)
  -> 集成测试 -> Docker Build -> 部署 Staging -> E2E 测试
  -> 人工确认 -> 部署 Production
```

**契约测试**确保前后端集成不出现字段缺失、类型不匹配：

```typescript
// MSW + Zod 契约测试示例
const PaginatedResponseSchema = z.object({
  items: z.array(z.any()),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  next_offset: z.number().nullable(),
});

it('队列分页响应应匹配 schema', async () => {
  const response = await fetch('/api/v1/review/human/queue?offset=0&limit=20');
  const result = PaginatedResponseSchema.safeParse(await response.json());
  expect(result.success).toBe(true);
});
```

### 13.3 环境管理

| 环境 | 用途 | 部署方式 | 特殊配置 |
|------|------|---------|---------|
| local | 开发 | Docker Compose | 使用 MinIO 替代 S3 |
| staging | 集成测试 | Docker Compose / K8s | Shadow 模式策略 |
| production | 生产 | K8s (V2) | 多副本 + 自动扩缩 |

**Feature Flag 里程碑规划**：

| Flag | MVP | V1.1 | V2 | 前置条件 |
|------|-----|------|-----|---------|
| `enableFullDispositionMatrix` | false | false | true | 后端返回 7 态 |
| `enableDashboardHealth` | false | true | true | 健康 API 就绪 |
| `enableSoRTemplates` | false | true | true | SoR 模块就绪 |
| `enableReconnectSync` | false | true | true | WS 事件重放就绪 |

---

## 14. 开发规范

### 14.1 代码规范

**后端**：
- Python 3.11+，使用 type hints
- Pydantic v2 数据校验
- 所有公共方法必须有 docstring
- 异步函数使用 `async def`
- 日志使用 structlog 结构化格式

**前端**：
- TypeScript strict 模式
- ESLint + Prettier 统一格式
- 组件文件使用 PascalCase，工具文件使用 camelCase
- 所有可交互元素必须包含 ARIA 属性
- 色彩对比度满足 WCAG 2.1 AA 标准

### 14.2 Git工作流

- 主分支 `main` 受保护，需 PR + Code Review
- 功能分支命名: `feat/xxx`、`fix/xxx`、`refactor/xxx`
- Commit message 使用 Conventional Commits
- 策略变更必须关联 Jira ticket

### 14.3 测试策略

| 层级 | 工具 | 覆盖目标 |
|------|------|---------|
| 单元测试 | pytest / Vitest | 策略逻辑、规则引擎、状态机 |
| 集成测试 | pytest + httpx / RTL | API 端点、数据库交互 |
| 契约测试 | MSW + Zod | 前后端 API 契约一致性 |
| E2E 测试 | Playwright | 人审工作台全流程 |

**关键测试场景**：
- 策略注册表热加载不丢失配置
- 熔断器滑动窗口在 80% 失败率下正确打开
- 并发领取任务不产生重复分配
- 黄金题评估结果正确包含在响应中
- 分页响应字段与前端 Schema 严格匹配
- WebSocket 断线重连后数据自动恢复
