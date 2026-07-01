// 后端契约的 TypeScript 类型（对齐 backend/app/schemas.py 与 services.py 返回结构）。

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  roles: string[]
}

export interface DimensionVerdict {
  dimension_id: string
  dimension_name: string
  decision: 'VIOLATION' | 'NO_VIOLATION' | 'UNCERTAIN'
  confidence: number
  severity_suggestion: string | null
  reason: string
  source: string
}

export interface DecisionSummary {
  final_decision: string
  risk_score: number
  machine_recommendation: string
  triggered_rules: string[]
  action: { publish: boolean; route_to_human_review: boolean; priority: string }
}

export interface ReviewTask {
  task_id: string
  content_id: string
  evidence_package_id: string
  status: string
  assigned_to: string | null
  decision: string | null
  priority: number
  is_sensitive: boolean
  jurisdiction: string
  lock_expires_at: string | null
  sla_deadline: string | null
  title?: string
  machine_recommendation?: string
  machine_confidence?: number
}

export interface CaseDetail {
  task: ReviewTask
  content: {
    id: string
    title: string
    description: string
    creator_id: string
    poi: string
    video_url: string
    final_decision: string | null
  }
  evidence: Record<string, unknown>
  machine_review: {
    recommendation: string | null
    confidence: number
    rationale: string
    verdicts: DimensionVerdict[]
  }
}

export interface Dimension {
  dimension_id: string
  dimension_name: string
  dimension_axis: string
  enabled: boolean
  status: string
  version: number
  auto_block_threshold: number
  human_review_threshold: number
  approved_by: string | null
  has_strategy_class: boolean
}

export interface Appeal {
  appeal_id: string
  content_id: string
  appellant_id: string
  appeal_reason: string
  original_decision: string
  status: string
  assigned_reviewer_id: string | null
  resolved_decision: string | null
  created_at: string
}

export interface QualitySummary {
  flywheel_by_source: Record<string, number>
  total_samples: number
  passed_quality_gate: number
  golden: { total: number; correct: number; accuracy: number | null }
  human_override_rate: number
  appeal_overturn_rate: number
  irr: { kappa: number | null; items: number; meets_threshold?: boolean; note?: string }
}

export interface DashboardSummary {
  total_content: number
  queue: { pending: number; decided: number }
  pipeline: { queued: number; processing: number; completed: number; failed: number }
  decisions: { pass: number; block: number }
}

export interface WsEnvelope {
  type: string
  payload: Record<string, unknown>
  timestamp: string
  correlation_id: string
}
