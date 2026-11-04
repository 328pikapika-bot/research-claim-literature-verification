export interface ParsedFileMeta {
  fileId: string
  name: string
  type: string
  size: number
  parsedAt: string
  url?: string
  content?: string
  truncated?: boolean
}

export type TaskStatus =
  | 'queued'
  | 'pending'
  | 'running'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'canceled'

export type TaskStepStatus =
  | 'pending'
  | 'queued'
  | 'waiting'
  | 'running'
  | 'processing'
  | 'completed'
  | 'done'
  | 'success'
  | 'failed'
  | 'error'
  | 'cancelled'
  | 'canceled'
  | 'skipped'

export type TaskStageKey =
  | 'preprocess'
  | 'claim_extract'
  | 'retrieval'
  | 'judgment'
  | 'output'

export interface TaskStep {
  step_no: number
  step_key: TaskStageKey | string
  title: string
  status: TaskStepStatus | string
  summary?: string
  started_at?: string
  completed_at?: string
  failed_at?: string
  sub_steps?: Array<{ name?: string; title?: string; status?: string; text?: string }>
  degradations?: Array<{ stage?: string; reason?: string; detail?: string }>
  payload?: Record<string, unknown>
  error?: string
}

export interface TaskDetail {
  task_id: string
  thread_id: string
  topic: string
  research_type: string
  status: TaskStatus | string
  created_at: string
  completed_at?: string | null
  duration_seconds?: number | null
  current_step: number
  error_message?: string | null
  steps_data?: TaskStep[] | null
  steps?: TaskStep[] | null
  result?: FinalResult | null
  final_result?: FinalResult | null
  input_digest?: Record<string, unknown> | null
  error_category?: string | null
}

export interface FinalResult {
  summary?: {
    claim_count?: number
    reference_count?: number
    status_counts?: Record<string, number>
    degraded?: boolean
    degradations?: Array<{ stage: string; reason: string; detail?: string }>
  }
  claims?: Array<{
    claim_id: string
    text: string
    status: string
    reason: string
    method?: string
    evidence?: EvidenceItem[]
  }>
  references?: ReferenceItem[]
  evidence_by_claim?: Record<string, EvidenceItem[]>
  retrieval_detail?: Record<string, unknown>
  input_digest?: Record<string, unknown>
  final_report_markdown?: string
}

export interface EvidenceItem {
  evidence_id: string
  reference_id: string
  relation: string
  title: string
  year: number
  snippet: string
  score: number
}

export interface ReferenceItem {
  reference_id: string
  paper_id?: string
  title: string
  authors?: string[]
  year?: number
  venue?: string
  doi?: string
  url?: string
  language?: string
  abstract?: string
  source?: string
  citation_count?: number
}

export interface TaskStageDefinition {
  step_no: number
  step_key: TaskStageKey
  title: string
  defaultSummary: string
}

export interface TaskStageView {
  step_no: number
  step_key: TaskStageKey
  title: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled' | 'skipped'
  summary: string
  sub_steps: Array<{ title: string; status: string }>
  degradations: Array<{ reason: string; detail?: string }>
  error?: string
  started_at?: string
  completed_at?: string
  failed_at?: string
  isActive: boolean
}

export interface TaskClaimEvidenceView {
  evidence_id: string
  reference_id: string
  citation: number
  relation: string
  title: string
  snippet: string
  score: number
}

export interface TaskClaimView {
  claim_id: string
  text: string
  status: string
  reason: string
  method?: string
  evidence: TaskClaimEvidenceView[]
}

export interface TaskSummaryView {
  claimCount: number
  referenceCount: number
  statusCounts: Record<string, number>
  degraded: boolean
  degradations: Array<{ stage: string; reason: string; detail?: string }>
}

export interface LiteratureCardView {
  key: string
  referenceId: string
  citation: number
  title: string
  authorsText: string
  metaText: string
  doi?: string
  url?: string
  abstract?: string
  source?: string
  citationCount?: number
  snippets: string[]
  labels: string[]
}

export interface TaskResultView {
  summary: TaskSummaryView
  claims: TaskClaimView[]
  references: LiteratureCardView[]
  citationMap: Record<string, number>
  finalReportMarkdown: string
}
