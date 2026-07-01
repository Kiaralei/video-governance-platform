import { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Col, Descriptions, Empty, Input, Row, Space, Table, Tag, Typography, App as AntApp, Statistic,
} from 'antd'
import { CheckCircleOutlined, StopOutlined, RightCircleOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { CaseDetail, DimensionVerdict, ReviewTask } from '../api/types'
import { SLACountdown } from '../components/SLACountdown'

const RECO_COLOR: Record<string, string> = { block: 'red', pass: 'green', uncertain: 'gold' }

function VerdictTable({ verdicts }: { verdicts: DimensionVerdict[] }) {
  return (
    <Table<DimensionVerdict>
      size="small"
      rowKey="dimension_id"
      pagination={false}
      dataSource={verdicts}
      columns={[
        { title: '维度', dataIndex: 'dimension_name' },
        {
          title: '判定',
          dataIndex: 'decision',
          render: (d: string) => (
            <Tag color={d === 'VIOLATION' ? 'red' : d === 'NO_VIOLATION' ? 'green' : 'gold'}>{d}</Tag>
          ),
        },
        { title: '置信度', dataIndex: 'confidence', render: (c: number) => c.toFixed(2) },
        { title: '理由', dataIndex: 'reason', ellipsis: true },
      ]}
    />
  )
}

export function ReviewWorkbench() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const [current, setCurrent] = useState<CaseDetail | null>(null)
  const [reason, setReason] = useState('')

  const queue = useQuery<ReviewTask[]>({
    queryKey: ['queue'],
    queryFn: async () => (await api.get('/review/human/queue')).data.items,
    refetchInterval: 15000,
  })

  const fetchNext = useMutation({
    mutationFn: async () => (await api.post('/review/human/next')).data,
    onSuccess: (data) => {
      if (data.status === 'assigned') {
        setCurrent(data as CaseDetail)
        setReason('')
      } else if (data.status === 'break_required') {
        message.warning('已达强制休息阈值，请稍后再领取')
      } else {
        message.info('暂无待审案件')
      }
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: () => message.error('领取失败'),
  })

  const openCase = useMutation({
    mutationFn: async (taskId: string) => (await api.post(`/review/human/${taskId}/claim`)).data,
    onSuccess: (data) => { setCurrent(data as CaseDetail); setReason('') },
    onError: (e: unknown) => message.error(`领取失败：${extractErr(e)}`),
  })

  const decide = useMutation({
    mutationFn: async ({ taskId, decision }: { taskId: string; decision: 'pass' | 'block' }) =>
      (await api.post(`/review/human/${taskId}/decide`, { decision, reason })).data,
    onSuccess: (data) => {
      if (data.golden_test_result) {
        const g = data.golden_test_result
        message[g.is_correct ? 'success' : 'error'](`黄金题：${g.is_correct ? '答对' : '答错'}（应为 ${g.expected_decision}）`)
      } else {
        message.success(`已裁定：${data.decision}`)
      }
      setCurrent(null)
      setReason('')
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (e: unknown) => message.error(`裁定失败：${extractErr(e)}`),
  })

  const submitDecision = useCallback(
    (decision: 'pass' | 'block') => {
      if (!current) return
      if (!reason.trim()) { message.warning('请填写裁定理由'); return }
      decide.mutate({ taskId: current.task.task_id, decision })
    },
    [current, reason, decide, message],
  )

  // 快捷键：P=通过 B=拦截 N=下一个。输入框聚焦时不触发。
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.key.toLowerCase() === 'p') submitDecision('pass')
      else if (e.key.toLowerCase() === 'b') submitDecision('block')
      else if (e.key.toLowerCase() === 'n') fetchNext.mutate()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [submitDecision, fetchNext])

  return (
    <Row gutter={16}>
      <Col span={7}>
        <Card
          title={`待审队列（${queue.data?.length ?? 0}）`}
          extra={<Button type="primary" icon={<RightCircleOutlined />} onClick={() => fetchNext.mutate()}>领取下一个 (N)</Button>}
        >
          <Table<ReviewTask>
            size="small"
            rowKey="task_id"
            loading={queue.isLoading}
            dataSource={queue.data || []}
            pagination={false}
            onRow={(r) => ({ onClick: () => openCase.mutate(r.task_id), style: { cursor: 'pointer' } })}
            columns={[
              { title: '优先级', dataIndex: 'priority', width: 70, render: (p: number) => <Tag color={p <= 2 ? 'red' : p <= 3 ? 'orange' : 'default'}>{p}</Tag> },
              { title: '标题', dataIndex: 'title', ellipsis: true },
              { title: '机审', dataIndex: 'machine_recommendation', width: 72, render: (r: string) => <Tag color={RECO_COLOR[r] || 'default'}>{r || '—'}</Tag> },
            ]}
          />
        </Card>
      </Col>
      <Col span={17}>
        {!current ? (
          <Card><Empty description="从左侧队列选择案件，或按 N 领取下一个。快捷键：P 通过 · B 拦截 · N 下一个" /></Card>
        ) : (
          <Card
            title={<Space>一屏决策<Tag color="blue">{current.task.task_id}</Tag>{current.task.is_sensitive && <Tag color="red">敏感</Tag>}</Space>}
            extra={<SLACountdown deadline={current.task.sla_deadline} />}
          >
            <Row gutter={16}>
              <Col span={14}>
                <Descriptions size="small" column={1} bordered>
                  <Descriptions.Item label="标题">{current.content.title}</Descriptions.Item>
                  <Descriptions.Item label="简介">{current.content.description}</Descriptions.Item>
                  <Descriptions.Item label="创作者">{current.content.creator_id}</Descriptions.Item>
                  <Descriptions.Item label="挂载地点">{current.content.poi}</Descriptions.Item>
                </Descriptions>
                <Typography.Title level={5} style={{ marginTop: 16 }}>机审维度判定</Typography.Title>
                <VerdictTable verdicts={current.machine_review.verdicts} />
              </Col>
              <Col span={10}>
                <Card size="small" title="机审建议">
                  <Statistic
                    title="推荐"
                    value={current.machine_review.recommendation || 'uncertain'}
                    valueStyle={{ color: current.machine_review.recommendation === 'block' ? '#cf1322' : current.machine_review.recommendation === 'pass' ? '#3f8600' : '#d48806' }}
                  />
                  <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>{current.machine_review.rationale}</Typography.Paragraph>
                </Card>
                <Input.TextArea
                  style={{ marginTop: 16 }}
                  rows={4}
                  placeholder="裁定理由（必填）"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <Space style={{ marginTop: 16 }}>
                  <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => submitDecision('pass')} loading={decide.isPending}>通过 (P)</Button>
                  <Button danger icon={<StopOutlined />} onClick={() => submitDecision('block')} loading={decide.isPending}>拦截 (B)</Button>
                </Space>
              </Col>
            </Row>
          </Card>
        )}
      </Col>
    </Row>
  )
}

function extractErr(e: unknown): string {
  const err = e as { response?: { data?: { error?: string } } }
  return err.response?.data?.error || '请求失败'
}
