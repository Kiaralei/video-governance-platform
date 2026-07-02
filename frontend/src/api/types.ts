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
  model_version?: string
  llm_unavailable?: boolean
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
  business_context?: BusinessContext
  shopping_cart_url?: string
  product_title?: string
  product_category?: string
  merchant_name?: string
}

export interface BusinessContext {
  poi?: { id?: string; name?: string; category?: string; city?: string; geo?: unknown }
  shopping_cart?: { url?: string; landing_page_domain?: string }
  product?: { title?: string; category?: string; sku_id?: string }
  products?: unknown[]
  merchant?: { id?: string; name?: string }
  extra?: Record<string, unknown>
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
    business_context?: BusinessContext
    shopping_cart_url?: string
    product_title?: string
    product_category?: string
    merchant_name?: string
    final_decision: string | null
  }
  evidence: EvidencePackage
  machine_review: {
    recommendation: string | null
    confidence: number
    rationale: string
    verdicts: DimensionVerdict[]
  }
}

export interface ModalityInvocation {
  modality: 'asr' | 'ocr' | 'vision' | string
  status: 'completed' | 'failed' | 'not_configured' | 'invalid_response' | string
  provider?: string
  model_version?: string
  error?: string
  warnings?: string[]
}

export interface EvidencePackage {
  ep_id?: string
  content_id?: string
  metadata?: Record<string, unknown>
  media_asset?: {
    status?: string
    source_type?: string
    storage_backend?: string
    mime_type?: string
    file_size_bytes?: number
    local_path?: string
    storage_uri?: string
  }
  video_meta?: Record<string, unknown>
  frames?: Array<{ frame_id: string; timestamp_ms?: number; thumbnail_path?: string; caption?: string }>
  asr_transcript?: Array<{ start_ms?: number; end_ms?: number; text: string; source?: string; model_version?: string }>
  ocr_results?: Array<{ frame_id?: string; text: string; bbox?: unknown; source?: string; model_version?: string }>
  object_detections?: Array<{ frame_id?: string; label: string; confidence?: number; source?: string }>
  scene_tags?: Array<{ tag: string; confidence?: number }>
  modality_model_invocations?: ModalityInvocation[]
  modality_availability?: Record<string, { available?: boolean; source?: string; mode?: string; extracted_count?: number }>
  extraction_notes?: string[]
  machine_review_llm_used?: boolean
}

export interface Dimension {
  dimension_id: string
  dimension_name: string
  dimension_axis: string
  enabled: boolean
  llm_review_enabled: boolean
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

export interface MachineReviewRow {
  review_id: string
  content_id: string
  task_id: string | null
  evidence_package_id: string
  title: string
  description: string
  creator_id: string
  business_context?: BusinessContext
  shopping_cart_url?: string
  product_title?: string
  product_category?: string
  merchant_name?: string
  content_status: string
  task_status: string | null
  final_decision: string | null
  recommendation: string | null
  confidence: number
  rationale: string
  verdicts: DimensionVerdict[]
  decision_summary: DecisionSummary | null
  created_at: string
}

export interface DemoCaseResult {
  scenario: string
  expected_policy_decision: string
  content_id: string
  job_id: string
  title: string
  recommendation: string
  final_decision: string | null
  content_status: string
  task_id: string | null
  task_status: string | null
  policy_decision: string
  risk_score: number
  triggered_rules: string[]
}

export interface DemoCasesResponse {
  batch_id: string
  cleared?: number
  total: number
  items: DemoCaseResult[]
}

export interface WsEnvelope {
  type: string
  payload: Record<string, unknown>
  timestamp: string
  correlation_id: string
}
