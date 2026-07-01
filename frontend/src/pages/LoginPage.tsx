import { Alert, Button, Card, Input, Message, Typography } from '@arco-design/web-react'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { api } from '../api/client'

export function LoginPage() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [username, setUsername] = useState('reviewer_demo')
  const [password, setPassword] = useState('demo-pass')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      nav('/workbench')
    } catch {
      setError('登录失败：请检查用户名和密码。')
    } finally {
      setLoading(false)
    }
  }

  async function seed() {
    await api.post('/dev/seed-users')
    Message.success('演示账号已创建，密码均为 demo-pass')
  }

  return (
    <div className="login-shell">
      <div className="login-copy">
        <div>
          <div className="brand-lockup" style={{ padding: 0, borderBottom: 0 }}>
            <div className="brand-mark">V</div>
            <div>
              <div className="brand-title">视频治理平台</div>
              <div className="brand-subtitle">Machine Governance Ops</div>
            </div>
          </div>
          <h1 style={{ marginTop: 56 }}>面向机审、人审、申诉和质检闭环的治理后台</h1>
          <p>用统一证据链、策略决策和审计记录，把演示流程讲成一套可运营系统。</p>
        </div>
        <Typography.Text style={{ color: 'rgba(255,255,255,.56)' }}>Demo Environment · PostgreSQL · ASR/OCR/Vision · LLM</Typography.Text>
      </div>
      <div className="login-panel">
      <Card className="login-card">
        <Typography.Title heading={3} style={{ marginTop: 0 }}>登录控制台</Typography.Title>
        <Typography.Paragraph type="secondary">使用审核员或运营账号进入对应工作台。</Typography.Paragraph>
        <form onSubmit={onSubmit}>
          <div style={{ marginBottom: 14 }}>
            <label className="field-label" htmlFor="username">用户名</label>
            <Input
              id="username"
              name="username"
              autoComplete="username"
              spellCheck={false}
              value={username}
              onChange={setUsername}
            />
          </div>
          <div style={{ marginBottom: 18 }}>
            <label className="field-label" htmlFor="password">密码</label>
            <Input.Password
              id="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={setPassword}
            />
          </div>
          {error && <div className="inline-error" aria-live="polite" style={{ marginBottom: 12 }}>{error}</div>}
          <Button type="primary" htmlType="submit" long loading={loading}>登录</Button>
        </form>
        <Alert
          style={{ marginTop: 16 }}
          type="info"
          content="演示模式：reviewer_demo / policy_pm_demo / policy_approver_demo / appeal_demo / qa_demo / ops_demo，密码均为 demo-pass。"
        />
        <Button type="text" long onClick={seed} style={{ marginTop: 8 }}>初始化演示账号</Button>
      </Card>
      </div>
    </div>
  )
}
