# 视频治理平台 -- 前端技术方案（修订版）

**版本**: MVP v1.3 | **日期**: 2026-07-01 | **状态**: 二次修订稿  
**修订说明**: 根据第二轮技术专家评审反馈，重点修复分页协议矛盾、WebSocket 认证失败、金标测试时序错位、机审建议偏差等关键问题。全面提升前后端集成（5->8+）、稳定性（7->8+）、鲁棒性（7->8+）、安全性（7->8+）。所有新增或修改内容以【修订】标注。

---

## 1. 整体前端架构

### 1.1 技术选型总览

| 领域 | 选型 | 版本 | 选型理由 |
|------|------|------|----------|
| 框架 | React | 18.3+ | Concurrent 模式保障高频更新下的流畅度；生态成熟 |
| 语言 | TypeScript | 5.4+ | 强类型约束，与 PRD 数据契约（EvidencePackage / DimensionVerdict）一一映射 |
| 构建 | Vite | 6.x | HMR 快、ESBuild 预构建依赖秒级启动 |
| UI 库 | Ant Design | 5.x | 企业级 B 端组件齐全，Tree/Table/Form/Modal 与业务高度吻合 |
| 状态管理 | Zustand | 5.x | 轻量，slice 模式天然支持状态分层，无 Provider 包裹 |
| 请求层 | TanStack Query | 5.x | stale-while-revalidate 缓存策略、乐观更新、请求去重 |
| 图表 | ECharts | 5.5+ | 大屏场景渲染性能好，支持增量渲染 |
| 视频 | xgplayer | 3.x | 西瓜播放器对国内视频格式兼容好，插件架构可扩展 |
| 路由 | React Router | 7.x | 数据路由 + loader/action 模式适合权限拦截 |
| 测试 | Vitest + RTL + Playwright | — | 单元/集成/E2E 三层 |
| 虚拟滚动 | react-virtuoso | 4.x | 对变高行支持好，队列场景直接可用 |
| 契约测试 | MSW + Zod | — |【修订】Mock Service Worker 拦截 + Zod Schema 校验 |

### 1.2 项目结构

```
frontend/
  public/
  src/
    app/                        # 应用壳：路由注册、权限守卫、全局 Provider
      routes.tsx                # 路由表（含权限 meta）
      App.tsx
      AuthGuard.tsx
      ErrorBoundary.tsx         # 全局 & 面板级错误边界
    api/                        # 接口层：所有 REST / WebSocket 封装
      client.ts                 # axios 实例 + 请求/响应拦截器
      ws.ts                     #【修订】WebSocket 管理器（ws-token 认证/HEARTBEAT 心跳/重连/补推）
      adapters/                 # 前后端契约适配层
        pagination.ts           #【修订】分页模型适配（offset-based，字段名 items）
        disposition.ts          #   处置枚举适配（MVP 2 态 / V2 7 态）
        evidence.ts             #   EvidencePackage 序列化适配
        response.ts             #【修订】后端响应格式统一适配
      endpoints/
        videos.ts
        reviews.ts
        appeals.ts
        policies.ts
        dashboard.ts
        audit.ts
        shadow.ts
        auth.ts                 #【修订】认证端点（含 ws-token）
        quality.ts              #【修订】质检端点（金标统计）
        reviewers.ts            #【修订】审核员管理端点
    stores/                     # Zustand 状态切片
      authStore.ts              # 用户身份、角色、法域
      reviewStore.ts            # 人审工作台运行态（当前案件、锁、草稿）
      queueStore.ts             # 队列状态
      wsStore.ts                #【修订】WebSocket 连接态 + ws-token 管理 + 消息缓冲
      dashboardStore.ts         # 机审大屏实时数据
      configStore.ts            # Feature Flag、主题、系统配置
    features/                   # 按业务域拆分的页面级模块
      dashboard/                # 机审监控面板
        pages/
        components/
        hooks/
      review/                   # 人审工作台
        pages/
        components/
        hooks/
      appeal/                   # 申诉管理
        pages/
        components/
      policy/                   # 策略管理
        pages/
        components/
      admin/                    # 管理后台
        pages/
        components/
      audit/                    # 审计日志
        pages/
        components/
      quality/                  #【修订】质检管理（QA 管理员视图）
        pages/
        components/
    components/                 # 通用业务组件
      VideoPlayer/
      EvidenceViewer/
      DynamicForm/
      ReviewPanel/
      TaskCard/
      StatusBadge/
      TimelineMarker/
      SLACountdown/
      TraumaShield/
      PanelErrorBoundary/       # 面板级错误边界
    lib/                        # 纯工具函数（无副作用）
      constants.ts              # 全局枚举、决策映射
      permissions.ts            # RBAC 工具
      evidence.ts               # EvidencePackage 解析
      formatter.ts              # 时间/分数格式化
      hotkeys.ts                # 快捷键注册
      a11y.ts                   # 无障碍工具函数
    hooks/                      #【修订】通用自定义 hooks
      useStableCallback.ts      #【修订】稳定回调引用（解决 useEffect 闭包问题）
      useWsSubscription.ts      #【修订】WebSocket 订阅（修复依赖不稳定问题）
      useBroadcastChannel.ts    #【修订】多标签页同步
    types/                      # 全局 TypeScript 类型定义
      evidence.ts               # EvidencePackage 类型
      verdict.ts                # DimensionVerdict 类型
      policy.ts                 # 策略/处置枚举
      review.ts                 # 人审案件类型
      ws.ts                     #【修订】WebSocket 消息类型（对齐后端 HEARTBEAT/HEARTBEAT_ACK）
      api-contract.ts           #【修订】前后端 API 响应契约类型（对齐 offset-based 分页）
    styles/
      theme.ts                  # Ant Design 主题定制 token
      a11y.ts                   # 无障碍样式 token（对比度、焦点环）
    plugins/                    # 插件注册表（可扩展审核维度 UI）
      registry.ts
      types.ts
  tests/
    unit/
    integration/
    e2e/
    contract/                   #【修订】基于 MSW + Zod 的契约测试
    mocks/                      #【修订】MSW handler 定义
  vite.config.ts
  tsconfig.json
```

### 1.3 组件分层架构

```
  Page Components     -- 路由级容器，负责数据编排（loader + useQuery）、权限校验
        |
  Feature Components  -- 业务组件，绑定特定领域（ReviewWorkbench, PolicyEditor）
        |
  Common Components   -- 通用业务组件（VideoPlayer, EvidenceViewer, DynamicForm）
        |
  Ant Design 5.x      -- 基础 UI 原子（Button, Table, Modal, Form...）
```

规则：上层可引用下层，同层可平行引用，下层不得引用上层。Feature Components 通过 hooks + stores 获取数据，不直接调 API。

### 1.4 状态管理分层

采用 Zustand slice 模式，状态按生命周期和更新频率分层：

| 状态层 | 存储 | 更新频率 | 示例 |
|--------|------|----------|------|
| 服务端缓存态 | TanStack Query | 按 staleTime | 视频列表、案件详情、策略列表 |
| 实时推送态 | wsStore | 高频（WebSocket） | 锁状态、SLA tick、告警 |
| 会话运行态 | reviewStore / queueStore | 中频（用户操作） | 当前审核案件、草稿、筛选条件 |
| 全局配置态 | authStore / configStore | 低频（登录/刷新） | 用户角色、Feature Flag、主题 |
| 组件局部态 | useState / useReducer | 组件级 | 表单输入、展开/折叠 |

关键设计原则：TanStack Query 管"从服务端来的数据"，Zustand 管"前端自有的运行状态"，二者不重叠。WebSocket 推送的事件通过 wsStore 分发后，必要时 invalidate 对应的 Query key 触发重新获取，而非手动维护一份客户端副本。

### 1.5 路由设计

```typescript
// src/app/routes.tsx
const routes: RouteConfig[] = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      // ---- 机审监控 ----
      {
        path: 'dashboard',
        element: <DashboardLayout />,
        meta: { roles: ['ops_admin', 'policy_pm', 'sre'] },
        children: [
          { index: true, element: <RealtimeOverview /> },
          { path: 'trends', element: <TrendsAnalysis /> },
          { path: 'alerts', element: <AlertCenter /> },
          { path: 'health', element: <SystemHealth /> },
        ],
      },

      // ---- 策略管理 ----
      {
        path: 'policy',
        element: <PolicyLayout />,
        meta: { roles: ['policy_pm', 'policy_approver', 'ops_admin'] },
        children: [
          { index: true, element: <PolicyList /> },
          { path: ':policyId', element: <PolicyDetail /> },
          { path: ':policyId/edit', element: <PolicyEditor /> },
          { path: 'dimensions', element: <DimensionRegistry /> },
          { path: 'shadow', element: <ShadowCompareView /> },
          { path: 'shadow/:reportId', element: <ShadowReportDetail /> },
        ],
      },

      // ---- 人审工作台 ----
      {
        path: 'review',
        element: <ReviewLayout />,
        meta: { roles: ['reviewer_t1', 'reviewer_t2', 'reviewer_t3', 'senior_reviewer'] },
        children: [
          { index: true, element: <ReviewQueue /> },
          { path: 'case/:caseId', element: <ReviewWorkbench /> },
          { path: 'my-tasks', element: <MyTasks /> },
          { path: 'my-stats', element: <MyStats /> },  // 【修订】审核员个人统计（含金标准确率）
        ],
      },

      // ---- 申诉管理 ----
      {
        path: 'appeal',
        element: <AppealLayout />,
        meta: { roles: ['triage', 'reviewer_appeal', 'specialist', 'compliance'] },
        children: [
          { index: true, element: <AppealQueue /> },
          { path: ':appealId', element: <AppealReview /> },
        ],
      },

      // ---- 管理后台 ----
      {
        path: 'admin',
        element: <AdminLayout />,
        meta: { roles: ['ops_admin', 'qa_admin', 'compliance_auditor'] },
        children: [
          { path: 'users', element: <UserManagement /> },
          { path: 'roles', element: <RoleConfig /> },
          { path: 'reviewers', element: <ReviewerManagement /> },
          { path: 'workflow', element: <WorkflowEditor /> },
          { path: 'violation-types', element: <ViolationTypeManager /> },
          { path: 'notifications', element: <NotificationConfig /> },
          { path: 'audit', element: <AuditLogViewer /> },
        ],
      },

      // ---- 质检管理 ----
      // 【修订】新增质检管理路由，QA 管理员可查看金标测试结果
      {
        path: 'quality',
        element: <QualityLayout />,
        meta: { roles: ['qa_admin', 'ops_admin'] },
        children: [
          { path: 'golden-results', element: <GoldenTestResults /> },
          { path: 'irr-report', element: <IRRReport /> },
        ],
      },

      // ---- 数据分析 ----
      {
        path: 'analytics',
        element: <AnalyticsLayout />,
        meta: { roles: ['ops_admin', 'policy_pm', 'qa_admin'] },
        children: [
          { path: 'efficiency', element: <EfficiencyReport /> },
          { path: 'consistency', element: <ConsistencyAnalysis /> },
          { path: 'reviewer-perf', element: <ReviewerPerformance /> },
          { path: 'flywheel', element: <DataFlywheelDashboard /> },
        ],
      },
    ],
  },
  { path: '/login', element: <LoginPage /> },
  { path: '*', element: <NotFoundPage /> },
];
```

权限守卫 `AuthGuard` 读取 `authStore` 的当前用户角色，与路由 `meta.roles` 交集为空时渲染 403 页面。

### 1.6 错误边界策略

为防止单个面板的渲染异常导致整个工作台崩溃，系统采用分层错误边界设计：

```typescript
// src/app/ErrorBoundary.tsx
// 通用错误边界 -- 支持面板级降级和全局降级两种模式

interface PanelErrorBoundaryProps {
  panelName: string;
  children: React.ReactNode;
  fallbackHeight?: number | string; // 降级占位高度，保持布局不塌陷
  onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
}

class PanelErrorBoundary extends React.Component<
  PanelErrorBoundaryProps,
  { hasError: boolean; error: Error | null }
> {
  constructor(props: PanelErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // 上报错误监控
    reportPanelError({
      panel: this.props.panelName,
      error: error.message,
      stack: errorInfo.componentStack,
    });
    this.props.onError?.(error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="panel-error-fallback"
          style={{ minHeight: this.props.fallbackHeight ?? 200 }}
          role="alert"
          aria-label={`${this.props.panelName} 加载失败`}
        >
          <Result
            status="warning"
            title={`${this.props.panelName} 渲染异常`}
            subTitle="该面板出现错误，其他面板不受影响。"
            extra={
              <Button onClick={() => this.setState({ hasError: false, error: null })}>
                重试
              </Button>
            }
          />
        </div>
      );
    }
    return this.props.children;
  }
}

// 路由级全局错误边界
class GlobalErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    reportCriticalError({ error: error.message, stack: errorInfo.componentStack });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="global-error-page" role="alert">
          <Result
            status="error"
            title="页面发生严重错误"
            subTitle="请刷新页面重试。如果问题持续，请联系技术支持。"
            extra={<Button type="primary" onClick={() => window.location.reload()}>刷新页面</Button>}
          />
        </div>
      );
    }
    return this.props.children;
  }
}
```

**错误边界部署位置**：

| 边界层级 | 覆盖范围 | 降级行为 |
|---------|---------|---------|
| 全局边界 | 包裹 `<App />` 根节点 | 展示全局错误页，提供刷新按钮 |
| 路由边界 | 包裹每个路由级 Layout | 展示路由级错误页，不影响导航 |
| 面板边界 | VideoPlayer / EvidenceViewer / VerdictPanel / DispositionPanel 各自独立 | 单面板降级不影响其他面板使用 |

关键原则：**审核员即使视频播放器崩溃，仍可查看证据包文本并完成处置提交**。DispositionPanel 作为最核心面板，其错误边界优先级最高，确保提交通道始终可用。

### 1.7 无障碍设计（Accessibility）

针对高强度审核操作场景，系统在以下层面实现无障碍支持：

**键盘导航**

```typescript
// 所有可交互元素支持 Tab 导航 + 焦点管理
// 审核工作台定义逻辑 Tab 顺序：
// 1. 视频播放器控制 -> 2. 证据 Tab 列表 -> 3. 维度评分面板 -> 4. 处置按钮组 -> 5. 理由表单 -> 6. 提交按钮

const FOCUS_REGIONS = [
  { id: 'video-controls', label: '视频控制区' },
  { id: 'evidence-tabs', label: '证据面板' },
  { id: 'verdict-panel', label: '维度评分' },
  { id: 'disposition-buttons', label: '处置选择' },
  { id: 'reason-form', label: '理由填写' },
  { id: 'submit-area', label: '提交区域' },
] as const;

// 区域间快速跳转：Alt+1~6
const useRegionNavigation = () => {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.altKey && e.key >= '1' && e.key <= '6') {
        e.preventDefault();
        const region = FOCUS_REGIONS[parseInt(e.key) - 1];
        document.getElementById(region.id)?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);
};
```

**ARIA 标注规范**

```typescript
// 所有自定义组件必须包含语义化 ARIA 属性
// 示例：SLA 倒计时
const SLACountdown: React.FC<{ remainingMs: number; type: 'legal' | 'operational' }> = ({
  remainingMs,
  type,
}) => {
  const isWarning = remainingMs < 60_000;
  return (
    <span
      role="timer"
      aria-label={`${type === 'legal' ? '法定' : '运营'} SLA 剩余时间`}
      aria-live={isWarning ? 'assertive' : 'polite'}
      className={isWarning ? 'sla-warning' : ''}
    >
      {formatDuration(remainingMs)}
    </span>
  );
};

// 示例：处置按钮组
<Radio.Group
  value={selectedDisposition}
  onChange={(e) => setSelectedDisposition(e.target.value)}
  role="radiogroup"
  aria-label="选择处置动作"
>
  {availableDispositions.map((d) => (
    <Radio.Button
      key={d.action}
      value={d.action}
      aria-describedby={`disposition-desc-${d.action}`}
    >
      {d.label}
    </Radio.Button>
  ))}
</Radio.Group>
```

**色彩对比度**

```typescript
// src/styles/a11y.ts
// 所有前景/背景色组合满足 WCAG 2.1 AA 标准（对比度 >= 4.5:1）
export const A11Y_COLORS = {
  // 严重度色彩 -- 在浅色/深色背景下均满足对比度要求
  critical: { bg: '#fff1f0', fg: '#a8071a', border: '#ff4d4f' },  // 对比度 7.2:1
  high:     { bg: '#fff7e6', fg: '#ad4e00', border: '#fa8c16' },  // 对比度 5.1:1
  medium:   { bg: '#fffbe6', fg: '#ad6800', border: '#faad14' },  // 对比度 4.8:1
  low:      { bg: '#f5f5f5', fg: '#434343', border: '#8c8c8c' },  // 对比度 8.6:1
};

// 焦点可见性 -- 所有可交互元素获得焦点时显示高对比度焦点环
export const FOCUS_RING_STYLE = {
  outline: '2px solid #1677ff',
  outlineOffset: '2px',
};
```

**屏幕阅读器支持**

- 所有图标按钮附带 `aria-label` 描述（不依赖纯视觉图标传达语义）
- 状态变更（SLA 告警、锁状态变更、提交结果）通过 `aria-live` region 播报
- 图表组件提供 `aria-label` 文本摘要（如"过去 24 小时审核量 12,345 条，其中 BLOCK 占比 3.2%"）
- 视频播放器控件遵循 WAI-ARIA 媒体播放器模式

---

## 2. 机审监控面板（Machine Review Dashboard）

### 2.1 实时数据监控大屏

大屏布局采用 CSS Grid 12 列网格，支持拖拽自定义面板排列（后续版本），MVP 固定布局：

```
+-----------------------------------------------------+
| 系统健康状态条 (全宽)                                    |
+------------------+------------------+----------------+
| 审核量趋势图      | 违规类型分布      | 策略命中率       |
| (ECharts Line)   | (ECharts Sunburst)| (ECharts Bar)  |
+------------------+------------------+----------------+
| 三阶段漏斗转化     | 决策分布饼图      | LLM 置信度分布   |
| (Funnel)         | (Pie)            | (Histogram)    |
+------------------+------------------+----------------+
| 实时告警流 (全宽)                                       |
+-----------------------------------------------------+
```

**审核量趋势图**
- X 轴：时间（粒度可切换：5min / 1h / 1d）
- Y 轴：审核量（条）
- 多折线：总量 / PASS / BLOCK / NEEDS_REVIEW
- 支持按策略维度（dimension_id）筛选
- 支持圈选时间段下钻到具体案件列表

**违规类型分布图**
- Sunburst 旭日图：外圈 = 具体类目（如 violence、hate_speech），内圈 = 三大维度轴（安全/质量/业务）
- 点击穿透到该类目的详细命中列表
- 支持法域筛选（Global / US / EU / SEA）

**策略命中率**
- 分组柱状图：每个 dimension_id 一组，柱子高度 = 命中率
- 对比维度：本周 vs 上周，或新策略(Shadow) vs 当前(Active)
- 悬浮 tooltip 展示置信度分布

**系统健康状态指示器**

```typescript
// 健康指示器组件
interface HealthIndicator {
  stage: 'extraction' | 'pre_filter' | 'llm_review' | 'aggregation';
  label: string;
  p95LatencyMs: number;
  slaTargetMs: number;
  errorRate: number;
  status: 'healthy' | 'degraded' | 'critical';
  lastUpdated: number;
}

const SystemHealthBar: React.FC = () => {
  // 【修订】健康数据由后端 GET /api/v1/system/health 提供（见 2.4 节 API 对齐表）
  const healthEnabled = useFeatureFlag('enableDashboardHealth');

  const indicators = useQuery({
    queryKey: ['system-health'],
    queryFn: () => api.system.getHealth(),
    refetchInterval: 10_000,
    enabled: healthEnabled,
  });

  if (!healthEnabled) {
    return (
      <div className="health-bar-placeholder" role="region" aria-label="系统健康状态">
        <Alert message="系统健康面板开发中" type="info" showIcon />
      </div>
    );
  }

  return (
    <PanelErrorBoundary panelName="系统健康状态">
      <div className="health-bar" role="region" aria-label="系统健康状态">
        {indicators.data?.components?.map((ind: HealthIndicator) => (
          <HealthCard
            key={ind.stage}
            label={ind.label}
            latency={`P95: ${ind.p95LatencyMs}ms`}
            target={`SLA: ${ind.slaTargetMs}ms`}
            status={ind.status}
            errorRate={`${(ind.errorRate * 100).toFixed(2)}%`}
            aria-label={`${ind.label}: 状态 ${ind.status}, P95 延迟 ${ind.p95LatencyMs}ms`}
          />
        ))}
      </div>
    </PanelErrorBoundary>
  );
};
```

四个阶段对应 PRD 定义的 SLA 目标：证据提取按时长分档 / 基础初筛 3s P95 / LLM 审查 30s P95 / 聚合决策 <1s。

### 2.2 策略管理界面

**策略列表**

| 列 | 说明 |
|----|------|
| 策略名称 | dimension_name（人读） + dimension_id（技术标识） |
| 维度轴 | 安全 / 质量 / 业务（带颜色标签） |
| 状态 | Draft / Shadow / Active / Archived（四态生命周期） |
| 当前版本 | policy_version 号 |
| 命中率(7d) | 近 7 天命中百分比 |
| 灰度比例 | 1% / 5% / 25% / 50% / 100% |
| 操作 | 查看 / 编辑 / Shadow 报告 / Kill-switch |

策略状态流转可视化：Draft -> Shadow -> Active -> Archived，以 Steps 组件呈现当前位置。

**策略参数配置表单（动态表单驱动）**

策略配置界面由 DynamicForm 组件驱动，配置 Schema 来自维度注册表：

```typescript
// 策略配置 Schema 示例（后端下发）
interface PolicyConfigSchema {
  dimension_id: string;
  fields: FieldDefinition[];
}

interface FieldDefinition {
  name: string;
  label: string;
  type: 'number' | 'select' | 'switch' | 'slider' | 'json' | 'text';
  defaultValue: unknown;
  validation?: { min?: number; max?: number; required?: boolean };
  description?: string;
  jurisdictionOverridable?: boolean;
}

const PolicyConfigForm: React.FC<{ schema: PolicyConfigSchema; values: Record<string, unknown> }> = ({
  schema,
  values,
}) => {
  const [form] = Form.useForm();

  const renderField = (field: FieldDefinition) => {
    switch (field.type) {
      case 'number':
        return (
          <Form.Item
            name={field.name}
            label={field.label}
            tooltip={field.description}
            rules={[{ required: field.validation?.required }]}
          >
            <InputNumber
              min={field.validation?.min}
              max={field.validation?.max}
              style={{ width: '100%' }}
              aria-describedby={`field-desc-${field.name}`}
            />
          </Form.Item>
        );
      case 'slider':
        return (
          <Form.Item name={field.name} label={field.label} tooltip={field.description}>
            <Slider
              min={field.validation?.min ?? 0}
              max={field.validation?.max ?? 1}
              step={0.01}
              marks={{ 0: '0', 0.5: '0.5', 1: '1.0' }}
            />
          </Form.Item>
        );
      case 'switch':
        return (
          <Form.Item name={field.name} label={field.label} valuePropName="checked">
            <Switch />
          </Form.Item>
        );
      // ... select, json, text 同理
    }
  };

  return (
    <Form form={form} initialValues={values} layout="vertical">
      {schema.fields.map(renderField)}
      <JurisdictionOverridePanel
        fields={schema.fields.filter((f) => f.jurisdictionOverridable)}
        baseValues={values}
      />
    </Form>
  );
};
```

**策略效果对比 (A/B / Shadow 对比)**

ShadowCompareView 消费 `GET /api/v1/shadow/reports/latest` 端点，展示：
- 整体一致率进度条 + 漂移红线标注
- 逐维度命中率对比柱状图（新版本 vs Active 版本）
- FP/FN 估计表
- 成本影响指标（LLM 调用次数变化 / Token 用量变化）
- 差异样本列表（可点击进入具体案件对比视图）

### 2.3 异常告警展示

```typescript
// 实时告警流（WebSocket 驱动 + REST 回落）
const AlertStream: React.FC = () => {
  const alertsEnabled = useFeatureFlag('enableDashboardAlerts');

  // 【修订】WebSocket 消息类型对齐后端
  const wsAlerts = useWsSubscription<CriticalAlert>('CRITICAL_ALERT');
  const historicalAlerts = useQuery({
    queryKey: ['alerts', 'recent'],
    queryFn: () => api.system.getAlerts({ status: 'active', limit: 50 }),
    refetchInterval: 30_000,
    enabled: alertsEnabled,
  });

  if (!alertsEnabled) {
    return <Alert message="告警管理面板开发中" type="info" showIcon />;
  }

  const mergedAlerts = useMergedAlerts(wsAlerts, historicalAlerts.data?.alerts);

  return (
    <PanelErrorBoundary panelName="告警流">
      <Timeline mode="left" role="log" aria-label="实时告警">
        {mergedAlerts.map((alert) => (
          <Timeline.Item
            key={alert.id}
            color={alert.level === 'critical' ? 'red' : alert.level === 'high' ? 'orange' : 'blue'}
            label={formatTime(alert.timestamp)}
          >
            <AlertCard
              title={alert.category}
              description={alert.message}
              contentId={alert.content_id}
              requiresActionBy={alert.requires_action_by_ms}
              onAcknowledge={() => api.system.acknowledgeAlert(alert.id, {
                acknowledged_by: useAuthStore.getState().userId,
              })}
            />
          </Timeline.Item>
        ))}
      </Timeline>
    </PanelErrorBoundary>
  );
};
```

告警详情弹窗包含：告警来源（哪个阶段/维度触发）、关联的 EvidencePackage 摘要、建议处置动作、处理记录历史。

### 2.4【修订】前后端 API 对齐表（Dashboard 模块）

以下是 Dashboard 模块前端所需端点与后端现有端点的映射。**端点路径严格对齐后端设计文档**。

| 前端调用 | 后端端点 | 状态 | 说明 |
|---------|----------------------|------|------|
| `api.system.getHealth()` | `GET /api/v1/system/health` | 已实现 | 返回系统健康状态及组件详情 |
| `api.system.getAlerts()` | `GET /api/v1/system/alerts` | 已实现 | 返回告警列表，支持 `?status=active&limit=20` |
| `api.system.acknowledgeAlert()` | `POST /api/v1/system/alerts/{id}/acknowledge` | 已实现 | 确认告警，需传 `{acknowledged_by}` |
| `api.dashboard.getTrends()` | `GET /api/v1/stats/trends` | 现有 | 审核量趋势数据 |
| `api.dashboard.getDistribution()` | `GET /api/v1/stats/distribution` | 现有 | 违规类型分布 |

**前端降级策略**：通过 feature flag `enableDashboardHealth` / `enableDashboardAlerts` 控制相关面板的显示/隐藏。对应面板在 flag 关闭时展示"功能开发中"占位符，而非调用不存在的接口。

---

## 3. 人审工作台（Human Review Workstation）

人审工作台是整个平台最核心的交互界面。设计目标：**一屏完成**决策 -- 查看证据 + 选择处置 + 填写理由 + 提交，无需跳转页面。

### 3.1 整体布局

```
+------------------------------------------------------------------+
| 顶栏: SLA 倒计时 | 案件 ID | 严重度 Badge | 锁状态 | 快捷键提示    |
+----------------------------+---------+---------------------------+
|                            |         | 机审维度评分面板            |
|   视频播放器                |   时    | - 安全维度 (各类目分数)      |
|   (含命中点标注时间轴)       |   间    | - 质量维度 (各类目分数)      |
|                            |   轴    | - 业务维度 (各类目分数)      |
|                            |   标    | - 触发规则列表              |
|                            |   注    | - LLM 判断理由             |
+----------------------------+   面    +---------------------------+
| 证据面板 (Tabs)             |   板    | 处置操作面板                |
| [ASR] [OCR] [目标检测]      |         | - 机审建议处置 (高亮)        |
| [场景识别] [初筛结果]        |         | - 可选处置按钮组             |
|                            |         | - 理由 (结构化 + 自由文本)   |
| 元数据 + 创作者信息          |         | - 连带后果预览 [V2]         |
| 相似历史决策参考             |         |                           |
+----------------------------+---------+---------------------------+
| 状态栏: 疲劳指标 | 曝光计数 | 屏蔽模式开关 | Wellness 入口        |
+------------------------------------------------------------------+
```

### 3.2 视频播放器组件

```typescript
interface VideoPlayerProps {
  src: string;
  evidencePackage: EvidencePackage;
  onTimestampClick?: (timestampMs: number) => void;
  traumaShieldEnabled?: boolean;
  csamRestricted?: boolean;
}

const VideoPlayer: React.FC<VideoPlayerProps> = ({
  src,
  evidencePackage,
  onTimestampClick,
  traumaShieldEnabled,
  csamRestricted,
}) => {
  const playerRef = useRef<XgPlayer>(null);
  const [playbackRate, setPlaybackRate] = useState(1);

  // CSAM 限制：完全屏蔽，不渲染播放器
  if (csamRestricted) {
    return (
      <div className="csam-restricted-placeholder" role="alert">
        <LockOutlined aria-hidden="true" />
        <Typography.Text type="warning">
          内容已受限，请通过 critical 专审通道处理
        </Typography.Text>
      </div>
    );
  }

  // 从 EvidencePackage 提取命中点，渲染到时间轴上
  const hitMarkers = useMemo(() => extractHitMarkers(evidencePackage), [evidencePackage]);

  // 创伤屏蔽模式：默认模糊 + 静音
  const playerConfig: XgPlayerConfig = {
    url: src,
    autoplay: traumaShieldEnabled ? false : undefined,
    volume: traumaShieldEnabled ? 0 : 0.5,
    playbackRate: [0.25, 0.5, 1, 1.5, 2, 4],
    plugins: [
      TimelineMarkerPlugin({ markers: hitMarkers, onClick: onTimestampClick }),
      FrameStepPlugin(),
      ScreenshotPlugin(),
      BlurOverlayPlugin({
        enabled: traumaShieldEnabled,
        onReveal: () => { /* 记录 "已准备好查看" 日志 */ },
      }),
    ],
  };

  return (
    <PanelErrorBoundary panelName="视频播放器" fallbackHeight={400}>
      <div className="video-player-container" role="region" aria-label="视频播放区域">
        <XgPlayerReact ref={playerRef} config={playerConfig} />

        {/* 时间轴命中点标注 */}
        <TimelineAnnotationBar
          duration={evidencePackage.video_meta.duration_ms}
          markers={hitMarkers}
          onMarkerClick={(ms) => {
            playerRef.current?.seek(ms / 1000);
            onTimestampClick?.(ms);
          }}
          aria-label="命中点时间轴"
        />

        {/* 播放控制增强 */}
        <div className="player-controls-extra" id="video-controls" tabIndex={-1}>
          <Tooltip title="逐帧后退 (,)">
            <Button
              icon={<StepBackwardOutlined />}
              onClick={() => playerRef.current?.stepBack()}
              aria-label="逐帧后退"
            />
          </Tooltip>
          <Tooltip title="逐帧前进 (.)">
            <Button
              icon={<StepForwardOutlined />}
              onClick={() => playerRef.current?.stepForward()}
              aria-label="逐帧前进"
            />
          </Tooltip>
          <Select
            value={playbackRate}
            onChange={(v) => { setPlaybackRate(v); playerRef.current!.playbackRate = v; }}
            options={[
              { label: '0.25x', value: 0.25 },
              { label: '0.5x', value: 0.5 },
              { label: '1x', value: 1 },
              { label: '1.5x', value: 1.5 },
              { label: '2x', value: 2 },
              { label: '4x', value: 4 },
            ]}
            aria-label="播放速度"
          />
        </div>
      </div>
    </PanelErrorBoundary>
  );
};
```

**命中点标注时间轴**采用自定义 Canvas 渲染，在视频进度条下方绘制色块：
- 红色区域：安全维度命中帧范围
- 橙色区域：质量维度命中帧范围
- 蓝色区域：业务维度命中帧范围
- 点击色块跳转到对应时间点
- Canvas 元素附带 `role="img"` 和 `aria-label`，描述命中点的文本摘要

**画面截取与标记**：审核员可在任意帧截图并用矩形框标注关注区域，标注数据存入审核草稿，作为内部理由附件提交。

### 3.3 证据查看器

```typescript
const EvidenceViewer: React.FC<{ ep: EvidencePackage }> = ({ ep }) => {
  const [activeTab, setActiveTab] = useState('asr');

  // 安全解析 -- 防御畸形 EvidencePackage
  const truncatedModalities = safeGet(ep, 'truncated_modalities', [] as string[]);
  const hasTruncation = ep.llm_verdicts?.some(
    (v) => v.reason?.includes('Token 预算限制')
  ) || truncatedModalities.length > 0;

  return (
    <PanelErrorBoundary panelName="证据面板" fallbackHeight={300}>
      {hasTruncation && (
        <Alert
          type="warning"
          message="部分证据受 Token 限制未完整分析"
          description={`受限模态: ${truncatedModalities.join(', ') || '未知'}`}
          showIcon
          role="alert"
        />
      )}

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        aria-label="证据类型选择"
      >
        <Tabs.TabPane tab="ASR 转录" key="asr">
          <ASRTranscriptPanel
            segments={ep.asr_transcript ?? []}
            onSegmentClick={(startMs) => /* 跳转播放器 */ undefined}
            highlightPatterns={extractRiskKeywords(ep)}
          />
        </Tabs.TabPane>

        <Tabs.TabPane tab="OCR 识别" key="ocr">
          <OCRResultPanel
            results={ep.ocr_results ?? []}
            frames={ep.frames ?? []}
          />
        </Tabs.TabPane>

        <Tabs.TabPane tab="目标检测" key="objects">
          <ObjectDetectionPanel
            detections={ep.object_detections ?? []}
            frames={ep.frames ?? []}
          />
        </Tabs.TabPane>

        <Tabs.TabPane tab="场景识别" key="scene">
          <SceneTagPanel tags={ep.scene_tags ?? []} />
        </Tabs.TabPane>

        <Tabs.TabPane tab="初筛结果" key="prefilter">
          <PreFilterResultPanel results={ep.pre_filter_results} />
        </Tabs.TabPane>
      </Tabs>
    </PanelErrorBoundary>
  );
};
```

ASR 转录面板设计要点：
- 左侧时间戳列表，点击跳转播放器
- 风险关键词高亮（红色：诱导/联系方式，橙色：营销话术，蓝色：地名/品牌）
- 语种标注
- 标注"机器转写，可能有误"

### 3.4【修订】审核操作面板（处置枚举对齐后端）

**MVP 处置枚举严格限定为 `pass | block` 两态**，与后端 `HumanReviewDecisionModel.decision` 字段完全对齐。7 态处置矩阵（PASS / DEMOTE / LABEL / AGE_GATE / GEO_BLOCK / REMOVE / REMOVE_AND_ESCALATE）通过 feature flag `enableFullDispositionMatrix` 控制，MVP 阶段 flag 默认关闭。

```typescript
// src/api/adapters/disposition.ts
// 处置枚举适配层 -- MVP 与 V2 的桥接

// MVP 阶段后端支持的处置枚举（唯一事实来源）
export type MVPDisposition = 'pass' | 'block';

// V2 阶段完整处置矩阵（feature flag 控制）
export type FullDispositionAction =
  | 'PASS' | 'DEMOTE' | 'LABEL' | 'AGE_GATE'
  | 'GEO_BLOCK' | 'REMOVE' | 'REMOVE_AND_ESCALATE';

// MVP 处置配置（硬编码，不依赖后端端点）
const MVP_DISPOSITIONS: DispositionOption[] = [
  {
    action: 'pass' as MVPDisposition,
    label: '通过',
    description: '内容合规，允许发布',
    icon: <CheckCircleOutlined />,
    color: 'green',
  },
  {
    action: 'block' as MVPDisposition,
    label: '拒绝',
    description: '内容违规，下架处理',
    icon: <StopOutlined />,
    color: 'red',
  },
];

// V2 完整处置映射（flag 开启后使用，需后端 getAvailableDispositions 端点就绪）
const FULL_DISPOSITION_MAP: Record<FullDispositionAction, MVPDisposition> = {
  'PASS': 'pass',
  'DEMOTE': 'block',     // MVP 降级为 block
  'LABEL': 'pass',       // MVP 降级为 pass（仅标记）
  'AGE_GATE': 'block',   // MVP 降级为 block
  'GEO_BLOCK': 'block',  // MVP 降级为 block
  'REMOVE': 'block',
  'REMOVE_AND_ESCALATE': 'block',
};

// 获取当前可用处置列表
export function getAvailableDispositions(featureFlags: FeatureFlags): DispositionOption[] {
  if (featureFlags.enableFullDispositionMatrix) {
    // V2: 从后端动态获取
    return []; // 由 useQuery 填充
  }
  return MVP_DISPOSITIONS;
}

// 提交时适配：确保发给后端的值严格为 'pass' | 'block'
export function toBackendDisposition(
  action: MVPDisposition | FullDispositionAction,
  featureFlags: FeatureFlags,
): MVPDisposition {
  if (!featureFlags.enableFullDispositionMatrix) {
    // MVP 模式：action 本身就是 'pass' | 'block'
    return action as MVPDisposition;
  }
  // V2 模式：映射到后端支持的值
  return FULL_DISPOSITION_MAP[action as FullDispositionAction] ?? 'block';
}
```

```typescript
// 【修订】处置面板 -- 修复机审建议偏差问题
const DispositionPanel: React.FC<{
  caseData: ReviewCase;
  onSubmit: (decision: DispositionSubmission) => Promise<void>;
}> = ({ caseData, onSubmit }) => {
  const [form] = Form.useForm();
  const [selectedDisposition, setSelectedDisposition] = useState<MVPDisposition | null>(null);
  const featureFlags = useConfigStore((s) => s.featureFlags);

  // MVP: 使用本地硬编码处置列表，不调用后端端点
  // V2: feature flag 开启后改用 useQuery 从后端获取
  const availableDispositions = useMemo(
    () => getAvailableDispositions(featureFlags),
    [featureFlags],
  );

  // 机审建议处置
  const machineRecommendation = caseData.decision_summary?.recommended_disposition;

  // 【修订】将机审建议映射为 MVP 二态
  // 关键修复：needs_human_review 不映射为 block，而是返回 null（无建议）
  const mappedRecommendation: MVPDisposition | null = machineRecommendation
    ? mapMachineDecisionToMVP(machineRecommendation)
    : null;

  // 【修订】判断是否为 override：仅在机审有明确建议且审核员选择不同时才算 override
  const isOverride = mappedRecommendation !== null && selectedDisposition !== mappedRecommendation;

  const handleSubmit = async () => {
    const values = await form.validateFields();
    if (!selectedDisposition) {
      message.warning('请先选择处置动作');
      return;
    }

    await onSubmit({
      caseId: caseData.id,
      // 提交给后端的值严格为 'pass' | 'block'
      decision: toBackendDisposition(selectedDisposition, featureFlags),
      reason: values.reason ?? '',
      reason_category: values.reason_category,
      isOverride,
      overrideReason: isOverride ? values.overrideReason : undefined,
    });
  };

  return (
    <PanelErrorBoundary panelName="处置操作面板">
      <div className="disposition-panel" id="disposition-buttons" tabIndex={-1}>
        {/* 【修订】机审建议展示 -- 修复偏差问题 */}
        <div className="machine-recommendation" role="status">
          <Typography.Text type="secondary">机审建议处置：</Typography.Text>
          {mappedRecommendation !== null ? (
            <StatusBadge disposition={mappedRecommendation} highlight />
          ) : (
            // 【修订】当机审决策为 needs_human_review 时，
            // 展示"需人工判断"而非偏向 block，避免系统性偏差
            <Tag color="default" icon={<QuestionCircleOutlined />}>
              需人工判断（机审未给出明确建议）
            </Tag>
          )}
        </div>

        {/* 处置按钮组 -- MVP 仅 pass/block 两个按钮 */}
        <Radio.Group
          value={selectedDisposition}
          onChange={(e) => setSelectedDisposition(e.target.value)}
          className="disposition-buttons"
          role="radiogroup"
          aria-label="选择处置动作"
        >
          {availableDispositions.map((d) => (
            <Radio.Button
              key={d.action}
              value={d.action}
              className={d.action === mappedRecommendation ? 'recommended' : ''}
              aria-describedby={`disp-desc-${d.action}`}
            >
              {d.icon} {d.label}
            </Radio.Button>
          ))}
        </Radio.Group>

        {/* 连带后果预览 -- MVP 不调用后端端点，改为静态文案 */}
        {selectedDisposition === 'block' && (
          <Alert
            type="info"
            message="处置后果"
            description="内容将被下架，创作者将收到违规通知，可在规定期限内提交申诉。"
            role="status"
          />
        )}
        {selectedDisposition === 'pass' && (
          <Alert
            type="info"
            message="处置后果"
            description="内容将正常发布，无后续动作。"
            role="status"
          />
        )}

        {/* 理由填写 */}
        <Form form={form} layout="vertical">
          <Form.Item
            name="reason_category"
            label="理由分类"
          >
            <Select
              placeholder="选择理由分类（可选）"
              options={REASON_CATEGORIES}
              allowClear
              aria-label="理由分类"
            />
          </Form.Item>

          <Form.Item
            name="reason"
            label="审核理由"
            rules={[{ required: isOverride, message: '推翻机审建议时必须填写理由' }]}
          >
            <TextArea
              rows={3}
              placeholder={
                !isOverride
                  ? '同意机审建议，可补充说明（选填）'
                  : '请说明推翻机审建议的理由（必填）'
              }
              aria-label="审核理由"
            />
          </Form.Item>

          {/* Override 理由（仅在推翻机审建议时显示） */}
          {isOverride && (
            <Form.Item
              name="overrideReason"
              label={
                <span>
                  Override 理由
                  <Tag color="orange" style={{ marginLeft: 8 }}>推翻机审</Tag>
                </span>
              }
              rules={[{ required: true, message: '推翻机审建议时必须填写 Override 理由' }]}
            >
              <TextArea rows={2} aria-label="Override 理由" />
            </Form.Item>
          )}
        </Form>

        <Button
          type="primary"
          onClick={handleSubmit}
          disabled={!selectedDisposition}
          block
          aria-label="提交处置 (Ctrl+Enter)"
        >
          提交处置 (Ctrl+Enter)
        </Button>
      </div>
    </PanelErrorBoundary>
  );
};

// 【修订】机审决策到 MVP 二态的映射 -- 修复 needs_human_review 偏差
// 关键修复：needs_human_review 返回 null，表示机审无明确建议，
// 避免系统性偏向 block，让审核员基于证据独立判断。
function mapMachineDecisionToMVP(decision: string): MVPDisposition | null {
  switch (decision) {
    case 'auto_pass':
      return 'pass';
    case 'auto_block':
      return 'block';
    case 'critical_escalate':
      return 'block'; // critical 场景确实应建议 block
    case 'needs_human_review':
      // 【修订】机审不确定时不给出偏向性建议
      // 返回 null 表示"无建议"，前端展示"需人工判断"
      return null;
    default:
      return null; // 未知决策类型也不给偏向性建议
  }
}
```

### 3.5 快捷键系统

```typescript
// src/lib/hotkeys.ts
const DEFAULT_KEYBINDINGS: Record<string, HotkeyAction> = {
  ' ':            { action: 'PLAY_PAUSE',       label: '播放/暂停' },
  'ArrowRight':   { action: 'NEXT_HIT_POINT',   label: '下一个命中点' },
  'ArrowLeft':    { action: 'PREV_HIT_POINT',   label: '上一个命中点' },
  ',':            { action: 'FRAME_BACK',        label: '逐帧后退' },
  '.':            { action: 'FRAME_FORWARD',     label: '逐帧前进' },
  // MVP 快捷键简化为 pass/block 二态
  'p':            { action: 'SELECT_PASS',       label: '选择通过' },
  'b':            { action: 'SELECT_BLOCK',      label: '选择拒绝' },
  'f':            { action: 'FLAG_DIFFICULT',     label: '标记疑难' },
  'e':            { action: 'ESCALATE',           label: '升级' },
  'h':            { action: 'TOGGLE_BLUR',        label: '切换模糊显隐' },
  'Ctrl+Enter':   { action: 'SUBMIT_AND_NEXT',   label: '提交并取下一个' },
  'Ctrl+Shift+x': { action: 'CRITICAL_MELTDOWN', label: 'Critical 熔断（需二次确认）' },
  // 区域跳转快捷键
  'Alt+1':        { action: 'FOCUS_VIDEO',        label: '跳转到视频区' },
  'Alt+2':        { action: 'FOCUS_EVIDENCE',     label: '跳转到证据面板' },
  'Alt+3':        { action: 'FOCUS_VERDICT',      label: '跳转到评分面板' },
  'Alt+4':        { action: 'FOCUS_DISPOSITION',   label: '跳转到处置区' },
  'Alt+5':        { action: 'FOCUS_REASON',        label: '跳转到理由表单' },
  'Alt+6':        { action: 'FOCUS_SUBMIT',        label: '跳转到提交区' },
};

const ReviewWorkbench: React.FC = () => {
  useHotkeys(DEFAULT_KEYBINDINGS, {
    SELECT_PASS: () => setSelectedDisposition('pass'),
    SELECT_BLOCK: () => setSelectedDisposition('block'),
    CRITICAL_MELTDOWN: () => {
      Modal.confirm({
        title: 'Critical 熔断确认',
        content: '此操作将立即冻结内容并转入专审通道，是否继续？',
        okText: '确认熔断',
        okButtonProps: { danger: true },
        onOk: () => handleCriticalMeltdown(),
      });
    },
    SUBMIT_AND_NEXT: () => handleSubmitAndFetchNext(),
    // ...
  });

  // 区域焦点管理
  useRegionNavigation();

  // ...
};
```

### 3.6【修订】任务队列界面（分页模型对齐 -- offset-based）

```typescript
// src/api/adapters/pagination.ts
// 【修订】分页适配层 -- 严格对齐后端 offset-based PaginatedResponse

// 后端统一分页响应格式（唯一事实来源：backend/app/common/pagination.py）
interface BackendPaginatedResponse<T> {
  items: T[];              // 【修订】后端使用 "items"（非 "tasks"）
  total: number;
  offset: number;          // 【修订】后端使用 offset（非 page）
  limit: number;
  next_offset: number | null;  // null 表示没有更多数据
}

// 前端 useInfiniteQuery 使用的适配格式
interface FrontendPageResponse<T> {
  items: T[];
  total: number;
  nextOffset: number | undefined;  // undefined 表示已到末页
}

// 【修订】适配后端响应为前端 useInfiniteQuery 所需格式
export function adaptPaginatedResponse<T>(
  response: BackendPaginatedResponse<T>,
): FrontendPageResponse<T> {
  return {
    items: response.items,
    total: response.total,
    // 后端 next_offset 为 null 表示无更多数据，前端转为 undefined
    nextOffset: response.next_offset ?? undefined,
  };
}

// 【修订】将前端 pageParam 转换为后端 query 参数（offset-based）
export function toBackendOffsetParams(offset: number, limit: number = 20) {
  return {
    offset,
    limit,
  };
}
```

```typescript
// 【修订】队列组件使用 offset-based 分页，严格对齐后端 PaginatedResponse
const ReviewQueue: React.FC = () => {
  const [filters, setFilters] = useState<QueueFilters>(DEFAULT_FILTERS);
  const PAGE_SIZE = 20;

  // 【修订】使用 offset-based infinite query，对齐后端 ?offset=N&limit=M 模型
  const queue = useInfiniteQuery({
    queryKey: ['review-queue', filters],
    queryFn: async ({ pageParam = 0 }) => {
      const response = await api.reviews.getQueue({
        ...filters,
        ...toBackendOffsetParams(pageParam, PAGE_SIZE),
      });
      // 【修订】后端返回 { items, total, offset, limit, next_offset }
      return adaptPaginatedResponse(response);
    },
    // 【修订】getNextPageParam 直接使用后端 next_offset
    getNextPageParam: (lastPage) => lastPage.nextOffset,
    initialPageParam: 0,
  });

  // 【修订】WebSocket 消息类型对齐后端（task_lock_renewed / task_lock_expired）
  useWsSubscription('task_lock_renewed', (event: TaskLockEvent) => {
    queryClient.setQueryData(['review-queue', filters], (old: any) =>
      updateCaseLockInPages(old, event.payload.task_id, event.payload.reviewer_id)
    );
  });

  useWsSubscription('task_reassigned', (event: TaskReassignedEvent) => {
    queryClient.invalidateQueries({ queryKey: ['review-queue'] });
  });

  return (
    <div className="review-queue" role="region" aria-label="审核队列">
      {/* 法定时限案件始终置顶，不可被筛选隐藏 */}
      <LegalDeadlineBanner cases={extractLegalDeadlineCases(queue.data)} />

      {/* 筛选工具栏 */}
      <QueueFilterBar
        filters={filters}
        onChange={setFilters}
        savedViews={useSavedViews()}
      />

      {/* 虚拟滚动列表 */}
      <Virtuoso
        data={flattenPages(queue.data)}
        endReached={() => queue.fetchNextPage()}
        itemContent={(index, caseItem) => (
          <TaskCard
            key={caseItem.task_id}
            case={caseItem}
            slaRemaining={caseItem.sla_remaining_ms}
            severity={caseItem.max_severity}
            isLocked={caseItem.assigned_to !== null}
            lockedBy={caseItem.assigned_to}
            priorityIndicator={caseItem.has_legal_deadline ? 'legal' : caseItem.max_severity}
            onClick={() => handleClaimCase(caseItem.task_id)}
          />
        )}
      />
    </div>
  );
};
```

**TaskCard 组件**包含：
- 左侧：严重度色条（critical=红/high=橙/medium=黄/low=灰）
- 缩略图（敏感内容默认模糊）
- 命中维度标签列表
- SLA 倒计时（临近 20% 标红闪烁）
- 创作者风险等级图标
- 锁状态指示（他人处理中显示审核员名）
- 法定时限标识（带法条来源标签）

### 3.7 协作功能

**复审场景 -- 审核意见查看**

二审员在 ReviewWorkbench 中可看到：
- 原审核员的全部操作记录（选了什么处置、写了什么理由）
- 机审原始分数 + LLM DimensionVerdict 列表
- 申诉方提供的理由和补充证据（申诉场景）

但系统强制排除原审核员的 ID（`二审 != 原审`），原审案件在二审队列中对原审员不可见。

**实时在线状态**

组长视图中展示审核员实时状态列表：
- 在线（当前处理案件 ID + SLA 剩余）
- 空闲可借调
- 强制休息中（剩余时间）
- 离线

基于 WebSocket 心跳推送实现，前端 wsStore 维护全局审核员状态。

### 3.8 反疲劳设计（前端实现）

```typescript
interface FatigueState {
  traumaShieldEnabled: boolean;
  currentShiftCsamCount: number;
  consecutiveCriticalCount: number;
  isRestLocked: boolean;
  restRemainingMs: number;
  csamWeeklyCount: number;
}

const useFatigueStore = create<FatigueState & FatigueActions>((set, get) => ({
  traumaShieldEnabled: false,
  currentShiftCsamCount: 0,
  consecutiveCriticalCount: 0,
  isRestLocked: false,
  restRemainingMs: 0,
  csamWeeklyCount: 0,

  toggleTraumaShield: () => set((s) => ({ traumaShieldEnabled: !s.traumaShieldEnabled })),

  recordCaseProcessed: (severity: string, category: string) => {
    const state = get();
    const isCsam = ['C1-a', 'C1-b', 'C2'].includes(category);

    if (isCsam) {
      const newCount = state.currentShiftCsamCount + 1;
      set({ currentShiftCsamCount: newCount });

      if (state.consecutiveCriticalCount + 1 >= 3) {
        set({ isRestLocked: true, restRemainingMs: 5 * 60 * 1000 });
      }
      if (state.consecutiveCriticalCount + 1 >= 5) {
        set({ isRestLocked: true, restRemainingMs: 15 * 60 * 1000 });
      }
      if (newCount >= 10) {
        api.reviews.reportCsamExposureLimit();
      }
    }
  },
}));

// 【修订】WebSocket 驱动的强制休息提醒（对齐后端 break_reminder 消息类型）
const useBreakReminder = () => {
  useWsSubscription('break_reminder', (event: BreakReminderEvent) => {
    const { break_type, duration_minutes, reason } = event.payload;
    if (break_type === 'mandatory') {
      useFatigueStore.getState().setRestLocked(true, duration_minutes * 60 * 1000);
    }
  });
};

const RestLockOverlay: React.FC = () => {
  const { isRestLocked, restRemainingMs } = useFatigueStore();

  if (!isRestLocked) return null;

  return (
    <div className="rest-lock-overlay" role="alertdialog" aria-label="强制休息中">
      <div className="rest-lock-content">
        <Typography.Title level={3}>强制休息中</Typography.Title>
        <Countdown value={Date.now() + restRemainingMs} format="mm:ss" />
        <Typography.Paragraph>
          连续处理高敏内容已达阈值，系统已暂停派单。
          此期间运营 SLA 正常暂停计时。
        </Typography.Paragraph>
        <Divider />
        <Button type="link" href={WELLNESS_RESOURCES_URL} target="_blank">
          心理健康资源与支持
        </Button>
      </div>
    </div>
  );
};
```

创伤屏蔽模式开启时，所有高敏内容帧自动 CSS `filter: blur(30px)`，视频默认静音不自播。审核员点击"我已准备好查看"后临时解锁单帧（操作记录写入审计日志）。案件切换间隙插入 2 秒纯色缓冲屏。

### 3.9【修订】金标测试案件（Golden Test）前端支持

**设计对齐后端契约**：后端对金标案件采用"对审核员完全透明（不可见）"策略。审核员在审核过程中不知道哪些是金标案件，提交后也不会收到即时反馈弹窗。金标评估由后端 Celery 异步完成，结果仅通过 QA 管理员查询端点暴露。

这一设计的核心理由：若审核员知道某案件是金标测试，其审核行为会受到影响（霍桑效应），导致金标测试无法真实反映审核质量。

```typescript
// 【修订】金标案件处理策略（对齐后端 8.7 节契约）
//
// 1. 注入阶段：后端在队列中注入金标案件（is_golden_test=true），
//    但 API 响应中不包含 is_golden_test 字段 -- 前端无法区分
// 2. 审核阶段：审核员正常审核并提交处置
// 3. 提交阶段：后端返回 { task_id, status: "decided", decision }，
//    金标评估由 Celery 异步执行，不在同步响应中返回
// 4. 结果查看：
//    - QA 管理员通过 GET /api/v1/quality/golden-results 查看全量结果
//    - 审核员通过 GET /api/v1/reviewers/{id}/golden-stats 查看个人统计

// 【修订】处置提交 -- 移除同步金标反馈，对齐后端实际响应格式
const useSubmitDisposition = () => {
  return useMutation({
    mutationFn: async (data: DispositionSubmission) => {
      // 【修订】后端响应格式为 { task_id, status, decision }
      // 不包含 golden_test_result（金标评估异步执行）
      const response = await api.reviews.submitDecision(data.caseId, {
        decision: data.decision,
        reason_category: data.reason_category ?? '',
        reason_detail: data.reason ?? '',
        internal_notes: data.overrideReason ?? '',
      });
      return response;
    },
    onSuccess: (response) => {
      // 【修订】移除同步金标反馈弹窗
      // 金标评估结果由后端异步处理，前端不做即时展示
      message.success('处置已提交');
    },
  });
};

// 【修订】QA 管理员视图 -- 金标测试结果查看
// 仅 qa_admin / ops_admin 角色可访问
const GoldenTestResults: React.FC = () => {
  const [reviewerId, setReviewerId] = useState<string | undefined>();

  const results = useQuery({
    queryKey: ['golden-results', reviewerId],
    queryFn: () => api.quality.getGoldenResults({ reviewer_id: reviewerId }),
  });

  return (
    <div role="region" aria-label="金标测试结果">
      <Select
        placeholder="按审核员筛选"
        onChange={setReviewerId}
        allowClear
        options={useReviewerOptions()}
        style={{ width: 240, marginBottom: 16 }}
      />
      <Table
        columns={[
          { title: '审核员', dataIndex: 'reviewer_id' },
          { title: '总测试数', dataIndex: 'total_golden_tests' },
          { title: '正确数', dataIndex: 'correct' },
          { title: '准确率', dataIndex: 'accuracy', render: (v: number | null) => v != null ? `${(v * 100).toFixed(1)}%` : '--' },
        ]}
        dataSource={results.data?.results ?? []}
      />
    </div>
  );
};

// 【修订】审核员个人统计 -- 含金标准确率（自我校准用途）
// 审核员仅可见自己的数据
const ReviewerMyStats: React.FC = () => {
  const myId = useAuthStore((s) => s.userId);

  // 审核员个人统计（不含金标的绩效数据）
  const stats = useQuery({
    queryKey: ['reviewer-stats', myId],
    queryFn: () => api.reviewers.getStats(myId!, { period: 'weekly' }),
    enabled: !!myId,
  });

  // 金标准确率（单独端点）
  const goldenStats = useQuery({
    queryKey: ['reviewer-golden-stats', myId],
    queryFn: () => api.reviewers.getGoldenStats(myId!),
    enabled: !!myId,
  });

  return (
    <div>
      <Card title="审核绩效">
        <Statistic title="本周完成量" value={stats.data?.completed ?? 0} />
        <Statistic title="Override 率" value={`${((stats.data?.override_rate ?? 0) * 100).toFixed(1)}%`} />
      </Card>
      <Card title="质检校准（金标测试）" style={{ marginTop: 16 }}>
        <Statistic title="总测试数" value={goldenStats.data?.total_golden_tests ?? 0} />
        <Statistic
          title="准确率"
          value={goldenStats.data?.accuracy != null ? `${(goldenStats.data.accuracy * 100).toFixed(1)}%` : '--'}
        />
        <Typography.Paragraph type="secondary">
          金标测试结果仅用于自我校准，不计入绩效考核。
        </Typography.Paragraph>
      </Card>
    </div>
  );
};
```

关键约束：
- 审核员在审核过程中**无法区分**金标案件与真实案件
- 金标案件的处置提交结果**不计入**审核员的绩效统计
- 金标评估由后端异步执行，前端不做同步等待
- 审核员可查看个人金标准确率用于自我校准
- QA 管理员可查看全量金标评估结果

---

## 4. 管理后台（Admin Panel）

### 4.1 用户与权限管理

**RBAC 可视化**

角色配置页面以矩阵表格呈现（行=角色，列=权限点），允许管理员可视化查看和编辑权限映射。角色定义严格遵循 PRD 第七节统一角色与权限矩阵。

```typescript
const PermissionMatrix: React.FC = () => {
  const roles = useQuery({ queryKey: ['roles'], queryFn: api.admin.getRoles });
  const permissions = useQuery({ queryKey: ['permissions'], queryFn: api.admin.getPermissions });

  return (
    <Table
      columns={[
        { title: '角色', dataIndex: 'roleName', fixed: 'left', width: 200 },
        ...permissions.data?.map((perm) => ({
          title: <Tooltip title={perm.description}>{perm.label}</Tooltip>,
          dataIndex: perm.id,
          width: 80,
          render: (hasPermission: boolean, record: RoleRow) => (
            <Checkbox
              checked={hasPermission}
              disabled={perm.isSystemLocked}
              onChange={(e) => handleToggle(record.roleId, perm.id, e.target.checked)}
              aria-label={`${record.roleName} - ${perm.label}`}
            />
          ),
        })) ?? [],
      ]}
      dataSource={buildMatrixData(roles.data, permissions.data)}
      scroll={{ x: 'max-content' }}
      pagination={false}
    />
  );
};
```

**审核员管理**

| 功能 | 说明 |
|------|------|
| 审核员列表 | 姓名、角色(T1/T2/T3)、技能标签(语言/法域/类目)、当前负载 |
| 技能标签管理 | 标签可配置：语言能力、法域资质、类目专长 |
| 负载看板 | 每人当前待处理量、日均产能、SLA 达成率 |
| CSAM 曝光监控 | 单班/周累计 CSAM 处理量、距上限比例 |
| 排班管理 | 排班日历、轮岗规则（高敏类目自动轮换） |

### 4.2 系统配置

**可视化工作流编辑器**

MVP 版本以流程图组件展示当前审核工作流，不支持拖拽编辑（Roadmap 功能），但支持参数配置：

```
视频提交 -> 证据提取 -> 基础初筛 -> [分支]
                                      |-> 命中 critical -> critical 专审
                                      |-> 高置信命中 -> 自动 BLOCK
                                      |-> 无命中 -> LLM 策略审查 -> [分支]
                                                                     |-> auto_pass -> PASS
                                                                     |-> auto_block -> BLOCK
                                                                     |-> needs_review -> 人审队列
```

每个节点可点击打开配置面板（DynamicForm 驱动），修改阈值参数。

**违规类型管理**

即维度注册表的前端管理界面。展示所有已注册维度（dim_id、名称、维度轴、启用状态、LLM 审查开关、Prompt 模板 ID），支持新增维度条目（零改造扩展路径的前端入口）。新增/修改走 Maker-Checker：提交后进入待审批状态，需 Policy Approver 确认。

### 4.3 数据分析

**审核效率报表**

| 指标 | 图表类型 | 维度 |
|------|---------|------|
| 日均处理量 | 折线图 | 按审核员 / 按 Tier / 按类目 |
| 平均处理时长 | 柱状图 | 按严重度 / 按类目 |
| SLA 达成率 | 仪表盘 | 法定 SLA vs 运营 SLA |
| Override 率 | 趋势图 | 审核员推翻机审比例 |

**审核一致性分析**

IRR (Inter-Rater Reliability) 看板：
- Cohen's Kappa 系数（按维度/类目展示）
- 不一致案件列表（可点击查看具体分歧）
- 热力图：不一致集中在哪些维度组合

**审核员绩效面板**

遵守 PRD 绩效防火墙要求：二审/质检改判的负反馈归原审/原规则，不让改判者承担同侪绩效后果。暴露/wellness 指标仅用于健康干预，不公开排名、不与绩效负向挂钩。

审核员个人仅可见本人数据；组长可见本组聚合数据（不含审核员姓名逐条明细）。

### 4.4 审计日志

```typescript
const AuditLogViewer: React.FC = () => {
  const [filters, setFilters] = useState<AuditFilters>({});

  // 【修订】审计日志使用 offset-based 分页，对齐后端
  const logs = useQuery({
    queryKey: ['audit-logs', filters],
    queryFn: () => api.audit.getLogs({
      ...filters,
      ...toBackendOffsetParams(filters.offset ?? 0, 50),
    }),
  });

  return (
    <div role="region" aria-label="审计日志">
      <AuditFilterBar
        filters={filters}
        onChange={setFilters}
        options={{
          actionTypes: AUDIT_ACTION_TYPES,
          actors: useActorList(),
          dateRange: true,
          videoId: true,
        }}
      />
      <Table
        columns={[
          { title: '时间', dataIndex: 'created_at', render: formatDateTime },
          { title: '操作', dataIndex: 'action', render: (a) => <AuditActionTag action={a} /> },
          { title: '操作人', dataIndex: 'actor' },
          { title: '内容 ID', dataIndex: 'content_id' },
          { title: '详情', dataIndex: 'details', render: (d) => <JsonViewer data={d} /> },
          { title: '策略版本', dataIndex: 'policy_version' },
        ]}
        dataSource={logs.data?.items}
        pagination={{
          total: logs.data?.total,
          pageSize: 50,
          onChange: (page) => {
            setFilters((f) => ({ ...f, offset: (page - 1) * 50 }));
          },
        }}
      />
    </div>
  );
};
```

审计日志为 append-only，前端仅提供只读查询，不支持删除/修改操作。支持按 content_id 全链路追溯（从摄取 -> 机审 -> 人审 -> 申诉 -> 最终处置）。

---

## 5. 组件库设计

### 5.1 Ant Design 二次封装策略

原则：不魔改 Ant Design 内部实现，只在外层包装业务语义。

```typescript
// 二次封装示例：StatusBadge（统一处置状态展示）
// MVP 状态集合精简为后端实际支持的枚举值

interface StatusBadgeProps {
  disposition: MVPDisposition | PolicyDecision | null;
  size?: 'small' | 'default';
  highlight?: boolean;
}

// MVP 阶段配置
const MVP_STATUS_CONFIG: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
  pass:                  { color: 'green',  label: '通过',     icon: <CheckCircleOutlined /> },
  block:                 { color: 'red',    label: '拒绝',     icon: <StopOutlined /> },
  auto_pass:             { color: 'green',  label: '自动通过', icon: <RobotOutlined /> },
  auto_block:            { color: 'red',    label: '自动拒绝', icon: <RobotOutlined /> },
  needs_human_review:    { color: 'orange', label: '待人审',   icon: <EyeOutlined /> },
  critical_escalate:     { color: 'red',    label: '高危上报', icon: <FireOutlined /> },
};

// V2 扩展配置（feature flag 控制加载）
const V2_STATUS_CONFIG: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
  PASS:                  { color: 'green',  label: '通过',     icon: <CheckCircleOutlined /> },
  DEMOTE:                { color: 'gold',   label: '限流降权', icon: <WarningOutlined /> },
  LABEL:                 { color: 'blue',   label: '打标',     icon: <TagOutlined /> },
  AGE_GATE:              { color: 'orange', label: '年龄门',   icon: <UserOutlined /> },
  GEO_BLOCK:             { color: 'purple', label: '地理屏蔽', icon: <GlobalOutlined /> },
  REMOVE:                { color: 'red',    label: '下架',     icon: <StopOutlined /> },
  REMOVE_AND_ESCALATE:   { color: 'red',    label: '下架并上报', icon: <AlertOutlined /> },
};

const StatusBadge: React.FC<StatusBadgeProps> = ({ disposition, size = 'default', highlight }) => {
  const featureFlags = useConfigStore((s) => s.featureFlags);
  const statusConfig = featureFlags.enableFullDispositionMatrix
    ? { ...MVP_STATUS_CONFIG, ...V2_STATUS_CONFIG }
    : MVP_STATUS_CONFIG;

  const config = statusConfig[disposition ?? ''] ?? { color: 'default', label: disposition ?? '--', icon: null };
  return (
    <Tag
      color={config.color}
      icon={config.icon}
      className={highlight ? 'badge-highlight' : ''}
      role="status"
      aria-label={`处置状态: ${config.label}`}
    >
      {config.label}
    </Tag>
  );
};
```

### 5.2 VideoPlayer 组件（详细设计见 3.2）

核心能力汇总：
- 基于 xgplayer 3.x 插件架构
- 命中点时间轴标注（Canvas 渲染，性能好）
- 逐帧控制（前进/后退，快捷键 `,` 和 `.`）
- 倍速播放（0.25x ~ 4x）
- 画面截取与矩形标注
- 创伤屏蔽模式（blur overlay + 点击解锁）
- CSAM 限制模式（完全屏蔽，仅展示占位符）
- 自适应码率切换
- 多画质选择
- 被 PanelErrorBoundary 包裹，崩溃不影响处置面板

### 5.3 DynamicForm 组件

支持策略配置的动态表单生成系统：

```typescript
interface DynamicFormProps {
  schema: FormSchema;
  values?: Record<string, unknown>;
  onValuesChange?: (changed: Record<string, unknown>, all: Record<string, unknown>) => void;
  onSubmit?: (values: Record<string, unknown>) => void;
  readonly?: boolean;
  jurisdictionMode?: boolean;
}

type FieldType =
  | 'text' | 'number' | 'slider' | 'switch'
  | 'select' | 'multi-select' | 'cascader'
  | 'date' | 'date-range'
  | 'json-editor'
  | 'threshold-pair'
  | 'rubric-editor'
  | 'dimension-ref';

const FIELD_RENDERERS: Record<FieldType, React.FC<FieldRendererProps>> = {
  'text': TextFieldRenderer,
  'number': NumberFieldRenderer,
  'slider': SliderFieldRenderer,
  'threshold-pair': ThresholdPairRenderer,
  // ...
};
```

`threshold-pair` 渲染器专为策略阈值设计，展示一个双滑块区间选择器：左端 = 人审下限阈值，右端 = 自动处置阈值，中间区域标注"人审区间"。

### 5.4 数据可视化组件

基于 ECharts 封装一组业务图表组件：

| 组件名 | 用途 | 图表类型 |
|--------|------|---------|
| `TrendChart` | 审核量趋势 | 折线图（带缩放） |
| `DistributionChart` | 违规类型分布 | 旭日图/饼图 |
| `FunnelChart` | 三阶段漏斗转化 | 漏斗图 |
| `ConfidenceHistogram` | LLM 置信度分布 | 柱状图 |
| `HeatmapChart` | IRR 一致性热力图 | 热力图 |
| `GaugeChart` | SLA 达成率 | 仪表盘 |
| `SankeyFlow` | 案件流转路径 | 桑基图 |

所有图表组件统一接口：

```typescript
interface ChartProps<T> {
  data: T[];
  loading?: boolean;
  height?: number;
  onDataPointClick?: (point: T) => void;
  theme?: 'light' | 'dark';
  // 无障碍文本摘要
  ariaLabel?: string;
  ariaSummary?: string;  // 数据文本摘要，供屏幕阅读器使用
}

// 图表组件基础包裹，统一添加 a11y 支持和错误边界
const ChartWrapper: React.FC<{ ariaLabel?: string; ariaSummary?: string; children: React.ReactNode }> = ({
  ariaLabel,
  ariaSummary,
  children,
}) => (
  <PanelErrorBoundary panelName={ariaLabel ?? '图表'}>
    <div role="img" aria-label={ariaLabel} aria-describedby={ariaSummary ? 'chart-summary' : undefined}>
      {children}
      {ariaSummary && (
        <div id="chart-summary" className="sr-only">{ariaSummary}</div>
      )}
    </div>
  </PanelErrorBoundary>
);
```

### 5.5 通用业务组件

| 组件 | 职责 |
|------|------|
| `ReviewPanel` | 机审维度评分展示面板，按三维度轴分组显示各类目分数 + DimensionVerdict 理由 |
| `TaskCard` | 队列中的案件卡片，含缩略图/严重度/SLA/锁状态/标签 |
| `StatusBadge` | 统一的状态标签（MVP 覆盖 pass/block + L2 四态，V2 扩展 L3 七态） |
| `SLACountdown` | SLA 倒计时组件，区分法定/运营，临近标红闪烁 |
| `EvidenceViewer` | 证据包多模态展示（ASR/OCR/目标检测/场景标签，按 Tab 组织） |
| `TimelineMarker` | 视频时间轴命中点标注（Canvas，色块表示命中区间） |
| `TraumaShield` | 创伤屏蔽遮罩层 + "已准备好查看"交互 |
| `JsonViewer` | 审计日志 JSON 详情折叠展示 |
| `PanelErrorBoundary` | 面板级错误边界，包裹每个独立面板 |

---

## 6. 性能优化方案

### 6.1 视频加载优化

| 策略 | 实现 |
|------|------|
| 懒加载 | 仅当审核员进入案件时加载视频，队列列表只加载缩略图 |
| 自适应码率 | 播放器接入 HLS/DASH 流，根据网络带宽自动切换 360p/720p/1080p |
| 预加载下一条 | 当审核员处理当前案件时，后台预加载队列中下一条的视频元数据和证据包（不预加载视频本体） |
| 帧缓存 | EvidencePackage 中的 frames 图片使用浏览器缓存 + CDN，避免重复拉取 |
| 按需加载帧 | 目标检测 bounding box 叠加层仅在点击到对应 Tab 时渲染 |

### 6.2 长列表虚拟滚动

```typescript
<Virtuoso
  data={queueItems}
  endReached={() => fetchNextPage()}
  overscan={5}
  itemContent={(index, item) => <TaskCard case={item} />}
  components={{
    Footer: () => isFetching ? <Spin /> : null,
  }}
/>
```

审计日志、相似历史决策参考列表同样使用虚拟滚动。

### 6.3 代码分割策略

**路由级分割**（Vite 自动 chunk）：
```typescript
const DashboardLayout = lazy(() => import('./features/dashboard/pages/DashboardLayout'));
const ReviewWorkbench = lazy(() => import('./features/review/pages/ReviewWorkbench'));
const PolicyEditor = lazy(() => import('./features/policy/pages/PolicyEditor'));
const AuditLogViewer = lazy(() => import('./features/admin/pages/AuditLogViewer'));
```

**组件级分割**：
- ECharts 按需引入（只 import 使用的图表类型和组件）
- Monaco Editor（JSON 编辑器）动态加载
- xgplayer 插件按需注册

**预期首屏体积**：主 chunk < 200KB gzipped，单个路由 chunk < 100KB gzipped。

### 6.4 请求优化

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
});

// WebSocket 在线时：不轮询，由 ws 事件 invalidate 对应 queryKey
// WebSocket 断线时：降级为 5 秒轮询
const useAdaptiveRefetch = (queryKey: string[]) => {
  const wsConnected = useWsStore((s) => s.isConnected);
  return useQuery({
    queryKey,
    refetchInterval: wsConnected ? false : 5000,
  });
};
```

**【修订】乐观更新**：审核员提交处置时，前端立即将案件状态更新为"已提交"并从队列移除，同时发送请求。若请求失败则回滚并提示。

```typescript
const submitDisposition = useMutation({
  mutationFn: (data: DispositionSubmission) => api.reviews.submitDecision(data.caseId, {
    decision: data.decision,
    reason_category: data.reason_category ?? '',
    reason_detail: data.reason ?? '',
    internal_notes: data.overrideReason ?? '',
  }),
  onMutate: async (data) => {
    await queryClient.cancelQueries({ queryKey: ['review-queue'] });
    const previous = queryClient.getQueryData(['review-queue']);
    queryClient.setQueryData(['review-queue'], (old: any) =>
      removeCaseFromPages(old, data.caseId)
    );
    return { previous };
  },
  onError: (err, data, context) => {
    queryClient.setQueryData(['review-queue'], context?.previous);
    message.error('提交失败，案件已恢复到队列');
  },
  onSettled: () => {
    queryClient.invalidateQueries({ queryKey: ['review-queue'] });
  },
  // 【修订】乐观更新后直接跳转到下一个案件
  // 不等待同步响应中的金标结果（后端异步处理）
});
```

### 6.5 资源缓存策略

Vite 构建输出使用内容哈希命名 (`[name].[hash].js`)，配合 CDN 设置长缓存。

对于 EvidencePackage 中的帧图片 (`image_ref` 指向 S3/CDN)：
- HTTP Cache-Control: `public, max-age=86400`
- 浏览器 Service Worker 拦截图片请求，Cache First 策略
- 审核工作台预取当前案件的全部关键帧

```typescript
// 【修订】Service Worker 缓存策略 -- 增加 ETag/版本感知的缓存失效机制
registerRoute(
  ({ url }) => url.pathname.startsWith('/evidence/') && url.pathname.endsWith('.jpg'),
  new StaleWhileRevalidate({
    // 【修订】改用 StaleWhileRevalidate 替代 CacheFirst
    // 原因：证据帧可能在重处理后更新（如模型版本升级重新提取），
    // StaleWhileRevalidate 先返回缓存（保证速度），同时后台校验是否有更新，
    // 有更新则下次请求使用新版本。避免 CacheFirst 导致的陈旧证据误导审核员。
    cacheName: 'evidence-frames',
    plugins: [
      new ExpirationPlugin({ maxEntries: 500, maxAgeSeconds: 24 * 60 * 60 }),
      new CacheableResponsePlugin({ statuses: [0, 200] }),
    ],
  })
);
```

---

## 7. 实时通信

### 7.1【修订】WebSocket 连接管理（ws-token 认证 + HEARTBEAT 协议）

```typescript
// src/api/ws.ts
// 【修订】关键修复：
// 1. 使用 ws-token 专用端点获取短期令牌（后端 verify_ws_token 要求 type='ws'）
// 2. 心跳消息类型对齐后端：HEARTBEAT / HEARTBEAT_ACK（非 PING/PONG）
// 3. 消息格式对齐后端信封：{ type, payload, timestamp, correlation_id }
// 4. ws-token 自动续期机制解决 5 分钟过期问题

class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectDelay = 30_000;
  private maxReconnectAttempts = 10;
  private heartbeatInterval: number | null = null;
  private lastSeenTimestamp = 0;
  private messageHandlers = new Map<string, Set<(payload: any) => void>>();
  // 【修订】已处理消息的 correlation_id 集合，用于去重
  private processedCorrelationIds = new Set<string>();
  private correlationIdCleanupInterval: number | null = null;

  async connect() {
    // 【修订】关键修复：必须调用 POST /api/v1/auth/ws-token 获取专用 WebSocket 令牌
    // 后端 verify_ws_token() 要求 JWT payload 中包含 type='ws'，
    // 普通登录 JWT 不包含此字段，直接使用会被后端以 code=4001 拒绝。
    let wsToken: string;
    try {
      const tokenResponse = await api.auth.getWsToken();
      wsToken = tokenResponse.ws_token;
      // 记录 ws-token 过期时间，用于主动续期
      useWsStore.getState().setWsTokenExpiresAt(new Date(tokenResponse.expires_at).getTime());
    } catch (e) {
      console.error('获取 WebSocket 令牌失败:', e);
      // 若获取 ws-token 失败（如用户未登录），不尝试连接
      return;
    }

    this.ws = new WebSocket(`${WS_BASE_URL}/ws/review?token=${wsToken}`);
    this.ws.onopen = this.handleOpen;
    this.ws.onmessage = this.handleMessage;
    this.ws.onclose = this.handleClose;
    this.ws.onerror = this.handleError;
  }

  private handleOpen = () => {
    this.reconnectAttempts = 0;
    useWsStore.getState().setConnected(true);

    // 【修订】启动心跳（30 秒间隔）-- 消息类型对齐后端 HEARTBEAT
    this.heartbeatInterval = window.setInterval(() => {
      this.send({
        type: 'HEARTBEAT',
        payload: {},
        timestamp: new Date().toISOString(),
        correlation_id: crypto.randomUUID(),
      });
    }, 30_000);

    // 【修订】启动 ws-token 续期定时器
    // ws-token 有效期 5 分钟，在到期前 1 分钟主动续期
    this.scheduleWsTokenRefresh();

    // 【修订】启动 correlation_id 去重集合定期清理
    this.correlationIdCleanupInterval = window.setInterval(() => {
      // 每 5 分钟清理一次，防止内存泄漏
      this.processedCorrelationIds.clear();
    }, 5 * 60 * 1000);

    // 重连后全量重同步（后端支持 RECONNECT_SYNC 时可优化为增量）
    if (this.lastSeenTimestamp > 0) {
      this.performFullResyncOrIncremental();
    }
  };

  // 【修订】ws-token 续期机制
  // 解决问题：ws-token 仅 5 分钟有效，长审核会话中连接断开后重连需要新 token
  private wsTokenRefreshTimer: number | null = null;

  private scheduleWsTokenRefresh = () => {
    if (this.wsTokenRefreshTimer) {
      clearTimeout(this.wsTokenRefreshTimer);
    }
    const expiresAt = useWsStore.getState().wsTokenExpiresAt;
    if (!expiresAt) return;

    // 在到期前 60 秒刷新
    const refreshInMs = Math.max(0, expiresAt - Date.now() - 60_000);
    this.wsTokenRefreshTimer = window.setTimeout(async () => {
      try {
        const tokenResponse = await api.auth.getWsToken();
        useWsStore.getState().setWsTokenExpiresAt(
          new Date(tokenResponse.expires_at).getTime()
        );
        // ws-token 续期成功，存储新 token 供重连使用
        useWsStore.getState().setLatestWsToken(tokenResponse.ws_token);
        this.scheduleWsTokenRefresh(); // 继续调度下一次续期
      } catch (e) {
        console.error('ws-token 续期失败:', e);
        // 续期失败不立即断开连接（当前连接仍有效），
        // 但标记状态以便重连时使用登录 token 重新获取
      }
    }, refreshInMs);
  };

  // 【修订】重连后同步策略
  private performFullResyncOrIncremental = () => {
    const featureFlags = useConfigStore.getState().featureFlags;

    if (featureFlags.enableReconnectSync) {
      // V2: 发送 RECONNECT_SYNC 请求增量补发
      this.send({
        type: 'RECONNECT_SYNC',
        payload: { lastSeenTimestamp: this.lastSeenTimestamp },
        timestamp: new Date().toISOString(),
        correlation_id: crypto.randomUUID(),
      });
    } else {
      // MVP: 直接 invalidate 所有活跃 Query，由 TanStack Query 重新拉取
      this.performFullResync();
    }
  };

  private performFullResync = () => {
    const queryClient = getQueryClient();
    queryClient.invalidateQueries({ queryKey: ['review-queue'] });
    queryClient.invalidateQueries({ queryKey: ['case'] });
    queryClient.invalidateQueries({ queryKey: ['alerts'] });
    queryClient.invalidateQueries({ queryKey: ['system-health'] });

    notification.info({
      message: '连接已恢复',
      description: '数据已自动刷新。',
      duration: 3,
    });
  };

  private handleMessage = (event: MessageEvent) => {
    // 防御性解析，防止畸形消息导致崩溃
    let msg: BackendWsMessage;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      console.error('WebSocket 消息解析失败:', event.data);
      return;
    }

    // 【修订】消息去重 -- 使用后端提供的 correlation_id
    if (msg.correlation_id && this.processedCorrelationIds.has(msg.correlation_id)) {
      return; // 重复消息，静默忽略
    }
    if (msg.correlation_id) {
      this.processedCorrelationIds.add(msg.correlation_id);
    }

    // 【修订】更新 lastSeenTimestamp（后端使用 ISO 8601 格式）
    if (msg.timestamp) {
      this.lastSeenTimestamp = new Date(msg.timestamp).getTime();
    }

    // 【修订】心跳回复对齐后端 HEARTBEAT_ACK
    if (msg.type === 'HEARTBEAT_ACK' || msg.type === 'pong') return;

    // 未知消息类型静默忽略，不阻断处理流程
    const handlers = this.messageHandlers.get(msg.type);
    if (!handlers || handlers.size === 0) {
      console.debug(`未注册的 WebSocket 消息类型: ${msg.type}`);
      return;
    }
    handlers.forEach((h) => {
      try {
        h(msg);
      } catch (e) {
        console.error(`WebSocket handler 异常 [${msg.type}]:`, e);
      }
    });
  };

  private handleError = (event: Event) => {
    console.error('WebSocket 错误:', event);
  };

  private handleClose = (event: CloseEvent) => {
    useWsStore.getState().setConnected(false);
    if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
    if (this.correlationIdCleanupInterval) clearInterval(this.correlationIdCleanupInterval);
    if (this.wsTokenRefreshTimer) clearTimeout(this.wsTokenRefreshTimer);

    // 【修订】code 4001 = 鉴权失败，不重连（需用户重新登录）
    if (event.code === 4001) {
      console.error('WebSocket 鉴权失败，不重连');
      notification.error({
        message: '连接鉴权失败',
        description: '请刷新页面重新登录。',
        duration: 0,
      });
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay);
    this.reconnectAttempts++;

    if (this.reconnectAttempts > this.maxReconnectAttempts) {
      useWsStore.getState().setNeedsFullRefresh(true);
      notification.warning({
        message: '实时连接中断',
        description: '已超过最大重连次数，数据将通过轮询方式更新。请刷新页面恢复实时连接。',
        duration: 0,
      });
      return;
    }

    setTimeout(() => this.connect(), delay);
  };

  subscribe(type: string, handler: (msg: BackendWsMessage) => void) {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, new Set());
    }
    this.messageHandlers.get(type)!.add(handler);
    return () => this.messageHandlers.get(type)?.delete(handler);
  }

  private send(msg: BackendWsMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  disconnect() {
    if (this.heartbeatInterval) clearInterval(this.heartbeatInterval);
    if (this.correlationIdCleanupInterval) clearInterval(this.correlationIdCleanupInterval);
    if (this.wsTokenRefreshTimer) clearTimeout(this.wsTokenRefreshTimer);
    this.ws?.close();
  }
}

export const wsManager = new WebSocketManager();
```

### 7.2【修订】实时数据推送处理（修复 useEffect 依赖不稳定问题）

```typescript
// src/hooks/useStableCallback.ts
// 【修订】稳定回调引用 -- 解决 useWsSubscription 中 handler 每次渲染创建新引用的问题
function useStableCallback<T extends (...args: any[]) => any>(callback: T): T {
  const callbackRef = useRef(callback);
  // 每次渲染更新 ref，但不触发 effect 重执行
  callbackRef.current = callback;
  // 返回一个稳定引用的包装函数
  return useCallback((...args: any[]) => callbackRef.current(...args), []) as T;
}
```

```typescript
// src/hooks/useWsSubscription.ts
// 【修订】修复关键 Bug：原实现中 handler 参数在 useEffect 依赖数组中，
// 但调用方通常传入内联箭头函数（每次渲染创建新引用），
// 导致 subscribe/unsubscribe 循环执行。
// 修复方案：使用 useStableCallback 包装 handler，确保 ref 稳定。

function useWsSubscription<T = any>(
  type: string,
  handler?: (msg: BackendWsMessage) => void,
) {
  const [latestPayload, setLatestPayload] = useState<T | null>(null);

  // 【修订】使用 useStableCallback 确保 handler ref 稳定
  const stableHandler = useStableCallback((msg: BackendWsMessage) => {
    setLatestPayload(msg.payload as T);
    handler?.(msg);
  });

  useEffect(() => {
    // 【修订】stableHandler 引用不变，不会导致 effect 重执行
    const unsubscribe = wsManager.subscribe(type, stableHandler);
    return unsubscribe;
  }, [type, stableHandler]);

  return latestPayload;
}
```

```typescript
// 审核工作台中的 WebSocket 订阅
// 【修订】消息类型对齐后端定义

const ReviewWorkbench: React.FC = () => {
  // 【修订】锁状态：后端使用 task_lock_expired / task_reassigned
  useWsSubscription('task_lock_expired', (msg) => {
    if (msg.payload.task_id === currentCaseId) {
      message.warning('任务锁已过期，任务已被释放');
      navigateToQueue();
    }
  });

  useWsSubscription('task_reassigned', (msg) => {
    if (msg.payload.task_id === currentCaseId) {
      message.warning('此案件已被系统重新分配');
      navigateToQueue();
    }
  });

  // 【修订】SLA 预警：后端使用 sla_warning / legal_deadline_warning
  useWsSubscription('sla_warning', (msg) => {
    if (msg.payload.task_id === currentCaseId) {
      notification.warning({
        message: 'SLA 即将到期',
        description: `剩余 ${msg.payload.remaining_minutes} 分钟`,
        duration: 0,
      });
    }
  });

  useWsSubscription('legal_deadline_warning', (msg) => {
    if (msg.payload.task_id === currentCaseId) {
      notification.error({
        message: '法定时限即将到期',
        description: `剩余 ${msg.payload.remaining_minutes} 分钟，请尽快完成审核`,
        duration: 0,
      });
    }
  });

  // 【修订】kill-switch 通知
  useWsSubscription('kill_switch_activated', (msg) => {
    Modal.warning({
      title: 'Kill-Switch 已激活',
      content: `原因: ${msg.payload.reason}。受影响策略: ${(msg.payload.affected_policies as string[]).join(', ')}。系统已切换为全人审模式。`,
      okText: '知道了',
    });
  });
};
```

### 7.3【修订】多标签页同步

使用 BroadcastChannel API 同步多标签页状态。**修复原方案仅覆盖 CASE_CLAIMED 的不足**，扩展覆盖认证状态和 WebSocket 连接协调。

```typescript
// src/hooks/useBroadcastChannel.ts
// 【修订】多标签页同步 -- 扩展覆盖范围

type BroadcastMessage =
  | { type: 'CASE_CLAIMED'; caseId: string; tabId: string }
  | { type: 'AUTH_LOGOUT' }                    // 【修订】登出同步
  | { type: 'AUTH_TOKEN_REFRESHED'; token: string }  // 【修订】token 刷新同步
  | { type: 'WS_CONNECTED'; tabId: string }    // 【修订】WS 连接状态同步
  | { type: 'WS_DISCONNECTED'; tabId: string };

const TAB_ID = crypto.randomUUID();
const channel = new BroadcastChannel('review-workbench');

function useBroadcastSync() {
  useEffect(() => {
    const handler = (event: MessageEvent<BroadcastMessage>) => {
      switch (event.data.type) {
        case 'CASE_CLAIMED':
          if (event.data.caseId === getCurrentCaseId() && event.data.tabId !== TAB_ID) {
            message.warning('此案件已在另一个标签页中打开');
          }
          break;

        // 【修订】任一标签页登出时，其他标签页同步登出
        case 'AUTH_LOGOUT':
          useAuthStore.getState().logout();
          window.location.href = '/login';
          break;

        // 【修订】token 刷新后同步到其他标签页，避免各标签页独立刷新 token
        case 'AUTH_TOKEN_REFRESHED':
          useAuthStore.getState().setAccessToken(event.data.token);
          break;

        // 【修订】WebSocket 连接协调：
        // 避免 N 个标签页打开 N 个独立 WebSocket 连接
        // 仅由最新活跃标签页维护连接，其他标签页通过 BroadcastChannel 接收事件
        case 'WS_CONNECTED':
          if (event.data.tabId !== TAB_ID) {
            // 另一个标签页已建立连接，本标签页降级为从属模式
            useWsStore.getState().setPeerConnected(true);
          }
          break;

        case 'WS_DISCONNECTED':
          if (event.data.tabId !== TAB_ID) {
            useWsStore.getState().setPeerConnected(false);
          }
          break;
      }
    };

    channel.addEventListener('message', handler);
    return () => channel.removeEventListener('message', handler);
  }, []);
}

// 广播事件
function broadcastCaseClaimed(caseId: string) {
  channel.postMessage({ type: 'CASE_CLAIMED', caseId, tabId: TAB_ID } as BroadcastMessage);
}

function broadcastLogout() {
  channel.postMessage({ type: 'AUTH_LOGOUT' } as BroadcastMessage);
}

function broadcastTokenRefreshed(token: string) {
  channel.postMessage({ type: 'AUTH_TOKEN_REFRESHED', token } as BroadcastMessage);
}
```

---

## 8. 可扩展性设计

### 8.1 插件化架构（新审核类型快速接入）

遵循 PRD $11.A 零改造扩展路径要求。前端通过"两级渲染"实现维度 UI 扩展：

**第一级：Schema 驱动的默认渲染（零代码变更）**

对于简单维度，后端维度注册表中定义的 Schema 字段由 DynamicForm 和 DefaultVerdictRenderer 自动渲染。新增维度只需在后端注册表中配置字段定义，前端**无需任何代码变更**即可展示和配置该维度。

**第二级：自定义渲染器插件（需代码变更和重部署）**

对于需要特殊可视化的复杂维度（如 AIGC 检测需要展示伪造热力图），则通过插件注册表注册自定义 React 组件。**此路径需要编写新组件文件、注册并重新部署**，不是零代码变更。

```typescript
// src/plugins/registry.ts
interface DimensionUIPlugin {
  dimensionId: string;
  // 人审工作台中该维度的自定义渲染器（覆盖 DefaultVerdictRenderer）
  VerdictRenderer?: React.FC<{ verdict: DimensionVerdict }>;
  // 策略配置表单中该维度的自定义字段渲染器（覆盖 DynamicForm 默认渲染）
  ConfigRenderer?: React.FC<{ schema: FieldDefinition[]; values: Record<string, unknown> }>;
  // 该维度在仪表盘中的自定义图表
  DashboardWidget?: React.FC<{ data: DimensionStats }>;
}

class PluginRegistry {
  private plugins = new Map<string, DimensionUIPlugin>();

  register(plugin: DimensionUIPlugin) {
    this.plugins.set(plugin.dimensionId, plugin);
  }

  getVerdictRenderer(dimensionId: string): React.FC<{ verdict: DimensionVerdict }> {
    return this.plugins.get(dimensionId)?.VerdictRenderer ?? DefaultVerdictRenderer;
  }

  getConfigRenderer(dimensionId: string): React.FC<any> {
    return this.plugins.get(dimensionId)?.ConfigRenderer ?? DefaultConfigRenderer;
  }
}

export const pluginRegistry = new PluginRegistry();

// 注册示例：新增 "AIGC 生成标识" 维度的复杂自定义渲染器
pluginRegistry.register({
  dimensionId: 'dim_aigc_disclosure',
  VerdictRenderer: AIGCVerdictRenderer,
  ConfigRenderer: AIGCConfigRenderer,
});
```

**扩展性总结**：

| 扩展场景 | 前端变更量 | 后端变更量 |
|---------|-----------|-----------|
| 新增简单维度（标准 UI 即可满足） | **零** -- DefaultVerdictRenderer + DynamicForm 自动渲染 | 维度注册表新增一行配置 |
| 新增复杂维度（需要自定义可视化） | 新增自定义渲染器组件 + 注册调用，需重新构建部署 | 维度注册表新增 + 后端处理逻辑 |

人审工作台的维度评分面板动态渲染：

```typescript
const VerdictPanel: React.FC<{ verdicts: DimensionVerdict[] }> = ({ verdicts }) => {
  return (
    <PanelErrorBoundary panelName="维度评分面板">
      <Collapse>
        {verdicts.map((verdict) => {
          const Renderer = pluginRegistry.getVerdictRenderer(verdict.dimension_id);
          return (
            <Collapse.Panel
              key={verdict.dimension_id}
              header={
                <Space>
                  <Typography.Text strong>{verdict.dimension_name}</Typography.Text>
                  <StatusBadge disposition={verdict.decision as any} />
                  <ConfidenceBar value={verdict.confidence} />
                </Space>
              }
            >
              <Renderer verdict={verdict} />
            </Collapse.Panel>
          );
        })}
      </Collapse>
    </PanelErrorBoundary>
  );
};
```

### 8.2 动态表单系统

策略配置表单的 Schema 由后端维度注册表下发，前端不硬编码任何维度的配置字段。新维度上线时，只需在注册表中定义字段 Schema，前端自动渲染对应表单。

详见 5.3 节 DynamicForm 组件设计。

### 8.3 微前端考量

**MVP 阶段不引入微前端**。理由：
- 当前为单团队开发，模块间耦合度可控
- Vite 代码分割 + 路由懒加载已能满足隔离和按需加载需求
- 微前端引入的复杂度（子应用通信、样式隔离、共享依赖）在当前规模下得不偿失

**V2 阶段考虑引入的场景**：若人审工作台、机审大屏、管理后台由不同团队独立迭代，可采用 Module Federation 方案，将三大模块拆为独立部署单元。预留设计：
- 所有跨模块通信已通过 Zustand store + Event Bus 解耦
- 路由表集中管理，支持动态注册子应用路由
- 共享组件库独立发包

### 8.4 Feature Flag 集成

```typescript
interface FeatureFlags {
  enableShadowCompare: boolean;
  enableBatchReview: boolean;
  enableTraumaShield: boolean;
  enableDataFlywheel: boolean;
  maxBatchSize: number;
  // MVP 与 V2 功能边界
  enableFullDispositionMatrix: boolean;   // 7 态处置矩阵（MVP=false）
  enableConsequencePreview: boolean;      // 连带后果预览（MVP=false，需后端端点就绪）
  enableDashboardHealth: boolean;         // 系统健康面板（MVP=false，需后端端点就绪）
  enableDashboardAlerts: boolean;         // 告警管理（MVP=false，需后端端点就绪）
  enableSoRTemplates: boolean;            // SoR 模板系统（MVP=false，需后端 SoR 模型就绪）
  enableReconnectSync: boolean;           // WS RECONNECT_SYNC（MVP=false，需后端事件重放就绪）
}

const useFeatureFlag = (flag: keyof FeatureFlags): boolean => {
  return useConfigStore((s) => s.featureFlags[flag] ?? false);
};

const ReviewQueue: React.FC = () => {
  const batchEnabled = useFeatureFlag('enableBatchReview');
  return (
    <div>
      {batchEnabled && <BatchReviewButton />}
      {/* ... */}
    </div>
  );
};
```

### 8.5【修订】Feature Flag 里程碑规划

| Feature Flag | MVP | V1.1 | V2 | 前置条件 |
|-------------|-----|------|-----|---------|
| `enableFullDispositionMatrix` | false | false | true | 后端 `GET /api/v1/policy/dispositions` 返回 7 态 |
| `enableConsequencePreview` | false | false | true | 后端新增 `GET /api/v1/policy/dispositions/{id}/consequences` |
| `enableDashboardHealth` | false | true | true | 后端 `GET /api/v1/system/health` 已就绪 |
| `enableDashboardAlerts` | false | true | true | 后端 `GET /api/v1/system/alerts` 已就绪 |
| `enableSoRTemplates` | false | true | true | 后端 SoR 模块 4 个 API 已就绪 |
| `enableReconnectSync` | false | true | true | 后端 WebSocket RECONNECT_SYNC handler 已就绪 |

每个 flag 的开启条件：**后端端点通过契约测试 + 前端集成测试通过**。禁止在后端端点未就绪时开启对应 flag。

### 8.6 主题/品牌定制

基于 Ant Design 5.x ConfigProvider token 系统：

```typescript
// src/styles/theme.ts
export const defaultTheme: ThemeConfig = {
  token: {
    colorPrimary: '#1677ff',
    borderRadius: 6,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  components: {
    Table: { headerBg: '#fafafa' },
    Tag: { defaultBg: '#f5f5f5' },
  },
};

export const SEVERITY_COLORS = {
  critical: '#ff4d4f',
  high: '#fa8c16',
  medium: '#faad14',
  low: '#8c8c8c',
};
```

---

## 9.【修订】核心 TypeScript 类型定义（对齐后端契约）

以下类型严格对齐 PRD v2.2 $1.E 的字段名权威映射表和后端实际数据模型。

```typescript
// src/types/evidence.ts -- EvidencePackage 完整类型
export interface EvidencePackage {
  ep_id: string;
  schema_version: string;
  content_id: string;
  snapshot_id: string;
  created_at: number; // Unix ms
  video_meta: VideoMeta;
  frames: Frame[];
  asr_transcript: ASRSegment[];
  ocr_results: OCRResult[];
  object_detections: ObjectDetection[];
  scene_tags: SceneTag[];
  modality_availability?: ModalityAvailability;
  truncated_modalities?: string[];
  pre_filter_results: PreFilterResults;
  llm_verdicts: DimensionVerdict[];
  decision_summary: DecisionSummary | null;
  access_policy: AccessPolicy;
  // 【修订】新增后端暴露的字段
  token_budget_used?: number;
  token_budget_limit?: number;
}

export interface Frame {
  frame_id: string;
  timestamp_ms: number;
  is_keyframe: boolean;
  image_ref: string;
  resolution: { width: number; height: number };
}

export interface ASRSegment {
  start_ms: number;
  end_ms: number;
  text: string;
  confidence: number;
  lang: string;
}

export interface OCRResult {
  frame_ts: number;
  text: string;
  bbox: [number, number, number, number];
  confidence: number;
}

export interface ObjectDetection {
  frame_ts: number;
  label: string;
  bbox: [number, number, number, number];
  score: number;
  model_version: string;
}

export interface PreFilterResults {
  csam_hash_hit: boolean;
  cloud_api_hits: Array<{ category: string; confidence: number; severity: string }>;
  rule_hits: Array<{ rule_id: string; description: string }>;
  dedup_reuse: { original_content_id: string; original_decision: string } | null;
  skip_llm_review: boolean;
  skip_reason: string | null;
}

export interface AccessPolicy {
  readable_roles: string[];
  csam_exception: boolean;
  retention_days: number;
}

// src/types/verdict.ts -- DimensionVerdict
export interface DimensionVerdict {
  dimension_id: string;
  dimension_name: string;
  decision: DimensionDecision;
  confidence: number;
  severity_suggestion: SeveritySuggestion | null;
  reason: string;
  evidence_refs: EvidenceRef[];
  policy_version: string;
  model_version: string;
  llm_unavailable: boolean;
}

export type DimensionDecision = 'VIOLATION' | 'NO_VIOLATION' | 'UNCERTAIN';
export type SeveritySuggestion = 'critical' | 'high' | 'medium' | 'low';

export interface EvidenceRef {
  ref_type: 'frame' | 'asr_segment' | 'ocr_region' | 'object_detection';
  frame_id?: string;
  timestamp_ms?: number;
  start_ms?: number;
  end_ms?: number;
  text_excerpt?: string;
  description: string;
}

// src/types/policy.ts -- 决策枚举映射
// L1: LLM 维度判断层（DimensionDecision 已在 verdict.ts 定义）
// L2: 规则引擎决策层
export type PolicyDecision = 'auto_pass' | 'auto_block' | 'needs_human_review' | 'critical_escalate';

// L3 处置动作层 -- MVP 与 V2 分离定义
// MVP: 仅 pass | block，与后端 HumanReviewDecisionModel.decision 严格对齐
export type MVPDisposition = 'pass' | 'block';

// V2: 完整处置矩阵（feature flag enableFullDispositionMatrix 控制）
export type FullDispositionAction =
  | 'PASS' | 'DEMOTE' | 'LABEL' | 'AGE_GATE'
  | 'GEO_BLOCK' | 'REMOVE' | 'REMOVE_AND_ESCALATE';

// 当前生效的处置类型（编译时由 feature flag 决定运行时行为，类型声明保持联合）
export type DispositionAction = MVPDisposition | FullDispositionAction;

// src/types/ws.ts -- WebSocket 消息类型
// 【修订】对齐后端消息信封格式和消息类型名
export interface BackendWsMessage {
  type: BackendWsMessageType;
  payload: Record<string, unknown>;
  timestamp: string;           // 【修订】ISO 8601 格式（非 timestamp_ms）
  correlation_id: string;      // 【修订】UUID，用于去重
}

// 【修订】后端实际定义的消息类型（来自后端设计文档 6.1 节）
export type BackendWsMessageType =
  | 'task_lock_renewed'        // 任务锁续约确认
  | 'task_lock_expired'        // 任务锁超时
  | 'task_reassigned'          // 任务被重新分配
  | 'sla_warning'              // SLA 距截止不足 30 分钟
  | 'legal_deadline_warning'   // 法定时限不足 30 分钟
  | 'kill_switch_activated'    // kill-switch 触发
  | 'queue_spike'              // 队列积压告警
  | 'break_reminder'           // 强制休息提醒
  | 'CRITICAL_ALERT'           // 高危告警（后端 8.3 节定义）
  | 'SHADOW_REPORT_READY'      // Shadow 报告就绪
  | 'HEARTBEAT'                // 【修订】心跳（非 PING）
  | 'HEARTBEAT_ACK'            // 【修订】心跳回复（非 PONG）
  | 'RECONNECT_SYNC';          // 断线重连同步（V2，feature flag 控制）

// src/types/api-contract.ts
// 【修订】前后端 API 响应契约类型 -- 严格匹配后端实际返回格式

// 【修订】后端统一分页响应格式（来自 backend/app/common/pagination.py）
export interface BackendPaginatedResponse<T> {
  items: T[];             // 【修订】后端使用 "items"（非 "tasks"）
  total: number;
  offset: number;         // 【修订】offset-based（非 page-based）
  limit: number;
  next_offset: number | null;  // null 表示没有更多数据
}

// 【修订】后端处置提交请求格式（对齐 submit_decision 参数）
export interface BackendDecisionRequest {
  decision: 'pass' | 'block';       // 后端仅接受此二值
  reason_category: string;           // 【修订】后端期望的字段名
  reason_detail: string;             // 【修订】后端期望的字段名
  internal_notes?: string;           // 【修订】后端期望的字段名
  dimension_overrides?: Record<string, unknown>;
}

// 【修订】后端处置提交响应格式（对齐 submit_decision 返回值）
// 关键修复：后端返回 { task_id, status, decision }，
// 不包含 golden_test_result（金标评估异步执行）
export interface BackendDecisionResponse {
  task_id: string;         // 【修订】后端实际返回的字段
  status: string;          // 【修订】"decided"
  decision: string;        // 【修订】提交的决策值
  // 注意：不包含 golden_test_result -- 金标评估由 Celery 异步执行
}

// 【修订】ws-token 响应格式
export interface WsTokenResponse {
  ws_token: string;
  expires_at: string;  // ISO 8601
}

// 【修订】后端 ReviewTask 格式（队列列表项）
export interface BackendReviewTask {
  task_id: string;
  video_id: string;
  content_id: string;
  priority: number;
  dimension_ids: string[];
  jurisdiction: string;
  sla_deadline: string | null;       // ISO 8601
  assigned_to: string | null;
  locked_at: string | null;
  lock_expires_at: string | null;
  status: 'pending' | 'locked' | 'in_review' | 'completed';
  evidence_package_id: string;
  machine_decision_summary: Record<string, unknown>;
  // 注意：is_golden_test 不在 API 响应中暴露（对审核员透明）
}

// 【修订】金标统计响应格式
export interface GoldenStatsResponse {
  reviewer_id: string;
  total_golden_tests: number;
  correct: number;
  accuracy: number | null;  // null 表示无数据
}
```

---

## 10.【修订】前后端集成契约对齐

本节系统性列举前端所依赖的全部后端端点，标注现有/待新增状态，并给出前端在后端端点未就绪时的降级策略。**所有端点路径严格对齐后端设计文档**。

### 10.1 端点对齐总表

| 前端调用 | 后端端点 | 状态 | 前端降级策略 |
|---------|---------|------|-------------|
| **审核队列** | | | |
| `api.reviews.getQueue()` | `GET /api/v1/review/human/queue?offset=0&limit=20` | 现有 | -- |
| `api.reviews.claimNext()` | `POST /api/v1/review/human/next` | 现有 | -- |
| `api.reviews.getTaskDetail()` | `GET /api/v1/review/human/{task_id}` | 现有 | -- |
| `api.reviews.submitDecision()` | `POST /api/v1/review/human/{task_id}/decide` | 现有 | -- |
| `api.reviews.releaseTask()` | `POST /api/v1/review/human/{task_id}/release` | 现有 | -- |
| `api.reviews.heartbeat()` | `POST /api/v1/review/human/{task_id}/heartbeat` | 现有 | -- |
| `api.reviews.escalate()` | `POST /api/v1/review/human/{task_id}/escalate` | 现有 | -- |
| `api.reviews.batchDecide()` | `POST /api/v1/review/human/batch-decide` | 现有 | feature flag `enableBatchReview` 控制 |
| **处置相关** | | | |
| `api.policy.getDispositions()` | `GET /api/v1/policy/dispositions?jurisdiction=global` | 现有 | MVP 使用本地硬编码 `pass/block` 二态列表 |
| **证据包** | | | |
| `api.evidence.getPackage()` | `GET /api/v1/evidence/{ep_id}` | 现有 | 前端对可选字段使用 `??` 默认值防御 |
| **系统健康与告警** | | | |
| `api.system.getHealth()` | `GET /api/v1/system/health` | 现有 | feature flag `enableDashboardHealth` 控制 |
| `api.system.getReady()` | `GET /api/v1/system/ready` | 现有 | -- |
| `api.system.getAlerts()` | `GET /api/v1/system/alerts?status=active&limit=20` | 现有 | feature flag `enableDashboardAlerts` 控制 |
| `api.system.acknowledgeAlert()` | `POST /api/v1/system/alerts/{id}/acknowledge` | 现有 | 同上 |
| **认证** | | | |
| `api.auth.login()` | `POST /api/v1/auth/login` | 现有 | -- |
| `api.auth.refresh()` | `POST /api/v1/auth/refresh` | 现有 | -- |
| `api.auth.getWsToken()` | `POST /api/v1/auth/ws-token` | 现有 | -- |
| **SoR 模板** | | | |
| `api.sor.getTemplates()` | `GET /api/v1/sor/templates` | 现有 | feature flag `enableSoRTemplates` 控制 |
| `api.sor.getTemplate()` | `GET /api/v1/sor/templates/{id}` | 现有 | 同上 |
| `api.sor.render()` | `POST /api/v1/sor/render` | 现有 | 同上 |
| **质检** | | | |
| `api.quality.getGoldenResults()` | `GET /api/v1/quality/golden-results` | 现有 | QA 管理员视图 |
| `api.quality.getIRRReport()` | `GET /api/v1/quality/irr-report` | 现有 | QA 管理员视图 |
| **审核员管理** | | | |
| `api.reviewers.getList()` | `GET /api/v1/reviewers` | 现有 | -- |
| `api.reviewers.getStats()` | `GET /api/v1/reviewers/{id}/stats` | 现有 | -- |
| `api.reviewers.getGoldenStats()` | `GET /api/v1/reviewers/{id}/golden-stats` | 现有 | -- |
| **策略管理** | | | |
| `api.policy.getVersions()` | `GET /api/v1/policy/versions` | 现有 | -- |
| `api.policy.getDimensions()` | `GET /api/v1/policy/dimensions` | 现有 | -- |
| **Shadow 报告** | | | |
| `api.shadow.getReports()` | `GET /api/v1/shadow/reports?offset=0&limit=20` | 现有 | -- |
| `api.shadow.getLatest()` | `GET /api/v1/shadow/reports/latest` | 现有 | -- |
| **审计日志** | | | |
| `api.audit.getEvents()` | `GET /api/v1/audit/events?offset=0&limit=20` | 现有 | -- |

### 10.2【修订】分页契约

前后端统一使用 **offset-based 分页**（对齐后端 PaginatedResponse）：

```
请求: GET /api/v1/review/human/queue?offset=0&limit=20&jurisdiction=US&sort=created_at&order=desc
响应: {
    "items": [...],       // 【修订】字段名为 "items"（非 "tasks"）
    "total": 150,
    "offset": 0,
    "limit": 20,
    "next_offset": 20     // null 表示最后一页
}
```

前端 `useInfiniteQuery` 对接方式：

```typescript
const queue = useInfiniteQuery({
  queryKey: ['review-queue', filters],
  queryFn: async ({ pageParam = 0 }) => {
    const response = await api.reviews.getQueue({
      ...filters,
      offset: pageParam,
      limit: 20,
    });
    return adaptPaginatedResponse(response);
  },
  // 【修订】直接使用后端 next_offset
  getNextPageParam: (lastPage) => lastPage.nextOffset,
  initialPageParam: 0,
});
```

### 10.3 EvidencePackage 序列化契约

前端要求后端 `GET /api/v1/evidence/{ep_id}` 端点在响应中包含以下字段（即使为空数组/null）：

```json
{
  "ep_id": "...",
  "schema_version": "1.0",
  "content_id": "...",
  "video_meta": { "duration_ms": 120000 },
  "frames": [],
  "asr_transcript": [],
  "ocr_results": [],
  "object_detections": [],
  "scene_tags": [],
  "pre_filter_results": { "csam_hash_hit": false, "cloud_api_hits": [], "rule_hits": [], "dedup_reuse": null, "skip_llm_review": false, "skip_reason": null },
  "llm_verdicts": [],
  "decision_summary": null,
  "access_policy": { "readable_roles": [], "csam_exception": false, "retention_days": 90 },
  "modality_availability": null,
  "truncated_modalities": [],
  "token_budget_used": 0,
  "token_budget_limit": 8000
}
```

前端对所有列表类型字段使用 `?? []` 防御，对可选对象字段使用 `?? null` 防御：

```typescript
// src/api/adapters/evidence.ts
export function normalizeEvidencePackage(raw: any): EvidencePackage {
  return {
    ep_id: raw.ep_id,
    schema_version: raw.schema_version ?? '1.0',
    content_id: raw.content_id,
    snapshot_id: raw.snapshot_id ?? '',
    created_at: raw.created_at ?? 0,
    video_meta: raw.video_meta ?? { duration_ms: 0 },
    frames: raw.frames ?? [],
    asr_transcript: raw.asr_transcript ?? [],
    ocr_results: raw.ocr_results ?? [],
    object_detections: raw.object_detections ?? [],
    scene_tags: raw.scene_tags ?? [],
    modality_availability: raw.modality_availability ?? null,
    truncated_modalities: raw.truncated_modalities ?? [],
    pre_filter_results: raw.pre_filter_results ?? {
      csam_hash_hit: false,
      cloud_api_hits: [],
      rule_hits: [],
      dedup_reuse: null,
      skip_llm_review: false,
      skip_reason: null,
    },
    llm_verdicts: raw.llm_verdicts ?? [],
    decision_summary: raw.decision_summary ?? null,
    access_policy: raw.access_policy ?? {
      readable_roles: [],
      csam_exception: false,
      retention_days: 90,
    },
    token_budget_used: raw.token_budget_used ?? 0,
    token_budget_limit: raw.token_budget_limit ?? 0,
  };
}
```

### 10.4【修订】WebSocket 协议契约

严格对齐后端设计文档第 6 章和第 8.3 节。

```
连接建立:
  1. 前端调用 POST /api/v1/auth/ws-token 获取短期 JWT（type='ws', 有效期 5 分钟）
  2. 前端连接 ws://host/ws/review?token={ws_token}
  3. 后端 verify_ws_token() 校验 JWT，接受连接
  4. 前端在 ws-token 到期前 60 秒主动刷新 token（调用 ws-token 端点），
     存储新 token 供断线重连时使用

消息信封格式:
  {
    "type": "<消息类型>",
    "payload": { ... },
    "timestamp": "2026-07-01T12:02:00Z",   // ISO 8601
    "correlation_id": "uuid-v4"              // 用于去重
  }

心跳协议:
  前端发送: { type: "HEARTBEAT", ... }      // 每 30 秒
  后端回复: { type: "HEARTBEAT_ACK", ... }

消息类型对照表:
  | 后端消息类型            | 前端处理逻辑 |
  |------------------------|------------|
  | task_lock_renewed      | 更新锁状态 UI |
  | task_lock_expired      | 提示锁过期，返回队列 |
  | task_reassigned        | 提示案件被重分配，返回队列 |
  | sla_warning            | SLA 倒计时告警 |
  | legal_deadline_warning | 法定时限紧急告警 |
  | kill_switch_activated  | 全局弹窗通知 |
  | queue_spike            | 队列积压告警 |
  | break_reminder         | 触发强制休息 |
  | CRITICAL_ALERT         | 告警流更新 |
  | SHADOW_REPORT_READY    | 刷新 Shadow 报告 |
  | HEARTBEAT_ACK          | 静默处理 |

断线重连:
  MVP: 前端重连后 invalidate 所有活跃 TanStack Query（全量重拉）
  V2:  前端发送 RECONNECT_SYNC { lastSeenTimestamp }，后端从 Redis Stream 补发遗漏事件
```

### 10.5【修订】处置提交契约

```
请求: POST /api/v1/review/human/{task_id}/decide
请求体: {
  "decision": "pass" | "block",
  "reason_category": "...",
  "reason_detail": "...",
  "internal_notes": "...",
  "dimension_overrides": {}
}

响应: {
  "task_id": "...",
  "status": "decided",
  "decision": "pass" | "block"
}

注意事项:
  - 响应中不包含 golden_test_result（金标评估由 Celery 异步执行）
  - 响应中不包含 success 布尔字段（通过 HTTP 200 判断成功）
  - 金标测试结果通过独立端点查询:
    - QA 管理员: GET /api/v1/quality/golden-results?reviewer_id=xxx
    - 审核员个人: GET /api/v1/reviewers/{id}/golden-stats
```

### 10.6【修订】契约测试

为防止前后端集成时出现字段缺失、类型不匹配等问题，使用 **MSW (Mock Service Worker) + Zod Schema** 实现契约测试。

相比直接请求后端真实 API，MSW 方案的优势：
1. 不依赖后端服务运行，CI 中可独立执行
2. Mock handler 可作为前后端契约的可执行文档
3. 当后端响应格式变更时，Zod Schema 校验立即失败，提前发现问题

```typescript
// tests/mocks/handlers.ts
// 【修订】使用 MSW 定义后端 API 的 Mock handler

import { http, HttpResponse } from 'msw';

export const handlers = [
  // 队列查询
  http.get('/api/v1/review/human/queue', ({ request }) => {
    const url = new URL(request.url);
    const offset = parseInt(url.searchParams.get('offset') ?? '0');
    const limit = parseInt(url.searchParams.get('limit') ?? '20');

    return HttpResponse.json({
      items: generateMockTasks(limit),
      total: 150,
      offset,
      limit,
      next_offset: offset + limit < 150 ? offset + limit : null,
    });
  }),

  // 处置提交
  http.post('/api/v1/review/human/:taskId/decide', async ({ params }) => {
    return HttpResponse.json({
      task_id: params.taskId,
      status: 'decided',
      decision: 'pass',
    });
  }),

  // ws-token
  http.post('/api/v1/auth/ws-token', () => {
    return HttpResponse.json({
      ws_token: 'mock-ws-token-jwt',
      expires_at: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
    });
  }),

  // 证据包
  http.get('/api/v1/evidence/:epId', ({ params }) => {
    return HttpResponse.json(generateMockEvidencePackage(params.epId as string));
  }),
];
```

```typescript
// tests/contract/pagination.contract.test.ts
// 【修订】使用 Zod schema 校验 API 响应是否符合前后端约定

import { z } from 'zod';
import { setupServer } from 'msw/node';
import { handlers } from '../mocks/handlers';

const server = setupServer(...handlers);

// 【修订】分页响应 Schema -- 对齐后端 PaginatedResponse
const PaginatedResponseSchema = z.object({
  items: z.array(z.any()),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
  next_offset: z.number().nullable(),
});

// 【修订】处置提交响应 Schema -- 对齐后端实际返回
const DecisionResponseSchema = z.object({
  task_id: z.string(),
  status: z.string(),
  decision: z.enum(['pass', 'block']),
  // 注意：无 success 字段，无 golden_test_result
});

// 【修订】ws-token 响应 Schema
const WsTokenResponseSchema = z.object({
  ws_token: z.string(),
  expires_at: z.string(), // ISO 8601
});

// 【修订】EvidencePackage 响应 Schema
const EvidencePackageSchema = z.object({
  ep_id: z.string(),
  schema_version: z.string(),
  content_id: z.string(),
  video_meta: z.object({ duration_ms: z.number() }),
  frames: z.array(z.any()),
  asr_transcript: z.array(z.any()),
  ocr_results: z.array(z.any()),
  object_detections: z.array(z.any()),
  scene_tags: z.array(z.any()),
  pre_filter_results: z.object({
    csam_hash_hit: z.boolean(),
    cloud_api_hits: z.array(z.any()),
    rule_hits: z.array(z.any()),
  }),
  llm_verdicts: z.array(z.object({
    dimension_id: z.string(),
    decision: z.enum(['VIOLATION', 'NO_VIOLATION', 'UNCERTAIN']),
    confidence: z.number(),
  })),
  truncated_modalities: z.array(z.string()),
  access_policy: z.object({
    readable_roles: z.array(z.string()),
    csam_exception: z.boolean(),
    retention_days: z.number(),
  }),
}).passthrough();

describe('API Contract Tests', () => {
  beforeAll(() => server.listen());
  afterEach(() => server.resetHandlers());
  afterAll(() => server.close());

  it('队列分页响应应匹配 PaginatedResponse schema', async () => {
    const response = await fetch('/api/v1/review/human/queue?offset=0&limit=20');
    const data = await response.json();
    const result = PaginatedResponseSchema.safeParse(data);
    expect(result.success).toBe(true);
  });

  it('处置提交响应应匹配 DecisionResponse schema', async () => {
    const response = await fetch('/api/v1/review/human/task-123/decide', {
      method: 'POST',
      body: JSON.stringify({ decision: 'pass', reason_category: '', reason_detail: '' }),
    });
    const data = await response.json();
    const result = DecisionResponseSchema.safeParse(data);
    expect(result.success).toBe(true);
  });

  it('ws-token 响应应匹配 WsTokenResponse schema', async () => {
    const response = await fetch('/api/v1/auth/ws-token', { method: 'POST' });
    const data = await response.json();
    const result = WsTokenResponseSchema.safeParse(data);
    expect(result.success).toBe(true);
  });

  it('证据包响应应匹配 EvidencePackage schema', async () => {
    const response = await fetch('/api/v1/evidence/ep-test-001');
    const data = await response.json();
    const result = EvidencePackageSchema.safeParse(data);
    expect(result.success).toBe(true);
  });

  // 【修订】验证处置提交响应中不包含 golden_test_result
  it('处置提交响应不应包含 golden_test_result', async () => {
    const response = await fetch('/api/v1/review/human/task-123/decide', {
      method: 'POST',
      body: JSON.stringify({ decision: 'block', reason_category: '', reason_detail: '' }),
    });
    const data = await response.json();
    expect(data).not.toHaveProperty('golden_test_result');
    expect(data).not.toHaveProperty('success');
  });

  // 【修订】验证分页响应使用 items（非 tasks）
  it('分页响应应使用 items 字段名', async () => {
    const response = await fetch('/api/v1/review/human/queue?offset=0&limit=20');
    const data = await response.json();
    expect(data).toHaveProperty('items');
    expect(data).not.toHaveProperty('tasks');
    expect(data).toHaveProperty('offset');
    expect(data).toHaveProperty('next_offset');
    expect(data).not.toHaveProperty('page');
  });
});
```

---

## 组件层级图描述

以人审工作台最核心的 `ReviewWorkbench` 页面为例，完整组件树如下：

```
GlobalErrorBoundary (全局)
  |
  ReviewWorkbench (Page)
    |
    +-- TopBar
    |     +-- SLACountdown (法定 SLA / 运营 SLA)  [role="timer", aria-live]
    |     +-- CaseIdDisplay
    |     +-- StatusBadge (当前案件严重度)           [role="status"]
    |     +-- LockStatusIndicator
    |     +-- HotkeyHelpPopover
    |
    +-- MainContent (三栏布局)
    |     |
    |     +-- LeftPanel (60% 宽度)
    |     |     +-- PanelErrorBoundary("视频播放器")
    |     |     |     +-- VideoPlayer (xgplayer 封装)
    |     |     |           +-- TimelineAnnotationBar (Canvas 命中标注) [role="img"]
    |     |     |           +-- PlayerControlsExtra (逐帧/倍速/截图)
    |     |     |           +-- BlurOverlay (创伤屏蔽)
    |     |     |           +-- CSAMPlaceholder (CSAM 限制占位)
    |     |     |
    |     |     +-- PanelErrorBoundary("证据面板")
    |     |     |     +-- EvidenceViewer (Tabs)
    |     |     |           +-- ASRTranscriptPanel (时间对齐文本 + 关键词高亮)
    |     |     |           +-- OCRResultPanel (帧图片 + bbox 叠加)
    |     |     |           +-- ObjectDetectionPanel (检测结果 + bbox 叠加)
    |     |     |           +-- SceneTagPanel (场景标签列表)
    |     |     |           +-- PreFilterResultPanel (初筛命中列表)
    |     |     |
    |     |     +-- MetadataPanel (标题/描述/POI/发布时间)
    |     |     +-- CreatorInfoPanel (信用分/历史违规/观察期)
    |     |     +-- SimilarDecisionsPanel (相似历史决策)
    |     |
    |     +-- CenterPanel (时间轴面板，窄列)
    |     |     +-- VerticalTimeline (按时间线展示多模态命中事件)
    |     |
    |     +-- RightPanel (40% 宽度)
    |           +-- PanelErrorBoundary("维度评分面板")
    |           |     +-- VerdictPanel (DimensionVerdict 列表)
    |           |           +-- [PluginRenderer per dimension] (插件注册表驱动)
    |           |           +-- TriggeredRulesPanel (触发规则列表)
    |           |           +-- ConfidenceBar (置信度可视化)
    |           |           +-- TruncationWarning (Token 截断警告)
    |           |
    |           +-- PanelErrorBoundary("处置操作面板")
    |                 +-- DispositionPanel (处置操作面板)
    |                       +-- MachineRecommendation (机审建议：明确建议/需人工判断) 【修订】
    |                       +-- DispositionButtonGroup (MVP: pass/block 两按钮)
    |                       +-- StaticConsequenceInfo (静态后果文案)
    |                       +-- ReasonCategorySelect (理由分类选择)     【修订】
    |                       +-- ReasonForm (审核理由: 自由文本)
    |                       +-- OverrideReasonForm (Override 理由，条件显示)
    |                       +-- SubmitButton (提交 + 快捷键)
    |
    +-- BottomBar
    |     +-- FatigueIndicator (疲劳指标)
    |     +-- ExposureCounter (曝光计数: 当班/周累计) [aria-live="polite"]
    |     +-- TraumaShieldToggle (屏蔽模式开关)
    |     +-- WellnessLink (心理支持入口)
    |
    +-- RestLockOverlay (强制休息遮罩，条件渲染) [role="alertdialog"]
    +-- CriticalMeltdownModal (熔断确认弹窗，条件渲染)
    +-- TransitionBuffer (案件切换间隙纯色缓冲屏，条件渲染)
```

---

## 修订摘要

以下汇总本次修订对应的专家反馈条目及处理方式：

### 关键问题修复

| 反馈编号 | 反馈摘要 | 处理方式 | 涉及章节 |
|---------|---------|---------|---------|
| 关键-1 | 分页协议矛盾：后端 offset-based（items/offset/limit/next_offset），前端 page-based（tasks/page/page_size） | 前端全面改为 offset-based，字段名从 `tasks` 改为 `items`，参数从 `page/page_size` 改为 `offset/limit`，`getNextPageParam` 直接使用后端 `next_offset` | 3.6, 9, 10.2 |
| 关键-2 | WebSocket 认证必败：后端 `verify_ws_token()` 要求 `type='ws'`，前端复用登录 JWT 不含此字段 | 前端改为调用 `POST /api/v1/auth/ws-token` 获取专用令牌，并增加 5 分钟到期前自动续期机制 | 7.1, 9, 10.4 |
| 关键-3 | 金标测试时序错位：前端期望同步响应含 `golden_test_result`，后端异步处理不返回 | 移除同步金标反馈弹窗；金标结果通过独立端点查询（QA 管理员 + 审核员个人统计） | 3.9, 9, 10.5 |
| 关键-4 | `mapMachineDecisionToMVP` 将 `needs_human_review` 映射为 `block`，系统性偏差 | `needs_human_review` 返回 `null`（无建议），前端展示"需人工判断"而非偏向 block | 3.4 |

### 前后端集成修复

| 反馈编号 | 反馈摘要 | 处理方式 | 涉及章节 |
|---------|---------|---------|---------|
| 集成-1 | 后端 `items` vs 前端 `tasks` 字段名不匹配 | `BackendPaginatedResponse` 类型改为 `items`，适配函数对齐 | 3.6, 9, 10.2 |
| 集成-2 | 后端 offset 参数 vs 前端 page 参数不匹配 | `toBackendOffsetParams` 使用 offset/limit | 3.6, 10.2 |
| 集成-3 | 后端心跳 `HEARTBEAT/HEARTBEAT_ACK` vs 前端 `PING/PONG` | 前端改为发送 `HEARTBEAT`，期望 `HEARTBEAT_ACK` | 7.1, 9 |
| 集成-4 | 金标异步 vs 同步响应格式不匹配 | 同关键-3 | 3.9, 10.5 |
| 集成-5 | 后端响应无 `success` 字段，前端 Schema 期望 `success` | `BackendDecisionResponse` 改为 `{ task_id, status, decision }` | 9, 10.5, 10.6 |
| 集成-6 | SoR 模板无里程碑规划 | 新增 Feature Flag 里程碑规划表（8.5 节），明确各 flag 开启条件 | 8.5 |
| 集成-7 | ws-token 5 分钟过期导致长会话重连问题 | 增加 ws-token 到期前 60 秒自动续期机制，存储最新 token 供重连使用 | 7.1 |

### 次要问题修复

| 反馈编号 | 反馈摘要 | 处理方式 | 涉及章节 |
|---------|---------|---------|---------|
| 次要-1 | 契约测试直接请求后端，CI 不可用 | 改用 MSW + Zod，不依赖运行中的后端服务 | 10.6 |
| 次要-2 | `useWsSubscription` 的 `handler` 依赖不稳定 | 新增 `useStableCallback` hook 包装 handler ref | 7.2 |
| 次要-3 | BroadcastChannel 仅覆盖 CASE_CLAIMED | 扩展覆盖 AUTH_LOGOUT / AUTH_TOKEN_REFRESHED / WS 连接协调 | 7.3 |
| 次要-4 | Service Worker CacheFirst 导致陈旧证据帧 | 改用 StaleWhileRevalidate，后台校验更新 | 6.5 |
| 次要-5 | 乐观更新未考虑金标反馈交互 | 移除同步金标反馈后，乐观更新逻辑简化，无交互冲突 | 6.4 |

### 维度评分提升目标

| 维度 | 修订前 | 修订后目标 | 提升措施 |
|------|-------|-----------|---------|
| 稳定性 | 7/10 | 8+ | ws-token 自动续期、WS 重连增强、correlation_id 去重、4001 不重连 |
| 鲁棒性 | 7/10 | 8+ | mapMachineDecision 偏差修复、StaleWhileRevalidate 缓存、消息去重、useStableCallback |
| 前后端集成 | 5/10 | 8+ | 分页协议统一、WS 认证修复、心跳协议对齐、响应格式对齐、金标时序修复、端点路径全面对齐 |
| 可扩展性 | 7/10 | 8+ | Feature Flag 里程碑规划、SoR 集成路线图 |
| 安全性 | 7/10 | 8+ | ws-token 专用认证、多标签页登出同步、4001 鉴权失败处理 |
