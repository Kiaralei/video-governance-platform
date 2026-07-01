import { Button, Card, Popconfirm, Space, Table, Tag, App as AntApp } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Dimension } from '../api/types'
import { useAuth } from '../auth/AuthContext'

const STATUS_COLOR: Record<string, string> = {
  draft: 'default',
  shadow: 'purple',
  active: 'green',
  archived: 'red',
}

// 四态生命周期允许的下一步（对齐后端 VALID_STATUS_TRANSITIONS）。
const NEXT: Record<string, string[]> = {
  draft: ['shadow'],
  shadow: ['active', 'draft'],
  active: ['archived', 'shadow'],
  archived: [],
}

export function PolicyManagement() {
  const qc = useQueryClient()
  const { message } = AntApp.useApp()
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
    onSuccess: () => { message.success('状态已流转'); qc.invalidateQueries({ queryKey: ['dimensions'] }) },
    onError: (e: unknown) => message.error(extractErr(e)),
  })
  const approve = useMutation({
    mutationFn: async (id: string) => (await api.post(`/policy/dimensions/${id}/approve`)).data,
    onSuccess: () => { message.success('已审批'); qc.invalidateQueries({ queryKey: ['dimensions'] }) },
    onError: (e: unknown) => message.error(extractErr(e)),
  })

  return (
    <Card title="策略维度注册表" extra={<Button onClick={() => qc.invalidateQueries({ queryKey: ['dimensions'] })}>刷新</Button>}>
      <Table<Dimension>
        rowKey="dimension_id"
        loading={dims.isLoading}
        dataSource={dims.data || []}
        columns={[
          { title: '维度', dataIndex: 'dimension_name' },
          { title: 'ID', dataIndex: 'dimension_id' },
          { title: '轴', dataIndex: 'dimension_axis', render: (a: string) => <Tag>{a}</Tag> },
          { title: '状态', dataIndex: 'status', render: (s: string) => <Tag color={STATUS_COLOR[s]}>{s}</Tag> },
          { title: '启用', dataIndex: 'enabled', render: (e: boolean) => (e ? '是' : '否') },
          { title: '拦截阈值', dataIndex: 'auto_block_threshold' },
          { title: '审批人', dataIndex: 'approved_by', render: (a: string | null) => a || '—' },
          {
            title: '操作',
            render: (_: unknown, r: Dimension) => (
              <Space>
                {canApprove && !r.approved_by && (
                  <Button size="small" onClick={() => approve.mutate(r.dimension_id)}>审批</Button>
                )}
                {canWrite &&
                  NEXT[r.status]?.map((target) => (
                    <Popconfirm key={target} title={`流转到 ${target}?`} onConfirm={() => transition.mutate({ id: r.dimension_id, target })}>
                      <Button size="small" type={target === 'active' ? 'primary' : 'default'}>→ {target}</Button>
                    </Popconfirm>
                  ))}
              </Space>
            ),
          },
        ]}
      />
    </Card>
  )
}

function extractErr(e: unknown): string {
  const err = e as { response?: { data?: { error?: string } } }
  return err.response?.data?.error || '操作失败'
}
