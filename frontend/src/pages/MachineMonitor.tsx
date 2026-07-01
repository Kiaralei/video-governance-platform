import { Card, Col, Row, Statistic, Table, Tag, Progress } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { DashboardSummary } from '../api/types'

interface MachineReviewRow {
  content_id: string
  title: string
  recommendation: string | null
  confidence: number
  task_status: string
}

const RECO_COLOR: Record<string, string> = { block: 'red', pass: 'green', uncertain: 'gold' }

export function MachineMonitor() {
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

  const s = summary.data
  const pipeline = s?.pipeline
  const totalJobs = pipeline ? pipeline.queued + pipeline.processing + pipeline.completed + pipeline.failed : 0

  return (
    <>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="内容总量" value={s?.total_content ?? 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="人审待处理" value={s?.queue.pending ?? 0} valueStyle={{ color: '#d48806' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="通过" value={s?.decisions.pass ?? 0} valueStyle={{ color: '#3f8600' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="拦截" value={s?.decisions.block ?? 0} valueStyle={{ color: '#cf1322' }} /></Card></Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={8}>
          <Card title="流水线状态">
            {pipeline && (
              <>
                <Progress percent={totalJobs ? Math.round((pipeline.completed / totalJobs) * 100) : 0} status="active" />
                <Row style={{ marginTop: 12 }}>
                  <Col span={6}><Statistic title="排队" value={pipeline.queued} /></Col>
                  <Col span={6}><Statistic title="处理中" value={pipeline.processing} /></Col>
                  <Col span={6}><Statistic title="完成" value={pipeline.completed} /></Col>
                  <Col span={6}><Statistic title="失败" value={pipeline.failed} valueStyle={{ color: pipeline.failed ? '#cf1322' : undefined }} /></Col>
                </Row>
              </>
            )}
          </Card>
        </Col>
        <Col span={16}>
          <Card title="最新机审结果">
            <Table<MachineReviewRow>
              size="small"
              rowKey="content_id"
              loading={reviews.isLoading}
              dataSource={reviews.data || []}
              columns={[
                { title: '标题', dataIndex: 'title', ellipsis: true },
                { title: '机审建议', dataIndex: 'recommendation', render: (r: string) => <Tag color={RECO_COLOR[r] || 'default'}>{r || '—'}</Tag> },
                { title: '风险分', dataIndex: 'confidence', render: (c: number) => (c ?? 0).toFixed(2) },
                { title: '任务状态', dataIndex: 'task_status', render: (t: string) => <Tag>{t}</Tag> },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </>
  )
}
