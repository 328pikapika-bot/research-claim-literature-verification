import type {
  EvidenceItem,
  FinalResult,
  LiteratureCardView,
  ReferenceItem,
  TaskClaimView,
  TaskDetail,
  TaskResultView,
  TaskStageDefinition,
  TaskStageKey,
  TaskStageView,
  TaskStatus,
  TaskStep,
  TaskStepStatus,
  TaskSummaryView,
} from '../types'

export const TASK_STAGE_DEFINITIONS: TaskStageDefinition[] = [
  {
    step_no: 1,
    step_key: 'preprocess',
    title: '输入预处理',
    defaultSummary: '正在整理输入文本与已解析文件，准备进入一致性评估流程。',
  },
  {
    step_no: 2,
    step_key: 'claim_extract',
    title: '文本解析与主张提取',
    defaultSummary: '正在从文本中提取可验证科研主张，并拆分为可独立核验的判断单元。',
  },
  {
    step_no: 3,
    step_key: 'retrieval',
    title: '文献检索与证据组织',
    defaultSummary: '正在围绕主张关键词检索文献，并整理候选证据线索。',
  },
  {
    step_no: 4,
    step_key: 'judgment',
    title: '一致性判定',
    defaultSummary: '正在对照证据逐项判定主张状态，生成一致性说明。',
  },
  {
    step_no: 5,
    step_key: 'output',
    title: '引用标注与最终输出',
    defaultSummary: '正在整理引用编号、主张结论和最终评估报告。',
  },
]

const TERMINAL_TASK_STATUSES = new Set(['completed', 'failed', 'cancelled', 'canceled'])
const POLLING_TASK_STATUSES = new Set(['queued', 'pending', 'running', 'processing'])

export function normalizeTaskDetail(rawTask: Partial<TaskDetail> | null | undefined): TaskDetail | null {
  if (!rawTask) return null

  const rawSteps = Array.isArray(rawTask.steps_data)
    ? rawTask.steps_data
    : Array.isArray(rawTask.steps)
      ? rawTask.steps
      : []
  const steps = TASK_STAGE_DEFINITIONS.map((definition, index) =>
    normalizeTaskStep(rawSteps[index], definition),
  )

  const task: TaskDetail = {
    task_id: String(rawTask.task_id || ''),
    thread_id: String(rawTask.thread_id || ''),
    topic: String(rawTask.topic || ''),
    research_type: String(rawTask.research_type || ''),
    status: String(rawTask.status || 'queued'),
    created_at: String(rawTask.created_at || new Date().toISOString()),
    completed_at: rawTask.completed_at ?? null,
    duration_seconds: rawTask.duration_seconds ?? null,
    current_step: Number(rawTask.current_step || 0),
    error_message: rawTask.error_message ?? null,
    steps,
    steps_data: steps,
    result: normalizeFinalResult(rawTask.result),
    final_result: normalizeFinalResult(rawTask.final_result),
    input_digest: rawTask.input_digest ?? null,
    error_category: rawTask.error_category ?? null,
  }

  task.steps = applyTaskStatusFallbacks(task)
  task.steps_data = task.steps
  return task
}

export function createPendingTaskDetail(taskId: string, overrides: Partial<TaskDetail> = {}): TaskDetail {
  const nowIso = new Date().toISOString()
  return normalizeTaskDetail({
    task_id: taskId,
    thread_id: '',
    topic: '一致性评估任务',
    research_type: '综合评估',
    status: 'queued',
    created_at: nowIso,
    current_step: 0,
    steps_data: TASK_STAGE_DEFINITIONS.map((definition) => normalizeTaskStep(undefined, definition)),
    ...overrides,
  }) as TaskDetail
}

export function getTaskCollectionStorageKey(taskId: string): string {
  return taskId ? `claim_consistency_collected_literature_${taskId}` : ''
}

export function restoreCollectedLiterature(taskId: string): Record<string, boolean> {
  const storageKey = getTaskCollectionStorageKey(taskId)
  if (!storageKey) return {}
  try {
    const raw = window.localStorage.getItem(storageKey)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? parsed as Record<string, boolean> : {}
  } catch (error) {
    console.warn('[TaskDetail] restore collected literature failed:', error)
    return {}
  }
}

export function persistCollectedLiterature(taskId: string, collected: Record<string, boolean>) {
  const storageKey = getTaskCollectionStorageKey(taskId)
  if (!storageKey) return

  try {
    const entries = Object.entries(collected).filter(([, value]) => Boolean(value))
    if (!entries.length) {
      window.localStorage.removeItem(storageKey)
      return
    }
    window.localStorage.setItem(storageKey, JSON.stringify(Object.fromEntries(entries)))
  } catch (error) {
    console.warn('[TaskDetail] persist collected literature failed:', error)
  }
}

export function clearPendingTaskCache(taskId: string) {
  const pendingRunId = window.localStorage.getItem('claim_consistency_pending_run_id')
  if (!taskId || !pendingRunId || String(pendingRunId) !== String(taskId)) return

  ;[
    'claim_consistency_pending_thread_id',
    'claim_consistency_pending_run_id',
    'claim_consistency_pending_topic',
    'claim_consistency_pending_status',
    'claim_consistency_pending_user_scope',
    'claim_consistency_pending_research_type',
    'claim_consistency_pending_report_length',
  ].forEach((key) => window.localStorage.removeItem(key))
}

export function buildPendingTaskFromStorage(taskId: string): TaskDetail | null {
  const pendingRunId =
    window.localStorage.getItem('claim_consistency_pending_run_id')
    || window.localStorage.getItem('claim_consistency_run_id')
  if (!pendingRunId || String(pendingRunId) !== String(taskId)) return null

  return createPendingTaskDetail(String(pendingRunId), {
    thread_id:
      window.localStorage.getItem('claim_consistency_pending_thread_id')
      || window.localStorage.getItem('claim_consistency_thread_id')
      || '',
    topic: window.localStorage.getItem('claim_consistency_pending_topic') || '一致性评估任务',
    research_type:
      window.localStorage.getItem('claim_consistency_pending_research_type') || '综合评估',
    status: (window.localStorage.getItem('claim_consistency_pending_status') || 'queued') as TaskStatus,
  })
}

export function isTerminalTaskStatus(status: string | null | undefined): boolean {
  return TERMINAL_TASK_STATUSES.has(String(status || '').toLowerCase())
}

export function shouldPollTask(status: string | null | undefined): boolean {
  return POLLING_TASK_STATUSES.has(String(status || '').toLowerCase())
}

export function normalizeTaskStepStatus(
  status: string | null | undefined,
): TaskStageView['status'] {
  const normalized = String(status || '').trim().toLowerCase() as TaskStepStatus
  if (normalized === 'completed' || normalized === 'done' || normalized === 'success') {
    return 'completed'
  }
  if (normalized === 'running' || normalized === 'processing') {
    return 'running'
  }
  if (normalized === 'failed' || normalized === 'error') {
    return 'failed'
  }
  if (normalized === 'cancelled' || normalized === 'canceled') {
    return 'cancelled'
  }
  if (normalized === 'skipped') {
    return 'skipped'
  }
  return 'pending'
}

export function getTaskProgress(task: TaskDetail | null): {
  currentStepNo: number
  completedStepCount: number
  activeStageKey: TaskStageKey
} {
  const steps = task?.steps || []
  const runningIndex = steps.findIndex((step) => normalizeTaskStepStatus(step.status) === 'running')
  if (runningIndex >= 0) {
    return {
      currentStepNo: runningIndex + 1,
      completedStepCount: countCompletedSteps(steps),
      activeStageKey: TASK_STAGE_DEFINITIONS[runningIndex].step_key,
    }
  }

  const failedIndex = steps.findIndex((step) => {
    const status = normalizeTaskStepStatus(step.status)
    return status === 'failed' || status === 'cancelled'
  })
  if (failedIndex >= 0) {
    return {
      currentStepNo: failedIndex + 1,
      completedStepCount: countCompletedSteps(steps),
      activeStageKey: TASK_STAGE_DEFINITIONS[failedIndex].step_key,
    }
  }

  const currentStepNo = Math.min(Math.max(Number(task?.current_step || 0), 1), TASK_STAGE_DEFINITIONS.length)
  const completedStepCount = countCompletedSteps(steps)
  const resolvedStepNo = completedStepCount > 0 ? Math.min(completedStepCount, TASK_STAGE_DEFINITIONS.length) : currentStepNo

  return {
    currentStepNo: resolvedStepNo,
    completedStepCount,
    activeStageKey: TASK_STAGE_DEFINITIONS[Math.max(resolvedStepNo - 1, 0)].step_key,
  }
}

export function buildTaskStages(task: TaskDetail | null): TaskStageView[] {
  const normalizedTask = task || createPendingTaskDetail('')
  const progress = getTaskProgress(normalizedTask)
  return TASK_STAGE_DEFINITIONS.map((definition, index) => {
    const step = normalizedTask.steps?.[index] || normalizeTaskStep(undefined, definition)
    const summary = String(step.summary || '').trim() || definition.defaultSummary
    return {
      step_no: definition.step_no,
      step_key: definition.step_key,
      title: definition.title,
      status: normalizeTaskStepStatus(step.status),
      summary,
      sub_steps: normalizeSubSteps(step.sub_steps),
      degradations: normalizeDegradations(step.degradations),
      error: step.error,
      started_at: step.started_at,
      completed_at: step.completed_at,
      failed_at: step.failed_at,
      isActive: progress.currentStepNo === definition.step_no,
    }
  })
}

export function buildTaskResultView(task: TaskDetail | null): TaskResultView {
  const finalResult = resolveFinalResult(task)
  const references = Array.isArray(finalResult.references) ? finalResult.references : []
  const citationMap: Record<string, number> = {}
  const snippetsByReference = new Map<string, string[]>()

  for (const claim of finalResult.claims || []) {
    for (const evidence of claim.evidence || []) {
      const referenceId = String(evidence.reference_id || '')
      if (!referenceId) continue
      const snippets = snippetsByReference.get(referenceId) || []
      if (evidence.snippet) {
        snippets.push(evidence.snippet)
      }
      snippetsByReference.set(referenceId, snippets)
    }
  }

  const referenceViews = references.map((reference, index) => {
    const referenceId = String(reference.reference_id || `R${index + 1}`)
    const citation = index + 1
    citationMap[referenceId] = citation
    return buildLiteratureCardView(reference, citation, snippetsByReference.get(referenceId) || [])
  })

  const claims = (finalResult.claims || []).map((claim) => buildTaskClaimView(claim, citationMap))
  const summary = buildTaskSummaryView(finalResult, claims.length, referenceViews.length)

  return {
    summary,
    claims,
    references: referenceViews,
    citationMap,
    finalReportMarkdown: String(finalResult.final_report_markdown || ''),
  }
}

export function getReferenceCardDomId(referenceId: string): string {
  return `reference-card-${String(referenceId).replace(/[^a-zA-Z0-9_-]+/g, '-')}`
}

export function getLiteratureKey(reference: LiteratureCardView): string {
  return reference.key
}

function normalizeTaskStep(rawStep: TaskStep | null | undefined, definition: TaskStageDefinition): TaskStep {
  return {
    step_no: definition.step_no,
    step_key: definition.step_key,
    title: rawStep?.title || definition.title,
    status: String(rawStep?.status || 'pending'),
    summary: rawStep?.summary || '',
    started_at: rawStep?.started_at,
    completed_at: rawStep?.completed_at,
    failed_at: rawStep?.failed_at,
    sub_steps: Array.isArray(rawStep?.sub_steps) ? rawStep.sub_steps : [],
    degradations: Array.isArray(rawStep?.degradations) ? rawStep.degradations : [],
    payload: rawStep?.payload || {},
    error: rawStep?.error,
  }
}

function normalizeFinalResult(rawResult: FinalResult | null | undefined): FinalResult | null {
  if (!rawResult || typeof rawResult !== 'object') return null
  return rawResult
}

function applyTaskStatusFallbacks(task: TaskDetail): TaskStep[] {
  const taskStatus = String(task.status || '').toLowerCase()
  const currentStep = Number(task.current_step || 0)

  return (task.steps || []).map((step, index) => {
    const nextStep = { ...step }
    const status = normalizeTaskStepStatus(step.status)

    if (taskStatus === 'completed') {
      nextStep.status = status === 'failed' || status === 'cancelled' ? status : 'completed'
      return nextStep
    }

    if ((taskStatus === 'failed' || taskStatus === 'cancelled' || taskStatus === 'canceled') && currentStep === index + 1) {
      nextStep.status = taskStatus === 'failed' ? 'failed' : 'cancelled'
      return nextStep
    }

    if (currentStep > 0 && index + 1 < currentStep && status === 'pending') {
      nextStep.status = 'completed'
      return nextStep
    }

    if (currentStep > 0 && index + 1 === currentStep && status === 'pending' && shouldPollTask(taskStatus)) {
      nextStep.status = 'running'
      return nextStep
    }

    return nextStep
  })
}

function normalizeSubSteps(subSteps: TaskStep['sub_steps']): Array<{ title: string; status: string }> {
  if (!Array.isArray(subSteps)) return []
  return subSteps
    .map((item) => ({
      title: String(item.title || item.name || item.text || '').trim(),
      status: String(item.status || '').trim(),
    }))
    .filter((item) => item.title)
}

function normalizeDegradations(
  degradations: TaskStep['degradations'],
): Array<{ reason: string; detail?: string }> {
  if (!Array.isArray(degradations)) return []
  return degradations
    .map((item) => ({
      reason: String(item.reason || '').trim(),
      detail: String(item.detail || '').trim() || undefined,
    }))
    .filter((item) => item.reason)
}

function countCompletedSteps(steps: TaskStep[]): number {
  let completed = 0
  for (const step of steps) {
    const status = normalizeTaskStepStatus(step.status)
    if (status !== 'completed' && status !== 'skipped') {
      break
    }
    completed += 1
  }
  return completed
}

function resolveFinalResult(task: TaskDetail | null): FinalResult {
  return task?.final_result || task?.result || { claims: [], references: [] }
}

function buildTaskSummaryView(
  result: FinalResult,
  claimCount: number,
  referenceCount: number,
): TaskSummaryView {
  const rawSummary = result.summary || {}
  const statusCounts = { ...(rawSummary.status_counts || {}) }
  return {
    claimCount: rawSummary.claim_count ?? claimCount,
    referenceCount: rawSummary.reference_count ?? referenceCount,
    statusCounts,
    degraded: Boolean(rawSummary.degraded),
    degradations: Array.isArray(rawSummary.degradations)
      ? rawSummary.degradations.map((item) => ({
          stage: String(item.stage || ''),
          reason: String(item.reason || ''),
          detail: item.detail ? String(item.detail) : undefined,
        }))
      : [],
  }
}

function buildTaskClaimView(
  claim: NonNullable<FinalResult['claims']>[number],
  citationMap: Record<string, number>,
): TaskClaimView {
  const evidence = Array.isArray(claim.evidence) ? claim.evidence : []
  return {
    claim_id: String(claim.claim_id || ''),
    text: String(claim.text || ''),
    status: String(claim.status || '缺乏文献支持'),
    reason: String(claim.reason || ''),
    method: claim.method ? String(claim.method) : undefined,
    evidence: evidence
      .map((item) => buildTaskClaimEvidence(item, citationMap))
      .filter((item) => Boolean(item.reference_id)),
  }
}

function buildTaskClaimEvidence(
  evidence: EvidenceItem,
  citationMap: Record<string, number>,
) {
  const referenceId = String(evidence.reference_id || '')
  return {
    evidence_id: String(evidence.evidence_id || ''),
    reference_id: referenceId,
    citation: citationMap[referenceId] || 0,
    relation: String(evidence.relation || ''),
    title: String(evidence.title || ''),
    snippet: String(evidence.snippet || ''),
    score: Number(evidence.score || 0),
  }
}

function buildLiteratureCardView(
  reference: ReferenceItem,
  citation: number,
  snippets: string[],
): LiteratureCardView {
  const authorsText = Array.isArray(reference.authors) ? reference.authors.join('，') : ''
  const metaParts = [authorsText, reference.year ? String(reference.year) : '', reference.venue || '']
    .map((item) => item.trim())
    .filter(Boolean)

  return {
    key: String(reference.reference_id || reference.paper_id || reference.title || `ref-${citation}`),
    referenceId: String(reference.reference_id || ''),
    citation,
    title: String(reference.title || '未命名文献'),
    authorsText,
    metaText: metaParts.join(' · '),
    doi: reference.doi ? String(reference.doi) : undefined,
    url: resolveReferenceUrl(reference),
    abstract: reference.abstract ? String(reference.abstract) : undefined,
    source: reference.source ? String(reference.source) : undefined,
    citationCount: reference.citation_count ? Number(reference.citation_count) : undefined,
    snippets: Array.from(new Set(snippets.filter(Boolean))),
    labels: buildReferenceLabels(reference),
  }
}

function buildReferenceLabels(reference: ReferenceItem): string[] {
  const labels: string[] = []
  if (reference.source) {
    labels.push(String(reference.source))
  }
  if (reference.language) {
    labels.push(String(reference.language).toUpperCase())
  }
  if (reference.doi) {
    labels.push('DOI')
  }
  return labels
}

function resolveReferenceUrl(reference: ReferenceItem): string | undefined {
  if (reference.url) return String(reference.url)
  if (reference.paper_id) {
    return `https://www.nstl.gov.cn/paper_detail.html?id=${encodeURIComponent(reference.paper_id)}`
  }
  return undefined
}
