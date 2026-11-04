<script setup lang="ts">
import type { TaskStep } from '../types'

defineProps<{
  steps: TaskStep[]
  currentStep: number
}>()

function statusLabel(status: string): string {
  switch (status) {
    case 'completed':
      return '已完成'
    case 'running':
      return '进行中'
    case 'failed':
      return '失败'
    default:
      return '待执行'
  }
}
</script>

<template>
  <div class="thinking-trace-list">
    <div
      v-for="step in steps"
      :key="step.step_key"
      class="trace-card"
      :class="[`trace-${step.status}`, { active: currentStep === step.step_no }]"
    >
      <div class="trace-card-header">
        <div class="trace-card-left">
          <span class="trace-card-index">{{ step.step_no }}</span>
          <span class="trace-card-title">{{ step.title }}</span>
        </div>
        <div class="trace-card-right">
          <span class="trace-card-status" :class="step.status">{{ statusLabel(step.status) }}</span>
        </div>
      </div>
      <div class="trace-card-body">
        <p class="trace-card-summary">{{ step.summary || '等待执行中' }}</p>
        <ul v-if="step.sub_steps?.length" class="trace-card-mini-list">
          <li v-for="(item, index) in step.sub_steps" :key="index">
            {{ item.name || item.title || item.text || '子步骤' }}
            <span class="mini-status">{{ item.status || '' }}</span>
          </li>
        </ul>
        <div v-if="step.degradations?.length" class="trace-card-degradations">
          <p v-for="(item, index) in step.degradations" :key="index">
            降级：{{ item.reason }}<span v-if="item.detail"> - {{ item.detail }}</span>
          </p>
        </div>
        <p v-if="step.error" class="trace-card-error">{{ step.error }}</p>
      </div>
    </div>
  </div>
</template>
