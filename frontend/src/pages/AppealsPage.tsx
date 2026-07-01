import { Button, Card, Input, Modal, Space, Table, Tag, App as AntApp } from 'antd'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Appeal } from '../api/types'
import { useAuth } from '../auth/AuthContext'

const STATUS_COLOR: Record<string, string> = {
  open: 'blue',
  in_review: 'gold',
  overturned: 'green',
  rejected: 'red',
}

export function AppealsPage() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
  const { hasRole } = useAuth()
  const canDecide = hasRole('appeal_reviewer', 'reviewer_t3')
  const [decideTarget, setDecideTarget] = useState<Appeal | null>(null)
  const [reason, setReason] = useState('')

  const appeals = useQuery({
    queryKey: ['appeals'],
    queryFn: async () => (await api.get('/appeal')).data.items as Appeal[],
    refetchInterval: 15000,
  })

  const claim = useMutation({
    mutationFn: async (id: string) => (await api.post(`/appeal/${id}/claim`)).data,
    onSuccess: () => { message.success('已领取二审'); qc.invalidateQueries({ queryKey: ['appeals'] }) },
    onError: (e: unknown) => message.error(extractErr(e)),
  })
  const decide = useMutation({
    mutationFn: async ({ id, outcome }: { id: string; outcome: 'overturn' | 'reject' }) =>
      (await api.post(`/appeal/${id}/decide`, { outcome, reason })).data,
    onSuccess: (d) => {
      message.success(`二审完成：${d.status}`)
      setDecideTarget(null); setReason('')
      qc.invalidateQueries({ queryKey: ['appeals'] })
    },
    onError: (e: unknown) => message.error(extractErr(e)),
  })

  return (
    <Card title="申诉闭环">
      <Table<Appeal>
        rowKey="appeal_id"
        loading={appeals.isLoading}
        dataSource={appeals.data || []}
        columns={[
          { title: '申诉ID', dataIndex: 'appeal_id', ellipsis: true },
          { title: '申诉人', dataIndex: 'appellant_id' },
          { title: '原处置', dataIndex: 'original_decision', render: (d: string) => <Tag color="red">{d}</Tag> },
          { title: '理由', dataIndex: 'appeal_reason', ellipsis: true },
          { title: '状态', dataIndex: 'status', render: (s: string) => <Tag color={STATUS_COLOR[s]}>{s}</Tag> },
          { title: '二审员', dataIndex: 'assigned_reviewer_id', render: (a: string | null) => a || '—' },
          {
            title: '操作',
            render: (_: unknown, r: Appeal) =>
              canDecide && (
                <Space>
                  {r.status === 'open' && <Button size="small" onClick={() => claim.mutate(r.appeal_id)}>领取</Button>}
                  {r.status === 'in_review' && <Button size="small" type="primary" onClick={() => setDecideTarget(r)}>裁决</Button>}
                </Space>
              ),
          },
        ]}
      />
      <Modal
        open={!!decideTarget}
        title="二审裁决（不可加重：改判只能 block→pass）"
        onCancel={() => setDecideTarget(null)}
        footer={[
          <Button key="reject" onClick={() => decideTarget && decide.mutate({ id: decideTarget.appeal_id, outcome: 'reject' })}>维持原判</Button>,
          <Button key="overturn" type="primary" danger onClick={() => decideTarget && decide.mutate({ id: decideTarget.appeal_id, outcome: 'overturn' })}>改判 (block→pass)</Button>,
        ]}
      >
        <Input.TextArea rows={4} placeholder="裁决理由（必填）" value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </Card>
  )
}

function extractErr(e: unknown): string {
  const err = e as { response?: { data?: { error?: string } } }
  return err.response?.data?.error || '操作失败'
}
