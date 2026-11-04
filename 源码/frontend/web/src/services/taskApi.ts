import { apiRequest } from './api'
import type { ParsedFileMeta, TaskDetail } from '../types'

export async function createRun(payload: {
  userInput: string
  researchType: string
  subjectArea: string
  yearRange: [number, number]
  languagePref: string
  uploadedFiles: ParsedFileMeta[]
}): Promise<{ id: string; thread_id: string; status: string; created_at: string }> {
  const threadId = `thread_${Date.now()}`
  return apiRequest(`/v1/threads/${threadId}/runs`, {
    method: 'POST',
    body: JSON.stringify({
      input: [
        {
          type: 'message',
          role: 'user',
          content: [
            { type: 'input_text', text: payload.userInput },
            {
              type: 'input_json',
              json: {
                research_type: payload.researchType,
                subject_area: payload.subjectArea,
                year_range: payload.yearRange,
                language_pref: payload.languagePref,
                uploaded_files: payload.uploadedFiles.map((file) => ({
                  fileId: file.fileId,
                  name: file.name,
                  type: file.type,
                  size: file.size,
                  parsedAt: file.parsedAt,
                  url: file.url,
                })),
              },
            },
          ],
        },
      ],
    }),
  })
}

export async function getTask(taskId: string): Promise<TaskDetail> {
  const response = await apiRequest<{ data: TaskDetail }>(
    `/v1/tasks/${encodeURIComponent(taskId)}?include_steps=true`,
  )
  return response.data
}

export async function listTasks(params: {
  page: number
  pageSize: number
  status?: string
  search?: string
}): Promise<{ data: TaskDetail[]; total: number }> {
  const search = new URLSearchParams()
  search.set('page', String(params.page))
  search.set('page_size', String(params.pageSize))
  if (params.status && params.status !== 'all') {
    search.set('status', params.status)
  }
  if (params.search) {
    search.set('search', params.search)
  }
  return apiRequest(`/v1/tasks?${search.toString()}`)
}

export async function cancelRun(threadId: string, taskId: string): Promise<void> {
  await apiRequest(`/v1/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(taskId)}/cancel`, {
    method: 'POST',
  })
}
