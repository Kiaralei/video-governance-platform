import { useEffect, useState } from 'react'
import { Tag } from '@arco-design/web-react'

// SLA 倒计时：<30min 转橙，过期转红。
export function SLACountdown({ deadline }: { deadline: string | null }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])
  if (!deadline) return <Tag color="gray">无 SLA</Tag>
  const remaining = new Date(deadline).getTime() - now
  if (remaining <= 0) return <Tag color="red">SLA 已超时</Tag>
  const mins = Math.floor(remaining / 60000)
  const secs = Math.floor((remaining % 60000) / 1000)
  const color = mins < 30 ? 'orange' : 'green'
  return (
    <Tag color={color}>
      SLA {mins}:{String(secs).padStart(2, '0')}
    </Tag>
  )
}
