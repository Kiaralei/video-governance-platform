import { useState } from 'react'
import { Layout, Menu, Badge, Button, Popconfirm, Space, Tag, Typography, Notification } from '@arco-design/web-react'
import {
  IconApps,
  IconDashboard,
  IconSettings,
  IconSafe,
  IconFile,
  IconPoweroff,
  IconWifi,
} from '@arco-design/web-react/icon'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useWebSocket } from '../hooks/useWebSocket'
import type { WsEnvelope } from '../api/types'

const { Header, Sider, Content } = Layout

const MENU = [
  { key: '/workbench', icon: <IconApps />, label: '人审工作台' },
  { key: '/monitor', icon: <IconDashboard />, label: '机审监控' },
  { key: '/policy', icon: <IconSettings />, label: '策略管理' },
  { key: '/appeals', icon: <IconFile />, label: '申诉复核' },
  { key: '/quality', icon: <IconSafe />, label: '质检回流' },
]

export function AppLayout() {
  const nav = useNavigate()
  const loc = useLocation()
  const { logout, roles } = useAuth()
  const [collapsed, setCollapsed] = useState(false)

  const { connected } = useWebSocket((e: WsEnvelope) => {
    const map: Record<string, string> = {
      sla_warning: 'SLA 临期告警',
      task_lock_expired: '案件锁已超时释放',
      task_reassigned: '任务被重新分配',
      appeal_overturned: '申诉改判',
      break_reminder: '强制休息提醒',
    }
    if (map[e.type]) Notification.warning({ title: map[e.type], content: JSON.stringify(e.payload) })
  })

  return (
    <Layout className="app-shell">
      <Sider className="app-sider" collapsible collapsed={collapsed} onCollapse={setCollapsed} width={220}>
        <div className="brand-lockup">
          <div className="brand-mark">V</div>
          {!collapsed && (
            <div>
              <div className="brand-title">视频治理平台</div>
              <div className="brand-subtitle">Machine Governance Ops</div>
            </div>
          )}
        </div>
        <Menu
          theme="dark"
          mode="vertical"
          selectedKeys={[loc.pathname]}
          onClickMenuItem={(key) => nav(key)}
        >
          {MENU.map((item) => (
            <Menu.Item key={item.key}>
              {item.icon}
              {item.label}
            </Menu.Item>
          ))}
        </Menu>
      </Sider>
      <Layout>
        <Header className="app-header">
          <Space size="large">
          <div>
            <Typography.Text type="secondary">当前角色</Typography.Text>
            <Typography.Text style={{ marginLeft: 8 }}>{roles.join(', ') || '—'}</Typography.Text>
          </div>
            <Tag color="arcoblue">Demo 环境</Tag>
            <Tag color="green">tenant: global</Tag>
          </Space>
          <Space size="large">
            <Space size={6}>
              <Badge status={connected ? 'success' : 'error'} />
              <IconWifi />
              <Typography.Text>{connected ? '实时在线' : '离线'}</Typography.Text>
            </Space>
            <Popconfirm
              title="确认退出当前控制台？"
              content="退出后需要重新登录才能继续审核或运营操作。"
              onOk={() => { logout(); nav('/login') }}
            >
              <Button icon={<IconPoweroff />}>退出</Button>
            </Popconfirm>
          </Space>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
