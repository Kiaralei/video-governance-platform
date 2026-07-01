import { Button, Card, Form, Input, Typography, App as AntApp, Alert } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'

export function LoginPage() {
  const { login } = useAuth()
  const nav = useNavigate()
  const { message } = AntApp.useApp()

  async function onFinish(values: { username: string; password: string }) {
    try {
      await login(values.username, values.password)
      nav('/workbench')
    } catch {
      message.error('登录失败：用户名或密码错误')
    }
  }

  async function seed() {
    await api.post('/dev/seed-users')
    message.success('演示账号已创建，密码均为 demo-pass')
  }

  return (
    <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', background: '#f0f2f5' }}>
      <Card style={{ width: 380 }}>
        <Typography.Title level={3} style={{ textAlign: 'center' }}>视频治理平台</Typography.Title>
        <Form onFinish={onFinish} layout="vertical" initialValues={{ username: 'reviewer_demo', password: 'demo-pass' }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input autoFocus />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>登录</Button>
        </Form>
        <Alert
          style={{ marginTop: 16 }}
          type="info"
          message="演示账号"
          description="reviewer_demo / policy_pm_demo / policy_approver_demo / appeal_demo / qa_demo / ops_demo（密码 demo-pass）"
        />
        <Button type="link" block onClick={seed}>初始化演示账号</Button>
      </Card>
    </div>
  )
}
