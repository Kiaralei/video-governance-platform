# 视频治理平台技术选型理由书

> **版本**: 1.0 | **日期**: 2026-07-01

---

## 1. 架构模式

### 选型：模块化单体（Modular Monolith）

| 候选方案 | 优势 | 劣势 |
|---------|------|------|
| **模块化单体** ✅ | 部署简单、事务一致性强、调试直观 | 单进程扩缩容粒度粗 |
| 微服务 | 独立扩缩容、技术栈自由 | 运维复杂度高、分布式事务难、需 K8s 基建 |
| 传统单体 | 最简部署 | 无模块边界、代码腐化快、无法渐进拆分 |

**选型理由**：

1. **团队规模匹配**：MVP 阶段 3-8 人，微服务带来的服务网格、链路追踪、配置中心等运维负担远超团队承载能力。模块化单体在单一部署单元内通过 Python Package 实现逻辑隔离，享受单体的简单部署同时保留清晰的模块边界。
2. **数据一致性刚需**：机审→人审→申诉的核心链路跨多个实体（ContentItem、EvidencePackage、HumanReviewTask、AppealCase），状态流转和审计日志必须原子写入。单体内的数据库事务天然满足，微服务则需引入 Saga 或 2PC。
3. **演进路径明确**：当某模块（如证据提取的 CPU 密集计算）出现独立扩缩容需求时，Celery Worker 已经是独立进程，可平滑拆为独立服务。模块间通过 Service 层调用而非直接 import Model，拆分成本可控。

**风险缓解**：通过 Celery Worker 进程实现 CPU 密集任务（抽帧、OCR）与 API 服务的隔离，避免计算任务阻塞 HTTP 请求。

---

## 2. 后端技术栈

### 2.1 编程语言：Python 3.11+

| 候选 | 优势 | 劣势 |
|------|------|------|
| **Python 3.11+** ✅ | AI/ML 生态完整、团队技术栈、FastAPI 异步性能足够 | GIL 限制 CPU 并行、运行时类型检查弱 |
| Go | 高并发原生支持、编译型性能好 | AI/ML 库生态弱、团队学习成本 |
| Java/Kotlin | 企业级成熟度高、JVM 性能 | 开发效率低、AI/ML 集成不如 Python 直接 |

**选型理由**：

- **AI/ML 生态**：视频治理的核心价值在 AI 能力（OCR、ASR、目标检测、LLM 策略审查）。Python 是 PyTorch/TensorFlow/Transformers/PaddleOCR/Whisper 的第一公民语言，模型加载与推理无需跨语言桥接。
- **团队技术栈**：减少上手成本，聚焦业务逻辑而非语言学习。
- **3.11+ 性能提升**：CPython 3.11 比 3.10 平均快 25%（PEP 659 自适应解释器），3.12+ 进一步改善 GIL，对异步 IO 密集场景已足够。
- **GIL 缓解**：CPU 密集任务（抽帧、模型推理）由 Celery Worker 多进程执行，不受 GIL 限制。

### 2.2 Web 框架：FastAPI 0.115+

| 候选 | 优势 | 劣势 |
|------|------|------|
| **FastAPI** ✅ | 原生异步、自动 OpenAPI 文档、Pydantic 集成、WebSocket 支持 | 社区规模小于 Django |
| Django + DRF | 生态成熟、ORM 内置、Admin 开箱即用 | 同步为主、异步支持不完整、性能较低 |
| Flask | 轻量灵活 | 无异步、无自动文档、需大量三方库拼装 |

**选型理由**：

- **异步原生**：人审工作台的 WebSocket 长连接（锁续约、SLA 倒计时、告警推送）要求框架原生支持异步。FastAPI 基于 Starlette，async/await 是一等公民。
- **自动 API 文档**：FastAPI 自动生成 OpenAPI 3.0 文档，前后端联调时前端工程师可直接从 `/docs` 查看请求/响应 Schema，降低沟通成本。前后端集成是本项目评审中的薄弱环节（6/10），自动文档能部分缓解。
- **Pydantic 深度集成**：请求参数校验、响应序列化、策略配置 Schema 全部复用 Pydantic 模型，一套类型定义贯穿 API 层→Service 层→数据库层。

### 2.3 ORM：SQLAlchemy 2.0+

| 候选 | 优势 | 劣势 |
|------|------|------|
| **SQLAlchemy 2.0** ✅ | 支持异步、成熟稳定、灵活度高、丰富的 PostgreSQL 方言支持 | 学习曲线陡 |
| Tortoise ORM | 异步原生、Django 风格 | 社区小、复杂查询支持弱 |
| 原生 asyncpg | 性能最优 | 无 ORM 映射、手写 SQL 维护成本高 |

**选型理由**：

- **异步支持**：SQLAlchemy 2.0 通过 `asyncpg` 驱动实现真正的异步数据库操作，与 FastAPI 的异步架构匹配。
- **PostgreSQL 特性利用**：项目大量使用 JSONB（证据包、策略配置）、`FOR UPDATE SKIP LOCKED`（任务领取）、分区表（审计日志）等 PostgreSQL 高级特性，SQLAlchemy 对这些方言的支持最完善。
- **复杂查询能力**：人审任务分配涉及 EXISTS 子查询（排除已审案件）、多维排序（优先级 + SLA + 创建时间）、行级锁，SQLAlchemy 的 Core 表达式语言能直接表达这些查询而不退化为原生 SQL。

### 2.4 数据库：PostgreSQL 16+

| 候选 | 优势 | 劣势 |
|------|------|------|
| **PostgreSQL 16** ✅ | JSONB、分区、行锁、丰富索引、ACID | 需 DBA 调优、写入吞吐不如 NoSQL |
| MySQL 8 | 广泛使用、运维成熟 | JSONB 支持弱、`SKIP LOCKED` 引入晚 |
| MongoDB | Schema 灵活、写入吞吐高 | 事务支持弱、多表关联不自然 |

**选型理由**：

- **JSONB**：证据包（EvidencePackage）结构半固定，帧、ASR、OCR、目标检测等模态可选出现。JSONB 列允许灵活存储而不牺牲查询能力（GIN 索引），避免为每种模态建立关联表。
- **`FOR UPDATE SKIP LOCKED`**：人审任务领取是典型的并发消费场景，`SKIP LOCKED` 让多个审核员同时领取时互不阻塞，PostgreSQL 9.5+ 即支持，比 MySQL 更成熟。
- **行级锁 + 乐观锁**：ContentItem 的状态流转使用 `version` 字段乐观锁，配合 PostgreSQL 的 MVCC，并发冲突概率低且处理简单。
- **审计链完整性**：审计日志使用 SHA-256 链式哈希，PostgreSQL 的事务保证每条审计事件与业务操作原子写入，不会出现"操作成功但审计丢失"的情况。

### 2.5 缓存与消息队列：Redis 7+

| 候选 | 优势 | 劣势 |
|------|------|------|
| **Redis 7** ✅ | 多功能合一（缓存+队列+锁+Pub/Sub+熔断）、运维简单 | 内存成本、持久化非绝对可靠 |
| Kafka | 持久化强、吞吐量极高、消息回放 | 运维复杂、MVP 阶段 overkill |
| RabbitMQ | AMQP 标准、路由灵活 | 多引入一个中间件 |

**选型理由**：

- **一个中间件解决多个问题**：MVP 阶段，Redis 同时承担 5 种角色——缓存（策略配置热加载）、消息代理（Celery broker）、分布式锁（任务锁）、Pub/Sub（WebSocket 跨实例广播）、滑动窗口熔断器状态存储。引入 Kafka/RabbitMQ 意味着多一个需要运维的有状态服务。
- **Celery 原生支持**：Celery 对 Redis 的支持最成熟，配置最简单。Kafka 作为 Celery broker 需要额外适配且社区支持有限。
- **Redis Streams**：V2 阶段 WebSocket 断线重连需要事件重放，Redis Streams 提供持久化的消息日志能力，无需额外引入 Kafka。

**风险与演进**：当视频量增长到 Redis 内存无法承载队列积压时（预估日均 > 50 万视频），将 Celery broker 迁移至 Kafka，Redis 仍保留缓存和锁的职责。

### 2.6 任务队列：Celery 5.3+

| 候选 | 优势 | 劣势 |
|------|------|------|
| **Celery** ✅ | Python 生态标准、chain/chord 编排、多 Worker 多队列 | 调试不直观、Worker 重启慢 |
| Dramatiq | 更简洁的 API、性能略好 | 生态小、chain 编排能力弱 |
| Temporal | 工作流引擎级能力、状态持久化 | 重基建、团队学习成本高 |
| arq | 轻量、asyncio 原生 | 功能少、无编排原语 |

**选型理由**：

- **任务链编排**：机审流水线是 4 阶段串行处理（证据提取→安全初筛→LLM审查→决策聚合），Celery 的 `chain()` 原语直接表达，每阶段独立任务、独立重试策略、独立超时，已完成阶段不因后续失败重新执行。
- **多队列隔离**：证据提取（CPU 密集）、LLM 审查（IO 密集、慢）、数据回流（低优先级）分配到不同队列和 Worker 池，互不影响。`evidence` 队列可分配 4 并发，`review` 队列 2 并发（受 LLM API 速率限制）。
- **Dead Letter 支持**：通过 `link_error` 回调实现死信处理，永久失败的任务写入 `dead_letter_tasks` 表供运维人工介入。

### 2.7 对象存储：MinIO（开发）/ S3（生产）

| 候选 | 优势 | 劣势 |
|------|------|------|
| **MinIO / S3** ✅ | S3 协议标准、开发/生产一致 API | MinIO 需自运维 |
| 本地文件系统 | 最简单 | 无法水平扩展、无冗余 |
| OSS (阿里云) | 国内访问快 | 厂商锁定 |

**选型理由**：

- **开发生产一致性**：MinIO 提供 100% S3 兼容 API，本地开发使用 Docker 启动 MinIO，生产切换 S3 只需改环境变量，代码零修改。
- **分桶隔离**：不同安全等级的内容存储在不同桶（`uploads/`、`evidence/`、`csam-vault/`），CSAM 相关内容独立加密桶，仅特定角色可访问。

### 2.8 AI 模型选型

| 组件 | 选型 | 候选 | 选型理由 |
|------|------|------|---------|
| LLM 策略审查 | **Claude claude-sonnet-4-6** | GPT-4o、Gemini | 多模态理解能力强，结构化输出（JSON Schema）稳定性好，安全分类场景准确率高，tool use 原生支持策略审查输出格式 |
| 语音识别 (ASR) | **Whisper / FunASR** | 讯飞 ASR、百度 ASR | Whisper 开源可私有部署，中文识别准确率高；FunASR 对中文场景优化，支持标点恢复和热词 |
| 文字识别 (OCR) | **PaddleOCR / EasyOCR** | Tesseract | PaddleOCR 对中文场景优化显著优于 Tesseract，支持文字检测+识别+方向分类的端到端流水线；EasyOCR 作为备选 |
| 目标检测 | **YOLO / Grounding DINO** | Detectron2 | YOLOv8+ 推理速度快（适合批量抽帧），Grounding DINO 支持开放词汇检测（"未成年人"、"二维码"等自定义类别），与策略可扩展性对齐 |
| 视频处理 | **OpenCV + ffmpeg** | GStreamer | ffmpeg 是视频转码/抽帧的行业标准，OpenCV 提供 Python 层面的帧操作 API，组合使用覆盖所有视频处理需求 |

**关键设计决策**：LLM 策略审查使用 Claude API 而非本地部署大模型。原因：

1. **多模态理解**：策略审查需要综合理解视频帧图像 + ASR 文本 + OCR 文本 + 元数据，Claude 的多模态能力在视频内容理解场景表现优于纯文本模型。
2. **结构化输出**：每个维度的审查结果需要严格的 JSON Schema（`DimensionVerdict`），Claude 的 tool use 机制保证输出格式一致性，减少解析失败。
3. **成本可控**：通过短路优化（CSAM/高置信安全风险直接跳过 LLM）和 Token 预算管理降低 API 调用量。
4. **降级兜底**：LLM API 不可用时，verdict 置为 UNCERTAIN 并路由人审，确保不因 AI 服务中断而阻塞审核流。

### 2.9 监控：Prometheus + Grafana

**选型理由**：开源标准组合，Prometheus 拉取模型天然适配容器化部署，FastAPI 通过 `prometheus-fastapi-instrumentator` 自动暴露 HTTP 指标。Grafana 提供可视化看板，支持告警规则配置。自定义指标覆盖审核漏斗各阶段延迟、LLM 调用成功率、人审队列深度等业务指标。

---

## 3. 前端技术栈

### 3.1 框架：React 18.3+ (TypeScript)

| 候选 | 优势 | 劣势 |
|------|------|------|
| **React 18** ✅ | Concurrent 模式、生态最大、人才池广 | 非框架（需自组装路由/状态管理） |
| Vue 3 | 上手快、官方全家桶 | 大型项目 TypeScript 集成不如 React 自然 |
| Angular | 全框架、企业级支持 | 学习成本高、包体积大 |

**选型理由**：

- **Concurrent 模式**：人审工作台是典型的高频交互场景（视频播放 + 快捷键操作 + WebSocket 实时推送），React 18 的 `startTransition` 和自动批处理保证高频状态更新不卡顿 UI。
- **TypeScript 深度集成**：后端 Pydantic 模型可通过工具（如 `pydantic-to-typescript`）自动生成前端 TypeScript 类型定义，前后端契约类型安全。
- **组件生态**：视频播放器（xgplayer）、图表库（ECharts）、UI 库（Ant Design）均提供 React 组件封装。

### 3.2 UI 组件库：Ant Design 5.x

| 候选 | 优势 | 劣势 |
|------|------|------|
| **Ant Design 5** ✅ | 企业级 B 端组件齐全、中文文档、Design Token 主题 | 包体积偏大 |
| Material UI | 设计感强 | 偏 C 端风格、中文支持弱 |
| Arco Design | 字节出品、轻量 | 社区小、三方生态少 |

**选型理由**：

- **B 端场景完备**：审核平台是典型的 B 端应用，Ant Design 的 Table（审核队列）、Form（策略配置）、Tree（违规分类树）、Modal（操作确认）等组件直接可用，减少自定义开发。
- **Design Token**：Ant Design 5 的 CSS-in-JS + Design Token 体系支持主题定制，后续多租户/多品牌需求可通过 Token 覆写实现。
- **Pro Components**：ProTable、ProForm 等高阶组件适合快速构建管理后台页面。

### 3.3 状态管理：Zustand 5.x

| 候选 | 优势 | 劣势 |
|------|------|------|
| **Zustand** ✅ | 极轻量（1KB）、API 简洁、slice 模式、无 Provider | 无 DevTools 内置（需插件） |
| Redux Toolkit | 生态最大、DevTools 强 | boilerplate 仍多于 Zustand |
| Jotai/Recoil | 原子化状态、细粒度更新 | 状态分散、全局状态管理不直观 |
| MobX | 响应式、直觉简单 | 隐式依赖追踪、调试不透明 |

**选型理由**：

- **分层状态架构**：项目将状态分为 4 层（服务端缓存态/实时推送态/会话运行态/全局配置态），Zustand 的 slice 模式让每层对应一个独立 store（`authStore`、`reviewStore`、`wsStore`），互不干扰。
- **与 TanStack Query 协作**：服务端数据缓存由 TanStack Query 管理，Zustand 只负责客户端会话状态（当前审核案件、操作草稿），职责清晰，避免重复缓存。
- **无 Provider**：不需要在组件树顶层包裹 Provider，对错误边界和代码分割友好。

### 3.4 请求层：TanStack Query (React Query) 5.x

| 候选 | 优势 | 劣势 |
|------|------|------|
| **TanStack Query** ✅ | stale-while-revalidate、自动缓存失效、乐观更新 | 学习概念多（staleTime/gcTime） |
| SWR | 更轻量 | mutation 支持弱、无 devtools |
| axios + 手动缓存 | 完全可控 | 重复发明轮子、缓存一致性难维护 |

**选型理由**：

- **stale-while-revalidate**：审核队列数据设置 `staleTime=30s`，30 秒内重复访问返回缓存数据同时后台刷新。WebSocket 在线时自动 invalidate 相关 query，实现"有推送时实时、无推送时近实时"。
- **乐观更新**：审核员提交处置决策时，前端立即更新 UI（乐观更新），请求失败则自动回滚，避免等待网络往返的卡顿感。
- **Mutation + Invalidation**：提交决策后自动 invalidate 队列 query，审核员无需手动刷新。

### 3.5 构建工具：Vite 6.x

| 候选 | 优势 | 劣势 |
|------|------|------|
| **Vite** ✅ | HMR 极快（< 100ms）、ESBuild 预构建、原生 ESM | 生态比 Webpack 年轻 |
| Webpack 5 | 生态最成熟、插件多 | 配置复杂、HMR 慢 |
| Turbopack | Vercel 出品、Rust 性能 | 尚未稳定 |

**选型理由**：

- **开发体验**：Vite 的 HMR 基于原生 ESM，修改组件后毫秒级热更新，对前端频繁调整审核工作台布局的开发模式至关重要。
- **代码分割**：Vite 生产构建使用 Rollup，支持路由级自动 chunk。目标：主 chunk < 200KB gzipped，路由 chunk < 100KB，保证首屏加载速度。

### 3.6 视频播放器：xgplayer 3.x

| 候选 | 优势 | 劣势 |
|------|------|------|
| **xgplayer** ✅ | 国内视频格式兼容好（FLV/HLS）、插件化、逐帧控制 API | 国际社区小 |
| video.js | 国际社区大、插件生态丰富 | 国内视频格式支持需额外插件 |
| plyr | 轻量、UI 美观 | 功能少、无逐帧控制 |

**选型理由**：

- **审核场景定制需求**：人审工作台需要逐帧控制（`,`/`.` 快捷键）、时间轴标注（命中点标记）、倍速播放（0.5x-4x）、画面截取。xgplayer 的插件化架构允许在不 fork 源码的情况下扩展这些能力。
- **国内视频格式**：项目处理的视频来自国内创作者，FLV/HLS 是常见格式，xgplayer 原生支持。
- **创伤屏蔽集成**：审核敏感内容（CSAM、暴力）时需要模糊遮罩功能，xgplayer 的自定义渲染层可实现 `TraumaShield` 组件覆盖。

### 3.7 图表：ECharts 5.5+

| 候选 | 优势 | 劣势 |
|------|------|------|
| **ECharts** ✅ | 大屏渲染性能好、中文文档完善、图表类型丰富 | 包体积大（按需引入缓解） |
| AntV (G2/G6) | Ant Design 体系、语法简洁 | 大数据量渲染性能不如 ECharts |
| D3.js | 最灵活、可定制性最强 | 学习成本极高、非开箱即用 |
| Recharts | React 友好、声明式 | 性能差、大数据量卡顿 |

**选型理由**：

- **大屏场景**：机审监控面板需要实时渲染趋势图、漏斗图、分布图，ECharts 的 Canvas 渲染引擎在万级数据点场景下性能优于 SVG 方案（AntV G2、Recharts）。
- **按需引入**：通过 `import * as echarts from 'echarts/core'` + 按需注册组件，只加载使用的图表类型，控制包体积。

### 3.8 契约测试：MSW + Zod

| 候选 | 优势 | 劣势 |
|------|------|------|
| **MSW + Zod** ✅ | 前端独立验证 API 契约、无需启动后端 | 契约需手动同步 |
| Pact | 双向契约测试、自动化程度高 | 引入 Pact Broker 运维成本 |
| 手动 Mock | 无额外依赖 | 契约漂移无法发现 |

**选型理由**：

- **前后端集成保障**：技术专家评审中前后端集成得分最低（6/10），MSW（Mock Service Worker）拦截网络请求 + Zod Schema 校验响应结构，确保前端期望的字段、类型与后端实际响应一致。
- **CI 中运行**：契约测试在 CI 流水线中运行，后端修改 API 响应结构后，前端 Zod Schema 不匹配即 CI 失败，提前发现集成问题。

---

## 4. 基础设施

### 4.1 容器化：Docker + Docker Compose（MVP）→ Kubernetes（V2）

**选型理由**：

- **MVP 阶段**：Docker Compose 编排 API + Worker + PostgreSQL + Redis + MinIO，单机部署，`docker compose up` 一键启动完整环境。
- **V2 演进**：当需要多副本自动扩缩容时迁移至 Kubernetes。Celery Worker 已是独立容器，迁移成本仅为编写 K8s manifests。

### 4.2 认证方案：JWT (PyJWT)

| 候选 | 优势 | 劣势 |
|------|------|------|
| **JWT** ✅ | 无状态、WebSocket 握手兼容、简单 | Token 撤销需额外机制 |
| Session Cookie | 撤销简单 | WebSocket 认证不方便、需 session 存储 |
| OAuth 2.0 (完整) | 标准化、第三方集成 | MVP 阶段过度工程 |

**选型理由**：

- **WebSocket 兼容**：人审工作台的 WebSocket 连接需要认证，JWT 可通过 URL query parameter 传递（`ws://host/ws/review?token={token}`），比 Cookie 方案更直接。
- **双 Token 设计**：登录 JWT（长期）+ WS 专用短期 JWT（30 分钟），WebSocket Token 泄露影响范围有限。

---

## 5. 关键设计模式选型

### 5.1 策略可扩展性：Strategy Pattern + Registry Pattern + Decorator 注册

**为什么不用规则引擎（如 Drools）**：

- 审核维度的判断依赖 LLM 多模态理解（不是简单的 if-else 规则），规则引擎无法表达"看这几帧画面判断是否存在未成年人"这样的语义理解任务。
- 策略模式 + 注册表让每个维度自包含（抽象基类 → 具体实现 → 装饰器注册），新增维度不改核心代码，满足"随时新增策略"的设计要求。

### 5.2 任务领取：`SELECT FOR UPDATE SKIP LOCKED`

**为什么不用 Redis 分布式锁**：

- 任务分配涉及复杂过滤条件（法域权限、技能匹配、独立性排除、反疲劳），这些查询必须在数据库中完成。将过滤结果写入 Redis 再加锁会引入数据库→Redis 的一致性问题。
- `SKIP LOCKED` 让数据库查询和加锁原子完成，并发审核员领取时互不阻塞。

### 5.3 熔断器：滑动窗口 + Redis 分布式

**为什么不用 Hystrix/Resilience4j 模式的本地熔断**：

- 多实例部署场景下，本地熔断器各实例状态独立，实例 A 检测到 LLM API 故障打开熔断，实例 B 仍然尝试调用。
- 基于 Redis Sorted Set 的滑动窗口熔断器，所有实例共享失败率统计，一个实例检测到故障，全集群同步降级。

---

## 6. 未选方案及理由存档

| 技术 | 未选理由 |
|------|---------|
| GraphQL | 审核平台 API 结构稳定，不存在前端动态查询字段的需求，REST 更简单 |
| gRPC | 模块化单体内无跨服务调用，不需要 Protobuf 序列化开销 |
| Kafka | MVP 阶段视频量不足以需要 Kafka 级别的吞吐量和持久化，Redis 足够 |
| Elasticsearch | 全文搜索需求目前仅限审计日志按 content_id 查询，PostgreSQL 的 B-tree 索引足够 |
| Next.js/Remix | 审核平台是纯 SPA，不需要 SSR/SSG，引入 Node.js 服务端增加部署复杂度 |
| Tailwind CSS | Ant Design 已提供完整样式系统，混用 Tailwind 造成样式体系分裂 |
| Temporal | 工作流引擎能力强大但基建重，Celery chain 已满足当前编排需求 |
| 微前端 (qiankun) | 单团队开发，模块间共享状态多（当前审核案件），微前端隔离反而增加通信成本 |

---

## 7. 技术选型演进路径

| 阶段 | 当前选型 | 触发条件 | 演进方向 |
|------|---------|---------|---------|
| 消息队列 | Redis (Celery broker) | 日均视频 > 50 万 | Kafka 替代 broker，Redis 保留缓存/锁 |
| 部署 | Docker Compose | 需要多副本自动扩缩容 | Kubernetes |
| 搜索 | PostgreSQL B-tree | 需要全文搜索/模糊匹配 | Elasticsearch |
| 前端架构 | 单体 SPA | 多团队独立开发模块 | 微前端 (Module Federation) |
| 数据库 | 单主 + 只读副本 | 写入 QPS > 5000 | 读写分离 + 分库分表 |
| LLM 模型 | Claude API (云端) | 成本/延迟/合规要求 | 私有部署开源模型 + Claude 混合 |
