import { useState } from 'react'
import { Button, Card, Input, InputNumber, Message, Modal, Popconfirm, Space, Switch, Table, Tag, Typography } from '@arco-design/web-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Dimension } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { EmptyActionButton, EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { StatusTag, statusMeta } from '../components/StatusTag'

// 四态生命周期允许的下一步（对齐后端 VALID_STATUS_TRANSITIONS）。
const NEXT: Record<string, string[]> = {
  draft: ['shadow'],
  shadow: ['active', 'draft'],
  active: ['archived', 'shadow'],
  archived: [],
}

function axisLabel(axis: string) {
  const labels: Record<string, { text: string; color: string }> = {
    safety: { text: '内容安全', color: 'red' },
    quality: { text: '用户体验', color: 'orange' },
    business: { text: '信息匹配', color: 'arcoblue' },
  }
  return labels[axis] || { text: axis, color: 'gray' }
}

type PolicyEditDraft = {
  dimension_name: string
  enabled: boolean
  llm_review_enabled: boolean
  auto_block_threshold: number
  human_review_threshold: number
}

function toEditDraft(row: Dimension): PolicyEditDraft {
  return {
    dimension_name: row.dimension_name,
    enabled: row.enabled,
    llm_review_enabled: row.llm_review_enabled,
    auto_block_threshold: Number(row.auto_block_threshold),
    human_review_threshold: Number(row.human_review_threshold),
  }
}

function normalizeThreshold(value: number | string | null | undefined): number {
  const next = Number(value)
  if (!Number.isFinite(next)) return 0
  return Math.max(0, Math.min(1, next))
}

export function PolicyManagement() {
  const qc = useQueryClient()
  const { hasRole } = useAuth()
  const canWrite = hasRole('policy_admin', 'system_admin')
  const canApprove = canWrite
  const [editTarget, setEditTarget] = useState<Dimension | null>(null)
  const [editDraft, setEditDraft] = useState<PolicyEditDraft | null>(null)

  const dims = useQuery({
    queryKey: ['dimensions'],
    queryFn: async () => (await api.get('/policy/dimensions')).data.items as Dimension[],
  })

  const transition = useMutation({
    mutationFn: async ({ id, target }: { id: string; target: string }) =>
      (await api.post(`/policy/dimensions/${id}/transition`, { target_status: target })).data,
    onSuccess: () => { Message.success('状态已流转'); qc.invalidateQueries({ queryKey: ['dimensions'] }) },
    onError: (e: unknown) => Message.error(extractErr(e)),
  })
  const approve = useMutation({
    mutationFn: async (id: string) => (await api.post(`/policy/dimensions/${id}/approve`)).data,
    onSuccess: () => { Message.success('已审批'); qc.invalidateQueries({ queryKey: ['dimensions'] }) },
    onError: (e: unknown) => Message.error(extractErr(e)),
  })

  const update = useMutation({
    mutationFn: async ({ id, patch }: { id: string; patch: Partial<PolicyEditDraft> }) =>
      (await api.patch(`/policy/dimensions/${id}`, patch)).data,
    onSuccess: () => {
      Message.success('策略已保存')
      setEditTarget(null)
      setEditDraft(null)
      qc.invalidateQueries({ queryKey: ['dimensions'] })
    },
    onError: (e: unknown) => Message.error(extractErr(e)),
  })

  const openEditor = (row: Dimension) => {
    setEditTarget(row)
    setEditDraft(toEditDraft(row))
  }

  const updateDraft = <K extends keyof PolicyEditDraft>(key: K, value: PolicyEditDraft[K]) => {
    setEditDraft((draft) => draft ? { ...draft, [key]: value } : draft)
  }

  const saveEditor = () => {
    if (!editTarget || !editDraft) return
    const patch: Partial<PolicyEditDraft> = editTarget.status === 'active'
      ? { dimension_name: editDraft.dimension_name }
      : editDraft
    const original = editTarget as unknown as Record<string, unknown>
    const hasChanges = Object.entries(patch).some(([key, value]) => original[key] !== value)
    if (!hasChanges) {
      Message.info('没有检测到变更')
      return
    }
    update.mutate({ id: editTarget.dimension_id, patch })
  }

  return (
    <div className="page-stack">
      <PageHeader
        title="策略管理"
        description="管理审核维度、审批状态和发布流转。策略变更会影响后续机审路由。"
        meta={<Space wrap><Tag color={canWrite ? 'green' : 'gray'}>{canWrite ? '可编辑' : '只读'}</Tag><Tag color={canApprove ? 'arcoblue' : 'gray'}>{canApprove ? '可审批' : '无审批权限'}</Tag></Space>}
        actions={<Button onClick={() => qc.invalidateQueries({ queryKey: ['dimensions'] })}>刷新</Button>}
      />
      <Card title="策略维度注册表">
        <Table<Dimension>
          rowKey="dimension_id"
          loading={dims.isLoading}
          data={dims.data || []}
          noDataElement={
            <EmptyState
              title="暂无策略维度"
              description="启动服务时会自动注册默认策略；如果这里为空，请检查迁移或重新加载策略。"
              action={<EmptyActionButton onClick={() => qc.invalidateQueries({ queryKey: ['dimensions'] })}>重新加载</EmptyActionButton>}
            />
          }
          columns={[
            { title: '维度', dataIndex: 'dimension_name', width: 150 },
            { title: 'ID', dataIndex: 'dimension_id', ellipsis: true },
            { title: '轴', dataIndex: 'dimension_axis', width: 110, render: (a: string) => {
              const axis = axisLabel(a)
              return <Tag color={axis.color}>{axis.text}</Tag>
            } },
            { title: '状态', dataIndex: 'status', width: 110, render: (s: string) => <StatusTag kind="lifecycle" value={s} /> },
            { title: '启用', dataIndex: 'enabled', width: 80, render: (e: boolean) => <Tag color={e ? 'green' : 'gray'}>{e ? '启用' : '停用'}</Tag> },
            { title: '拦截阈值', dataIndex: 'auto_block_threshold', width: 100, align: 'right', render: (v: number) => <span className="num-cell">{Number(v).toFixed(2)}</span> },
            { title: '人审阈值', dataIndex: 'human_review_threshold', width: 100, align: 'right', render: (v: number) => <span className="num-cell">{Number(v).toFixed(2)}</span> },
            { title: '审批人', dataIndex: 'approved_by', render: (a: string | null) => a || '—' },
            {
              title: '操作',
              width: 340,
              render: (_: unknown, r: Dimension) => (
                <Space wrap>
                  {canWrite && (
                    <Button size="small" type="primary" onClick={() => openEditor(r)}>
                      编辑
                    </Button>
                  )}
                  {canApprove && !r.approved_by && (
                    <Popconfirm
                      title={`确认审批 ${r.dimension_name}？`}
                      content="审批后该维度才允许进入发布流转。"
                      onOk={() => approve.mutate(r.dimension_id)}
                    >
                      <Button size="small" loading={approve.isPending}>审批</Button>
                    </Popconfirm>
                  )}
                  {canWrite &&
                    NEXT[r.status]?.map((target) => (
                      <Popconfirm
                        key={target}
                        title={`确认将 ${r.dimension_name} 流转为 ${statusMeta('lifecycle', target).label}？`}
                        content={`当前状态：${statusMeta('lifecycle', r.status).label}。策略状态变化会影响后续机审配置。`}
                        onOk={() => transition.mutate({ id: r.dimension_id, target })}
                      >
                        <Button size="mini" type={target === 'active' ? 'primary' : 'default'} loading={transition.isPending}>
                          {statusMeta('lifecycle', target).label}
                        </Button>
                      </Popconfirm>
                    ))}
                  {!canWrite && !canApprove && <Tag color="gray">无操作权限</Tag>}
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Modal
        title={editTarget ? `编辑策略：${editTarget.dimension_name}` : '编辑策略'}
        visible={!!editTarget && !!editDraft}
        confirmLoading={update.isPending}
        okText="保存"
        cancelText="取消"
        onOk={saveEditor}
        onCancel={() => { setEditTarget(null); setEditDraft(null) }}
        unmountOnExit
      >
        {editDraft && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {editTarget?.status === 'active' && (
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                active 策略的阈值和启用状态已冻结；如需调整，请先流转到 shadow，保存后重新审批上线。
              </Typography.Paragraph>
            )}
            <div className="kv-grid">
              <div className="label">策略名称</div>
              <Input
                value={editDraft.dimension_name}
                onChange={(value) => updateDraft('dimension_name', value)}
              />
              <div className="label">启用</div>
              <Switch
                checked={editDraft.enabled}
                disabled={editTarget?.status === 'active'}
                onChange={(checked) => updateDraft('enabled', Boolean(checked))}
              />
              <div className="label">LLM 复核</div>
              <Switch
                checked={editDraft.llm_review_enabled}
                disabled={editTarget?.status === 'active'}
                onChange={(checked) => updateDraft('llm_review_enabled', Boolean(checked))}
              />
              <div className="label">自动拦截阈值</div>
              <InputNumber
                min={0}
                max={1}
                step={0.01}
                precision={2}
                value={editDraft.auto_block_threshold}
                disabled={editTarget?.status === 'active'}
                style={{ width: '100%' }}
                onChange={(value) => updateDraft('auto_block_threshold', normalizeThreshold(value))}
              />
              <div className="label">进入人审阈值</div>
              <InputNumber
                min={0}
                max={1}
                step={0.01}
                precision={2}
                value={editDraft.human_review_threshold}
                disabled={editTarget?.status === 'active'}
                style={{ width: '100%' }}
                onChange={(value) => updateDraft('human_review_threshold', normalizeThreshold(value))}
              />
            </div>
          </Space>
        )}
      </Modal>
    </div>
  )
}

function extractErr(e: unknown): string {
  if (e instanceof Error) return e.message
  const err = e as { response?: { data?: { error?: string; detail?: string } } }
  return err.response?.data?.detail || err.response?.data?.error || '操作失败'
}
