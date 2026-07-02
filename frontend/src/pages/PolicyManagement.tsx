import { useState } from 'react'
import {
  Button,
  Card,
  Input,
  InputNumber,
  Message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from '@arco-design/web-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Dimension } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { EmptyActionButton, EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { StatusTag, statusMeta } from '../components/StatusTag'

const NEXT: Record<string, string[]> = {
  draft: ['shadow'],
  shadow: ['active', 'draft'],
  active: ['archived', 'shadow'],
  archived: ['draft'],
}

const LIFECYCLE_ACTION: Record<string, string> = {
  draft: '退回草稿',
  shadow: '进入试运行',
  active: '上线生效',
  archived: '停用',
}

const LIFECYCLE_HELP: Record<string, string> = {
  draft: '草稿状态只保存配置，不参与机审。',
  shadow: '试运行会并行产出评估结果，但不影响最终处置。',
  active: '线上生效，会参与后续机审决策。',
  archived: '已停用，不参与机审；可恢复到草稿后重新编辑上线。',
}

const AXIS_OPTIONS = [
  { value: 'safety', label: '内容安全', color: 'red' },
  { value: 'quality', label: '用户体验', color: 'orange' },
  { value: 'business', label: '信息匹配', color: 'arcoblue' },
]

function axisMeta(axis: string) {
  return AXIS_OPTIONS.find((item) => item.value === axis) || { value: axis, label: axis || '未设置', color: 'gray' }
}

function lifecycleAction(current: string, target: string) {
  if (current === 'archived' && target === 'draft') return '恢复到草稿'
  return LIFECYCLE_ACTION[target] || statusMeta('lifecycle', target).label
}

type PolicyEditDraft = {
  dimension_name: string
  dimension_axis: string
  enabled: boolean
  llm_review_enabled: boolean
  auto_block_threshold: number
  human_review_threshold: number
  prompt_template_id: string
  sor_template_id: string
}

function toEditDraft(row: Dimension): PolicyEditDraft {
  return {
    dimension_name: row.dimension_name,
    dimension_axis: row.dimension_axis,
    enabled: row.enabled,
    llm_review_enabled: row.llm_review_enabled,
    auto_block_threshold: Number(row.auto_block_threshold),
    human_review_threshold: Number(row.human_review_threshold),
    prompt_template_id: row.prompt_template_id || '',
    sor_template_id: row.sor_template_id || '',
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
    onSuccess: () => {
      Message.success('状态已更新')
      qc.invalidateQueries({ queryKey: ['dimensions'] })
    },
    onError: (e: unknown) => Message.error(extractErr(e)),
  })

  const approve = useMutation({
    mutationFn: async (id: string) => (await api.post(`/policy/dimensions/${id}/approve`)).data,
    onSuccess: () => {
      Message.success('已审批')
      qc.invalidateQueries({ queryKey: ['dimensions'] })
    },
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
    setEditDraft((draft) => (draft ? { ...draft, [key]: value } : draft))
  }

  const saveEditor = () => {
    if (!editTarget || !editDraft) return
    const patch: Partial<PolicyEditDraft> =
      editTarget.status === 'active' ? { dimension_name: editDraft.dimension_name } : editDraft
    const original = editTarget as unknown as Record<string, unknown>
    const hasChanges = Object.entries(patch).some(([key, value]) => original[key] !== value)
    if (!hasChanges) {
      Message.info('没有检测到变更')
      return
    }
    update.mutate({ id: editTarget.dimension_id, patch })
  }

  const sensitiveDisabled = editTarget?.status === 'active'

  return (
    <div className="page-stack">
      <PageHeader
        title="策略管理"
        description="管理机审维度、LLM 提示词模板、阈值和上线状态。"
        meta={
          <Space wrap>
            <Tag color={canWrite ? 'green' : 'gray'}>{canWrite ? '可编辑' : '只读'}</Tag>
            <Tag color={canApprove ? 'arcoblue' : 'gray'}>{canApprove ? '可审批' : '无审批权限'}</Tag>
          </Space>
        }
        actions={<Button onClick={() => qc.invalidateQueries({ queryKey: ['dimensions'] })}>刷新</Button>}
      />
      <Card title="策略维度">
        <Table<Dimension>
          rowKey="dimension_id"
          loading={dims.isLoading}
          data={dims.data || []}
          scroll={{ x: 1280 }}
          noDataElement={
            <EmptyState
              title="暂无策略维度"
              description="服务启动后会注册默认策略；如果这里为空，请重新加载。"
              action={<EmptyActionButton onClick={() => qc.invalidateQueries({ queryKey: ['dimensions'] })}>重新加载</EmptyActionButton>}
            />
          }
          columns={[
            { title: '维度', dataIndex: 'dimension_name', width: 150 },
            { title: 'ID', dataIndex: 'dimension_id', width: 190, ellipsis: true },
            {
              title: '轴',
              dataIndex: 'dimension_axis',
              width: 105,
              render: (a: string) => {
                const axis = axisMeta(a)
                return <Tag color={axis.color}>{axis.label}</Tag>
              },
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 105,
              render: (s: string) => <StatusTag kind="lifecycle" value={s} tooltip={LIFECYCLE_HELP[s] || s} />,
            },
            {
              title: '机审',
              width: 130,
              render: (_: unknown, r: Dimension) => (
                <Space size={4} wrap>
                  <Tag color={r.status !== 'archived' && r.enabled ? 'green' : 'gray'}>
                    {r.status !== 'archived' && r.enabled ? '启用' : '停用'}
                  </Tag>
                  <Tag color={r.llm_review_enabled ? 'arcoblue' : 'gray'}>{r.llm_review_enabled ? 'LLM' : '规则'}</Tag>
                </Space>
              ),
            },
            {
              title: '阈值',
              width: 125,
              render: (_: unknown, r: Dimension) => (
                <Typography.Text className="num-cell">
                  拦截 {Number(r.auto_block_threshold).toFixed(2)} / 人审 {Number(r.human_review_threshold).toFixed(2)}
                </Typography.Text>
              ),
            },
            {
              title: '提示词模板',
              dataIndex: 'prompt_template_id',
              width: 210,
              ellipsis: true,
              render: (v: string) => v || '未绑定',
            },
            {
              title: '理由模板',
              dataIndex: 'sor_template_id',
              width: 190,
              ellipsis: true,
              render: (v: string) => v || '未绑定',
            },
            { title: '版本', dataIndex: 'version', width: 70, align: 'right' },
            { title: '审批人', dataIndex: 'approved_by', width: 100, render: (a: string | null) => a || '—' },
            {
              title: '操作',
              width: 330,
              fixed: 'right',
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
                      content="审批后才允许上线生效。"
                      onOk={() => approve.mutate(r.dimension_id)}
                    >
                      <Button size="small" loading={approve.isPending}>审批</Button>
                    </Popconfirm>
                  )}
                  {canWrite &&
                    NEXT[r.status]?.map((target) => (
                      <Popconfirm
                        key={target}
                        title={`确认${lifecycleAction(r.status, target)}？`}
                        content={`${r.dimension_name}：${statusMeta('lifecycle', r.status).label} -> ${statusMeta('lifecycle', target).label}`}
                        onOk={() => transition.mutate({ id: r.dimension_id, target })}
                      >
                        <Button size="mini" type={target === 'active' ? 'primary' : 'default'} loading={transition.isPending}>
                          {lifecycleAction(r.status, target)}
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
        onCancel={() => {
          setEditTarget(null)
          setEditDraft(null)
        }}
        unmountOnExit
      >
        {editDraft && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {sensitiveDisabled && (
              <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
                生效中策略的治理配置已冻结；如需调整阈值、LLM 或模板，请先转为试运行，保存后重新审批上线。
              </Typography.Paragraph>
            )}
            <div className="policy-edit-grid">
              <div className="label">策略名称</div>
              <Input value={editDraft.dimension_name} onChange={(value) => updateDraft('dimension_name', value)} />

              <div className="label">策略轴</div>
              <Select
                value={editDraft.dimension_axis}
                disabled={sensitiveDisabled}
                onChange={(value) => updateDraft('dimension_axis', String(value))}
              >
                {AXIS_OPTIONS.map((item) => (
                  <Select.Option key={item.value} value={item.value}>{item.label}</Select.Option>
                ))}
              </Select>

              <div className="label">启用维度</div>
              <Switch
                checked={editDraft.enabled}
                disabled={sensitiveDisabled}
                onChange={(checked) => updateDraft('enabled', Boolean(checked))}
              />

              <div className="label">LLM 机审</div>
              <Switch
                checked={editDraft.llm_review_enabled}
                disabled={sensitiveDisabled}
                onChange={(checked) => updateDraft('llm_review_enabled', Boolean(checked))}
              />

              <div className="label">自动拦截阈值</div>
              <InputNumber
                min={0}
                max={1}
                step={0.01}
                precision={2}
                value={editDraft.auto_block_threshold}
                disabled={sensitiveDisabled}
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
                disabled={sensitiveDisabled}
                style={{ width: '100%' }}
                onChange={(value) => updateDraft('human_review_threshold', normalizeThreshold(value))}
              />

              <div className="label">LLM 提示词模板</div>
              <Input
                value={editDraft.prompt_template_id}
                disabled={sensitiveDisabled}
                placeholder="prompt.general_policy.v1"
                onChange={(value) => updateDraft('prompt_template_id', value)}
              />

              <div className="label">处置理由模板</div>
              <Input
                value={editDraft.sor_template_id}
                disabled={sensitiveDisabled}
                placeholder="sor.general_policy.v1"
                onChange={(value) => updateDraft('sor_template_id', value)}
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
