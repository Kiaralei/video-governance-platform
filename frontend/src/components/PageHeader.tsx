import { Space, Typography } from '@arco-design/web-react'
import type { ReactNode } from 'react'

interface PageHeaderProps {
  title: string
  description: string
  meta?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ title, description, meta, actions }: PageHeaderProps) {
  return (
    <div className="page-titlebar">
      <div className="page-titlecopy">
        <h1>{title}</h1>
        <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>
        {meta && <div className="page-meta">{meta}</div>}
      </div>
      {actions && <Space wrap className="page-actions">{actions}</Space>}
    </div>
  )
}
