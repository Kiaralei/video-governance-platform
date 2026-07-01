import { Tag, Tooltip } from '@arco-design/web-react'

type StatusKind = 'decision' | 'policy' | 'task' | 'lifecycle' | 'appeal' | 'verdict' | 'source'

const STATUS: Record<StatusKind, Record<string, { label: string; color: string }>> = {
  decision: {
    pass: { label: '通过', color: 'green' },
    block: { label: '拦截', color: 'red' },
    uncertain: { label: '需人审', color: 'orange' },
    pending: { label: '待裁定', color: 'orange' },
  },
  policy: {
    auto_pass: { label: '机审通过', color: 'green' },
    auto_block: { label: '机审拦截', color: 'red' },
    critical_escalate: { label: '高危拦截', color: 'red' },
    needs_human_review: { label: '进入人审', color: 'orange' },
  },
  task: {
    pending: { label: '待领取', color: 'orange' },
    assigned: { label: '审核中', color: 'arcoblue' },
    decided: { label: '已裁定', color: 'green' },
    expired: { label: '已超时', color: 'red' },
    released: { label: '已释放', color: 'gray' },
  },
  lifecycle: {
    draft: { label: '草稿', color: 'gray' },
    shadow: { label: '影子运行', color: 'purple' },
    active: { label: '生效中', color: 'green' },
    archived: { label: '已归档', color: 'gray' },
  },
  appeal: {
    open: { label: '待领取', color: 'orange' },
    in_review: { label: '二审中', color: 'arcoblue' },
    overturned: { label: '已改判', color: 'purple' },
    rejected: { label: '维持原判', color: 'gray' },
  },
  verdict: {
    VIOLATION: { label: '违规', color: 'red' },
    NO_VIOLATION: { label: '无违规', color: 'green' },
    UNCERTAIN: { label: '不确定', color: 'orange' },
  },
  source: {
    completed: { label: '已完成', color: 'green' },
    failed: { label: '失败', color: 'red' },
    not_configured: { label: '未配置', color: 'gray' },
    invalid_response: { label: '响应异常', color: 'orange' },
    available: { label: '可用', color: 'green' },
    fallback: { label: '降级', color: 'gray' },
  },
}

export function statusMeta(kind: StatusKind, value?: string | null) {
  const key = value || ''
  return STATUS[kind][key] || { label: key || '—', color: 'gray' }
}

export function StatusTag({ kind, value, tooltip }: { kind: StatusKind; value?: string | null; tooltip?: string }) {
  const meta = statusMeta(kind, value)
  const tag = <Tag color={meta.color}>{meta.label}</Tag>
  return tooltip || value ? <Tooltip content={tooltip || value}>{tag}</Tooltip> : tag
}
