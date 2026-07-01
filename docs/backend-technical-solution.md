│                     │ 审核员达疲劳上限          │ 拒绝分配，推送休息通知 │
└─────────────────────┴──────────────────────────┴───────────────────────┘

最终兜底原则：任何阶段不可用 → NEEDS_REVIEW（保守策略），禁止静默通过
CSAM 例外：任何阶段不可用 → 硬阻断，不允许降级为 NEEDS_REVIEW，须人工干预

### 5.2 幂等性设计

```python
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_max_retries=3,
    task_default_retry_delay=5,
    task_serializer="json",
    result_expires=86400,
)

@celery_app.task(bind=True)
def extract_evidence(self, video_id: str, content_hash: str):
    try:
        ...
    except TransientError as exc:
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
```

### 5.3 监控告警【修订：LLMTimeoutHigh 阈值从 10% 调整为 25%，对齐 25s 超时基准】

```yaml
groups:
  - name: video-governance-platform
    rules:
      - alert: EvidenceExtractionFailureHigh
        expr: rate(evidence_extraction_failed_total[5m]) /
              rate(evidence_extraction_total[5m]) > 0.05
        for: 2m
        labels: { severity: warning }
        annotations:
          summary: "证据提取失败率超过 5%"

      # 【修订】超时阈值从 10% 调整为 25%（单次超时从 5s 改为 25s，基准不同）
      - alert: LLMTimeoutHigh
        expr: rate(llm_timeout_total[5m]) / rate(llm_call_total[5m]) > 0.25
        for: 2m
        labels: { severity: critical }
        annotations:
          summary: "LLM 超时率超过 25%（25s 基准），触发降级告警"

      - alert: HumanReviewQueueBacklog
        expr: redis_zcard{key="human_review:queue"} > 500
        for: 5m
        labels: { severity: warning }
        annotations:
          summary: "人审任务队列积压超过 500 条"

      - alert: LegalDeadlineImminent
        expr: count(human_review_task_legal_deadline_remaining_minutes < 30) > 0
        for: 0m
        labels: { severity: critical }
        annotations:
          summary: "存在法定时限不足 30 分钟的未处理任务"

      - alert: OverturnRateHigh
        expr: rate(appeal_overturned_total[1h]) /
              rate(decision_total[1h]) > 0.15
        for: 5m
        labels: { severity: critical }
        annotations:
          summary: "改判率超 15%，触发自动护栏暂停灰度放量"

      - alert: ShadowDivergenceHigh
        expr: shadow_policy_divergence_rate > 0.20
        for: 10m
        labels: { severity: warning }
        annotations:
          summary: "Shadow 策略分歧率超 20%，请人工 Review Prompt 和阈值"

      # 【新增】反疲劳告警
      - alert: ReviewerFatigueLimitHit
        expr: increase(reviewer_fatigue_limit_hit_total[1h]) > 5
        for: 0m
        labels: { severity: warning }
        annotations:
          summary: "1 小时内超过 5 次审核员达疲劳上限，建议增加排班"

      - alert: CSAMIsolationFailure
        expr: increase(csam_isolation_failure_total[5m]) > 0
        for: 0m
        labels: { severity: critical }
        annotations:
          summary: "CSAM 隔离通道写入失败，需立即人工介入"
```

**关键 Prometheus 指标列表：**

| 指标名 | 类型 | 阈值 | 含义 |
|--------|------|------|------|
| `evidence_extraction_duration_seconds` | Histogram | p99 < 60s | 证据提取耗时 |
| `llm_call_duration_seconds` | Histogram | p95 < 25s | LLM 调用耗时（修订） |
| `decision_engine_throughput` | Counter | > 100/min | 决策引擎吞吐 |
| `human_review_queue_size` | Gauge | < 500 | 人审队列积压 |
| `appeal_overturn_rate` | Gauge | < 15% | 申诉改判率 |
| `modality_unavailable_rate` | Gauge | < 10% | 模态不可用率 |
| `kill_switch_active` | Gauge | = 0 正常 | kill-switch 状态 |
| `shadow_policy_divergence_rate` | Gauge | < 20% | Shadow 分歧率（新增） |
| `reviewer_fatigue_limit_hit_total` | Counter | — | 疲劳上限触发次数（新增） |
| `csam_isolation_failure_total` | Counter | = 0 | CSAM 隔离失败次数（新增） |

---

## 6. WebSocket 实时推送协议【新增章节】

WebSocket 是人审前后端集成的核心依赖，用于推送锁状态变更、SLA 预警和系统告警。

### 6.1 消息格式

所有消息为 JSON，统一结构如下：

```typescript
// 通用消息信封
interface WSMessage {
  type: WSMessageType;
  payload: Record<string, unknown>;
  timestamp: string;        // ISO 8601
  correlation_id: string;   // UUID，用于客户端去重
}

type WSMessageType =
  | "task_lock_renewed"       // 任务锁续约确认
  | "task_lock_expired"       // 任务锁超时，任务已被释放
  | "task_reassigned"         // 任务被系统重新分配
  | "sla_warning"             // SLA 距截止时间不足 30 分钟
  | "legal_deadline_warning"  // 法定时限不足 30 分钟
  | "kill_switch_activated"   // kill-switch 触发，切全人审
  | "queue_spike"             // 队列积压告警
  | "break_reminder"          // 强制休息提醒
  | "ping"                    // 心跳
  | "pong";                   // 心跳响应
```

各消息 payload 示例：

```json
// sla_warning
{
  "type": "sla_warning",
  "payload": {
    "task_id": "task_abc123",
    "video_id": "vid_xyz789",
    "deadline_at": "2026-07-01T12:30:00Z",
    "remaining_minutes": 28
  },
  "timestamp": "2026-07-01T12:02:00Z",
  "correlation_id": "uuid-v4"
}

// break_reminder
{
  "type": "break_reminder",
  "payload": {
    "break_type": "mandatory",
    "duration_minutes": 10,
    "reason": "Continuous review exceeded 2 hours"
  },
  "timestamp": "2026-07-01T14:00:00Z",
  "correlation_id": "uuid-v4"
}

// kill_switch_activated
{
  "type": "kill_switch_activated",
  "payload": {
    "activated_by": "auto_guardrail",
    "reason": "overturn_rate_exceeded_15pct",
    "affected_policies": ["minor_compliance", "marketing_compliance"]
  },
  "timestamp": "2026-07-01T10:00:00Z",
  "correlation_id": "uuid-v4"
}
```

### 6.2 鉴权机制

```python
from fastapi import WebSocket, WebSocketDisconnect, Depends
from fastapi.security import HTTPBearer

@app.websocket("/ws/v1/review")
async def review_websocket(
    websocket: WebSocket,
    token: str = Query(...),   # JWT 通过 query param 传入（WebSocket 不支持自定义 Header）
):
    # 1. 鉴权：验证 JWT，提取 reviewer_id
    try:
        reviewer = await verify_jwt_token(token)
    except InvalidTokenError:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    # 2. 注册会话到 Redis（用于服务端主动推送）
    connection_id = str(uuid4())
    redis_client.setex(f"ws:session:{reviewer.id}", 600, connection_id)
    connection_manager.register(reviewer.id, websocket)

    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_json(), timeout=60)
            if data.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat(),
                    "correlation_id": data.get("correlation_id", ""),
                })
                # 续约 Redis 会话
                redis_client.expire(f"ws:session:{reviewer.id}", 600)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        connection_manager.unregister(reviewer.id)
        redis_client.delete(f"ws:session:{reviewer.id}")
```

### 6.3 重连策略（客户端）

```typescript
// 前端 WebSocket 客户端重连策略
class ReviewWSClient {
  private retryCount = 0;
  private readonly MAX_RETRY = 8;
  private readonly BASE_DELAY_MS = 1000;
  private readonly MAX_DELAY_MS = 30000;

  connect(reviewerId: string, token: string): void {
    this.ws = new WebSocket(`wss://api.example.com/ws/v1/review?token=${token}`);

    this.ws.onclose = (event) => {
      if (event.code === 4001) return;  // 鉴权失败，不重连
      this.scheduleReconnect();
    };

    this.ws.onopen = () => {
      this.retryCount = 0;             // 连接成功后重置重试计数
      this.startHeartbeat();
    };
  }

  private scheduleReconnect(): void {
    if (this.retryCount >= this.MAX_RETRY) {
      console.error("WebSocket max retries exceeded, please refresh");
      return;
    }
    // 指数退避：1s → 2s → 4s → 8s → ... → 30s 上限
    const delay = Math.min(
      this.BASE_DELAY_MS * Math.pow(2, this.retryCount),
      this.MAX_DELAY_MS
    );
    setTimeout(() => { this.retryCount++; this.connect(/* ... */); }, delay);
  }

  private startHeartbeat(): void {
    setInterval(() => {
      if (this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "ping", correlation_id: crypto.randomUUID() }));
      }
    }, 30000);
  }
}
```

### 6.4 服务端广播工具

```python
class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}

    def register(self, reviewer_id: str, ws: WebSocket):
        self._connections[reviewer_id] = ws

    def unregister(self, reviewer_id: str):
        self._connections.pop(reviewer_id, None)

    async def send_to(self, reviewer_id: str, message: dict):
        ws = self._connections.get(reviewer_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.unregister(reviewer_id)

    async def broadcast(self, message: dict):
        """广播给所有在线审核员（用于 kill-switch 等全局事件）"""
        for reviewer_id, ws in list(self._connections.items()):
            await self.send_to(reviewer_id, message)

connection_manager = ConnectionManager()
```

---

## 7. 策略新增流程（零改代码扩展）

### 步骤 1：新建策略文件

```python
# policy_reviewer/policies/gambling_policy.py
from .base import PolicyBase

class GamblingPolicy(PolicyBase):
    policy_id = "gambling_compliance"
    version = "v1.0"
    description = "赌博/彩票内容合规审查"

    @property
    def prompt_template(self) -> str:
        return """
请审查视频内容是否涉及非法赌博、彩票销售或赌博诱导行为。
证据：
- 转录文本：{{ evidence.asr_transcript | map(attribute='text') | join(' ') | truncate(2000) }}
- 场景标签：{{ evidence.scene_tags | map(attribute='tag') | join(', ') }}
- OCR文字：{{ evidence.ocr.texts if evidence.ocr else [] }}

Few-shot 示例（略）

输出格式（严格 JSON，枚举值必须为 VIOLATION/NO_VIOLATION/UNCERTAIN）：
{"decision":"<VIOLATION|NO_VIOLATION|UNCERTAIN>","confidence":<0-1>,"reason":"<内部理由>","evidence_refs":["<字段路径>"]}
"""

    @property
    def thresholds(self) -> dict:
        return {"block_confidence": 0.80, "pass_confidence": 0.75}
```

### 步骤 2：注册策略（一行）

```python
# policy_reviewer/policies/__init__.py
from .gambling_policy import GamblingPolicy
PolicyRegistry.register(GamblingPolicy())
```

### 步骤 3：写入策略版本数据库

```sql
INSERT INTO policy_versions (policy_id, version, config, is_active, is_shadow)
VALUES ('gambling_compliance', 'v1.0',
        '{"block_confidence": 0.80, "pass_confidence": 0.75}',
        FALSE, TRUE);
```

### 步骤 4：Shadow 模式验证（2-7 天）

```python
# 监控 shadow_policy_divergence_rate（对应告警 ShadowDivergenceHigh，阈值 20%）
# 查询 API：GET /api/v1/shadow-reports?policy_id=gambling_compliance&days=7
```

### 步骤 5：灰度放量

```python
redis_client.set("rollout:gambling_compliance:v1.0:pct", "1")
# 自动护栏：改判率 > 15% 或 Shadow 分歧率 > 20% → 自动置 paused
```

### 步骤 6：全量激活

```sql
UPDATE policy_versions
SET is_active = TRUE, is_shadow = FALSE, activated_at = NOW()
WHERE policy_id = 'gambling_compliance' AND version = 'v1.0';
```

---

## 8. 部署架构

### 8.1 Kubernetes Deployment 要点

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: evidence-extractor
  namespace: vgp
spec:
  replicas: 3
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-accelerator: nvidia-tesla-t4
      containers:
        - name: worker
          image: vgp/evidence-extractor:v1.1
          resources:
            requests: { cpu: "2", memory: "8Gi", nvidia.com/gpu: "1" }
            limits:   { cpu: "4", memory: "16Gi", nvidia.com/gpu: "1" }
          env:
            - name: CELERY_BROKER_URL
              valueFrom: { secretKeyRef: { name: redis-secret, key: url } }
          livenessProbe:
            exec:
              command: ["celery", "-A", "celery_app", "inspect", "ping"]
            initialDelaySeconds: 30
            periodSeconds: 30
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: policy-reviewer
  namespace: vgp
spec:
  replicas: 5
  template:
    spec:
      containers:
        - name: worker
          image: vgp/policy-reviewer:v1.1
          resources:
            requests: { cpu: "1", memory: "2Gi" }
            limits:   { cpu: "2", memory: "4Gi" }
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: human-review-api
  namespace: vgp
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: api
          image: vgp/human-review-api:v1.1
          ports:
            - containerPort: 8000   # REST
            - containerPort: 8001   # WebSocket
          readinessProbe:
            httpGet: { path: /health, port: 8000 }
          resources:
            requests: { cpu: "500m", memory: "1Gi" }
```

### 8.2 Flywheel Worker PVC 挂载（备用方案）【修订】

```yaml
# 若使用 PVC 方式替代 minio.put_object() 流式写入
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: flywheel-pvc
  namespace: vgp
spec:
  accessModes: [ReadWriteMany]
  resources:
    requests:
      storage: 50Gi
---
# flywheel-worker Deployment 挂载 PVC
volumes:
  - name: flywheel-data
    persistentVolumeClaim:
      claimName: flywheel-pvc
containers:
  - name: worker
    volumeMounts:
      - name: flywheel-data
        mountPath: /data/flywheel   # 替代 /tmp 的持久化路径
```

### 8.3 水平扩缩容策略（HPA）

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: evidence-extractor-hpa
  namespace: vgp
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: evidence-extractor
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: External
      external:
        metric:
          name: celery_queue_length
          selector:
            matchLabels: { queue: evidence }
        target:
          type: AverageValue
          averageValue: "50"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: human-review-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: human-review-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### 8.4 存储方案

| 存储类型 | 用途 | 方案 | 备份策略 |
|--------|------|------|---------|
| 主数据库 | 业务数据、决策链 | PostgreSQL 16（主从 + 流复制） | WAL 归档 + 每日全量快照 |
| 缓存/队列 | 分布式锁、优先级队列 | Redis 7 Sentinel（1主2从） | AOF 持久化 + 定期 RDB |
| 对象存储（普通） | 视频文件、截帧图片、飞轮数据 | MinIO / AWS S3 | 跨区域复制 |
| 对象存储（CSAM 隔离） | CSAM 内容，物理隔离 | 独立加密 MinIO 桶，KMS 密钥管理 | 独立备份，访问审计 |
| 监控数据 | Metrics 时序数据 | Prometheus TSDB + Thanos | 30 天保留 |
| 日志 | 服务日志 | EFK（普通）+ 独立加密流（CSAM） | 7 天热存储，冷存 S3 |

---

## 9. 专家评审记录【新增章节】

### 9.1 评审基本信息

| 项目 | 内容 |
|------|------|
| 评审日期 | 2026-07-01 |
| 文档版本（评审时） | v1.0 |
| 评审评分 | **72 / 100** |
| 修订后版本 | v1.1 |

### 9.2 立即修复项（已完成）

| 编号 | 问题描述 | 严重程度 | 修订位置 | 修订状态 |
|------|----------|----------|----------|----------|
| F-1 | `anthropic.Anthropic()` 同步客户端用于异步上下文，policy-reviewer 服务运行时必现阻塞 | 致命 Bug | §2.3 LLM 统一调用层 | 已修复：改为 `anthropic.AsyncAnthropic()` |
| F-2 | `EvidencePackage` 缺少 9 个 PRD §1.B 要求字段，`scene_tags` 类型错误，`objects_detected` 命名不一致 | 高 | §2.1 EvidencePackage 模型 | 已修复：补充全部字段，改为 `list[SceneTag]`，重命名为 `object_detections` |
| F-3 | LLM 输出枚举（`pass/block/needs_review`）与 PRD §1.C 定义（`VIOLATION/NO_VIOLATION/UNCERTAIN`）混用，无类型分离 | 高 | §2.3 DimensionVerdictOutput、PolicyDecision | 已修复：新增 `DimensionVerdictOutput`，`PolicyDecision` 专用于内部聚合，`to_policy_decision()` 承担映射 |
| F-4 | Flywheel Worker 写入 `/tmp`，在 Kubernetes Pod 中存在临时存储限制和数据丢失风险 | 高 | §3.4 数据回流服务 | 已修复：改用 `minio.put_object()` 流式写入，备用方案使用 PVC 挂载路径 |
| F-5 | LLM 超时 5s 低于 P95 目标，重试间隔 1s→4s 过短；`LLMTimeoutHigh` 告警阈值 10% 基于旧超时基准 | 中 | §2.3 LLM 调用层、§5.3 监控告警 | 已修复：超时改为 25s，重试改为指数退避 5s→10s，告警阈值改为 25% |

### 9.3 跨文档一致性修复（已完成）

| 编号 | 问题描述 | 修订位置 | 修订状态 |
|------|----------|----------|----------|
| C-1 | EvidencePackage 字段名三文档各异，无显式映射层 | §0.1 跨文档契约 | 已修复：新增字段映射权威表 |
| C-2 | 决策枚举三套体系无映射规则，工程师只能靠猜 | §0.2 三层枚举映射 | 已修复：定义唯一权威映射规则及执行入口 |
| C-3 | CSAM 处理路径三文档层次不同，无统一隔离边界 | §2.2 CSAM 隔离通道 | 已修复：新增 `CSAMIsolationProtocol`，定义独立加密存储、审计日志、法律通知路径 |
| C-4 | WebSocket 协议（消息格式、鉴权、重连）在两份技术方案中均为协议真空 | §6 WebSocket 实时推送协议 | 已修复：新增完整章节，覆盖消息信封、鉴权、指数退避重连 |
| C-5 | 反疲劳设计在三份文档中均缺失，劳工合规红线 | §3.5 反疲劳设计 | 已修复：新增 `AntiFatigueGuard`，定义每日上限、CSAM 专项上限、强制休息逻辑及合规审计日志 |
| C-6 | LLM Token 预算按视频时长分档截断在 PRD §1.A.3 中有明确要求，后端无实现 | §2.1 Token 预算分档截断 | 已修复：新增 `compute_token_budget()` 和 `truncate_evidence_for_llm()`，按时长四档分配 |
| C-7 | Shadow 模式无报告聚合表和 API，前端 ShadowCompareView 数据来源未定义 | §2.3 Shadow 报告聚合、§4.1 DDL | 已修复：新增 `shadow_policy_reports` 表、`generate_shadow_report` 任务、`GET /api/v1/shadow-reports` API |

### 9.4 安全加固（本次修订附加）

| 项目 | 说明 |
|------|------|
| Prompt 注入防御 | `PolicyBase.build_prompt()` 改用 Jinja2 `SandboxedEnvironment`，防止证据包内容中的模板注入 |
| CSAM 日志隔离 | CSAM 事件不写入公共 ELK，仅写独立加密审计日志流，防止内容特征通过日志泄露 |
| 低置信度 block 防护 | `to_policy_decision()` 强制：`VIOLATION` 且 `confidence < block_threshold` 只能映射为 `needs_review`，不允许低置信度直接 block |

### 9.5 遗留待办（下一 Sprint）

| 编号 | 描述 | 优先级 |
|------|------|--------|
| T-1 | Prompt sanitize 规范需 PRD 补充后，由 LLM 策略层统一实现输入清洗（当前 SandboxedEnvironment 仅防模板注入，不防语义注入） | P0 |
| T-2 | policy-reviewer 服务需在修复 `AsyncAnthropic` 后执行全量集成回归测试，覆盖所有策略 + 降级链 + Shadow 模式路径 | P0 |
| T-3 | 三端负责人对齐 §0.1 字段契约后，前端 TypeScript 类型定义需同步更新（当前前端无对应字段） | P1 |
| T-4 | CSAM 法律合规通知接口需对接实际执法机关上报 API，当前仅为占位实现 | P1 |
| T-5 | 审核员心理健康支持方案需 HR 介入制定，技术侧提供 CSAM 曝光次数统计接口（`/api/v1/review/fatigue-status` 已实现） | P1 |

---

> **文档版本：v1.1 / 2026-07-01**
> 本修订版基于专家评审意见（72/100）完成全面修订，解决了 5 项立即修复问题和 7 项跨文档一致性问题，并附加 Prompt 注入防御和 CSAM 日志隔离加固。核心架构（三阶段漏斗、策略模式、降级链）保持不变。
