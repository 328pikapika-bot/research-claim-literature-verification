import { beforeEach, describe, expect, it } from 'vitest'

import {
  buildPendingTaskFromStorage,
  buildTaskStages,
  getTaskCollectionStorageKey,
  normalizeTaskDetail,
  normalizeTaskStepStatus,
  persistCollectedLiterature,
  restoreCollectedLiterature,
} from './taskDetailHelpers'

describe('taskDetailHelpers', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('maps backend step statuses to deterministic stage statuses', () => {
    expect(normalizeTaskStepStatus('pending')).toBe('pending')
    expect(normalizeTaskStepStatus('running')).toBe('running')
    expect(normalizeTaskStepStatus('processing')).toBe('running')
    expect(normalizeTaskStepStatus('completed')).toBe('completed')
    expect(normalizeTaskStepStatus('success')).toBe('completed')
    expect(normalizeTaskStepStatus('failed')).toBe('failed')
    expect(normalizeTaskStepStatus('cancelled')).toBe('cancelled')
    expect(normalizeTaskStepStatus('skipped')).toBe('skipped')
  })

  it('keeps pending backend placeholder steps from rendering as completed', () => {
    const task = normalizeTaskDetail({
      task_id: 'task-running',
      thread_id: 'thread-1',
      topic: '测试任务',
      research_type: '综合评估',
      status: 'running',
      created_at: '2026-06-03T12:00:00+08:00',
      current_step: 2,
      steps_data: [
        { step_no: 1, step_key: 'preprocess', title: '输入预处理', status: 'completed' },
        { step_no: 2, step_key: 'claim_extract', title: '文本解析与主张提取', status: 'running' },
        { step_no: 3, step_key: 'retrieval', title: '文献检索与证据组织', status: 'pending' },
        { step_no: 4, step_key: 'judgment', title: '一致性判定', status: 'pending' },
        { step_no: 5, step_key: 'output', title: '引用标注与最终输出', status: 'pending' },
      ],
    })

    const stages = buildTaskStages(task)
    expect(stages[0].status).toBe('completed')
    expect(stages[1].status).toBe('running')
    expect(stages[2].status).toBe('pending')
    expect(stages[3].status).toBe('pending')
    expect(stages[4].status).toBe('pending')
  })

  it('persists and restores task-level literature collections with the legacy key', () => {
    const taskId = 'task-collection'
    persistCollectedLiterature(taskId, {
      R1: true,
      R2: false,
      R3: true,
    })

    expect(window.localStorage.getItem(getTaskCollectionStorageKey(taskId))).toBe('{"R1":true,"R3":true}')
    expect(restoreCollectedLiterature(taskId)).toEqual({
      R1: true,
      R3: true,
    })
  })

  it('builds a pending task fallback from local storage', () => {
    window.localStorage.setItem('claim_consistency_pending_run_id', 'task-pending')
    window.localStorage.setItem('claim_consistency_pending_topic', '排队中的一致性任务')
    window.localStorage.setItem('claim_consistency_pending_status', 'queued')
    window.localStorage.setItem('claim_consistency_pending_research_type', '综合评估')

    const task = buildPendingTaskFromStorage('task-pending')
    expect(task?.task_id).toBe('task-pending')
    expect(task?.topic).toBe('排队中的一致性任务')
    expect(task?.status).toBe('queued')
    expect(task?.steps?.every((step) => step.status === 'pending')).toBe(true)
  })
})
