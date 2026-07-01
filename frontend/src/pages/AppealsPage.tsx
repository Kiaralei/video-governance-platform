import { Button, Card, Input, Message, Modal, Popconfirm, Space, Table, Tag } from '@arco-design/web-react'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Appeal } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { EmptyActionButton, EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { StatusTag } from '../components/StatusTag'

export function AppealsPage() {
  const qc = useQueryClient()
  const { hasRole } = useAuth()
  const canDecide = hasRole('appeal_reviewer', 'reviewer_t3')
  const [decideTarget, setDecideTarget] = useState<Appeal | null>(null)
  const [reason, setReason] = useState('')
  const [reasonTouched, setReasonTouched] = useState(false)

  const appeals = useQuery({
    queryKey: ['appeals'],
    queryFn: async () => (await api.get('/appeal')).data.items as Appeal[],
    refetchInterval: 15000,
  })

  const claim = useMutation({
    mutationFn: async (id: string) => (await api.post(`/appeal/${id}/claim`)).data,
    onSuccess: () => { Message.success('已领取二审'); qc.invalidateQueries({ queryKey: ['appeals'] }) },
    onError: (e: unknown) => Message.error(extractErr(e)),
  })
  const decide = useMutation({
    mutationFn: async ({ id, outcome }: { id: string; outcome: 'overturn' | 'reject' }) =>
      (await api.post(`/appeal/${id}/decide`, { outcome, reason })).data,
    onSuccess: (d) => {
      Message.success(`二审完成：${d.status}`)
      setDecideTarget(null); setReason(''); setReasonTouched(false)
      qc.invalidateQueries({ queryKey: ['appeals'] })
    },
    onError: (e: unknown) => Message.error(extractErr(e)),
  })

  const missingReason = reasonTouched && !reason.trim()

  return (
    <div className="page-stack">
      <PageHeader
        title="申诉复核"
        description="处理创作者申诉和二审裁决。改判只允许从拦截变为通过，保证不可加重。"
        meta={<Space wrap><Tag color={canDecide ? 'green' : 'gray'}>{canDecide ? '可二审' : '只读'}</Tag><Tag color="purple">不可加重原则</Tag></Space>}
        actions={<Button onClick={() => qc.invalidateQueries({ queryKey: ['appeals'] })}>刷新</Button>}
      />
      <Card title="申诉闭环">
        <Table<Appeal>
          rowKey="appeal_id"
          loading={appeals.isLoading}
          data={appeals.data || []}
          noDataElement={
            <EmptyState
              title="暂无申诉"
              description="当前没有需要二审的申诉。演示时可先通过拦截案例创建申诉，再在这里完成闭环。"
              action={<EmptyActionButton onClick={() => qc.invalidateQueries({ queryKey: ['appeals'] })}>刷新申诉</EmptyActionButton>}
            />
          }
          columns={[
            { title: '申诉ID', dataIndex: 'appeal_id', ellipsis: true, width: 180 },
            { title: '申诉人', dataIndex: 'appellant_id', ellipsis: true },
            { title: '原处置', dataIndex: 'original_decision', width: 90, render: (d: string) => <StatusTag kind="decision" value={d} /> },
            { title: '理由', dataIndex: 'appeal_reason', ellipsis: true },
            { title: '状态', dataIndex: 'status', width: 110, render: (s: string) => <StatusTag kind="appeal" value={s} /> },
            { title: '二审员', dataIndex: 'assigned_reviewer_id', render: (a: string | null) => a || '—' },
            {
              title: '操作',
              width: 150,
              render: (_: unknown, r: Appeal) =>
                canDecide ? (
                  <Space>
                    {r.status === 'open' && <Button size="small" onClick={() => claim.mutate(r.appeal_id)} loading={claim.isPending}>领取</Button>}
                    {r.status === 'in_review' && <Button size="small" type="primary" onClick={() => { setDecideTarget(r); setReasonTouched(false) }}>裁决</Button>}
                  </Space>
                ) : <Tag color="gray">无操作权限</Tag>,
            },
          ]}
        />
      </Card>
      <Modal
        visible={!!decideTarget}
        title="二审裁决（不可加重：改判只能 block→pass）"
        onCancel={() => { setDecideTarget(null); setReasonTouched(false) }}
        footer={null}
      >
        <label className="field-label" htmlFor="appeal-reason">裁决理由</label>
        <Input.TextArea
          id="appeal-reason"
          rows={4}
          placeholder="说明维持或改判依据，例如：证据不足以支持原拦截…"
          value={reason}
          onChange={(value) => { setReason(value); if (value.trim()) setReasonTouched(false) }}
          onBlur={() => setReasonTouched(true)}
        />
        {missingReason && <div className="inline-error">请填写裁决理由，作为申诉闭环凭证。</div>}
        <Space style={{ marginTop: 16 }}>
          <Popconfirm
            title="确认维持原判？"
            content="该申诉会结束，创作者侧将看到维持原判结果。"
            disabled={!reason.trim()}
            onOk={() => { if (decideTarget) decide.mutate({ id: decideTarget.appeal_id, outcome: 'reject' }) }}
          >
            <Button disabled={!reason.trim()} loading={decide.isPending}>维持原判</Button>
          </Popconfirm>
          <Popconfirm
            title="确认改判为通过？"
            content="改判会释放原拦截内容，并写入审计链。"
            disabled={!reason.trim()}
            onOk={() => { if (decideTarget) decide.mutate({ id: decideTarget.appeal_id, outcome: 'overturn' }) }}
          >
            <Button type="primary" status="danger" disabled={!reason.trim()} loading={decide.isPending}>改判为通过</Button>
          </Popconfirm>
        </Space>
      </Modal>
    </div>
  )
}

function extractErr(e: unknown): string {
  const err = e as { response?: { data?: { error?: string } } }
  return err.response?.data?.error || '操作失败'
}
