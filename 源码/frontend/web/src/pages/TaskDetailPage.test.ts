import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import TaskDetailPage from './TaskDetailPage.vue'

vi.mock('../components/LegacyPage.vue', () => ({
  default: defineComponent({
    name: 'LegacyPage',
    props: {
      page: {
        type: String,
        required: true,
      },
    },
    setup(props) {
      return () => h('div', {
        class: 'legacy-page-stub',
        'data-page': props.page,
      })
    },
  }),
}))

describe('TaskDetailPage', () => {
  it('renders the legacy task detail shell', () => {
    const wrapper = mount(TaskDetailPage)

    expect(wrapper.get('.legacy-page-stub').attributes('data-page')).toBe('task_detail')
  })
})
