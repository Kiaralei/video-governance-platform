修订完成。完整的 PRD v2.2 已生成，文件路径：

`/Users/lilithgames/Documents/Projects/video-governance-platform/docs/PRD_v2.2.md`

**文件概况：1484 行，约 94KB（原 v2.1 为 901 行 / 48KB）。**

---

**v2.2 修订内容总结（对应专家每条要求）：**

**一、专家要求的四项修复**

1. **附录 E 内嵌 v2.0 必读章节**（附录 E.1～E.3）：内嵌角色权限矩阵摘要、统一状态机摘要（含六态可见性状态、策略版本状态机、申诉状态机）、处置矩阵摘要（七档动作、取严链、三轴解耦），精确版本锚点为 Git commit `04243c1` / `docs/PRD.md`。

2. **SLA 工程默认值落地**（§1.A.5 + 附录 B.1）：`FILTER_SLA` → **3s（P95，Engineering Default）**，`LLM_SLA` → **30s（P95，Engineering Default）**；附录 B 拆分为 B.1（工程默认值，已约束）和 B.2（Legal-TBD，待法务）。

3. **反疲劳设计 §5.A**（模块 5 新增）：CSAM 单班曝光上限 10 条/自然周 30 条；强制休息触发阈值（3 条→5min，5 条→15min，不可跳过）；创伤内容屏蔽模式（帧模糊、播放控制、心理支持常驻入口）；监控指标清单。

4. **飞轮去相关性规则 §12.3.1**：同一 creator_id 单日入库占比上限 5%、批量入库时间窗口 7 天、近重复去重阈值 0.85、单维度多样性约束（单创作者 ≤10%）。

**二、七个跨文档一致性问题**（均在 §1.E 新增节中处理）

- §1.E.1：EvidencePackage 字段名 10 个字段的三端映射表，PRD 为唯一 Wire Format 权威
- §1.E.2：决策枚举三层（L1 DimensionDecision / L2 PolicyDecision / L3 DispositionAction）职责定义和完整映射规则
- §1.E.3：CSAM 五层统一隔离边界（存储层/流水线层/后端 API 层/前端展示层/访问控制层）
- §1.E.4：WebSocket 协议定义（7 种消息类型、JWT 鉴权、指数退避重连）
- §1.E.5：LLM Token 预算四档（8K/16K/32K/48K），截断规则及前后端实现要求
- §1.E.6：`shadow_reports` 表结构、4 个 REST API 端点、24h Cron 生成机制
- §1.E.7：Prompt 注入防御规范（输入净化/角色隔离/输出校验/日志告警）

**三、专家评审记录**（第十五章）：完整记录评分（81/100）、专家原文总结、11 个问题逐条处理状态及后端 Anthropic SDK 致命 Bug 的工程团队跟进清单。
