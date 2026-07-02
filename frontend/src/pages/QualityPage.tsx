import { Button, Card, Message, Space, Statistic, Table, Tag, Tooltip, Typography } from '@arco-design/web-react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, tokenStore } from '../api/client'
import type { QualitySummary } from '../api/types'
import { EmptyActionButton, EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { StatusTag } from '../components/StatusTag'

interface FlywheelRow {
  sample_id: string
  source_type: string
  source_label?: string
  source_description?: string
  error_type: string
  error_label?: string
  content_id: string
  dimension_id: string
  machine_decision: string
  human_decision: string
  final_decision: string
  quality_gate_passed: boolean
  is_correction: boolean
  created_at: string
}

const SOURCE_COLOR: Record<string, string> = {
  ground_truth: 'green',
  disagreement: 'orange',
  golden: 'blue',
  correction: 'purple',
}

function sourceTag(row: FlywheelRow) {
  const label = row.source_label || row.source_type
  const tag = <Tag color={SOURCE_COLOR[row.source_type] || 'gray'}>{label}</Tag>
  return row.source_description ? <Tooltip content={row.source_description}>{tag}</Tooltip> : tag
}

export function QualityPage() {
  const qc = useQueryClient()
  const [exporting, setExporting] = useState(false)
  const summary = useQuery({
    queryKey: ['quality-summary'],
    queryFn: async () => (await api.get<QualitySummary>('/quality/summary')).data,
    refetchInterval: 15000,
  })
  const samples = useQuery({
    queryKey: ['flywheel'],
    queryFn: async () => (await api.get('/quality/flywheel')).data.items as FlywheelRow[],
  })

  const s = summary.data
  const kappa = s?.irr.kappa

  function exportJsonl() {
    if (!(s?.passed_quality_gate ?? 0)) {
      Message.warning('暂无通过质量门的样本可导出')
      return
    }
    setExporting(true)
    fetch('/api/v1/quality/flywheel/export?only_passed=true', {
      headers: { Authorization: `Bearer ${tokenStore.get()}` },
    })
      .then((r) => {
        if (!r.ok) throw new Error('导出失败，请检查登录状态或稍后重试')
        return r.blob()
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'flywheel.jsonl'
        a.click()
        URL.revokeObjectURL(url)
        Message.success('已导出通过质量门的 JSONL 样本')
      })
      .catch((error: Error) => Message.error(error.message || '导出失败，请稍后重试'))
      .finally(() => setExporting(false))
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="质检回流"
        description="查看人审确认、人机分歧、黄金题和申诉改判沉淀的样本。"
        meta={
          <Space wrap>
            {(s?.flywheel_sources || []).map((item) => (
              <Tooltip key={item.source_type} content={item.source_description}>
                <Tag color={SOURCE_COLOR[item.source_type] || 'gray'}>{item.source_label} {item.count}</Tag>
              </Tooltip>
            ))}
          </Space>
        }
        actions={
          <>
            <Button onClick={() => { summary.refetch(); samples.refetch() }}>刷新</Button>
            <Button type="primary" onClick={exportJsonl} loading={exporting} disabled={!(s?.passed_quality_gate ?? 0)}>
              导出 JSONL
            </Button>
          </>
        }
      />
      <div className="metric-grid" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' }}>
        <Card><Statistic title="回流样本" value={s?.total_samples ?? 0} /></Card>
        <Card><Statistic title="过质量门" value={s?.passed_quality_gate ?? 0} /></Card>
        <Card><Statistic title="人审推翻率" value={((s?.human_override_rate ?? 0) * 100).toFixed(1)} suffix="%" /></Card>
        <Card><Statistic title="IRR Kappa" value={kappa === null || kappa === undefined ? '—' : kappa.toFixed(3)} styleValue={{ color: s?.irr.meets_threshold ? '#00a870' : '#ff7d00' }} /></Card>
        <Card><Statistic title="黄金题准确率" value={s?.golden.accuracy === null || s?.golden.accuracy === undefined ? '—' : (s.golden.accuracy * 100).toFixed(0)} suffix={s?.golden.accuracy != null ? '%' : ''} /></Card>
      </div>
      <Card title="数据回流样本">
        <Table<FlywheelRow>
          rowKey="sample_id"
          loading={samples.isLoading}
          data={samples.data || []}
          scroll={{ x: 1080 }}
          noDataElement={
            <EmptyState
              title="暂无回流样本"
              description="人审裁定、申诉改判或黄金题校准后会沉淀样本；通过质量门的样本可导出给模型训练。"
              action={<EmptyActionButton onClick={() => qc.invalidateQueries({ queryKey: ['flywheel'] })}>刷新样本</EmptyActionButton>}
            />
          }
          columns={[
            { title: '来源', width: 150, render: (_: unknown, r: FlywheelRow) => sourceTag(r) },
            {
              title: '错误类型',
              dataIndex: 'error_type',
              width: 120,
              render: (_: string, r: FlywheelRow) => (
                r.error_label ? <Tag color="volcano">{r.error_label}</Tag> : <Typography.Text type="secondary">—</Typography.Text>
              ),
            },
            { title: '内容 ID', dataIndex: 'content_id', width: 180, ellipsis: true },
            { title: '维度', dataIndex: 'dimension_id', width: 120 },
            { title: '机审', dataIndex: 'machine_decision', width: 95, render: (d: string) => <StatusTag kind="decision" value={d} /> },
            { title: '人审', dataIndex: 'human_decision', width: 95, render: (d: string) => <StatusTag kind="decision" value={d} /> },
            { title: '最终', dataIndex: 'final_decision', width: 95, render: (d: string) => <StatusTag kind="decision" value={d} /> },
            { title: '质量门', dataIndex: 'quality_gate_passed', width: 95, render: (p: boolean) => <Tag color={p ? 'green' : 'default'}>{p ? '通过' : '未过'}</Tag> },
            { title: '产生时间', dataIndex: 'created_at', width: 180 },
          ]}
        />
      </Card>
    </div>
  )
}
