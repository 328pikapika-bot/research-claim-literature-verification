import { createRouter, createWebHistory } from 'vue-router'

import HistoryPage from './pages/HistoryPage.vue'
import HomePage from './pages/HomePage.vue'
import TaskDetailPage from './pages/TaskDetailPage.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomePage },
    { path: '/task/:taskId', name: 'task-detail', component: TaskDetailPage, props: true },
    { path: '/history', name: 'history', component: HistoryPage },
    {
      path: '/index.html',
      redirect: (to) => ({ name: 'home', query: to.query }),
    },
    {
      path: '/history.html',
      redirect: () => ({ name: 'history' }),
    },
    {
      path: '/task_detail.html',
      redirect: (to) => ({
        name: 'task-detail',
        params: {
          taskId: String(to.query.task_id || to.query.run_id || to.query.report || ''),
        },
        query: to.query.thread_id ? { thread_id: String(to.query.thread_id) } : {},
      }),
    },
  ],
})

export default router
