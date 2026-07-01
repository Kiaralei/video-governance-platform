import { Button, Card, Col, Row, Statistic, Table, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { api, tokenStore } from '../api/client'
import type { QualitySummary } from '../api/types'

interface FlywheelRow {
  sample_id: string
  source_type: string
  error_type: string
  machine_decision: string
  human_decision: string
  quality_gate_passed: boolean
}

const SOURCE_COLOR: Record<string, string> = {
  ground_truth: 'green',
  disagreement: 'orange',
  golden: 'blue',
  correction: 'purple',
}

export function QualityPage() {
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
    // 直接带 token 打开导出（后端返回 ndjson）。
    fetch('/api/v1/quality/flywheel/export?only_passed=true', {
      headers: { Authorization: `Bearer ${tokenStore.get()}` },
    })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'flywheel.jsonl'
        a.click()
        URL.revokeObjectURL(url)
      })
  }

  return (
    <>
      <Row gutter={16}>
        <Col span={5}><Card><Statistic title="回流样本" value={s?.total_samples ?? 0} /></Card></Col>
        <Col span={5}><Card><Statistic title="过质量门" value={s?.passed_quality_gate ?? 0} /></Card></Col>
        <Col span={5}><Card><Statistic title="人审推翻率" value={((s?.human_override_rate ?? 0) * 100).toFixed(1)} suffix="%" /></Card></Col>
        <Col span={5}>
          <Card>
            <Statistic
              title="IRR (Fleiss' κ)"
              value={kappa === null || kappa === undefined ? '—' : kappa.toFixed(3)}
              valueStyle={{ color: s?.irr.meets_threshold ? '#3f8600' : '#d48806' }}
            />
          </Card>
        </Col>
        <Col span={4}><Card><Statistic title="黄金准确率" value={s?.golden.accuracy === null || s?.golden.accuracy === undefined ? '—' : (s.golden.accuracy * 100).toFixed(0)} suffix={s?.golden.accuracy != null ? '%' : ''} /></Card></Col>
      </Row>
      <Card
        title="数据回流样本"
        style={{ marginTop: 16 }}
        extra={<Button type="primary" onClick={exportJsonl}>导出 JSONL（过质量门）</Button>}
      >
        <Table<FlywheelRow>
          rowKey="sample_id"
          loading={samples.isLoading}
          dataSource={samples.data || []}
          columns={[
            { title: '来源', dataIndex: 'source_type', render: (t: string) => <Tag color={SOURCE_COLOR[t]}>{t}</Tag> },
            { title: '错误类型', dataIndex: 'error_type', render: (t: string) => (t ? <Tag color="volcano">{t}</Tag> : '—') },
            { title: '机审', dataIndex: 'machine_decision' },
            { title: '人审', dataIndex: 'human_decision' },
            { title: '质量门', dataIndex: 'quality_gate_passed', render: (p: boolean) => <Tag color={p ? 'green' : 'default'}>{p ? '通过' : '未过'}</Tag> },
          ]}
        />
      </Card>
    </>
  )
}
