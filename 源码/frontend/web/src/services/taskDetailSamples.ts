import type { TaskDetail } from '../types'

const SAMPLE_TASK_TITLE_LIST = [
  '室温超导材料的研究争议与验证路径',
  '土壤微塑料对农作物生长与食品安全的影响机制',
  '基于深度学习的医学影像分析技术在肺癌早期筛查中的应用方法',
]

const SAMPLE_TASK_TITLES = new Set(SAMPLE_TASK_TITLE_LIST)

let sampleBundlePromise: Promise<Record<string, TaskDetail>> | null = null

export function isSampleTaskTitle(taskId: string): boolean {
  return SAMPLE_TASK_TITLES.has(String(taskId || '').trim())
}

export async function loadSampleTask(taskId: string): Promise<TaskDetail | null> {
  if (!isSampleTaskTitle(taskId)) return null
  if (!sampleBundlePromise) {
    sampleBundlePromise = fetch(`${import.meta.env.BASE_URL}legacy/report-data.js`, {
      cache: 'no-cache',
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`样例报告加载失败: ${response.status}`)
        }
        const source = await response.text()
        const loader = new Function(
          `${source}\nreturn { reportData, reportData2, reportData3 };`,
        ) as () => { reportData: TaskDetail; reportData2: TaskDetail; reportData3: TaskDetail }

        const { reportData, reportData2, reportData3 } = loader()
        return {
          [SAMPLE_TASK_TITLE_LIST[0]]: reportData,
          [SAMPLE_TASK_TITLE_LIST[1]]: reportData2,
          [SAMPLE_TASK_TITLE_LIST[2]]: reportData3,
        }
      })
      .catch((error) => {
        sampleBundlePromise = null
        throw error
      })
  }

  const sampleMap = await sampleBundlePromise
  return sampleMap[String(taskId).trim()] || null
}
