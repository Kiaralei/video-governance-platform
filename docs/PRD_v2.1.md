# 视频内容治理平台 · 产品需求文档（PRD）

> **版本：v2.2（跨文档契约对齐 + 反疲劳设计 + 飞轮去相关性 + SLA 工程默认值版）**
> 状态：定稿草案 · 文档负责人：T&S 产品（总编 / 首席产品）· 日期：2026-07-01
>
> 本文档在 v2.1（机审三阶段强化 + MVP 范围明确版）基础上增订，继承 v2.1 全部内容。**v2.2 主要解决专家评审指出的四类问题：① 工程可控 SLA 从 TBD 提升为工程默认值；② 新增 §1.E 跨文档契约对齐节，消除 EvidencePackage 字段名/决策枚举/CSAM 隔离/WebSocket 协议的三文档不一致；③ 新增 §5.A 反疲劳设计节（CSAM 曝光上限、强制休息、创伤屏蔽）；④ §12.3 飞轮质量门补充同一上传者去相关性规则。此外，附录 E 内嵌 v2.0 必读章节（角色矩阵 / 状态机 / 处置矩阵摘要），消除单文档可读性缺口。** 骨架与模块正文冲突裁决规则不变：模块正文 > 本版骨架 > v2.1 > v2.0 > v1.0 骨架。

---

## 一、版本说明——v2.2 相对 v2.1 的变更摘要

### 1.1 v2.2 新增/强化项

| 变更类型 | 变更项 | 影响模块 | 说明 |
|---|---|---|---|
| **强化** | SLA 工程默认值提升（不再 TBD） | 模块 1 §1.A.5、附录 B | `FILTER_SLA` 提升为工程默认值 **3s**（P95），`LLM_SLA` 提升为工程默认值 **30s**（P95），不再标 TBD；仅法务约束项保留 Legal-TBD |
| **新增** | 跨文档契约对齐节 | 模块 1 §1.E | 专项消除 PRD / 后端 / 前端三文档的 EvidencePackage 字段名不一致、决策枚举三套不兼容、CSAM 隔离边界层次不同、WebSocket 协议真空、LLM Token 预算实现缺口、Shadow 报告存储未定义六个跨文档集成风险；提供显式字段映射表、枚举映射表、协议规范 |
| **新增** | 反疲劳设计（Anti-fatigue Design） | 模块 5 §5.A | CSAM 类目单班曝光上限（10 条）、强制 15 分钟休息触发阈值、创伤内容屏蔽模式；填补三文档均缺失的高合规风险漏洞 |
| **新增** | 飞轮质量门同一上传者去相关性规则 | §12.3 | 防止单一内容生态主导训练集：同一 creator_id 单日入库占比上限 5%，批量去相关性窗口 ≥ 7 天，相似度去重阈值 0.85 |
| **新增** | 附录 E：v2.0 必读章节内嵌摘要 | 附录 E | 内嵌 v2.0 角色权限矩阵摘要、统一状态机摘要、处置矩阵摘要，附精确版本锚点，消除单文档可读性缺口 |
| **新增** | Prompt 注入防御规范 | 模块 1 §1.E.7 | LLM 审查阶段的输入净化（sanitize）规范，防止创作者通过标题/描述/ASR 注入指令 |
| **新增** | 专家评审记录章节 | 末章 | 记录评审评分（81/100）、主要问题、改进点 |

### 1.2 v2.1 变更摘要（继承，不重述）

| 变更类型 | 变更项 | 影响模块 | 说明 |
|---|---|---|---|
| **新增（强化）** | 机审管线三阶段流程细化 | 模块 1 §1.A | 在原"多模态机审"之下新增三阶段子流程：证据提取层 → 基础安全初筛 → LLM 策略审查，完整覆盖处理编排 |
| **新增** | EvidencePackage 标准格式规范 | 模块 1 §1.B | 定义证据包结构、字段含义、示例 JSON，作为三阶段之间以及机审与人审之间的标准数据契约 |
| **新增** | LLM 策略审查输出格式规范 | 模块 1 §1.C | 定义 LLM 每个策略维度的 decision / confidence / reason / evidence_refs 结构化输出格式 |
| **新增** | 大模型与规则引擎职责边界强制声明 | 模块 1 §1.D | 明确"LLM 只负责理解归因，规则引擎负责最终决策"这一不可逾越的系统设计红线 |
| **新增** | MVP v1.1 范围声明 | §3.3（替换/强化） | 本期交付 vs 暂不交付，细化到子功能粒度，对齐架构设计文档 MVP v1.1 定义 |
| **新增** | 数据回流（Data Flywheel）产品规范 | §新增第十二节 | 四类回流数据、触发时机、Shadow 模式验证，从产品角度定义飞轮闭环要求 |
| **新增** | 策略可扩展性要求——零改造扩展路径 | 模块 11 §11.A | 注册表驱动的新审核策略维度扩展标准，强制约束不改五层核心代码 |
| **保留** | v2.0 全部 11 模块骨架 | 全模块 | 非关键段落标注"继承 v2.0 对应章节完整内容"，术语表、角色矩阵、状态机全部沿用 |

**本版不改动以下 v2.0 / v2.1 已定稿内容**：全局术语表（§五）、统一角色与权限矩阵（§七）、统一状态机总览（§八）、处置矩阵（模块 3）、申诉闭环（模块 7）、critical 高危上报（模块 8）、合规与透明度（模块 9）。如上述模块与本版新增内容有补充关系，以新增内容为细化规范，不替换原条款。

---

## 二、背景与目标（全平台）

继承 v2.0 对应章节完整内容。

**v2.1 补充背景**：在 v2.0 的系统设计原则基础上，v2.1 进一步强化了"机审管线如何在控制成本的同时提升判定质量"这一工程与产品交点问题。核心答案是**三阶段漏斗**：先用规则和轻量 API 快速过滤明显违规，再用多模态 LLM 对剩余内容做策略层理解归因，最终由规则引擎聚合 LLM 输出与其他信号做最终处置决策。此架构使 LLM 的高成本算力集中在边界态与复杂态内容，而非全量视频。

---

## 三、范围声明

### 3.1 全平台模块范围（11 模块）

继承 v2.0 §3.1 完整内容，11 模块清单与规范名不变。

### 3.2 全局边界

继承 v2.0 §3.2 完整内容，含外部/邻接系统声明（§3.2.1）。

### 3.3 本期 MVP v1.1 范围声明（v2.1 强化替换 v2.0 §3.3）

#### 3.3.1 本期交付（MVP v1.1 In-Scope）

以下能力为本期必须交付，上线前须通过验收：

**机审管线（模块 1）**
- 内容摄取三来源统一入口（创作者上传 / 上游业务接入 / 批量导入）
- 元数据校验 + 挂载位置可信度校验 + 法域解析（适用法域优先级三档）
- 机审管线三阶段完整实现：
  - 阶段 1 证据提取层：视频抽帧、ASR 语音转文字、OCR 文字识别、目标检测、场景识别，输出 EvidencePackage v1
  - 阶段 2 基础安全初筛：哈希库比对（CSAM 哈希）、云 API 内容安全检测、规则引擎快速过滤，命中 critical 直接 BLOCK 并进高危流水线，无命中进入阶段 3
  - 阶段 3 LLM 策略审查：多模态模型按注册策略维度输出结构化判断（decision / confidence / reason / evidence_refs），结果交由规则引擎聚合决策
- 机审裁决包（MVP 字段集，见 §1.A.5）产出与路由三走向落地
- CSAM-class P0 类目族独立流水线

**审核维度体系（模块 2）**
- 维度注册表 MVP 版本：安全维度（critical 四类目 + 违禁物 + 暴力血腥 + 仇恨言论）+ 质量维度（低质/垃圾内容）+ 业务维度（商业推广合规）
- 每类目配置：rubric / 子信号 / 分档判据，版本化存储

**决策引擎与策略管理（模块 4）**
- 策略四态生命周期（Draft → Shadow → Active → Archived）
- Shadow 模式并行评估，差异报告产出
- 灰度放量（1%→5%→25%→50%→100%）+ 自动护栏（二审推翻率 / 申诉率超红线暂停放量）
- Maker-Checker 双人审批，Kill-switch 生效键级总闸

**处置矩阵（模块 3）**：继承 v2.0 MVP 交付项，含七档处置动作、取严链、三轴解耦合并、地理围栏投放。

**人审工作台（模块 5）**：继承 v2.0 MVP 交付项，含法定时限队列、一屏决策支持、critical 实时熔断。

**质检与审核质量（模块 6）**：继承 v2.0 MVP 交付项，含随机抽检 + 定向抽检、IRR 统计、校准培训闭环。

**申诉闭环（模块 7）**：继承 v2.0 MVP 交付项，含 SoR 生成、送达、二审（排除原审）、恢复连锁四链。

**critical 高危上报（模块 8）**：继承 v2.0 MVP 交付项，含 critical_hold、evidence_hold、NCMEC 等法定上报。

**合规与透明度（模块 9）**：逐条 SoR 报送（VLOP 场景上线前必须就绪）、append-only 审计 + 链式完整性、DSAR 处理、legal hold。

**数据回流飞轮（新增，§十二）**：四类回流数据基础能力，Ground Truth 样本自动入库，Shadow 模式验证机制。

#### 3.3.2 本期暂不交付（MVP v1.1 Out-of-Scope）

以下能力明确推后至后续版本，本期不做、不验收、不作为上线门禁：

| 暂不交付项 | 说明 | 规划版本 |
|---|---|---|
| 直播实时审核（cut stream）| 实时内容治理模块为 Roadmap，本期直播 VOD 化后走常规流程 | V2 |
| 片段级处置 | 仅支持整条视频级处置 | V2 |
| 账号信用引擎自研 | 本期消费外部输入，信用分计算不在本期范围 | V2 |
| 多租户隔离完整实现 | 本期单租户，ContentItem 已预留 tenant 字段 | V2 |
| 第三方权利人通知渠道 | 版权/肖像/商标走独立产品线 | V2 |
| DSA 逐条报送（非 VLOP 场景）| 非 VLOP 场景可豁免，VLOP 上线前必须就绪 | V2/按法律义务 |
| 申诉批量代理授权（Delegate）| 基础申诉可用，授权代理人通道 Roadmap | V2 |
| 直播热待审核员角色 | 预留角色定义，本期不上岗不授权 | V2 |
| 复杂法域细分（国家子级）| 本期支持 US/EU/Global 三组，国家级 Roadmap | V3 |
| 自动合成媒体（deepfake）专项检测 | 本期作为 AI 生成声明辅助信号，专项检测推后 | V3 |

**P0 合规红线（不做则不可上线，任何场景）**：critical 独立流水线、CSAM 即报（法定时限 Legal-TBD）、SoR 生成与送达、DSA Art.20 申诉通道、证据保全、数据出境校验。

---

## 四、阅读指南

继承 v2.0 §四完整内容。

**v2.1 补充**：本版新增内容主要集中在 §1.A（机审三阶段）、§1.B（EvidencePackage）、§1.C（LLM 输出格式）、§1.D（职责边界）、§十二（数据回流飞轮）、§11.A（零改造扩展路径）。建议先读 §1.D 职责边界声明，再看三阶段细节，最后结合飞轮规范理解闭环。

---

## 五、全局术语表（Glossary）

继承 v2.0 §五全部七组术语（§5.1～§5.7）完整内容，以下为 v2.1 新增术语。

### 5.8 机审三阶段与数据回流（v2.1 新增）

| 术语 | 定义 | 主出处 |
|---|---|---|
| **证据提取层（Evidence Extraction Layer）** | 机审管线阶段 1：将原始视频解构为多模态特征信号（帧序列 / 语音转录 / 文字识别 / 目标检测结果 / 场景标签），产出标准化的 EvidencePackage | 模块 1 §1.A.1 |
| **基础安全初筛（Basic Safety Pre-filter）** | 机审管线阶段 2：用哈希比对、云 API 和规则快速过滤明显违规内容；命中 critical 直接 BLOCK 进高危流水线，其余进阶段 3；**设计目标是最大化减少无必要 LLM 调用** | 模块 1 §1.A.2 |
| **LLM 策略审查（LLM Policy Review）** | 机审管线阶段 3：多模态大语言模型消费 EvidencePackage，按注册策略维度逐维度输出结构化理解判断；**LLM 只做"理解归因"，不做最终处置决策** | 模块 1 §1.A.3 |
| **EvidencePackage（证据包）** | 阶段 1 产出的标准化多模态证据容器，是阶段 2 初筛和阶段 3 LLM 审查的统一输入，也是机审裁决包中证据指针所指向的实体 | 模块 1 §1.B |
| **LLM 策略维度判断（DimensionVerdict）** | LLM 对单个策略维度（类目）的结构化输出单元，含 dimension_id / decision / confidence / reason / evidence_refs 五字段，为规则引擎聚合决策的输入之一 | 模块 1 §1.C |
| **规则引擎聚合决策** | 收集阶段 3 全部 DimensionVerdict，结合策略阈值、置信度、法域、累犯信号等，按维度注册表的处置映射表产出最终建议处置与路由决策；**规则引擎是处置决策的唯一责任主体** | 模块 1 §1.D |
| **数据回流（Data Flywheel）** | 将人审确认样本、改判样本、申诉翻转样本、质检标注样本自动回流到模型训练、策略评估、黄金集的闭环机制 | §十二 |
| **Shadow 验证（Shadow Validation）** | 新模型版本或策略版本在正式切换前，以 Shadow 模式并行运行于真实流量上，对比输出差异，须满足漂移红线才能放量 | §十二 §12.4 |
| **零改造扩展（Zero-Modification Extension）** | 通过向维度注册表填写新维度定义，无需修改决策引擎 / 人审工作台 / 申诉闭环 / 审计 / 策略层五层核心代码，即可将新审核策略维度贯通全链路 | 模块 11 §11.A |

---

## 六、全平台模块地图与端到端数据流

继承 v2.0 §六完整内容（§6.1 模块地图、§6.2 端到端数据流文字版、§6.3 机审/人审子系统边界与接口）。

**v2.1 补充（§6.2 数据流局部更新）**：原 §6.2 "多模态机审"步骤展开为三阶段：

```
[机审管线 - 三阶段展开]
   ① 阶段1 证据提取层
      · 抽帧（关键帧 + 均匀采样，≥N帧/分钟，含转场帧）
      · ASR（自动语音识别，产出时间对齐转录文本）
      · OCR（画面文字识别，产出带坐标的文字区域）
      · 目标检测（人体/武器/毒品/标志等，产出 bounding box + 类别 + 置信度）
      · 场景识别（成人/暴力/户外/室内等场景分类）
      → 产出 EvidencePackage（见 §1.B）

   ② 阶段2 基础安全初筛（高速低成本过滤）
      · CSAM 哈希库比对（PhotoDNA/自有库）→ 命中即 BLOCK + 高危流水线
      · 云 API 内容安全检测（色情/暴恐/违禁物快速分类）
      · 规则引擎：关键词/画面哈希/元数据规则
      → 明显违规（critical/high 高置信）直接产出初筛命中记录 → 跳过阶段3
      → 无命中或命中中低置信 → 进入阶段3

   ③ 阶段3 LLM 策略审查（深度理解归因）
      · 多模态模型消费 EvidencePackage
      · 按维度注册表已启用的策略维度逐一产出 DimensionVerdict
      · LLM 不直接输出处置决策，只输出"对该维度的理解与归因"
      → 产出 LLM 策略审查报告（DimensionVerdict 列表）

   ④ 规则引擎聚合决策
      · 合并阶段2初筛结果 + 阶段3 DimensionVerdict 列表
      · 按策略版本阈值/法域/置信度规则产出最终处置建议与路由
      → 产出机审裁决包 → 路由三走向
```

---

## 七、统一角色与权限矩阵

继承 v2.0 §七完整内容。

---

## 八、统一状态机总览

继承 v2.0 §八完整内容（§8.1～§8.6）。

---

## 九、全局验收标准与上线门禁

继承 v2.0 对应章节完整内容。

---

## 十、全局路线图（MVP / V2 / V3）

继承 v2.0 对应章节完整内容，以下为 v2.1 补充更新：

| 里程碑 | 新增/调整项 | 版本 |
|---|---|---|
| MVP v1.1 | 机审三阶段完整落地，EvidencePackage v1 协议上线，Data Flywheel 基础能力，Shadow 验证机制 | 本版 |
| V2 | 直播实时审核，片段级处置，多租户完整隔离，LLM 模型迭代（支持更多维度） | 后续 |
| V3 | 国家子级法域，自动合成媒体专项检测，跨平台信号共享 | 远期 |

---

## 十一、各模块正文

### 模块 1：内容摄取与机审管线（v2.1 强化）

继承 v2.0 模块 1 §0（模块定位与边界）、§0.1（裁决包契约）、§0.2（输入契约）、§1（内容如何进入平台）至 §7 所有内容。

以下为 v2.1 新增子节，插入在 v2.0 模块 1 §1.4（CSAM-class）之后、§2（法域与 policy 锁定）之前。

---

#### §1.A 机审管线三阶段流程细化（v2.1 新增）

##### §1.A.0 三阶段设计原则

机审管线在"多模态机审"这一步按**三阶段漏斗**执行，每阶段有明确的职责边界、输入/输出契约、成本约束和异常处理规则：

1. **高速过滤在前，LLM 在后**：阶段 1+2 处理全量内容，用低成本手段淘汰明显合规与明显违规样本，只让边界态与复杂态内容进入阶段 3 的 LLM 调用，从根本上控制推理成本。
2. **阶段间契约化**：EvidencePackage 是阶段 1→2→3 的标准传递载体，任何阶段的改造不破坏相邻阶段的接口。
3. **LLM 只做"理解归因"**：阶段 3 的大模型输出是结构化的"判断理由与置信度"，而非可执行的处置指令；处置决策权归规则引擎，大模型无权对整条视频直接拍板（详见 §1.D）。
4. **任意阶段故障降级**：阶段 1 某模态提取失败，EvidencePackage 中该模态字段置空并标注 `unavailable`，阶段 2/3 按"缺该模态"保守策略处理（模态降级，参见全局术语表 §5.2），不静默当无命中。

##### §1.A.1 阶段 1：证据提取层（Evidence Extraction Layer）

**职责**：将原始视频（或类视频文件）解构为多模态特征信号，产出标准化 EvidencePackage，供后续两阶段消费。

**处理步骤与要求**：

| 信号类型 | 提取方式 | MVP 最低要求 | 输出格式 |
|---|---|---|---|
| **视频帧序列** | 关键帧提取（场景切换检测）+ 均匀采样 | ≥1 帧/秒，关键帧全覆盖，不超过 MAX_FRAMES 上限 | `frames[]`：时间戳 + 编码图像指针 + 场景切换标记 |
| **ASR 转录** | 语音识别，产出时间对齐文本 | 支持平台主要语言（≥Language_List_TBD），置信度字段 | `asr_transcript`：`{start_ms, end_ms, text, confidence}[]` |
| **OCR 识别** | 帧内文字检测与识别 | 对所有关键帧执行，字幕区域优先 | `ocr_results`：`{frame_ts, text, bbox, confidence}[]` |
| **目标检测** | 人体 / 武器 / 危险物品 / 特定标志 | 至少覆盖违禁类目所需实体集（由维度注册表配置） | `object_detections`：`{frame_ts, label, bbox, score}[]` |
| **场景识别** | 视频级场景分类 | 成人/暴力/户外/室内/特殊场所等基础标签 | `scene_tags`：`{label, confidence}[]` |

**提取层 SLA（机审子系统内部）**：
- P95 完成时间（文件上传到 EvidencePackage 就绪）≤ MAX_EXTRACTION_SLA_TBD（按视频时长分档）
- 提取失败率（任意单模态）：< FAIL_RATE_TBD，超标告警

**重要约束**：
- 提取结果按提交快照标识版本化存储，内容替换触发重提取
- CSAM 哈希比对的输入帧**不进入普通 EvidencePackage 存储路径**，走独立安全存储（见模块 8）
- EvidencePackage 完整生命周期须遵循合规模块（模块 9）的留存与清理策略

##### §1.A.2 阶段 2：基础安全初筛（Basic Safety Pre-filter）

**职责**：用轻量快速的检测手段过滤掉"明显违规"（直接 BLOCK）和"明显合规"（快速放行或降低 LLM 扫描优先级）的内容，最大化减少高成本 LLM 调用。

**处理策略（按检测类型）**：

| 检测手段 | 检测内容 | 命中结果 | 备注 |
|---|---|---|---|
| **CSAM 哈希库比对** | PhotoDNA / 行业共享哈希库 / 平台自有库 | 命中 → 立即 BLOCK，直接进 critical 流水线（不过阶段 3），产出 `pre_filter_hit: CSAM` | CSAM 检测永不被阶段 3 替代，即使阶段 3 未运行也已命中 |
| **云 API 内容安全** | 色情 / 儿童涉险 / 暴恐 / 违禁物品 快速分类 | 高置信命中 critical/high → 直接产出初筛命中记录，可跳过阶段 3（按策略版本配置） | 低置信命中仍进阶段 3 深化审查 |
| **规则引擎快速过滤** | 元数据规则（标题关键词/黑名单 hashtag）/ 画面 MD5 / 已知违规哈希 | 规则命中 → 按规则配置的严重度处理 | 规则配置归策略管理，版本化管理 |
| **重复内容裁决复用** | 内容指纹比对，命中已裁决内容 | 满足复用条件（同法域 + 同 policy 版本 + 原裁决非边界态）→ 直接复用裁决 | 跨法域不复用；复用不放松处置（见全局术语表 §5.2） |

**跳过阶段 3 的条件（可配置）**：
- 阶段 2 产出高置信（≥AUTO_THRESHOLD_TBD）的 critical/high 命中 → 跳过阶段 3，直接进裁决聚合
- 阶段 2 产出高置信 PASS（无命中，置信度高于 AUTO_PASS_THRESHOLD_TBD）→ 可配置降低阶段 3 LLM 调用优先级（info/low 类目仍可配置为必查）
- 涉及 critical 类目（C1-C4）的命中**永不跳过人工确认**（阶段 2 命中走高危流水线，而非直接终局）

**阶段 2 产出**：`pre_filter_results`（附加到 EvidencePackage）：
```json
{
  "pre_filter_results": {
    "csam_hash_hit": false,
    "cloud_api_hits": [
      {"category": "violence", "confidence": 0.91, "severity": "high"}
    ],
    "rule_hits": [],
    "dedup_reuse": null,
    "skip_llm_review": false,
    "skip_reason": null
  }
}
```

##### §1.A.3 阶段 3：LLM 策略审查（LLM Policy Review）

**职责**：多模态大语言模型消费完整 EvidencePackage，按维度注册表中已启用的策略维度**逐维度**输出结构化理解判断（DimensionVerdict），帮助规则引擎理解内容在每个策略维度上的语义本质。

**调用规则**：
- **调用触发**：阶段 2 未产出跳过信号，且内容类型需要语义理解（纯规则无法判断边界态）
- **维度范围**：由维度注册表的 `llm_review_enabled: true` 配置控制，按法域和内容形态过滤
- **模型版本**：调用时传入当前 Active policy 绑定的模型版本 ID，版本绑定写入裁决包（保证可追溯）
- **Prompt 构造**：从 EvidencePackage 中提取相关证据（关键帧/转录文本/OCR），按维度维护结构化 Prompt 模板（随 policy 版本化）；Prompt 模板变更走 Maker-Checker 双人审批

**输出要求**：
- LLM **只输出 DimensionVerdict 列表**，不输出处置动作枚举
- 每个 DimensionVerdict 含五字段（见 §1.C）
- LLM 输出须为 JSON 格式，Schema 版本与 policy 版本绑定
- LLM 调用失败（超时/模型不可用）→ 该维度 verdict 置 `decision: UNCERTAIN`，confidence = 0，标注 `llm_unavailable: true`，规则引擎按保守策略处理（通常路由人审）

**成本控制**：
- 单视频 LLM 调用次数上限由 `MAX_LLM_CALLS_PER_VIDEO_TBD` 配置
- Token 预算按视频时长分档，超出时截断 EvidencePackage 输入（按重要性排序：关键帧 > 转录文本 > OCR > 目标检测细节）
- Shadow 模式下 LLM 调用成本计入 Shadow 成本预算，独立统计

##### §1.A.4 规则引擎聚合决策（Decision Aggregation）

**职责**：收集阶段 2 初筛结果 + 阶段 3 DimensionVerdict 列表，结合法域 policy 版本配置、置信度阈值、账号信誉、累犯信号，按维度注册表的处置映射表计算最终建议处置与路由决策。

**聚合规则（按优先级）**：
1. 阶段 2 命中 CSAM 哈希 → 强制 REMOVE_AND_ESCALATE，进高危流水线（规则引擎不复算）
2. 阶段 2 命中 critical/high 高置信（且配置为跳过 LLM）→ 按 pre_filter 结论直接映射处置
3. 阶段 3 DimensionVerdict 命中 → 按严重度档/置信度/策略阈值计算每类目建议处置，取严链合并
4. 信誉/累犯信号叠加 → 按策略版本配置的累犯加重规则调整置信度阈值
5. 无任何命中 → 建议 PASS（高置信时自动放行，低置信路由人审）

**输出**：补全 EvidencePackage 中的 `decision_summary` 字段，并产出完整机审裁决包（见 §0.1）。

##### §1.A.5 三阶段 SLA 总览（MVP v1.1）

> **v2.2 更新**：`FILTER_SLA` 和 `LLM_SLA` 已从 TBD 提升为**工程默认值**（Engineering Default），无需法务签署即可落地约束；仅法规层面有法定时限要求的参数保留 Legal-TBD 标记。工程默认值不得在未经 Policy PM + SRE 双签的情况下单方放宽。

| 阶段 | 处理内容 | P95 时限目标 | 类型 | 失败处理 |
|---|---|---|---|---|
| 阶段 1：证据提取 | 全量视频 | 按视频时长分档（见下表） | Engineering Default | 模态降级，标注不可用 |
| 阶段 2：基础初筛 | 全量视频 | **3s**（P95，全时长档） | **Engineering Default（已落地）** | 初筛失败 → 跳过初筛直接进阶段 3（日志告警） |
| 阶段 3：LLM 审查 | 阶段 2 非直接结案内容 | **30s**（P95，全时长档） | **Engineering Default（已落地）** | LLM 失败 → UNCERTAIN + 路由人审 |
| 聚合决策 | 全量 | <1s | Engineering Default | 配置缺失 → 保守路由人审 |

**阶段 1 证据提取按视频时长分档（工程默认值）**：

| 视频时长 | P95 提取时限 |
|---|---|
| ≤60s（短视频） | 30s |
| 61s～10min | 120s |
| 10min～60min | 300s |
| >60min | 600s（超时触发告警，路由人审兜底） |

**超 SLA 告警规则**：阶段 2 P95 超过 3s 或阶段 3 P95 超过 30s，触发 P2 告警，SRE 值班接单；连续 5 分钟超标升 P1。

---

#### §1.B EvidencePackage 标准格式规范（v2.1 新增）

EvidencePackage 是机审管线三阶段之间、以及机审子系统与人审子系统之间的**标准数据契约**。格式版本化管理，Schema 变更走 Maker-Checker 评审。

##### §1.B.1 字段定义

| 字段路径 | 类型 | 说明 | 是否必填 |
|---|---|---|---|
| `ep_id` | string | 证据包唯一 ID，全局不重复 | 是 |
| `schema_version` | string | EvidencePackage Schema 版本（如 "1.0"） | 是 |
| `content_id` | string | 内容 ID，关联 ContentItem | 是 |
| `snapshot_id` | string | 提交快照标识，与机审裁决包绑定 | 是 |
| `created_at` | int64 | 证据包生成时间戳（Unix ms） | 是 |
| `video_meta` | object | 视频基础元数据（时长/分辨率/编码/文件大小） | 是 |
| `frames` | array | 帧序列，见下表 | 是（可为空但不得缺失字段） |
| `asr_transcript` | array | ASR 转录结果，`{start_ms, end_ms, text, confidence, lang}` | 是（音频不可用时为空，标注 unavailable） |
| `ocr_results` | array | OCR 识别结果，`{frame_ts, text, bbox:[x,y,w,h], confidence}` | 是（无文字时为空） |
| `object_detections` | array | 目标检测结果，`{frame_ts, label, bbox, score, model_version}` | 是 |
| `scene_tags` | array | 场景识别标签，`{label, confidence}` | 是 |
| `modality_availability` | object | 各模态可用性标记，`{video:true, audio:false, ...}` | 是 |
| `pre_filter_results` | object | 阶段 2 初筛结果（见 §1.A.2） | 是（阶段 2 完成后填充） |
| `llm_verdicts` | array | 阶段 3 DimensionVerdict 列表（见 §1.C） | 是（阶段 3 完成后填充，跳过时为空） |
| `decision_summary` | object | 规则引擎聚合结果摘要 | 是（聚合完成后填充） |
| `access_policy` | object | 证据访问控制策略（谁可解引用，CSAM 例外） | 是 |

**frames 子对象字段**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `frame_id` | string | 帧唯一 ID |
| `timestamp_ms` | int64 | 帧时间戳（视频内相对时间，毫秒） |
| `is_keyframe` | bool | 是否关键帧（场景切换触发） |
| `image_ref` | string | 编码图像存储指针（不内联图像数据） |
| `resolution` | object | `{width, height}` |

##### §1.B.2 示例 JSON（简化版）

```json
{
  "ep_id": "ep_20260701_abc12345",
  "schema_version": "1.0",
  "content_id": "vid_987654321",
  "snapshot_id": "snap_20260701_001",
  "created_at": 1751347200000,
  "video_meta": {
    "duration_ms": 62000,
    "resolution": {"width": 1920, "height": 1080},
    "codec": "h264",
    "file_size_bytes": 52428800
  },
  "modality_availability": {
    "video": true,
    "audio": true,
    "text_ocr": true,
    "asr": true
  },
  "frames": [
    {
      "frame_id": "frm_001",
      "timestamp_ms": 0,
      "is_keyframe": true,
      "image_ref": "s3://evidence-store/vid_987654321/snap_001/frm_001.jpg",
      "resolution": {"width": 1920, "height": 1080}
    },
    {
      "frame_id": "frm_031",
      "timestamp_ms": 31000,
      "is_keyframe": true,
      "image_ref": "s3://evidence-store/vid_987654321/snap_001/frm_031.jpg",
      "resolution": {"width": 1920, "height": 1080}
    }
  ],
  "asr_transcript": [
    {"start_ms": 0, "end_ms": 5200, "text": "今天给大家展示...", "confidence": 0.95, "lang": "zh-CN"},
    {"start_ms": 5200, "end_ms": 12800, "text": "这个方法可以...", "confidence": 0.88, "lang": "zh-CN"}
  ],
  "ocr_results": [
    {"frame_ts": 31000, "text": "限时优惠", "bbox": [120, 980, 300, 40], "confidence": 0.97}
  ],
  "object_detections": [
    {"frame_ts": 0, "label": "person", "bbox": [400, 100, 300, 600], "score": 0.98, "model_version": "det_v2.3"},
    {"frame_ts": 31000, "label": "product_display", "bbox": [200, 300, 800, 400], "score": 0.85, "model_version": "det_v2.3"}
  ],
  "scene_tags": [
    {"label": "indoor", "confidence": 0.93},
    {"label": "commercial_promotion", "confidence": 0.76}
  ],
  "pre_filter_results": {
    "csam_hash_hit": false,
    "cloud_api_hits": [],
    "rule_hits": [],
    "dedup_reuse": null,
    "skip_llm_review": false,
    "skip_reason": null
  },
  "llm_verdicts": [],
  "decision_summary": null,
  "access_policy": {
    "readable_roles": ["reviewer", "senior_reviewer", "qa_reviewer", "compliance_auditor"],
    "csam_exception": false,
    "retention_days": 365
  }
}
```

---

#### §1.C LLM 策略审查输出格式规范（v2.1 新增）

每次 LLM 策略审查产出一个 `DimensionVerdict` 列表，每条记录对应维度注册表中一个已启用的策略维度。

##### §1.C.1 DimensionVerdict 字段定义

| 字段 | 类型 | 含义 | 枚举/约束 |
|---|---|---|---|
| `dimension_id` | string | 策略维度唯一标识，对应维度注册表中的 `dim_id` | 必须是注册表中已注册的 ID |
| `dimension_name` | string | 策略维度人读名称（辅助调试，非判断依据） | — |
| `decision` | enum | LLM 对该维度的判断结论 | `VIOLATION` / `NO_VIOLATION` / `UNCERTAIN` |
| `confidence` | float | LLM 对本次判断结论的确定程度，0.0～1.0 | **不代表严重度**；与规则引擎阈值对照使用 |
| `severity_suggestion` | enum | LLM 建议的严重度档（供规则引擎参考，不可直接采用） | `critical` / `high` / `medium` / `low` / `null`（UNCERTAIN 时为 null） |
| `reason` | string | LLM 对本判断的自然语言解释，须引用具体证据（人话，可用于内部审查） | 长度 ≤ 500 字符；不得直接作为对外 SoR |
| `evidence_refs` | array | 支撑本判断的证据引用列表（指向 EvidencePackage 内的具体帧/片段） | 见 §1.C.2 |
| `policy_version` | string | 本次评判使用的 policy 版本号 | 与机审裁决包 policy_version 一致 |
| `model_version` | string | 调用的 LLM 模型版本 ID | — |
| `llm_unavailable` | bool | 该维度 LLM 调用是否失败 | true 时 decision 强制为 UNCERTAIN |

**关键约束**：
- `decision: VIOLATION` **不等于处置决策**。规则引擎可根据置信度不足将 VIOLATION 降级为路由人审，而非直接自动处置。
- `severity_suggestion` 为建议值，规则引擎须结合策略版本配置的阈值和法域 override 才能最终确认严重度档。
- `reason` 字段**严禁直接作为对外 SoR（Statement of Reason）**；SoR 须经 §0.1 裁决包规范处理后由申诉模块生成。

##### §1.C.2 evidence_refs 子字段

```json
{
  "evidence_refs": [
    {
      "ref_type": "frame",
      "frame_id": "frm_031",
      "timestamp_ms": 31000,
      "description": "画面中出现可疑标志，位于右下角"
    },
    {
      "ref_type": "asr_segment",
      "start_ms": 5200,
      "end_ms": 12800,
      "text_excerpt": "这个方法可以...",
      "description": "转录文本含特定话术"
    }
  ]
}
```

##### §1.C.3 完整 DimensionVerdict 示例

```json
{
  "dimension_id": "dim_hate_speech_incitement",
  "dimension_name": "仇恨言论与煽动性内容",
  "decision": "VIOLATION",
  "confidence": 0.83,
  "severity_suggestion": "high",
  "reason": "转录文本（5.2s-12.8s）包含针对特定群体的贬损性表述，结合字幕OCR（31s帧）中的强化文字，判定存在系统性仇恨言论特征，而非孤立性言辞失当。",
  "evidence_refs": [
    {
      "ref_type": "asr_segment",
      "start_ms": 5200,
      "end_ms": 12800,
      "text_excerpt": "（已脱敏，见安全存储）",
      "description": "含仇恨言论的语音片段"
    },
    {
      "ref_type": "frame",
      "frame_id": "frm_031",
      "timestamp_ms": 31000,
      "description": "字幕中出现强化性贬损词汇"
    }
  ],
  "policy_version": "policy_v3.2.1",
  "model_version": "multimodal_llm_v2.1.0",
  "llm_unavailable": false
}
```

---

#### §1.D 大模型与规则引擎职责边界强制声明（v2.1 新增核心设计红线）

**以下职责边界为全平台不可逾越的系统设计红线，所有产品功能设计、工程实现、策略配置均须遵守：**

##### 大模型（LLM）的职责范围：理解与归因

- LLM **只负责**：理解视频内容的语义本质、识别可能触发策略维度的具体证据、解释"为什么这段内容可能违规"、输出结构化的归因理由和置信度。
- LLM **不负责**：决定最终处置动作（PASS/REMOVE/DEMOTE/...）、决定严重度档的最终值、决定路由走向（人审/自动/高危）、决定是否触发法定上报。
- 大模型的输出（DimensionVerdict）是规则引擎的**输入之一**，地位等同于其他机审信号（云 API 结果、检测模型分数），不高于规则引擎。

##### 规则引擎的职责范围：决策与路由

- 规则引擎**唯一负责**：聚合所有信号（含 LLM 输出）→ 对照策略版本阈值和法域配置 → 产出最终建议处置枚举 → 产出路由决策（自动处置 / 人审 / 高危）。
- 规则引擎的配置（阈值、映射表）走 Maker-Checker + 版本化，策略变更不得绕过评审流程。
- **处置矩阵（模块 3）是最终处置落地的唯一权威**，规则引擎产出的"建议处置"须经处置矩阵执行。

##### 禁止事项（系统设计层面强制）

| 禁止项 | 原因 |
|---|---|
| 让 LLM 直接输出处置动作枚举（REMOVE/BLOCK/...） | 大模型输出不稳定且不可审计版本化，不可作为处置执行依据 |
| 让 LLM 对整条视频给出"通过/拒绝"一元判断 | 绕过了策略阈值配置和法域差异化，且无法按维度追责 |
| 让 LLM 输出的 severity_suggestion 直接作为最终严重度 | severity_suggestion 仅为参考，须经法域 override 和阈值校验 |
| 在 LLM Prompt 中透传"期望输出"暗示特定决策 | 构成偏向性审查，影响系统公正性 |
| Shadow 模式以外使用实验性 LLM 模型 | Shadow 外上线的 LLM 必须通过完整 Shadow 验证和漂移检测 |

---

#### §1.E 跨文档契约对齐规范（v2.2 新增——集成风险消除）

> **本节是 v2.2 的核心新增节**，专项解决专家评审指出的七个跨文档集成风险点。PRD（本文档）/ 后端技术方案 / 前端技术方案三份文档须以本节为唯一契约仲裁层，发现字段名/枚举值/协议不一致时以本节为准并在对应文档内更新至一致。

##### §1.E.1 EvidencePackage 字段名统一映射层

**问题背景**：PRD 定义 `ep_id / object_detections / asr_transcript`（数组），后端 Pydantic 模型使用 `package_id / objects_detected / asr`（ASRResult 对象），前端 TypeScript 无对应字段；无显式映射层，集成阶段极易字段丢失。

**解决方案**：以 PRD 定义的字段名为**唯一权威（Single Source of Truth）**，后端与前端须向 PRD 对齐；如因框架约束无法修改，须在各端维护显式映射适配层，适配层代码须经 PR Review 且须在本节注册映射关系。

**字段名权威映射表**：

| PRD 权威字段名（JSON Wire Format） | 后端当前字段名 | 前端当前字段名 | 对齐动作 | 字段类型 |
|---|---|---|---|---|
| `ep_id` | `package_id` | 无 | 后端改为 `ep_id`；前端新增 | `string` |
| `asr_transcript` | `asr`（ASRResult 对象） | 无 | 后端改为 `asr_transcript`；ASRResult 对象展开为数组 `{start_ms, end_ms, text, confidence, lang}[]` | `array` |
| `object_detections` | `objects_detected` | 无 | 后端改为 `object_detections` | `array` |
| `ocr_results` | （未定义） | 无 | 后端新增 `ocr_results` 字段 | `array` |
| `scene_tags` | （未定义） | 无 | 后端新增 `scene_tags` 字段 | `array` |
| `modality_availability` | （未定义） | 无 | 后端新增；缺失时默认 `{video:true, audio:true, text_ocr:true, asr:true}` | `object` |
| `pre_filter_results` | `fast_path_result`（部分） | 无 | 后端统一结构，对齐 §1.A.2 定义的子字段 | `object` |
| `llm_verdicts` | `policy_verdicts`（部分） | 无 | 后端改为 `llm_verdicts`，类型对齐 §1.C DimensionVerdict | `array` |
| `decision_summary` | `final_decision`（不完整） | `disposition`（枚举不兼容） | 见 §1.E.2 决策枚举映射 | `object` |
| `access_policy` | （未定义） | 无 | 后端新增；控制谁可解引用 EvidencePackage | `object` |

**适配层要求**：
- 后端须在 Pydantic Schema 中使用 `alias` 或字段迁移，对外 API 一律暴露 PRD 权威字段名
- 前端 TypeScript 须新增 `EvidencePackage` 接口定义，字段名与 PRD 完全一致
- 任何字段名变更须同步更新本映射表，走 Maker-Checker 评审

##### §1.E.2 决策枚举三层映射规则

**问题背景**：PRD §1.C 定义 `VIOLATION / NO_VIOLATION / UNCERTAIN`（LLM 维度层），后端 `PolicyDecision` 使用 `pass / block / needs_review`（规则引擎层），前端 `Disposition` 使用 `PASS / REMOVE / REMOVE_AND_ESCALATE` 等七档（处置矩阵层）；三层各自为政，无映射规则，工程师只能靠猜。

**三层枚举职责定义**：

| 层次 | 枚举名称 | 枚举值 | 职责 | 产出方 |
|---|---|---|---|---|
| **L1：LLM 维度判断层** | `DimensionDecision` | `VIOLATION` / `NO_VIOLATION` / `UNCERTAIN` | LLM 对单个策略维度的语义理解结论；**不是处置决策** | 阶段 3 LLM |
| **L2：规则引擎决策层** | `PolicyDecision` | `auto_pass` / `auto_block` / `needs_human_review` / `critical_escalate` | 规则引擎聚合全部信号后的路由决策；**不是最终处置枚举** | 规则引擎 §1.A.4 |
| **L3：处置动作层** | `DispositionAction` | `PASS` / `DEMOTE` / `LABEL` / `AGE_GATE` / `GEO_BLOCK` / `REMOVE` / `REMOVE_AND_ESCALATE` | 对内容的最终可见性/分发/标注动作；**唯一权威在处置矩阵** | 处置矩阵 模块 3 |

**三层映射规则（规则引擎执行，不可绕过）**：

```
L1 DimensionDecision → L2 PolicyDecision（由规则引擎聚合，非一一对应）：
  全部维度 NO_VIOLATION，置信度均 ≥ AUTO_PASS_THRESHOLD  → auto_pass
  任一维度 VIOLATION，severity=critical，置信度 ≥ AUTO_THRESHOLD → critical_escalate
  任一维度 VIOLATION，severity=high/medium，置信度 ≥ AUTO_THRESHOLD → auto_block
  任一维度 UNCERTAIN，或置信度 < 阈值  → needs_human_review
  （取严链：critical_escalate > auto_block > needs_human_review > auto_pass）

L2 PolicyDecision → L3 DispositionAction（由处置矩阵执行，参照 §3 处置矩阵）：
  auto_pass        → PASS
  auto_block       → REMOVE 或 DEMOTE（按严重度档和三轴解耦规则）
  critical_escalate → REMOVE_AND_ESCALATE（进高危流水线）
  needs_human_review → 路由人审，人审员选择 L3 动作
```

**前端 Disposition 兼容说明**：前端展示层消费的是 L3 `DispositionAction`，七档枚举值须与处置矩阵（模块 3）保持严格一致。前端不直接消费 L1 或 L2 枚举；如需展示"机审结论原因"，通过 `DimensionVerdict.reason` 字段，不暴露 L1 枚举值给终端用户。

##### §1.E.3 CSAM 统一隔离边界（三层一致）

**问题背景**：PRD 要求 CSAM 走独立安全存储（最强隔离），后端只有 `fast_path_block`（仍走普通流水线），前端只有展示屏蔽（最弱）；三层没有形成统一的 CSAM 隔离边界。

**统一 CSAM 隔离边界定义（全平台强制，不可降级）**：

| 层次 | 要求 | 违反后果 |
|---|---|---|
| **内容存储层** | CSAM 命中的原始视频本体及帧图像，**只存入 CSAM 专用安全存储（独立加密，独立访问控制，不与普通证据存储共用**）；EvidencePackage 中 CSAM 帧的 `image_ref` 指向 CSAM 安全存储路径，不可被普通证据解引用接口访问 | P0 合规告警，立即阻断 |
| **流水线层** | CSAM 命中后**立即退出普通机审流水线**，进 critical 专用流水线；不得将 CSAM 哈希命中内容的帧数据传入阶段 3 LLM Prompt（LLM 不处理 CSAM 原始内容） | P0 合规告警 |
| **后端 API 层** | 后端普通证据查询 API（`/evidence/{ep_id}/frames`）须在服务层校验 `access_policy.csam_exception`，为 `true` 时拒绝返回帧数据，返回 403 + 错误码 `CSAM_RESTRICTED_ACCESS` | 安全漏洞，按严重级别处理 |
| **前端展示层** | 前端须识别 `access_policy.csam_exception: true`，**对任何角色（含高级审核员、质检员）完全屏蔽帧预览**；仅展示"内容已受限，请通过 critical 专审通道处理"占位符；不得以任何方式绕过（含缩略图/base64 内联） | 安全漏洞 |
| **访问控制层** | 仅 `critical_specialist`（critical 专审员）+ `compliance_auditor`（合规审计）两个角色可通过 CSAM 专审 API 访问原始素材；访问须双人授权 + 全程录屏 + 审计留痕（同 v2.0 §七 break-glass 规则） | 四权分立硬约束 |

##### §1.E.4 WebSocket 实时协议定义

**问题背景**：WebSocket 是前后端集成的核心依赖（锁状态推送 / SLA 倒计时 / 告警通知），但后端技术方案和前端技术方案均未定义消息格式、鉴权机制和重连策略，存在协议真空。

**WebSocket 消息格式（JSON，Schema v1.0）**：

```json
{
  "ws_message_version": "1.0",
  "type": "<message_type>",
  "timestamp_ms": 1751347200000,
  "payload": { ... }
}
```

**消息类型枚举（`type` 字段）**：

| type | 方向 | 触发时机 | payload 说明 |
|---|---|---|---|
| `CASE_LOCK_ACQUIRED` | 服务端→客户端（广播） | 某审核员领取/锁定案件 | `{case_id, locked_by_reviewer_id, locked_at_ms, lock_expires_at_ms}` |
| `CASE_LOCK_RELEASED` | 服务端→客户端（广播） | 锁超时 / 审核员释放 / 系统回收 | `{case_id, released_reason: "timeout"|"manual"|"system"}` |
| `CASE_SLA_TICK` | 服务端→客户端（定向） | 每 30s 推送一次，仅推给持锁审核员 | `{case_id, remaining_sla_ms, sla_type: "legal"|"operational", is_warning: bool}` |
| `CASE_UPDATED` | 服务端→客户端（广播） | 案件状态变更（判决/改派/申诉） | `{case_id, new_status, updated_by, updated_at_ms}` |
| `CRITICAL_ALERT` | 服务端→客户端（角色广播） | critical 命中，推送给有权限的审核员 | `{content_id, alert_level: "critical", category, requires_action_by_ms}` |
| `SHADOW_DIFF_READY` | 服务端→客户端（管理员） | Shadow 差异报告生成完成 | `{report_id, policy_version, diff_summary}` |
| `PING` / `PONG` | 双向 | 心跳保活，30s 间隔 | `{}` |
| `ERROR` | 服务端→客户端 | 协议错误 / 鉴权失败 | `{error_code, error_message}` |

**鉴权机制**：
- 建立连接时，客户端须在 URL Query 或 `Authorization` 头中携带短期 JWT Token（有效期 ≤ 1h，由 REST API `/auth/ws-token` 签发）
- JWT Payload 须含 `reviewer_id`、`roles[]`、`allowed_jurisdictions[]`、`exp`
- 服务端在握手阶段校验 JWT，失败则返回 HTTP 401 拒绝升级为 WebSocket
- 服务端消息推送前须校验接收方的 `roles` 是否有权接收该消息类型（如 `CRITICAL_ALERT` 仅推 `critical_specialist` 等有权限角色）

**重连策略**：
- 客户端须实现指数退避重连：首次断开后 1s 重连，每次失败后翻倍，上限 30s
- 重连成功后，客户端须发送 `{type: "RECONNECT_SYNC", last_seen_timestamp_ms: <上次收到消息的时间戳>}`，服务端推送断连期间该客户端错过的事件（最多补推 5 分钟内消息）
- 持续断连超过 5 分钟，客户端须刷新页面并重新拉取全量状态（不依赖 WebSocket 补全）
- 心跳（PING/PONG）超时 90s 无响应，视为断连，触发重连流程

##### §1.E.5 LLM Token 预算实现规范

**问题背景**：PRD §1.A.3 要求 Token 预算按视频时长分档截断，但后端无实现，前端无感知，长视频会超出上下文窗口导致 LLM 调用报错且无降级。

**Token 预算分档（工程默认值，可由 Policy PM 调整）**：

| 视频时长 | 最大 Input Token 预算 | 截断优先级（重要性从高到低） |
|---|---|---|
| ≤60s | 8,000 tokens | 关键帧描述 > ASR 全文 > OCR 全文 > 目标检测细节 |
| 61s～10min | 16,000 tokens | 关键帧描述（前 20 帧）> ASR 摘要（全文压缩）> OCR 关键文本 > 目标检测摘要 |
| 10min～60min | 32,000 tokens | 关键帧描述（均匀采样 30 帧）> ASR 分段摘要 > OCR > 省略目标检测细节 |
| >60min | 48,000 tokens（硬上限） | 关键帧描述（均匀 40 帧）> ASR 关键段摘要 > 截断警告写入 EvidencePackage |

**截断处理规则**：
- EvidencePackage 须记录 `token_budget_used`、`token_budget_limit`、`truncated_modalities[]` 字段
- 当 ASR 转录被截断时，须优先保留**开头 30s + 结尾 30s + 最高置信度语音段**，而非简单截尾
- 截断发生时，`DimensionVerdict.reason` 须注明"部分证据因 Token 预算限制未纳入分析"
- 后端须在 LLM 调用前执行预算估算（不调用 API，本地 tokenizer 估算），超出预算则执行截断后再调用

**前端感知**：
- 前端须展示 `truncated_modalities` 标记，审核员界面中显示"⚠ 部分证据受 Token 限制未完整分析"警示
- 含截断标记的 DimensionVerdict 须在人审工作台中标注，审核员可手动触发"完整证据人审"流程

##### §1.E.6 Shadow 模式验证报告存储规范

**问题背景**：PRD §12.4 要求 Shadow 差异报告每 24h 产出，后端 `flywheel_samples` 表有 `is_shadow` 字段但无专门的 Shadow 报告聚合表或 API，前端 `ShadowCompareView` 的数据来源未定义 API 端点。

**Shadow 报告数据模型（新增，须在后端实现）**：

```
shadow_reports 表（新增）：
  report_id          string PRIMARY KEY
  policy_version_new string  -- 新版本（Shadow 版本）
  policy_version_old string  -- 对照版本（Active 版本）
  report_period_start_ms int64
  report_period_end_ms   int64
  generated_at_ms        int64
  status                 enum(generating, ready, archived)
  summary_json           json   -- 差异摘要（见下）
  drift_alerts_json      json   -- 漂移告警列表
  created_by             string -- "system_shadow_cron"
```

**`summary_json` 结构**：
```json
{
  "total_items_evaluated": 50000,
  "overall_agreement_rate": 0.934,
  "per_dimension_diff": [
    {
      "dimension_id": "dim_hate_speech_incitement",
      "new_hit_rate": 0.023,
      "old_hit_rate": 0.019,
      "delta": "+0.004",
      "fn_estimate": 0.002,
      "fp_estimate": 0.001
    }
  ],
  "cost_impact": {
    "llm_calls_delta_pct": "+3.2%",
    "token_usage_delta_pct": "+1.8%"
  }
}
```

**Shadow 报告 API 端点（须在后端实现）**：

| 端点 | 方法 | 描述 | 权限 |
|---|---|---|---|
| `/api/shadow/reports` | GET | 列出所有 Shadow 报告（分页） | policy_pm, qa_admin |
| `/api/shadow/reports/{report_id}` | GET | 获取单份 Shadow 报告详情 | policy_pm, qa_admin |
| `/api/shadow/reports/{report_id}/items` | GET | 获取报告中的差异样本列表（分页，支持按维度过滤） | policy_pm, qa_admin |
| `/api/shadow/reports/latest` | GET | 获取最新一份 ready 状态报告（供前端 ShadowCompareView 使用） | policy_pm, qa_admin |

**Shadow 报告生成 Cron**：每 24h 执行一次（建议凌晨 2:00 UTC），触发聚合任务，生成前 24h 的差异报告，写入 `shadow_reports` 表，生成完成后通过 WebSocket `SHADOW_DIFF_READY` 消息推送通知。

##### §1.E.7 Prompt 注入防御规范（v2.2 新增安全红线）

**问题背景**：专家评审指出 Prompt 注入防御在三份文档中均完全缺失，是安全红线。创作者可能在视频标题、描述、ASR 转录文本中嵌入指令，尝试操控 LLM 审查结论。

**Prompt 注入防御要求（全部为 P0 安全红线）**：

| 防御层 | 要求 | 实现方式 |
|---|---|---|
| **输入净化（Sanitize）** | ASR 转录、OCR 文字、标题/描述文本在注入 Prompt 之前，须经 Sanitizer 过滤；过滤目标：去除或转义 LLM 指令模式（如 `ignore previous instructions`、`system:`、`<|im_start|>` 等常见注入头） | 后端 Sanitizer 函数，正则 + 黑名单，须维护注入模式库 |
| **角色隔离（Role Separation）** | Prompt 中的用户内容（视频元数据、证据）须使用明确的内容隔离分隔符（如 `<user_content>…</user_content>`），与系统指令物理分离；LLM 调用须使用 system/user 角色分离（Assistant API），不得将用户内容拼入 system prompt | Prompt 模板设计规范，模板变更走 Maker-Checker |
| **输出校验（Output Validation）** | LLM 输出须经 Schema 校验（对照 §1.C DimensionVerdict Schema）；输出中若出现处置动作枚举（`REMOVE`/`BLOCK`/`PASS` 等），视为注入成功，该条 DimensionVerdict 废弃，标注 `injection_suspected: true`，路由人审 | 后端输出校验层 |
| **日志与告警** | 注入尝试（被 Sanitizer 检测到的异常模式）须记录到审计日志，`event_type: PROMPT_INJECTION_ATTEMPT`；单视频注入尝试次数 ≥ 3 次，触发账号风险信号，推送至外部账号信用引擎 | 审计日志 + 告警 |
| **模板版本控制** | Prompt 模板须包含"抗注入防护版本"字段（`injection_guard_version`），每次更新注入模式库须更新此版本；Shadow 验证须包含抗注入测试集 | Prompt 模板库管理规范 |

---

### 模块 2：审核维度体系

继承 v2.0 模块 2 全部内容。

---

### 模块 3（★）：处置矩阵

继承 v2.0 模块 3 全部内容。

---

### 模块 4：决策引擎与策略管理

继承 v2.0 模块 4 全部内容。

---

### 模块 5：人审工作台

继承 v2.0 模块 5 全部内容。

以下为 v2.2 新增子节：

#### §5.A 反疲劳设计（Anti-fatigue Design）（v2.2 新增——合规强制）

> **本节为合规强制项**。在日均亿级 PV 的平台上，人审员（尤其 CSAM 专审员）面临高强度创伤性内容曝光。缺乏系统级反疲劳保护是劳工合规红线（多国已立法或监管指引要求），也是平台风险治理的重要组成部分。**本节所有要求均为 P0 合规红线，不上线则不可启用人审能力。**

##### §5.A.1 CSAM 类目单班曝光上限

| 参数 | 默认值 | 说明 |
|---|---|---|
| 单班 CSAM 案件曝光上限 | **10 条** | 每个审核员单个工作班次（通常 8h）内处理 `CSAM-class` 案件不超过 10 条；第 11 条到达时系统自动改派至其他符合资质审核员，不得强制原审核员继续处理 |
| CSAM 累积曝光周期上限 | **30 条 / 自然周** | 同一审核员 7 天内处理 CSAM 类案件不超过 30 条；超过后系统自动移出 CSAM 排班，需 Crisis/Wellness 团队确认后方可恢复 |
| 曝光计数范围 | C1-a（真人 CSAM）+ C1-b（换脸合成）+ C2（未成年性化） | C1-c 纯合成内容不计入本上限，但仍适用强制休息规则 |

**系统实现要求**：
- 后端须维护 `reviewer_csam_exposure` 表，记录每个审核员的 CSAM 案件处理计数（按班次和自然周双维度）
- 人审工作台队列分配逻辑须在分配前查询该表，曝光已达上限的审核员不得被分配 CSAM 案件
- 超限案件须立即改派，不得进入超限审核员的待办列表
- 审核员本人可在工作台随时查看本人当前曝光计数（但不显示他人数据）

##### §5.A.2 强制休息触发阈值

| 触发条件 | 强制休息时长 | 是否可跳过 |
|---|---|---|
| 连续处理 CSAM/critical 案件达 **3 条** | 强制 5 分钟休息 | **不可跳过**（系统锁定工作台）|
| 连续处理 CSAM/critical 案件达 **5 条** | 强制 15 分钟休息 | **不可跳过**（系统锁定工作台）|
| 单班累计处理 CSAM 达曝光上限（10 条） | 强制下班（剩余班次不分配 CSAM） | **不可跳过** |
| 连续高敏作业（含 high-severity 暴力内容）达 20 条 | 强制 10 分钟休息 | 不可跳过 |

**强制休息期间的行为约束**：
- 工作台进入"休息锁定"状态，所有案件入口灰显，不响应提交操作
- 休息计时器在工作台显著位置展示（不可最小化）
- 法定时限案件（SLA 极端紧迫）：休息锁定期间若有法定时限案件到期风险（剩余时间 <15min），系统自动告警并通知组长手动覆盖（记录覆盖原因和授权人）；组长覆盖须留 WORM 审计记录，不允许审核员自行跳过
- 运营 SLA（非法定时限）在强制休息期间**正常暂停计时**（不扣分不告警）

##### §5.A.3 创伤内容屏蔽模式（Trauma-Shield Mode）

**触发方式**：
- 审核员在工作台主动开启（工具栏切换）
- 系统自动推荐：单班曝光计数 ≥ 7 条时，工作台弹出开启建议（不强制）
- 组长可为指定审核员强制开启（须记录原因）

**屏蔽模式行为**：

| 元素 | 屏蔽模式下的行为 |
|---|---|
| CSAM / C2 / 高严重度暴力帧 | 自动模糊处理（像素化），须主动点击"我已准备好查看"才能临时解锁单帧 |
| 视频自动播放 | 禁止；须手动点击播放，默认静音 |
| 时间戳前跳 | 允许；支持按分钟跳转，跳过高密度创伤内容段 |
| ASR 转录显示 | 保留（文字比视觉冲击小）；含极端仇恨言论/性暴力描述的片段可选折叠显示 |
| 案件切换间隙 | 插入 2s 纯色缓冲屏（黑/灰，可配置），防止创伤内容残留视觉冲击 |
| 心理支持入口 | 屏蔽模式开启时，工作台常驻显示 Crisis/Wellness 团队联系方式和自助资源链接 |

**屏蔽模式不影响**：案件判定逻辑、SLA 计时、审计记录。审核员在屏蔽模式下做出的判决与正常模式下具有同等法律效力。

##### §5.A.4 反疲劳设计的监控与审计

以下指标由运营健康度模块（模块 10）统一监控：

| 指标 | 说明 | 告警阈值 |
|---|---|---|
| 强制休息触发率（按审核员/班次） | 监控是否有审核员高频触发强制休息 | 单班 ≥ 3 次强制 15min 休息 → P2 告警（推 Wellness 团队）|
| CSAM 曝光上限超限尝试次数 | 系统改派次数（说明业务量超出曝光上限设计） | 周超限改派 >100 次 → 扩充 CSAM 资质审核员 P2 工单 |
| 创伤屏蔽模式开启率 | 监控审核员心理压力趋势 | <30% 开启率时主动推送开启建议 |
| 反疲劳参数变更记录 | 曝光上限/休息阈值任何变更 | 须 Maker-Checker 双签，变更记录进 WORM 审计日志 |

**合规说明**：反疲劳参数（曝光上限、休息阈值）的**任何放宽（上调上限或下调阈值）**须经 Crisis/Wellness 团队负责人 + 合规负责人双签，不得由运营管理员单方调整。参数收紧（更保护审核员）仅需 Policy PM 单签。

---

### 模块 6：质检与审核质量

继承 v2.0 模块 6 全部内容。

---

### 模块 7（★）：申诉闭环

继承 v2.0 模块 7 全部内容。

---

### 模块 8（★）：critical 高危上报

继承 v2.0 模块 8 全部内容。

---

### 模块 9：合规与透明度

继承 v2.0 模块 9 全部内容。

---

### 模块 10：平台运营与健康度

继承 v2.0 模块 10 全部内容。

---

### 模块 11：可复用性与可扩展性

继承 v2.0 模块 11 全部内容。

以下为 v2.1 新增子节：

#### §11.A 策略可扩展性要求——新审核策略维度零改造扩展路径（v2.1 新增）

##### §11.A.1 核心设计目标

平台的策略维度（审核类目）会随法规、内容生态、业务需求持续演进。新增一个审核策略维度**不应**触发五层核心代码的修改，否则会导致：开发周期长、回归风险高、跨模块协调成本大。

**零改造目标**：新增一个审核策略维度，从提案到在机审/人审/申诉/审计/策略全链路贯通，**零改造率 ≥ 95%**（即 ≥ 95% 的新维度不触发五层核心代码变更）。

##### §11.A.2 五层核心代码（禁止因新增维度改动）

| 层 | 系统组件 | 职责 |
|---|---|---|
| 决策层 | 规则引擎聚合逻辑 | 按维度注册表加载维度配置，通用逻辑不依赖具体维度 |
| 人审层 | 人审工作台 UI 框架 | 按注册表动态渲染审核维度选项，不硬编码类目 |
| 申诉层 | 申诉状态机与 SoR 生成 | 按注册表加载维度名称与对外模板，不硬编码 |
| 审计层 | 审计日志 Schema | 以 `dimension_id` 字段记录，不随具体维度变更 Schema |
| 策略层 | 策略版本化存储与解析 | 按 `dim_id` 键存储阈值与映射，通用解析器 |

##### §11.A.3 零改造扩展路径（注册表驱动）

新增审核策略维度的完整流程：

```
步骤 1：维度提案（Policy PM 发起）
  填写维度注册表条目：
  - dim_id（唯一标识，生成后不可改）
  - dim_name（人读名称，多语言）
  - dimension_axis（安全/质量/业务，三轴之一）
  - severity_tiers（各档判据 rubric，含子信号/分档标准/正反例）
  - llm_review_enabled（是否触发阶段3 LLM审查）
  - llm_prompt_template_id（引用 Prompt 模板库中的模板 ID）
  - jurisdiction_overrides（法域差异配置）
  - default_threshold_pair（人审下限 + 自动阈值默认值）
  - sor_template_id（对外 SoR 模板 ID，引用本地化模板库）
  - human_review_ui_config（人审工作台选项渲染配置）

步骤 2：双人评审（Maker-Checker）
  - 政策 PM + Policy Approver 双签
  - IRR 验证：新 rubric 必须通过黄金集标注，Kappa ≥ 0.8（安全类强制）

步骤 3：注册入库（技术侧自动化）
  - 维度定义写入维度注册表（版本化，不可原地修改，只追加新版本）
  - 自动触发：人审工作台维度列表刷新、决策引擎维度配置热加载、
    申诉 SoR 模板关联、审计日志维度枚举更新、飞轮分桶配置同步

步骤 4：Shadow 模式验证（机审侧）
  - 新维度以 Shadow 策略版本运行，收集差异报告
  - 确认 LLM 审查质量（DimensionVerdict 质量抽检，人工复核抽样）
  - 满足漂移红线 → 进灰度放量

步骤 5：灰度放量（1%→5%→25%→50%→100%）
  - 每档观察：新维度命中率、FP 率、人审推翻率、LLM 置信度分布
  - 自动护栏超红线 → 暂停放量，发起策略复盘

步骤 6：全量上线
  - 策略版本置 Active，全平台生效
  - 维度就绪态：已注册 + 机审已支持 + 人审已支持 + 已上线（四态）
```

**禁止的扩展方式**：
- 在规则引擎代码中硬编码 `if (dim_id == "xxx") { ... }` 逻辑
- 在人审 UI 中硬编码类目名称或选项
- 在申诉 SoR 生成逻辑中硬编码维度文案
- 新增维度时修改审计日志 Schema

##### §11.A.4 LLM Prompt 模板库（配合零改造路径）

- Prompt 模板独立版本化管理，与策略版本绑定
- 新维度新建模板条目，不改通用 Prompt 构造器
- 模板变更走 Maker-Checker 评审，变更后自动进入 Shadow 验证
- 模板库支持按维度 ID 精确查找，确保同一维度不同 policy 版本的 Prompt 可追溯

---

## 十二、数据回流（Data Flywheel）产品规范（v2.1 新增）

### 12.1 概述与设计目标

数据飞轮（Data Flywheel）是平台治理质量持续提升的内生动力。通过将人工审核确认结果、申诉改判结论、质检标注、黄金集回归数据**自动结构化回流**到模型训练、策略评估和决策引擎，形成"审核 → 人工确认 → 数据回流 → 模型/策略改进 → 更准确的机审"的正向循环。

**设计原则**：
- 回流数据须经**质量门控**，不让噪声数据污染训练集（一次错误改判不应直接写入训练集）
- 回流触发须**可审计**，每条回流数据可追溯到来源事件和触发时机
- 新模型/策略版本须经**Shadow 验证**才能正式上线，验证指标满足方可放量
- 飞轮回路不得影响**正在进行中的申诉或质检**的独立性

### 12.2 四类回流数据

#### 类型 A：Ground Truth（终审真值样本）

**定义**：经过人工审核最终确认的案件，结论经质量门认可，可作为机审训练的正样本。

**来源**：
- 人审工作台：审核员最终判定（非 Override，原始确认）
- 质检确认：质检员与裁决者共同确认的复核结论（盲判 + Adjudicator 终裁）
- 申诉裁决：申诉流程中 overturned / upheld 均可作为真值（标注结论类型）

**触发时机**：
- 案件进入 `已结案` 状态，且质量门判定为"可回流"（见 §12.3 质量门控）
- 批量：每日凌晨统一批处理上日结案样本（不阻塞实时审核路径）

**回流字段**：
```json
{
  "sample_id": "gt_20260701_abc001",
  "source_type": "human_review_confirmed",
  "content_id": "vid_987654321",
  "snapshot_id": "snap_20260701_001",
  "ep_id": "ep_20260701_abc12345",
  "dimension_id": "dim_hate_speech_incitement",
  "final_decision": "VIOLATION",
  "final_severity": "high",
  "annotator_tier": "senior_reviewer",
  "policy_version": "policy_v3.2.1",
  "created_at": 1751347200000,
  "quality_gate_passed": true
}
```

#### 类型 B：Disagreement（机审与人工不一致样本）

**定义**：机审结论与人工终审结论不一致的样本，是模型改进最有价值的训练数据。

**来源**：
- 人审 Override 记录（审核员推翻机审建议处置）
- 质检发现机审与复核结论不一致
- 申诉改判（申诉 overturned，说明原处置/机审存在错误）

**触发时机**：
- Override 事件发生后立即记录，标注 `disagreement_type`（machine_wrong / machine_right）
- 申诉 overturned 时延迟触发（等申诉质量门确认后再写入，防错误改判污染）

**回流字段**：在 Ground Truth 基础上增加：
```json
{
  "machine_decision": "NO_VIOLATION",
  "machine_confidence": 0.72,
  "llm_verdict": { ... },
  "disagreement_type": "machine_wrong",
  "disagreement_source": "human_override",
  "override_reason_category": "false_positive_context_misunderstood"
}
```

#### 类型 C：Golden Set（黄金回归集样本）

**定义**：由政策专家与资深合议共同签署的标准答案集，是模型版本切换和维度 rubric 更新的硬门禁。

**来源**：
- 新维度上线前的专家标注（步骤 2 IRR 验证期）
- 质检中 Adjudicator 终裁的高质量样本（经 QA Admin 手动加标）
- 申诉裁决中具有代表性、边界态清晰的典型案例（经样例集维护者 + 政策 PM 双签）

**触发时机**：
- 新维度上线流程步骤 2（双人评审 + IRR 验证时）
- 质检裁决者认为案件具有"黄金样本价值"时手动标记，经质量门批量入库
- 定期人工运营（季度）补充/淘汰过期黄金样本

**质量约束**：
- 黄金集写入须双人确认（样例集维护者 + 政策 PM）
- 黄金集不可被自动化逻辑删除，只能标注"已废弃"并保留历史
- 模型上线前必须通过黄金集回归测试（通过率 ≥ GOLDEN_PASS_RATE_TBD）

#### 类型 D：Policy Change Relabel（策略变更重标样本）

**定义**：当策略版本发生实质性变更（rubric 调整/阈值切档），导致部分历史已标注样本需要按新策略重新评估的样本集。

**来源**：
- 策略版本从 Active 切换到新 Active 时，决策引擎自动产出"受影响样本估计集"
- Backfill（存量内容重扫）执行前的预评估

**触发时机**：
- 新策略版本进入 Shadow 模式时，基于历史 Ground Truth 自动生成候选重标集
- 策略 PM 手动发起 Policy Change Relabel 任务（走 Maker-Checker 双签）

### 12.3 质量门控（Flywheel Quality Gate）

**以下条件任一不满足，样本不得进入回流通道**：

| 条件 | 说明 |
|---|---|
| 案件已完全结案（无未决申诉 / 未完成质检） | 防止在途争议样本进入训练 |
| 审核员独立性验证通过（二审≠原审，无排除规则违反） | 质量门须校验独立性，有违反则标注不可用 |
| 改判样本须经申诉质量门（非恶意刷申诉） | 申诉受理模块须完成刷量检测再触发回流 |
| policy_version 字段完整（可追溯到具体策略版本） | 无版本绑定的样本不可用于训练（策略背景不明） |
| snapshot_id 对应的 EvidencePackage 可访问 | 无证据包则无法重现审核输入，样本价值低 |
| **同一上传者批量去相关性校验通过**（v2.2 新增） | 防止单一内容生态主导训练集分布，见 §12.3.1 |

**质量门通过后**：样本写入 `flywheel_staging` 暂存区，经模型团队的日常 ETL 流程处理后进入训练数据集。**模型团队只读，不触及审核员个人评估数据（身份脱敏后入库）。**

#### §12.3.1 同一上传者批量去相关性规则（v2.2 新增）

**问题背景**：若某个高产创作者的内容大量进入训练集（尤其是违规创作者），其内容的分布偏好（拍摄风格、背景噪音、字体、话题偏好）可能主导模型学到的"违规特征"，导致模型对该风格的内容过度敏感、对其他风格欠敏感。

**去相关性规则（全部为质量门强制约束）**：

| 规则 | 参数 | 说明 |
|---|---|---|
| **单日单创作者入库占比上限** | **5%**（即同一 `creator_id` 的样本不超过当日入库总量的 5%）| 防止突发性大量内容（如某创作者一日发布大量相似违规视频）主导当日批次 |
| **批量入库去相关性时间窗口** | **7 天**（同一 creator_id 的样本须在 7 天内均匀分布入库，不得在单日集中入库）| 同一创作者的内容须分批次（每批 ≤ 3 条）按天分散写入 `flywheel_staging` |
| **内容相似度去重阈值** | **0.85**（视觉/ASR 特征余弦相似度）| 相似度 ≥ 0.85 的两条内容视为近重复（near-duplicate）；同一批次只保留 1 条（优先保留人审评审质量更高的那条），另一条标注 `dedup_skipped: true` |
| **单维度样本多样性校验** | 同一策略维度（`dimension_id`）下，单一 creator_id 贡献样本占比 ≤ 10% | 确保每个审核维度的训练集有足够多不同创作者的内容 |

**实现要求**：
- 后端 `flywheel_staging` 写入接口须在写入前查询以下条件：
  1. 今日该 `creator_id` 已入库样本量 / 今日总入库量
  2. 该 `creator_id` 近 7 天的入库分布
  3. 与待入库样本相似度 ≥ 0.85 的已入库样本（通过预计算特征向量索引）
- 相似度检测须在样本入库前完成，不得异步处理（防止竞态条件导致相似样本并发入库）
- 被去相关性规则拦截的样本须记录 `quality_gate_skipped_reason: "dedup_creator_limit|near_duplicate|distribution_limit"`，保留在 `flywheel_staging_rejected` 表中供审计

**监控指标**（由模块 10 监控）：
- 每日去相关性拦截率（拦截样本 / 提交样本）：>20% 时告警，说明上游可能存在内容生产异常
- 训练集 creator_id 多样性指数（Gini 系数）：目标 ≥ 0.8（即前 20% creator 贡献 ≤ 50% 样本）

### 12.4 Shadow 模式验证（新模型/策略上线前验证）

**触发场景**：
- 新 LLM 模型版本准备切换（替换现有 active 模型）
- 新策略版本从 Shadow → 准备放量
- 新审核维度准备从 Shadow → 灰度上线

**Shadow 验证流程**：

```
1. Shadow 并行运行（对真实流量，不执行处置）
   · 新版本与 active 版本同时运行
   · 记录所有 DimensionVerdict 差异
   · CSAM/critical 强制上报类仍真实执行（Shadow 不豁免合规强制项）

2. 差异分析报告生成（每 24h 一次）
   · 新旧版本在各维度的命中率差异
   · FP/FN 估计（与 Ground Truth 样本对照）
   · LLM 置信度分布变化
   · 成本影响估计（LLM 调用次数/Token 变化）

3. 漂移红线检测
   · critical 类目漏检率增加 > CRITICAL_FN_THRESHOLD_TBD → 阻断放量，强制升级
   · FP 率增加 > FP_INCREASE_THRESHOLD_TBD → 暂停放量，发起策略复盘
   · 整体一致率 < CONSISTENCY_THRESHOLD_TBD → 延长 Shadow 观察期

4. 通过漂移红线 → 进入灰度放量
   · 按 1%→5%→25%→50%→100% 梯次，每档最短观察期 MIN_CANARY_PERIOD_TBD
   · 人审推翻率实时监控，超红线暂停放量

5. 100% 放量完成 → 旧版本归档（Archived）
   · 归档版本保留完整策略文本和模型版本指针
   · 合规取证时可按版本号重现当时决策逻辑
```

**Shadow 期间禁止事项**：
- Shadow 版本的 DimensionVerdict 不得作为人审工作台的展示依据
- Shadow 期间不得降低对 active 版本的监控（不以 Shadow 替代 active 的质量观测）
- Shadow 差异报告不得泄露给申诉相关方（避免影响申诉公正性）

### 12.5 飞轮健康度指标

以下指标由运营健康度模块（模块 10）统一监控：

| 指标 | 说明 | 告警阈值（TBD） |
|---|---|---|
| 日回流样本量（按类型 A/B/C/D 分） | 回流通道是否畅通 | 突降 >50% 升 P2 |
| 质量门通过率 | 提交回流 vs 通过门控的比率 | <60% 升 P2 |
| Ground Truth 标注延迟 | 从案件结案到样本入库的时延 P95 | >24h 升 P3 |
| 黄金集覆盖率（按维度） | 每个 active 维度的黄金集样本量 | <MIN_GOLDEN_COUNT_TBD 升 P2 |
| Shadow 差异报告准时率 | 每 24h 产出一次 | 缺失升 P1 |
| 漂移红线触发次数（月） | 模型/策略质量趋势指标 | — |

---

## 十三、全局验收标准（v2.1 更新项）

继承 v2.0 对应章节内容，以下为 v2.1 新增/强化验收项：

| 验收项 | 验收标准 | 优先级 |
|---|---|---|
| 机审三阶段完整性 | 全量视频均经历阶段 1（EvidencePackage 产出）→ 阶段 2（初筛）→ 阶段 3（LLM）→ 规则引擎聚合，无阶段跳过（CSAM 哈希命中除外） | P0 |
| EvidencePackage Schema 合规 | 所有裁决包均可找到对应 EvidencePackage，字段完整率 ≥ 99.9% | P0 |
| LLM 职责边界 | 系统设计层无任何 LLM 直接输出处置动作的路径（代码 Review 验证） | P0 |
| 零改造扩展验证 | 本版至少完成 1 个新维度的零改造上线（仅填注册表，无核心代码改动），作为机制验证 | P1 |
| Shadow 验证覆盖 | 任何新模型/策略版本上线前，均有对应 Shadow 差异报告留存 | P0 |
| 数据回流四类样本 | 飞轮基础能力上线后，Ground Truth / Disagreement / Golden Set 三类均有样本入库记录 | P1 |
| 飞轮质量门 | 质量门代码路径覆盖测试 100%，无门控被绕过的路径 | P0 |

---

## 十四、附录

### 附录 A：术语全索引

继承 v2.0 附录 A 完整内容，新增 v2.1 术语（§5.8）。

### 附录 B：参数表——工程默认值 vs Legal-TBD 分类

> **v2.2 更新**：参数按"类型"区分为 Engineering Default（工程可控，已落地）和 Legal-TBD（需法务签署，尚未落地）。工程默认值可由 Policy PM + SRE 双签调整，无需法务介入；Legal-TBD 参数在法务签署前保持保守占位值，不作硬约束落地。

#### 附录 B.1 工程默认值参数（已落地约束）

| 参数名 | 工程默认值 | 说明 | 调整需双签方 |
|---|---|---|---|
| `FILTER_SLA_P95` | **3s** | 阶段 2 基础初筛 P95 时限（§1.A.5） | Policy PM + SRE |
| `LLM_SLA_P95` | **30s** | 阶段 3 LLM 审查 P95 时限（§1.A.5） | Policy PM + SRE |
| `MAX_FRAMES` | 60s→60帧；10min→300帧；60min→1800帧；>60min→3000帧 | 单视频最大抽帧数量上限（按时长分档） | SRE（成本约束） |
| `EXTRACTION_SLA_60s` | **30s** | ≤60s 视频证据提取 P95 时限 | Policy PM + SRE |
| `EXTRACTION_SLA_10min` | **120s** | 61s～10min 视频证据提取 P95 时限 | Policy PM + SRE |
| `EXTRACTION_SLA_60min` | **300s** | 10min～60min 视频证据提取 P95 时限 | Policy PM + SRE |
| `EXTRACTION_SLA_OVER_60min` | **600s** | >60min 视频提取 P95 时限（超时路由人审） | Policy PM + SRE |
| `CSAM_EXPOSURE_CAP_PER_SHIFT` | **10 条** | CSAM 类案件单班曝光上限（§5.A.1） | Crisis/Wellness + 合规（只能收紧，不能放宽） |
| `CSAM_EXPOSURE_CAP_PER_WEEK` | **30 条** | CSAM 类案件每自然周曝光上限（§5.A.1） | Crisis/Wellness + 合规 |
| `FORCED_REST_TRIGGER_3` | **3 条** → 强制 5min 休息 | 高敏案件连续处理触发阈值（§5.A.2） | Crisis/Wellness + 合规 |
| `FORCED_REST_TRIGGER_5` | **5 条** → 强制 15min 休息 | 高敏案件连续处理触发阈值（§5.A.2） | Crisis/Wellness + 合规 |
| `FLYWHEEL_CREATOR_DAILY_CAP` | **5%** | 单日单创作者入库占比上限（§12.3.1） | ML 团队 + Policy PM |
| `FLYWHEEL_DEDUP_WINDOW_DAYS` | **7 天** | 同一创作者样本分散入库时间窗口（§12.3.1） | ML 团队 |
| `FLYWHEEL_SIMILARITY_THRESHOLD` | **0.85** | 近重复内容去重阈值（§12.3.1） | ML 团队 |
| `TOKEN_BUDGET_60s` | **8,000 tokens** | ≤60s 视频 LLM Input Token 预算（§1.E.5） | ML 团队 + SRE |
| `TOKEN_BUDGET_10min` | **16,000 tokens** | 61s～10min 视频 Token 预算（§1.E.5） | ML 团队 + SRE |
| `TOKEN_BUDGET_60min` | **32,000 tokens** | 10min～60min 视频 Token 预算（§1.E.5） | ML 团队 + SRE |
| `TOKEN_BUDGET_HARD_CAP` | **48,000 tokens** | 所有视频 Input Token 绝对上限（§1.E.5） | ML 团队 + SRE |
| `WEBSOCKET_HEARTBEAT_INTERVAL_S` | **30s** | WebSocket 心跳间隔（§1.E.4） | SRE |
| `WEBSOCKET_RECONNECT_MAX_BACKOFF_S` | **30s** | WebSocket 重连最大退避时间（§1.E.4） | SRE |

#### 附录 B.2 Legal-TBD 参数（待法务签署，暂为占位值）

| 参数名 | 说明 | 法务签署前占位值 | 依赖方 |
|---|---|---|---|
| `CSAM_REPORT_SLA_TBD` | CSAM 命中到法定报送时限（如 NCMEC） | 各法域法条，不得自行设定 | 法务 + 合规 |
| `AUTO_THRESHOLD_TBD` | 阶段 2 初筛跳过 LLM 的高置信阈值 | 0.95（保守占位，正式值需策略 PM + 风控会签） | 策略 PM + 风控 |
| `AUTO_PASS_THRESHOLD_TBD` | 阶段 2 快速放行置信度阈值 | 0.98（保守占位） | 策略 PM + 风控 |
| `MAX_LLM_CALLS_PER_VIDEO_TBD` | 单视频最大 LLM 调用次数 | 3 次（保守占位） | ML 团队 + 成本约束 |
| `CRITICAL_FN_THRESHOLD_TBD` | Shadow 验证 critical 漏检率红线 | 0.001（0.1%，保守占位） | 安全策略负责人 + 合规双签 |
| `FP_INCREASE_THRESHOLD_TBD` | Shadow 验证 FP 率增幅红线 | 10%（相对增幅，占位） | 策略 PM |
| `CONSISTENCY_THRESHOLD_TBD` | Shadow 验证整体一致率下限 | 0.90（占位） | 策略 PM |
| `MIN_CANARY_PERIOD_TBD` | 灰度每档最短观察时间 | 24h（保守占位） | 策略 PM |
| `GOLDEN_PASS_RATE_TBD` | 黄金集回归测试通过率下限 | 0.95（占位） | QA Admin |
| `MIN_GOLDEN_COUNT_TBD` | 每个维度黄金集最小样本数 | 100 条（占位） | QA Admin |
| `FAIL_RATE_TBD` | 证据提取单模态失败率告警阈值 | 1%（占位） | SRE |
| `DSA_SOR_DELIVERY_SLA_TBD` | DSA 下 SoR 送达法定时限 | 待 EU DSA 法务核准 | 法务（EU） |

### 附录 C：EvidencePackage Schema 版本历史

| 版本 | 变更说明 | 生效 policy 版本范围 |
|---|---|---|
| v1.0 | 初始版本，含五类信号字段（MVP v1.1 交付） | policy v3.x.x 起 |

### 附录 D：变更日志

| 版本 | 日期 | 变更摘要 | 变更人 |
|---|---|---|---|
| v1.0 | 2026-xx-xx | 初始三核心模块骨架 | T&S 产品 |
| v2.0 | 2026-06-30 | 全平台 11 模块统一骨架版 | T&S 产品 |
| v2.1 | 2026-07-01 | 机审三阶段强化 + MVP 范围明确 + 数据飞轮 + 零改造扩展路径 | T&S 产品 |
| v2.2 | 2026-07-01 | 专家评审修订：SLA 工程默认值落地 + 跨文档契约对齐（§1.E）+ 反疲劳设计（§5.A）+ 飞轮去相关性（§12.3.1）+ 附录 E v2.0 内嵌摘要 + Prompt 注入防御 | T&S 产品（专家评审后修订） |

---

### 附录 E：v2.0 必读章节内嵌摘要（v2.2 新增——消除单文档可读性缺口）

> **版本锚点**：本附录内嵌自 PRD v2.0（全平台 11 模块统一骨架版，2026-06-30 定稿）。以下内容为 v2.0 相关章节的精确摘要，原文权威版本见 `docs/PRD.md`（Git commit: `04243c1`）。若本摘要与原文存在出入，以原文为准。

#### 附录 E.1 统一角色与权限矩阵（v2.0 §七 精确摘要）

以下为 v2.0 §七定义的跨平台角色及其核心权限边界。**完整矩阵（含全部 40+ 角色）见原文 `docs/PRD.md §七`**；此处内嵌与机审管线、人审工作台、数据飞轮直接相关的核心角色。

**机审与策略管理核心角色**：

| 角色 | 核心职责 | 关键权限边界 |
|---|---|---|
| 政策/治理产品经理 Policy PM | 提矩阵单元格、类目切档阈值、注册/下线类目、配 rubric/override | 不可单方上线；变更走版本化+二人评审 |
| 政策审批人 Policy Approver/Lead | 审批矩阵变更；高风险 four-eyes | 提交人≠审批人 |
| T&S 策略负责人 | 调阈值/参数、发起 policy 版本、回扫/漏检 owner；审批上线、一键回滚 | 发布需双人复核；**发布人≠审批人** |
| 安全策略负责人 | 安全·critical 审批·kill-switch | 高危变更需与合规双签 |
| 风控会签角色 | 对高危参数、降采样比例、熔断阈值会签 | 会签位不可同一人兼任 |

**人审核心角色**：

| 角色 | 核心职责 | 关键权限边界 |
|---|---|---|
| Tier 1/2/3 审核员 | 常规/疑难/政策法务专家三级处理；升级/回退/熔断 | T1/T2 无 critical 处理权与对外上报权 |
| Critical 专审员 / 资深专审员 | 一线确认（默认模糊视图）、复核、裁决分歧、C3/C1-c 判定 | **受强制轮换/限时暴露/心理支持约束**；单人不可终局；不删改证据 |
| Crisis/Wellness 团队 | C4 危机干预、**审核员心理健康支持** | 不做内容判定/上报；反疲劳参数变更须经此团队双签 |
| 组长 Lead | 队列调度·派单·改派·审批批量 | 回收锁须留痕、禁改派回原审 |

**贯穿全平台的角色硬约束（摘要）**：
1. 职责隔离：申诉复核、质检复核、critical 纠错均须与原处置决策者隔离；二审≠原审按账号 ID 排除
2. 四权分立（critical）：判定、上报、保全销毁、策略治理分属不同角色
3. Maker-Checker：策略、矩阵单元格、阈值、护栏、维度注册表变更均须双人
4. CSAM 不可下调：任何角色不可下调 CSAM 的 REMOVE_AND_ESCALATE
5. 绩效防火墙：wellness 指标仅用于健康干预，不公开排名、不与绩效负向挂钩

#### 附录 E.2 统一状态机总览（v2.0 §八 精确摘要）

**完整状态机定义见原文 `docs/PRD.md §八`**；此处内嵌与 v2.2 新增内容直接相关的状态轴。

**可见性状态轴（v2.0 §8.1，六态）**：

| 可见性状态 | 驱动处置 | 可叠加性 |
|---|---|---|
| 公开 Public | 放行 PASS | — |
| 限流 Demoted | 限流降权 DEMOTE | 可与打标叠加 |
| 年龄限制 Age-Restricted | 年龄门 AGE_GATE | 可与打标/地理叠加 |
| 地理限制 Geo-Restricted | 地理屏蔽 GEO_BLOCK | 可与年龄门并集叠加 |
| 下架 Removed | 下架 REMOVE / critical_hold | 打标不可叠加 |
| 证据冻结 Evidence-Held | 下架并上报 REMOVE_AND_ESCALATE / evidence_hold | 正交独立属性 |
| 发布门控 Publish Gate（v2.0 新增） | pre-publish gate timing | 完全不可见，等待初审 |

**决策引擎策略版本状态机（v2.0 §8.5）**：
```
Draft →（Maker 提交）→ 待审批 →（Checker 通过）→ Shadow →（灰度放量 1%→5%→25%→50%→100%）→ Active → Archived
  ↑（Checker 退回）    护栏超红线→暂停放量+告警
  秒回滚：Archived 重新置 Active 生成新版本指针，<60s，无需发版
  Kill-switch：生效键级总闸，停用后全走人审+保守限流兜底
```

**申诉状态机（v2.0 §8.4，简要）**：
```
提交 → open →（分配，排除原审）→ in_triage →（接单，独立性强校验）→ in_review
  → 维持 → upheld（终态）
  → 改判 → overturned（终态，触发恢复连锁四链）
  → 升级 → in_review（负责人变更）
```
关键硬约束：`in_review` 只能由人工事件离开；改判触发恢复连锁四链（恢复可见性 + 账号处罚回滚 + 质检负反馈 + 改判样本回流）。

#### 附录 E.3 处置矩阵摘要（v2.0 模块 3 精确摘要）

**完整处置矩阵正文见原文 `docs/PRD.md 模块 3（★）`**；此处内嵌七档处置动作和取严链，供机审/人审/数据飞轮引用。

**七档处置动作（SSOT = 处置矩阵 模块 3）**：

| 枚举值 | 名称 | 对应 L3 DispositionAction | 说明 |
|---|---|---|---|
| `PASS` | 放行 | PASS | 全渠道全量可见，无限制 |
| `DEMOTE` | 限流降权 | DEMOTE | 移出推荐流，仍可直链访问 |
| `LABEL` | 打标加注上下文 | LABEL | 正交标注，可叠加于任一可见性状态（下架/证据冻结除外） |
| `AGE_GATE` | 年龄门 | AGE_GATE | 仅 18+ 可见，须身份验证 |
| `GEO_BLOCK` | 地理屏蔽 | GEO_BLOCK | 部分地区不可见（按法域围栏） |
| `REMOVE` | 下架 | REMOVE | 全局不可见，可触发申诉 |
| `REMOVE_AND_ESCALATE` | 下架并上报 | REMOVE_AND_ESCALATE | 全局不可见 + 不可删除 + 已上报；CSAM 必须走此动作，任何角色不可降级 |

**取严链（可见性轴）**：
```
下架/证据冻结（5）> 地理屏蔽（3）> 年龄门（3）> 限流（2）> 放行（0）
打标（1）：永远叠加，不进取严链
证据冻结：正交独立属性，不受取严链影响
```

**三轴解耦合并规则**：
- 安全轴（否决项）：决定可见范围，命中 critical 强制 REMOVE_AND_ESCALATE
- 质量轴：决定分发力度，**永不下架**（质量轴只能产出 DEMOTE/LABEL，不产出 REMOVE）
- 业务轴：打标/屏蔽/去挂载/降权，独立计算后并行施加

**CSAM 强制处置规则（不可降级）**：CSAM-class 命中的处置动作永远为 `REMOVE_AND_ESCALATE`，任何角色（含超管）不可改为其他动作，不可被申诉改判为放行（申诉仅限"误命中"元数据级争议）。

---

## 十五、专家评审记录

> 本章记录对 PRD v2.1 进行的专家评审结果，作为 v2.2 修订的依据，永久保存在文档中，不可删除或修改。

### 15.1 评审基本信息

| 项目 | 内容 |
|---|---|
| 被评审版本 | PRD v2.1（机审三阶段强化 + MVP 范围明确版） |
| 评审日期 | 2026-07-01 |
| 评审评分 | **81 / 100** |
| 修订版本 | PRD v2.2（本文档） |

### 15.2 专家总体评价

> 原文摘录（保留专家原话）：
>
> "三份文档整体体现了扎实的内容治理系统设计功力：三阶段漏斗架构、LLM 与规则引擎的职责边界划分、幂等性与降级链设计均属业界水准。但仍存在三个阻断生产落地的高优问题：其一，后端 Anthropic SDK 同步/异步混用（Anthropic() 而非 AsyncAnthropic()）是运行时必现的致命 Bug，会导致 policy-reviewer 服务整体不可用；其二，EvidencePackage 字段名和决策枚举在 PRD/后端/前端三套文档中各自为政、无映射规则，集成阶段将大量返工；其三，反疲劳设计（CSAM 曝光上限、强制休息）和 Prompt 注入防御在三份文档中均完全缺失，前者是劳工合规红线，后者是安全红线。建议：修复致命 Bug 后启动后端集成测试，同时召集三端负责人对齐 EvidencePackage 契约和决策枚举映射，将反疲劳设计列入下一个 Sprint 强制交付，PRD 补充 Prompt sanitize 规范后方可启动 LLM 策略审查生产验证。"

### 15.3 专家要求修复的问题（逐条记录与处理状态）

#### 问题一：v2.0 必读章节缺少精确版本锚点

| 项目 | 内容 |
|---|---|
| **问题描述** | v2.1 附录中缺少对 v2.0 必读章节（角色矩阵/状态机/处置矩阵）的精确版本链接，单文档可读性存在缺口，读者必须跨文档查找关键定义 |
| **严重度** | 中（影响可读性和可维护性） |
| **v2.2 修复** | 新增附录 E，内嵌 v2.0 角色权限矩阵摘要（附录 E.1）、统一状态机摘要（附录 E.2）、处置矩阵摘要（附录 E.3），并提供精确版本锚点（Git commit `04243c1`，原文路径 `docs/PRD.md`） |
| **处理状态** | 已修复 |

#### 问题二：SLA 参数为 TBD 而非工程默认值

| 项目 | 内容 |
|---|---|
| **问题描述** | `FILTER_SLA_TBD`（目标 <3s）和 `LLM_SLA_TBD`（目标 <30s）标注为 TBD，但这两个参数实为工程可控参数，不依赖法务签署，不应与法务约束项混用 TBD 标签，导致工程侧缺乏明确约束 |
| **严重度** | 中（影响工程落地明确性） |
| **v2.2 修复** | §1.A.5 SLA 总览表：`FILTER_SLA` 改为工程默认值 **3s**（P95），`LLM_SLA` 改为工程默认值 **30s**（P95），并新增按时长分档的阶段 1 提取 SLA 表；附录 B 拆分为 B.1（工程默认值）和 B.2（Legal-TBD），FILTER/LLM SLA 移入 B.1 |
| **处理状态** | 已修复 |

#### 问题三：模块 5 缺少反疲劳设计子节

| 项目 | 内容 |
|---|---|
| **问题描述** | 模块 5 人审工作台继承 v2.0 未提及反疲劳设计；后端无审核员工作量限制实现；前端无强制休息逻辑；在日均亿级 PV 平台上，CSAM 类目审核员缺乏保护是高合规风险点（多国劳工法/监管指引已有要求） |
| **严重度** | 高（合规红线） |
| **v2.2 修复** | 新增 §5.A 反疲劳设计，包含：①§5.A.1 CSAM 类目单班曝光上限（10 条）和每周上限（30 条）；②§5.A.2 强制休息触发阈值（3 条→5min，5 条→15min 强制休息，不可跳过）；③§5.A.3 创伤内容屏蔽模式（帧模糊、播放控制、心理支持常驻入口）；④§5.A.4 监控指标；参数同步写入附录 B.1 工程默认值表 |
| **处理状态** | 已修复 |

#### 问题四：飞轮质量门未防止单一上传者主导训练集

| 项目 | 内容 |
|---|---|
| **问题描述** | §12.3 飞轮质量门五条条件未包含同一上传者样本批量入库的去相关性规则，存在单一内容生态（如某个高频违规创作者）主导训练集分布的风险，导致模型对特定内容风格过度敏感 |
| **严重度** | 中（模型质量风险） |
| **v2.2 修复** | §12.3 质量门新增第六条条件"同一上传者批量去相关性校验通过"；新增 §12.3.1 详细规则，包含：单日单创作者占比上限 5%、批量入库时间窗口 7 天、近重复内容去重阈值 0.85、单维度多样性校验（单创作者贡献 ≤ 10%）；附录 B.1 同步写入工程默认值 |
| **处理状态** | 已修复 |

### 15.4 跨文档一致性问题（逐条记录与处理状态）

#### 跨文档问题一：EvidencePackage 字段命名三文档不一致

| 项目 | 内容 |
|---|---|
| **问题描述** | PRD 定义 `ep_id / object_detections / asr_transcript`（数组），后端 Pydantic 使用 `package_id / objects_detected / asr`（ASRResult 对象），前端 TypeScript 无对应字段；三套命名没有显式映射层，集成时极易字段丢失 |
| **v2.2 修复** | 新增 §1.E.1，定义 PRD 字段名为唯一权威（Wire Format），提供 10 个字段的三端映射表及对齐动作；明确后端须用 alias 对外暴露 PRD 字段名，前端须新增 EvidencePackage TypeScript 接口 |
| **处理状态** | PRD 层已修复；后端/前端对齐动作已在 §1.E.1 定义，需工程团队按本节同步实现 |

#### 跨文档问题二：决策枚举三套体系完全不兼容

| 项目 | 内容 |
|---|---|
| **问题描述** | PRD §1.C 定义 VIOLATION/NO_VIOLATION/UNCERTAIN，后端 PolicyDecision 使用 pass/block/needs_review，前端 Disposition 使用 PASS/REMOVE/REMOVE_AND_ESCALATE 等七档；没有任何文档定义三层之间的映射规则 |
| **v2.2 修复** | 新增 §1.E.2，定义三层枚举的职责（L1 LLM 维度判断层 / L2 规则引擎决策层 / L3 处置动作层），提供 L1→L2→L3 的完整映射规则（含取严链），明确前端只消费 L3，L1/L2 不对外暴露 |
| **处理状态** | PRD 层已修复；后端须将 L2 枚举值改为 `auto_pass / auto_block / needs_human_review / critical_escalate` 以对齐本规范 |

#### 跨文档问题三：CSAM 处理路径三层不一致

| 项目 | 内容 |
|---|---|
| **问题描述** | PRD 要求 CSAM 走独立安全存储（最强），后端只是 fast_path_block（中等），前端只有展示屏蔽（最弱）；三层没有形成统一的 CSAM 隔离边界 |
| **v2.2 修复** | 新增 §1.E.3，定义五个隔离层次（内容存储层/流水线层/后端 API 层/前端展示层/访问控制层）的统一要求，明确违反后果（P0 合规告警/安全漏洞），形成端到端的 CSAM 隔离边界 |
| **处理状态** | PRD 层已修复；后端须实现 CSAM 专用安全存储隔离和 API 层 csam_exception 校验；前端须实现帧预览完全屏蔽逻辑 |

#### 跨文档问题四：WebSocket 协议真空

| 项目 | 内容 |
|---|---|
| **问题描述** | WebSocket 是前后端集成的核心依赖（锁状态/SLA 推送/告警），但后端技术方案和前端技术方案均未定义消息格式、鉴权机制和重连策略 |
| **v2.2 修复** | 新增 §1.E.4，完整定义 WebSocket 协议：7 种消息类型（含 payload 结构）、JWT 鉴权机制（连接鉴权 + 消息推送前角色校验）、指数退避重连策略（最大退避 30s）、断连补推机制（5 分钟内消息） |
| **处理状态** | PRD 层已修复；前后端须按 §1.E.4 各自实现 |

#### 跨文档问题五：反疲劳设计三文档均缺失

| 项目 | 内容 |
|---|---|
| **问题描述** | 反疲劳设计在 PRD 模块 5、后端、前端三份文档中均完全缺失；在日均亿级 PV 平台上是高合规风险点 |
| **v2.2 修复** | 已在 §5.A 完整定义（见问题三处理）；此处记录跨文档状态：**后端须实现 `reviewer_csam_exposure` 表和曝光计数拦截逻辑；前端须实现强制休息锁定 UI、创伤内容屏蔽模式和心理支持入口** |
| **处理状态** | PRD 层已修复；后端/前端实现动作已明确，需工程团队跟进 |

#### 跨文档问题六：LLM Token 预算无实现

| 项目 | 内容 |
|---|---|
| **问题描述** | PRD §1.A.3 要求 Token 预算按视频时长分档截断，后端无实现，前端无感知；长视频会超出上下文窗口导致 LLM 调用报错且无降级 |
| **v2.2 修复** | 新增 §1.E.5，定义四档 Token 预算（8K/16K/32K/48K），截断优先级规则，后端预算预估实现要求，前端 `truncated_modalities` 展示要求；附录 B.1 同步写入工程默认值 |
| **处理状态** | PRD 层已修复；后端须实现 tokenizer 预估和截断逻辑；前端须展示截断警示 |

#### 跨文档问题七：Shadow 报告存储未定义

| 项目 | 内容 |
|---|---|
| **问题描述** | PRD §12.4 要求每 24h 产出 Shadow 差异报告，但后端无专门的 Shadow 报告聚合表或 API，前端 ShadowCompareView 的数据来源也未定义 API 端点 |
| **v2.2 修复** | 新增 §1.E.6，定义 `shadow_reports` 表结构（含 `summary_json` 和 `drift_alerts_json` 子结构）、4 个 REST API 端点、24h Cron 生成机制和 WebSocket 推送通知 |
| **处理状态** | PRD 层已修复；后端须实现 `shadow_reports` 表和对应 API；前端 ShadowCompareView 须调用 `/api/shadow/reports/latest` |

### 15.5 未在 PRD 层修复的问题（需工程团队跟进）

以下问题经专家评审确认，属于工程实现层问题，超出 PRD 修订范围，已记录于此以便工程团队跟进：

| 问题 | 性质 | 优先级 | 负责方 |
|---|---|---|---|
| 后端 Anthropic SDK 同步/异步混用：`Anthropic()` 应改为 `AsyncAnthropic()`，否则 policy-reviewer 服务调用 LLM 时会阻塞事件循环，导致服务整体不可用 | 后端致命 Bug（运行时必现） | **P0，应在下次 PR 中修复** | 后端工程师 |
| 后端 `PolicyDecision` 枚举值需从 `pass/block/needs_review` 改为 `auto_pass/auto_block/needs_human_review/critical_escalate`，对齐 §1.E.2 | 后端枚举迁移 | P1 | 后端工程师 |
| 后端须实现 CSAM 专用安全存储（独立加密存储桶），与普通证据存储分离 | 后端安全实现 | P0 | 后端工程师 + 安全团队 |
| 前端须实现 EvidencePackage TypeScript 接口，字段名与 §1.E.1 完全一致 | 前端类型定义 | P1 | 前端工程师 |
| 后端须实现 `reviewer_csam_exposure` 计数表和队列分配前置校验 | 后端合规实现 | P0（合规红线） | 后端工程师 |
| 前端须实现强制休息锁定 UI（工作台不可操作 + 计时器显著展示）和创伤内容帧模糊处理 | 前端合规实现 | P0（合规红线） | 前端工程师 |

---

*本文档由 T&S 产品负责人维护，任何修改须经对应章节的负责人与 Policy Approver 双签后方可生效。本版本（v2.2）为专家评审后修订草案，待法务核准 Legal-TBD 参数（附录 B.2）后正式签发。*
