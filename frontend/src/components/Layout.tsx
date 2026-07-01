import { useState } from 'react'
import { Layout, Menu, Badge, Button, Space, Typography, App as AntApp } from 'antd'
import {
  AuditOutlined,
  DashboardOutlined,
  SettingOutlined,
  SolutionOutlined,
  SafetyOutlined,
  LogoutOutlined,
  WifiOutlined,
} from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useWebSocket } from '../hooks/useWebSocket'
import type { WsEnvelope } from '../api/types'

const { Header, Sider, Content } = Layout

const MENU = [
  { key: '/workbench', icon: <AuditOutlined />, label: '人审工作台' },
  { key: '/monitor', icon: <DashboardOutlined />, label: '机审监控大屏' },
  { key: '/policy', icon: <SettingOutlined />, label: '策略管理' },
  { key: '/appeals', icon: <SolutionOutlined />, label: '申诉' },
  { key: '/quality', icon: <SafetyOutlined />, label: '质检' },
]

export function AppLayout() {
  const nav = useNavigate()
  const loc = useLocation()
  const { logout, roles } = useAuth()
  const { notification } = AntApp.useApp()
  const [collapsed, setCollapsed] = useState(false)

  const { connected } = useWebSocket((e: WsEnvelope) => {
    const map: Record<string, string> = {
      sla_warning: 'SLA 临期告警',
      task_lock_expired: '案件锁已超时释放',
      task_reassigned: '任务被重新分配',
      appeal_overturned: '申诉改判',
      break_reminder: '强制休息提醒',
    }
    if (map[e.type]) notification.warning({ message: map[e.type], description: JSON.stringify(e.payload) })
  })

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed}>
        <div style={{ height: 48, margin: 16, color: '#fff', fontWeight: 700, fontSize: collapsed ? 12 : 16 }}>
          {collapsed ? 'VGP' : '视频治理平台'}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[loc.pathname]}
          items={MENU}
          onClick={({ key }) => nav(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingInline: 24 }}>
          <Typography.Text type="secondary">当前角色：{roles.join(', ') || '—'}</Typography.Text>
          <Space size="large">
            <Badge status={connected ? 'success' : 'error'} text={<Space size={4}><WifiOutlined />{connected ? '实时在线' : '离线'}</Space>} />
            <Button icon={<LogoutOutlined />} onClick={() => { logout(); nav('/login') }}>退出</Button>
          </Space>
        </Header>
        <Content style={{ margin: 16 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
