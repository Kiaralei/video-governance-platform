import { Button, Card, Message, Progress, Space, Statistic, Table, Tag, Tooltip } from '@arco-design/web-react'
import { IconPlayArrow, IconRefresh } from '@arco-design/web-react/icon'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { DashboardSummary, DemoCasesResponse, DimensionVerdict, MachineReviewRow } from '../api/types'
import { PageHeader } from '../components/PageHeader'
import { StatusTag, statusMeta } from '../components/StatusTag'

function TaskStatus({ row }: { row: MachineReviewRow }) {
  if (row.task_status) return <StatusTag kind="task" value={row.task_status} />
  if (row.final_decision) return <Tag color="arcoblue">机审终局</Tag>
  return <Tag color="gray">未路由</Tag>
}

function VerdictTags({ verdicts }: { verdicts: DimensionVerdict[] }) {
  const visible = verdicts.slice(0, 3)
  return (
    <div className="status-line">
      {visible.map((v) => (
        <Tooltip key={v.dimension_id} content={v.reason}>
          <Tag color={statusMeta('verdict', v.decision).color}>
            {v.dimension_name}:{statusMeta('verdict', v.decision).label}
          </Tag>
        </Tooltip>
      ))}
      {verdicts.length > visible.length && <Tooltip content={verdicts.slice(visible.length).map((v) => `${v.dimension_name}: ${statusMeta('verdict', v.decision).label}`).join(' / ')}><Tag color="gray">+{verdicts.length - visible.length}</Tag></Tooltip>}
    </div>
  )
}

function ruleLabel(rule: string) {
  const [dimension, decision] = rule.split(':')
  const dimensionName: Record<string, string> = {
    dim_general_policy: '通用策略',
    dim_gambling: '博彩/彩票',
    dim_drug_violence: '毒品/暴力',
    dim_minor_compliance: '未成年合规',
    dim_poi_match: 'POI 一致性',
    dim_marketing_review: '营销导流',
  }
  return `${dimensionName[dimension] || dimension}:${statusMeta('policy', decision).label}`
}

export function MachineMonitor() {
  const qc = useQueryClient()
  const summary = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => (await api.get<DashboardSummary>('/dashboard/summary')).data,
    refetchInterval: 10000,
  })
  const reviews = useQuery({
    queryKey: ['machine-reviews'],
    queryFn: async () => (await api.get('/machine/reviews')).data.items as MachineReviewRow[],
    refetchInterval: 10000,
  })
  const demo = useMutation({
    mutationFn: async () => (await api.post<DemoCasesResponse>('/dev/demo-cases')).data,
    onSuccess: (data) => {
      const human = data.items.filter((item) => item.policy_decision === 'needs_human_review').length
      const blocked = data.items.filter((item) => item.final_decision === 'block').length
      const passed = data.items.filter((item) => item.final_decision === 'pass').length
      Message.success(`已注入 ${data.total} 条演示案例：${blocked} 拦截 / ${human} 人审 / ${passed} 通过`)
      qc.invalidateQueries({ queryKey: ['dashboard'] })
      qc.invalidateQueries({ queryKey: ['machine-reviews'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (e: unknown) => Message.error(extractErr(e)),
  })

  const s = summary.data
  const pipeline = s?.pipeline
  const totalJobs = pipeline ? pipeline.queued + pipeline.processing + pipeline.completed + pipeline.failed : 0
  const updatedAtMs = Math.max(summary.dataUpdatedAt || 0, reviews.dataUpdatedAt || 0)
  const updatedAt = updatedAtMs
    ? new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date(updatedAtMs))
    : '尚未刷新'
  const hasLoadError = summary.isError || reviews.isError

  return (
    <div className="page-stack">
      <PageHeader
        title="机审监控"
        description="跟踪机器审核、特征提取和最终路由。明确通过/拦截由机审终局，只有不确定内容进入人审。"
        meta={<Space wrap><Tag color="arcoblue">今日视图</Tag><span>最后成功刷新 {updatedAt}</span>{hasLoadError && <Tag color="red">刷新失败</Tag>}</Space>}
        actions={
          <>
          <Button icon={<IconRefresh />} onClick={() => { summary.refetch(); reviews.refetch() }}>刷新</Button>
          <Button
            type="primary"
            icon={<IconPlayArrow />}
            loading={demo.isPending}
            onClick={() => demo.mutate()}
          >
            注入演示案例
          </Button>
          </>
        }
      />

      <div className="metric-grid">
        <Card className="metric-card"><Statistic title="内容总量" value={s?.total_content ?? 0} /></Card>
        <Card className="metric-card"><Statistic title="待人审" value={s?.queue.pending ?? 0} styleValue={{ color: '#ff7d00' }} /></Card>
        <Card className="metric-card"><Statistic title="机审/终局通过" value={s?.decisions.pass ?? 0} styleValue={{ color: '#00a870' }} /></Card>
        <Card className="metric-card"><Statistic title="机审/终局拦截" value={s?.decisions.block ?? 0} styleValue={{ color: '#f53f3f' }} /></Card>
      </div>

      <div className="panel-grid">
        <Card title="流水线状态">
          {pipeline && (
            <>
              <Progress percent={totalJobs ? Math.round((pipeline.completed / totalJobs) * 100) : 0} />
              <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)', marginTop: 12 }}>
                <Statistic title="排队" value={pipeline.queued} />
                <Statistic title="处理中" value={pipeline.processing} />
                <Statistic title="完成" value={pipeline.completed} />
                <Statistic title="失败" value={pipeline.failed} styleValue={{ color: pipeline.failed ? '#f53f3f' : undefined }} />
              </div>
            </>
          )}
        </Card>
        <Card title="处置口径">
          <div className="evidence-list">
            <Tooltip content="auto_pass">
              <div className="evidence-item"><StatusTag kind="policy" value="auto_pass" /> 直接发布/通过，不创建人审任务</div>
            </Tooltip>
            <Tooltip content="auto_block / critical_escalate">
              <div className="evidence-item"><StatusTag kind="policy" value="auto_block" /> / <StatusTag kind="policy" value="critical_escalate" /> 直接拦截，不创建人审任务</div>
            </Tooltip>
            <Tooltip content="needs_human_review">
              <div className="evidence-item"><StatusTag kind="policy" value="needs_human_review" /> 进入人工队列，由审核员二次裁定</div>
            </Tooltip>
          </div>
        </Card>
        <Card title="特征源">
          <div className="status-line">
            <Tag color="arcoblue">ASR</Tag>
            <Tag color="arcoblue">OCR</Tag>
            <Tag color="arcoblue">Vision</Tag>
            <Tag color="green">LLM gpt-5.5</Tag>
          </div>
        </Card>
      </div>

      <Card title="最新机审结果">
        <Table<MachineReviewRow>
          rowKey="content_id"
          loading={reviews.isLoading}
          data={reviews.data || []}
          pagination={{ pageSize: 8 }}
          columns={[
            { title: '标题', dataIndex: 'title', ellipsis: true, width: 220 },
            {
              title: '机审建议',
              dataIndex: 'recommendation',
              width: 100,
              render: (r) => <StatusTag kind="decision" value={String(r || '')} />,
            },
            {
              title: '最终处置',
              dataIndex: 'final_decision',
              width: 110,
              render: (d, row) => d ? <StatusTag kind="decision" value={String(d)} /> : <TaskStatus row={row} />,
            },
            {
              title: '策略决策',
              width: 140,
              render: (_, row) => {
                const policy = row.decision_summary?.final_decision || '—'
                return <StatusTag kind="policy" value={policy} />
              },
            },
            { title: '风险分', dataIndex: 'confidence', width: 90, align: 'right', render: (c) => <span className="num-cell">{(Number(c ?? 0)).toFixed(2)}</span> },
            { title: '人审状态', width: 110, render: (_, row) => <TaskStatus row={row} /> },
            {
              title: '分类/标签',
              width: 360,
              render: (_, row) => <VerdictTags verdicts={row.verdicts || []} />,
            },
            {
              title: '命中规则',
              width: 260,
              render: (_, row) => (
                <Space wrap>
                  {(row.decision_summary?.triggered_rules || []).slice(0, 3).map((r) => (
                    <Tooltip key={r} content={r}><Tag color="purple">{ruleLabel(r)}</Tag></Tooltip>
                  ))}
                  {!row.decision_summary?.triggered_rules?.length && <Tag color="gray">无</Tag>}
                </Space>
              ),
            },
          ]}
          rowClassName={(record) => {
            const policy = record.decision_summary?.final_decision
            if (policy === 'critical_escalate' || policy === 'auto_block') return 'risk-row-critical'
            if (policy === 'needs_human_review') return 'risk-row-review'
            return ''
          }}
        />
      </Card>
    </div>
  )
}

function extractErr(e: unknown): string {
  const err = e as { response?: { data?: { error?: string } } }
  return err.response?.data?.error || '演示案例注入失败'
}
