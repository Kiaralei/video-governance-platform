import { Button, Empty, Space, Typography } from '@arco-design/web-react'
import type { ReactNode } from 'react'

interface EmptyStateProps {
  title: string
  description: string
  action?: ReactNode
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <Empty description={null} />
      <Typography.Title heading={6}>{title}</Typography.Title>
      <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>
      {action && <Space>{action}</Space>}
    </div>
  )
}

export function EmptyActionButton(props: { children: ReactNode; onClick: () => void; loading?: boolean }) {
  return (
    <Button type="primary" onClick={props.onClick} loading={props.loading}>
      {props.children}
    </Button>
  )
}
