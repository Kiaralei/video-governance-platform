import { Button, Card, Message, Popconfirm, Space, Table, Tag } from '@arco-design/web-react'
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

export function PolicyManagement() {
  const qc = useQueryClient()
  const { hasRole } = useAuth()
  const canWrite = hasRole('policy_pm', 'ops_admin')
  const canApprove = hasRole('policy_approver')

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
            { title: '轴', dataIndex: 'dimension_axis', width: 90, render: (a: string) => <Tag>{a}</Tag> },
            { title: '状态', dataIndex: 'status', width: 110, render: (s: string) => <StatusTag kind="lifecycle" value={s} /> },
            { title: '启用', dataIndex: 'enabled', width: 80, render: (e: boolean) => <Tag color={e ? 'green' : 'gray'}>{e ? '启用' : '停用'}</Tag> },
            { title: '拦截阈值', dataIndex: 'auto_block_threshold', width: 100, align: 'right', render: (v: number) => <span className="num-cell">{Number(v).toFixed(2)}</span> },
            { title: '审批人', dataIndex: 'approved_by', render: (a: string | null) => a || '—' },
            {
              title: '操作',
              width: 280,
              render: (_: unknown, r: Dimension) => (
                <Space wrap>
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
    </div>
  )
}

function extractErr(e: unknown): string {
  const err = e as { response?: { data?: { error?: string } } }
  return err.response?.data?.error || '操作失败'
}
