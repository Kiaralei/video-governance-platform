import { type KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useState } from 'react'
import {
  Button,
  Card,
  Input,
  Message,
  Popconfirm,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from '@arco-design/web-react'
import { IconCheckCircle, IconRightCircle, IconStop } from '@arco-design/web-react/icon'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { CaseDetail, DimensionVerdict, EvidencePackage, ModalityInvocation, ReviewTask } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import { EmptyActionButton, EmptyState } from '../components/EmptyState'
import { PageHeader } from '../components/PageHeader'
import { SLACountdown } from '../components/SLACountdown'
import { StatusTag, statusMeta } from '../components/StatusTag'

const CURRENT_REVIEW_TASK_PREFIX = 'vgp_current_review_task_id'

function VerdictTable({ verdicts }: { verdicts: DimensionVerdict[] }) {
  return (
    <Table<DimensionVerdict>
      size="small"
      rowKey="dimension_id"
      pagination={false}
      data={verdicts}
      columns={[
        { title: '维度', dataIndex: 'dimension_name', width: 150 },
        {
          title: '判定',
          dataIndex: 'decision',
          width: 128,
          render: (d) => <StatusTag kind="verdict" value={String(d)} />,
        },
        { title: '置信度', dataIndex: 'confidence', width: 84, align: 'right', render: (c) => <span className="num-cell">{Number(c).toFixed(2)}</span> },
        {
          title: '来源',
          dataIndex: 'source',
          width: 116,
          render: (s, row) => <Tag color={s === 'llm' ? 'arcoblue' : 'gray'}>{row.model_version || s}</Tag>,
        },
        { title: '理由', dataIndex: 'reason', ellipsis: true },
      ]}
    />
  )
}

function ModalityPanel({ evidence }: { evidence: EvidencePackage }) {
  const invocations = evidence.modality_model_invocations || []
  const availability = evidence.modality_availability || {}
  const rows = ['asr', 'ocr', 'vision'].map((modality) => {
    const inv = invocations.find((item) => item.modality === modality) as ModalityInvocation | undefined
    const sourceKey = modality === 'vision' ? 'scene_classification' : modality
    return {
      modality,
      status: inv?.status || 'not_configured',
      provider: inv?.provider || inv?.model_version || '—',
      available: availability[sourceKey]?.available,
      source: availability[sourceKey]?.source || availability[sourceKey]?.mode || '—',
      error: inv?.error,
    }
  })

  return (
    <Card title="特征提取">
      <div className="evidence-list">
        {rows.map((row) => (
          <div className="evidence-item" key={row.modality}>
            <div className="status-line">
              <Tag color="arcoblue">{row.modality.toUpperCase()}</Tag>
              <StatusTag kind="source" value={row.status} />
              <StatusTag kind="source" value={row.available ? 'available' : 'fallback'} />
            </div>
            <div style={{ marginTop: 6, color: '#6b7785' }}>
              provider: {row.provider} · source: {row.source}
            </div>
            {row.error && <div style={{ marginTop: 4, color: '#f53f3f' }}>{row.error}</div>}
          </div>
        ))}
      </div>
    </Card>
  )
}

function EvidenceTags({ evidence }: { evidence: EvidencePackage }) {
  return (
    <Card title="证据标签">
      <div className="evidence-list">
        <div>
          <Typography.Text type="secondary">场景标签</Typography.Text>
          <div className="status-line" style={{ marginTop: 6 }}>
            {(evidence.scene_tags || []).slice(0, 8).map((tag) => (
              <Tag key={tag.tag} color="arcoblue">{tag.tag} {tag.confidence != null ? Number(tag.confidence).toFixed(2) : ''}</Tag>
            ))}
            {!evidence.scene_tags?.length && <Tag color="gray">无</Tag>}
          </div>
        </div>
        <div>
          <Typography.Text type="secondary">物体检测</Typography.Text>
          <div className="status-line" style={{ marginTop: 6 }}>
            {(evidence.object_detections || []).slice(0, 8).map((obj, index) => (
              <Tag key={`${obj.label}-${index}`} color="purple">{obj.label} {obj.confidence != null ? Number(obj.confidence).toFixed(2) : ''}</Tag>
            ))}
            {!evidence.object_detections?.length && <Tag color="gray">无</Tag>}
          </div>
        </div>
      </div>
    </Card>
  )
}

function TextEvidence({ evidence }: { evidence: EvidencePackage }) {
  return (
    <Card title="文本证据">
      <div className="evidence-list">
        <div className="evidence-item">
          <Typography.Text type="secondary">ASR</Typography.Text>
          {(evidence.asr_transcript || []).slice(0, 3).map((item, index) => (
            <div key={index}>{item.text}</div>
          ))}
          {!evidence.asr_transcript?.length && <div>—</div>}
        </div>
        <div className="evidence-item">
          <Typography.Text type="secondary">OCR</Typography.Text>
          {(evidence.ocr_results || []).slice(0, 5).map((item, index) => (
            <div key={index}>{item.frame_id || 'frame'}: {item.text}</div>
          ))}
          {!evidence.ocr_results?.length && <div>—</div>}
        </div>
      </div>
    </Card>
  )
}

function showValue(value?: string | null) {
  return value && value.trim() ? value : '—'
}

function BusinessContextCard({ current }: { current: CaseDetail }) {
  const context = current.content.business_context || {}
  const poi = context.poi || {}
  const product = context.product || {}
  const cart = context.shopping_cart || {}
  const merchant = context.merchant || {}
  const cartUrl = current.content.shopping_cart_url || cart.url || ''

  return (
    <Card title="挂载信息">
      <div className="kv-grid">
        <div className="label">POI</div><div>{showValue(poi.name || current.content.poi)}</div>
        <div className="label">POI 类目</div><div>{showValue(poi.category)}</div>
        <div className="label">商品</div><div>{showValue(current.content.product_title || product.title)}</div>
        <div className="label">商品类目</div><div>{showValue(current.content.product_category || product.category)}</div>
        <div className="label">商家</div><div>{showValue(current.content.merchant_name || merchant.name)}</div>
        <div className="label">购物车</div>
        <div className="breakable">
          {cartUrl ? <Typography.Text copyable={{ text: cartUrl }}>{cartUrl}</Typography.Text> : '—'}
        </div>
      </div>
    </Card>
  )
}

function VideoEvidence({ current }: { current: CaseDetail }) {
  const evidenceId = current.task.evidence_package_id || current.evidence.ep_id
  const frames = current.evidence.frames || []
  const meta = current.evidence.video_meta || {}
  const videoUrl = current.content.video_url || String(meta.source_url || meta.source || '')

  return (
    <Card title="视频证据">
      <div className="evidence-list">
        <div className="evidence-item">
          <div className="status-line">
            <StatusTag kind="source" value={meta.asset_status === 'stored' ? 'available' : 'fallback'} />
            <Tag color="gray">{String(meta.source_type || 'text_only')}</Tag>
          </div>
          <div className="breakable" style={{ marginTop: 6 }}>
            {videoUrl ? <Typography.Text copyable={{ text: videoUrl }}>{videoUrl}</Typography.Text> : '—'}
          </div>
          <div className="status-line" style={{ marginTop: 8 }}>
            {meta.duration_ms != null && <Tag color="arcoblue">{Math.round(Number(meta.duration_ms) / 1000)}s</Tag>}
            {meta.width != null && meta.height != null && <Tag color="arcoblue">{String(meta.width)}x{String(meta.height)}</Tag>}
            {meta.file_size_bytes != null && <Tag color="gray">{Math.round(Number(meta.file_size_bytes) / 1024)} KB</Tag>}
          </div>
        </div>
        <div className="frame-grid">
          {frames.slice(0, 3).map((frame) => {
            const canLoad = Boolean(evidenceId && frame.thumbnail_path)
            const src = `/api/v1/evidence/${evidenceId}/frames/${encodeURIComponent(frame.frame_id)}`
            return (
              <div className="frame-card" key={frame.frame_id}>
                {canLoad ? <img className="frame-thumb" src={src} alt={frame.caption || frame.frame_id} /> : <div className="frame-thumb frame-placeholder">{frame.frame_id}</div>}
                <div className="frame-caption">
                  <span className="num-cell">{Math.round(Number(frame.timestamp_ms || 0) / 1000)}s</span>
                  <span>{frame.caption || '关键帧证据'}</span>
                </div>
              </div>
            )
          })}
          {!frames.length && <div className="evidence-item">暂无关键帧，当前使用标题、简介、ASR/OCR 降级证据。</div>}
        </div>
      </div>
    </Card>
  )
}

export function ReviewWorkbench() {
  const qc = useQueryClient()
  const { hasRole, roles } = useAuth()
  const canReview = hasRole('reviewer')
  const [current, setCurrent] = useState<CaseDetail | null>(null)
  const [reason, setReason] = useState('')
  const [reasonTouched, setReasonTouched] = useState(false)
  const currentTaskStorageKey = `${CURRENT_REVIEW_TASK_PREFIX}:${roles.slice().sort().join('|') || 'anonymous'}`

  const rememberCurrent = useCallback(
    (data: CaseDetail) => {
      setCurrent(data)
      localStorage.setItem(currentTaskStorageKey, data.task.task_id)
    },
    [currentTaskStorageKey],
  )

  const clearCurrent = useCallback(() => {
    setCurrent(null)
    localStorage.removeItem(currentTaskStorageKey)
  }, [currentTaskStorageKey])

  const queue = useQuery<ReviewTask[]>({
    queryKey: ['queue'],
    queryFn: async () => (await api.get('/review/human/queue')).data.items,
    enabled: canReview,
    refetchInterval: 15000,
  })

  const fetchNext = useMutation({
    mutationFn: async () => {
      if (!canReview) throw new Error('当前账号没有人审领取权限，请切换到 reviewer_demo')
      return (await api.post('/review/human/next')).data
    },
    onSuccess: (data) => {
      if (data.status === 'assigned') {
        rememberCurrent(data as CaseDetail)
        setReason('')
        setReasonTouched(false)
      } else if (data.status === 'break_required') {
        Message.warning('已达强制休息阈值，请稍后再领取')
      } else {
        Message.info('暂无待审案件')
      }
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (e: unknown) => Message.error(`领取失败：${extractErr(e)}`),
  })

  const openCase = useMutation({
    mutationFn: async (taskId: string) => (await api.post(`/review/human/${taskId}/claim`)).data,
    onSuccess: (data) => { rememberCurrent(data as CaseDetail); setReason(''); setReasonTouched(false) },
    onError: (e: unknown) => Message.error(`领取失败：${extractErr(e)}`),
  })

  const decide = useMutation({
    mutationFn: async ({ taskId, decision }: { taskId: string; decision: 'pass' | 'block' }) =>
      (await api.post(`/review/human/${taskId}/decide`, { decision, reason })).data,
    onSuccess: (data) => {
      if (data.golden_test_result) {
        const g = data.golden_test_result
        Message[g.is_correct ? 'success' : 'error'](`黄金题：${g.is_correct ? '答对' : '答错'}（应为 ${g.expected_decision}）`)
      } else {
        Message.success(`已裁定：${data.decision}`)
      }
      clearCurrent()
      setReason('')
      setReasonTouched(false)
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (e: unknown) => Message.error(`裁定失败：${extractErr(e)}`),
  })

  const submitDecision = useCallback(
    (decision: 'pass' | 'block') => {
      if (!current) return
      if (!reason.trim()) { setReasonTouched(true); Message.warning('请填写裁定理由'); return }
      decide.mutate({ taskId: current.task.task_id, decision })
    },
    [current, reason, decide],
  )

  useEffect(() => {
    if (!canReview) {
      clearCurrent()
      return
    }
    if (current) return

    let cancelled = false
    async function restoreCurrent() {
      const savedTaskId = localStorage.getItem(currentTaskStorageKey)
      try {
        const { data } = savedTaskId
          ? await api.get(`/review/human/${savedTaskId}`)
          : await api.get('/review/human/current')
        if (cancelled) return
        if (data.status === 'empty') {
          localStorage.removeItem(currentTaskStorageKey)
          return
        }
        const detail = data as CaseDetail
        if (detail.task.status === 'decided') {
          localStorage.removeItem(currentTaskStorageKey)
          return
        }
        setCurrent(detail)
        localStorage.setItem(currentTaskStorageKey, detail.task.task_id)
        setReason('')
        setReasonTouched(false)
      } catch {
        localStorage.removeItem(currentTaskStorageKey)
        if (!savedTaskId || cancelled) return
        try {
          const { data } = await api.get('/review/human/current')
          if (cancelled || data.status === 'empty') return
          const detail = data as CaseDetail
          setCurrent(detail)
          localStorage.setItem(currentTaskStorageKey, detail.task.task_id)
          setReason('')
          setReasonTouched(false)
        } catch {
          // Ignore restore failures; the reviewer can claim the next task manually.
        }
      }
    }
    restoreCurrent()
    return () => { cancelled = true }
  }, [canReview, clearCurrent, current, currentTaskStorageKey])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (canReview && e.key.toLowerCase() === 'n') fetchNext.mutate()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [canReview, submitDecision, fetchNext])

  const pendingQueue = queue.data || []
  const highestPriority = pendingQueue.length ? Math.min(...pendingQueue.map((item) => Number(item.priority || 99))) : '—'
  const missingReason = reasonTouched && !reason.trim()

  return (
    <div className="page-stack">
      <PageHeader
        title="人审工作台"
        description="只处理机器审核无法确定的案件。审核员基于证据独立裁定，通过与拦截都会进入审计链路。"
        meta={<Space wrap><Tag color="orange">快捷键 N 领取</Tag><Tag color="arcoblue">裁定需二次确认</Tag></Space>}
        actions={
        <Button type="primary" icon={<IconRightCircle />} onClick={() => fetchNext.mutate()} loading={fetchNext.isPending} disabled={!canReview}>
          领取下一个
        </Button>
        }
      />

      {!canReview && (
        <Card>
          <EmptyState
            title="当前账号没有人审领取权限"
            description="机审监控可以被策略管理员和系统管理员查看；领取人审任务需要审核员角色。演示时请切换到 reviewer_demo。"
          />
        </Card>
      )}

      <div className="workbench-grid">
        <Card title={`待审队列 (${queue.data?.length ?? 0})`}>
          <Table<ReviewTask>
            size="small"
            rowKey="task_id"
            loading={queue.isLoading}
            data={queue.data || []}
            pagination={false}
            noDataElement={
              <EmptyState
                title="暂无待审任务"
                description="明确通过或拦截的内容已由机审终局；只有不确定内容会出现在这里。"
                action={<EmptyActionButton onClick={() => qc.invalidateQueries({ queryKey: ['queue'] })}>刷新队列</EmptyActionButton>}
              />
            }
            onRow={(r) => ({
              onClick: () => openCase.mutate(r.task_id),
              onKeyDown: (e: ReactKeyboardEvent) => {
                if (e.key === 'Enter' || e.key === ' ') openCase.mutate(r.task_id)
              },
              tabIndex: 0,
              role: 'button',
              className: 'clickable-row',
            })}
            columns={[
              { title: '优先级', dataIndex: 'priority', width: 70, render: (p) => <Tag color={Number(p) <= 2 ? 'red' : Number(p) <= 3 ? 'orange' : 'gray'}>{p}</Tag> },
              { title: '任务状态', dataIndex: 'status', width: 96, render: (s) => <StatusTag kind="task" value={String(s)} /> },
              { title: '标题', dataIndex: 'title', ellipsis: true },
              { title: '机审', dataIndex: 'machine_recommendation', width: 82, render: (r) => <StatusTag kind="decision" value={String(r || '')} /> },
            ]}
          />
        </Card>

        {!current ? (
          <Card>
            <div className="ready-panel">
              <div>
                <Typography.Title heading={5}>准备领取下一单</Typography.Title>
                <Typography.Paragraph type="secondary">
                  当前工作台只展示需人工复核的内容。领取后会锁定案件，并开始 SLA 计时。
                </Typography.Paragraph>
              </div>
              <div className="ready-panel-metrics">
                <div className="metric-chip"><Typography.Text type="secondary">待审</Typography.Text><div className="num-cell">{pendingQueue.length}</div></div>
                <div className="metric-chip"><Typography.Text type="secondary">最高优先级</Typography.Text><div className="num-cell">{highestPriority}</div></div>
                <div className="metric-chip"><Typography.Text type="secondary">当前状态</Typography.Text><div>空闲</div></div>
              </div>
              <Button type="primary" icon={<IconRightCircle />} onClick={() => fetchNext.mutate()} loading={fetchNext.isPending} disabled={!canReview}>
                领取下一单
              </Button>
            </div>
          </Card>
        ) : (
          <div className="page-stack">
            <Card
              title={<Space>案件决策 <Tag color="arcoblue">{current.task.task_id}</Tag>{current.task.is_sensitive && <Tag color="red">敏感</Tag>}</Space>}
              extra={<SLACountdown deadline={current.task.sla_deadline} />}
            >
              <div className="case-grid">
                <div className="page-stack">
                  <Card title="内容摘要">
                    <div className="kv-grid">
                      <div className="label">标题</div><div>{current.content.title}</div>
                      <div className="label">简介</div><div>{current.content.description}</div>
                      <div className="label">创作者</div><div>{current.content.creator_id}</div>
                      <div className="label">POI</div><div>{current.content.poi}</div>
                      <div className="label">任务状态</div><div><StatusTag kind="task" value={current.task.status} /></div>
                    </div>
                  </Card>
                  <Card title="机审维度">
                    <VerdictTable verdicts={current.machine_review.verdicts} />
                  </Card>
                  <BusinessContextCard current={current} />
                  <TextEvidence evidence={current.evidence} />
                </div>
                <div className="page-stack">
                  <Card title="机审建议">
                    <Statistic
                      title="推荐动作"
                      value={statusMeta('decision', current.machine_review.recommendation || 'uncertain').label}
                      styleValue={{ color: current.machine_review.recommendation === 'block' ? '#f53f3f' : current.machine_review.recommendation === 'pass' ? '#00a870' : '#ff7d00' }}
                    />
                    <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>{current.machine_review.rationale}</Typography.Paragraph>
                    <div className="status-line">
                      <Tag color="arcoblue">风险分 {Number(current.machine_review.confidence || 0).toFixed(2)}</Tag>
                      <Tooltip content="只有 needs_human_review 才会进入此工作台">
                        <Tag color="orange">人工复核</Tag>
                      </Tooltip>
                    </div>
                  </Card>
                  <VideoEvidence current={current} />
                  <ModalityPanel evidence={current.evidence} />
                  <EvidenceTags evidence={current.evidence} />
                  <Card title="裁定">
                    <Input.TextArea
                      rows={4}
                      placeholder="说明依据，例如：未见引流二维码，但口播存在营销导向…"
                      value={reason}
                      onChange={(value) => { setReason(value); if (value.trim()) setReasonTouched(false) }}
                      onBlur={() => setReasonTouched(true)}
                      aria-label="裁定理由"
                    />
                    {missingReason && <div className="inline-error">请先填写裁定理由，便于审计追踪。</div>}
                    <Space style={{ marginTop: 14 }}>
                      <Popconfirm
                        title={`确认通过案件 ${current.task.task_id}？`}
                        content="通过后内容会进入最终放行状态，并记录裁定理由。"
                        onOk={() => submitDecision('pass')}
                        disabled={!reason.trim()}
                      >
                        <Button type="primary" icon={<IconCheckCircle />} disabled={!reason.trim()} loading={decide.isPending}>通过</Button>
                      </Popconfirm>
                      <Popconfirm
                        title={`确认拦截案件 ${current.task.task_id}？`}
                        content="拦截是高影响动作，会写入审计链并影响后续申诉。"
                        onOk={() => submitDecision('block')}
                        disabled={!reason.trim()}
                      >
                        <Button status="danger" icon={<IconStop />} disabled={!reason.trim()} loading={decide.isPending}>拦截</Button>
                      </Popconfirm>
                    </Space>
                  </Card>
                </div>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  )
}

function extractErr(e: unknown): string {
  if (e instanceof Error) return e.message
  const err = e as { response?: { data?: { error?: string; detail?: string } } }
  if (err.response?.data?.detail) return err.response.data.detail
  return err.response?.data?.error || '请求失败'
}
