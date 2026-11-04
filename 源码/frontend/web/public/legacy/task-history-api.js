/**
 * 任务历史后端 API 集成模块
 *
 * 提供任务历史的后端存储功能，支持双写模式（localStorage + 后端）
 */

class TaskHistoryAPI {
  constructor() {
    this.enableBackend = true;  // 是否启用后端存储
  }

  /**
   * 获取 API 基础地址
   * 从 ClaimConsistencyConfig 统一配置中获取
   *
   * @returns {string} API 基础地址
   */
  getApiBase() {
    return ClaimConsistencyConfig.getApiBase();
  }

  /**
   * 获取用户标识（从认证系统）
   *
   * @returns {string} 用户 ID 或 'default'
   */
  getUserScope() {
    const params = new URLSearchParams(window.location.search);
    const taskId = params.get('task_id') || params.get('run_id');
    const pendingRunId = localStorage.getItem('claim_consistency_pending_run_id');
    const pendingUserScope = localStorage.getItem('claim_consistency_pending_user_scope');
    if (taskId && pendingRunId && pendingUserScope && String(taskId) === String(pendingRunId)) {
      return pendingUserScope;
    }

    // 从 auth.js 的 authManager 获取用户信息
    // console.log('[TaskHistoryAPI] getUserScope 调试:', {
    //  hasAuthManager: !!window.authManager,
    //  hasSessionManager: !!(window.authManager && window.authManager.sessionManager)
    //});

    if (window.authManager && window.authManager.sessionManager) {
      const session = window.authManager.sessionManager.getSession();
      // console.log('[TaskHistoryAPI] session 数据:', session);

      if (session && session.user && session.user.userId) {
        const userId = session.user.userId;
        // console.log('[TaskHistoryAPI] 获取到 userId:', userId);

        // 与首页创建任务保持一致：只过滤后端明确禁止的空值/占位值。
        if (userId &&
            userId !== 'mock_user_id' &&
            userId !== 'unknown' &&
            userId !== 'default') {
          // console.log('[TaskHistoryAPI] ✓ 返回用户 ID:', userId);
          return userId;
        } else {
          // console.log('[TaskHistoryAPI] ✗ userId 是占位值，返回 default');
          return 'default';
        }
      } else {
        // console.log('[TaskHistoryAPI] ✗ session 数据不完整');
      }
    }

    // authManager 未初始化或会话不存在，静默返回 default
    // console.log('[TaskHistoryAPI] ✗ authManager 未初始化，返回 default');
    return 'default';
  }

  /**
   * 创建任务记录
   */
  async createTask(taskData) {
    // console.log("taskData", taskData);
    // 1. 优先写入后端
    if (this.enableBackend) {
      try {
        const response = await fetch(`${this.getApiBase()}/v1/tasks`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-User-Scope': this.getUserScope()
          },
          body: JSON.stringify(taskData)
        });

        if (response.ok) {
          const result = await response.json();
          // console.log('[TaskHistoryAPI] 任务已创建到后端:', result);
          return { success: true, source: 'backend', data: result };
        } else {
          console.warn('[TaskHistoryAPI] 后端创建失败，回退到 localStorage');
        }
      } catch (err) {
        console.error('[TaskHistoryAPI] 后端创建失败，回退到 localStorage:', err);
      }
    }

    // 2. 回退到 localStorage（仅在后端失败时）
    try {
      const storedTasks = localStorage.getItem('claim_consistency_task_history');
      let allTasks = storedTasks ? JSON.parse(storedTasks) : [];

      // 检查是否已存在
      const exists = allTasks.some(t => t.task_id === taskData.task_id);
      if (!exists) {
        allTasks.push(taskData);
        localStorage.setItem('claim_consistency_task_history', JSON.stringify(allTasks));
      }
      return { success: true, source: 'localStorage' };
    } catch (err) {
      console.error('[TaskHistoryAPI] localStorage 写入失败:', err);
      return { success: false, source: 'localStorage', error: err.message };
    }
  }

  /**
   * 更新任务记录
   */
  async updateTask(taskId, updates) {
    // console.log("taskId", taskId);
    // console.log("updates", updates);
    // 1. 优先更新后端
    if (this.enableBackend) {
      try {
        const response = await fetch(`${this.getApiBase()}/v1/tasks/${taskId}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'X-User-Scope': this.getUserScope()
          },
          body: JSON.stringify(updates)
        });

        if (response.ok) {
          const result = await response.json();
          return { success: true, source: 'backend', data: result };
        } else {
          console.warn('[TaskHistoryAPI] 后端更新失败，回退到 localStorage');
        }
      } catch (err) {
        console.error('[TaskHistoryAPI] 后端更新失败，回退到 localStorage:', err);
      }
    }

    // 2. 回退到 localStorage（仅在后端失败时）
    try {
      const storedTasks = localStorage.getItem('claim_consistency_task_history');
      if (storedTasks) {
        let allTasks = JSON.parse(storedTasks);
        const taskIndex = allTasks.findIndex(t => t.task_id === taskId);

        if (taskIndex !== -1) {
          // 合并更新
          Object.assign(allTasks[taskIndex], updates);
          allTasks[taskIndex].last_updated_at = new Date().toISOString();
          localStorage.setItem('claim_consistency_task_history', JSON.stringify(allTasks));
        }
      }
      return { success: true, source: 'localStorage' };
    } catch (err) {
      console.error('[TaskHistoryAPI] localStorage 更新失败:', err);
      return { success: false, source: 'localStorage', error: err.message };
    }
  }

  /**
   * 查询任务列表
   */
  async listTasks(options = {}) {
    // 优先从后端加载
    if (this.enableBackend) {
      try {
        const params = new URLSearchParams();
        if (options.status) params.append('status', options.status);
        if (options.search) params.append('search', options.search);
        if (options.page) params.append('page', options.page);
        if (options.page_size) params.append('page_size', options.page_size);

        const response = await fetch(`${this.getApiBase()}/v1/tasks?${params}`, {
          headers: {
            'X-User-Scope': this.getUserScope()
          }
        });

        if (response.ok) {
          const data = await response.json();

          // 将后端数据同步到 localStorage 作为缓存
          try {
            if (data.data && Array.isArray(data.data)) {
              localStorage.setItem('claim_consistency_task_history', JSON.stringify(data.data));
              // console.log('[TaskHistoryAPI] 已将', data.data.length, '个任务同步到 localStorage');
            }
          } catch (err) {
            console.warn('[TaskHistoryAPI] 同步到 localStorage 失败:', err);
          }

          return { success: true, source: 'backend', data: data.data, total: data.total };
        }
      } catch (err) {
        console.warn('[TaskHistoryAPI] 后端加载失败，回退到 localStorage:', err);
      }
    }

    // 回退到 localStorage
    try {
      const storedTasks = localStorage.getItem('claim_consistency_task_history');
      const tasks = storedTasks ? JSON.parse(storedTasks) : [];

      // 简单的筛选和搜索
      let filtered = tasks;
      if (options.status && options.status !== 'all') {
        filtered = filtered.filter(t => t.status === options.status);
      }
      if (options.search) {
        const search = options.search.toLowerCase();
        filtered = filtered.filter(t =>
          t.topic.toLowerCase().includes(search) ||
          t.research_type.toLowerCase().includes(search)
        );
      }

      // 排序（按创建时间倒序）
      filtered.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

      return { success: true, source: 'localStorage', data: filtered, total: filtered.length };
    } catch (err) {
      console.error('[TaskHistoryAPI] localStorage 加载失败:', err);
      return { success: false, source: 'localStorage', data: [], total: 0 };
    }
  }

  /**
   * 查询单个任务详情
   */
  async getTask(taskId, includeSteps = false) {
    const userScope = this.getUserScope();
    // console.log('[TaskHistoryAPI] getTask 请求参数:', {
//      taskId,
//      includeSteps,
//      userScope
//    });

    // 优先从后端加载
    if (this.enableBackend) {
      try {
        const params = includeSteps ? '?include_steps=true' : '';
        const response = await fetch(`${this.getApiBase()}/v1/tasks/${taskId}${params}`, {
          headers: {
            'X-User-Scope': this.getUserScope()
          }
        });

        if (response.ok) {
          const payload = await response.json();
          const data = payload && payload.data && (payload.success !== undefined || payload.source)
            ? payload.data
            : payload;

          // 将后端数据更新到 localStorage（包含 steps）
          try {
            const storedTasks = localStorage.getItem('claim_consistency_task_history');
            let tasks = storedTasks ? JSON.parse(storedTasks) : [];

            // 查找并更新或添加任务
            const index = tasks.findIndex(t => t.task_id === taskId);
            if (index !== -1) {
              tasks[index] = data;
              // console.log('[TaskHistoryAPI] 已更新 localStorage 中的任务:', taskId);
            } else {
              tasks.push(data);
              // console.log('[TaskHistoryAPI] 已添加任务到 localStorage:', taskId);
            }

            localStorage.setItem('claim_consistency_task_history', JSON.stringify(tasks));
          } catch (err) {
            console.warn('[TaskHistoryAPI] 同步到 localStorage 失败:', err);
          }

          return { success: true, source: payload?.source || 'backend', data };
        } else {
          console.warn(`[TaskHistoryAPI] 后端返回 ${response.status}，回退到 localStorage`);
        }
      } catch (err) {
        console.warn('[TaskHistoryAPI] 后端加载失败，回退到 localStorage:', err);
      }
    }

    // 回退到 localStorage
    // console.log('[TaskHistoryAPI] 尝试从 localStorage 加载任务:', taskId);
    try {
      const storedTasks = localStorage.getItem('claim_consistency_task_history');
      if (storedTasks) {
        const tasks = JSON.parse(storedTasks);
        // console.log('[TaskHistoryAPI] localStorage 中共有', tasks.length, '个任务');
        const task = tasks.find(t => t.task_id === taskId);
        if (task) {
          // console.log('[TaskHistoryAPI] ✓ 从 localStorage 找到任务:', {
//            task_id: task.task_id,
//            topic: task.topic,
//            has_steps: !!task.steps,
//            steps_count: task.steps?.length || 0
//          });
          return { success: true, source: 'localStorage', data: task };
        } else {
          console.warn('[TaskHistoryAPI] ✗ localStorage 中未找到任务:', taskId);
        }
      } else {
        console.warn('[TaskHistoryAPI] ✗ localStorage 中没有任务历史数据');
      }
      return { success: false, source: 'localStorage', data: null };
    } catch (err) {
      console.error('[TaskHistoryAPI] localStorage 加载失败:', err);
      return { success: false, source: 'localStorage', data: null };
    }
  }

  /**
   * 删除任务记录
   */
  async deleteTask(taskId) {
    // 1. 优先从后端删除
    if (this.enableBackend) {
      try {
        const response = await fetch(`${this.getApiBase()}/v1/tasks/${taskId}`, {
          method: 'DELETE',
          headers: {
            'X-User-Scope': this.getUserScope()
          }
        });

        if (response.ok) {
          // 同步删除 localStorage 中的缓存
          this._deleteFromLocalStorage(taskId);
          return { success: true, source: 'backend' };
        } else if (response.status === 404) {
          return { success: false, source: 'backend', message: '任务不存在' };
        }
      } catch (err) {
        console.warn('[TaskHistoryAPI] 后端删除失败，回退到 localStorage:', err);
      }
    }

    // 2. 回退到 localStorage 删除
    try {
      this._deleteFromLocalStorage(taskId);
      return { success: true, source: 'localStorage' };
    } catch (err) {
      console.error('[TaskHistoryAPI] localStorage 删除失败:', err);
      return { success: false, source: 'localStorage', error: err.message };
    }
  }

  /**
   * 从 localStorage 删除任务（内部方法）
   */
  _deleteFromLocalStorage(taskId) {
    const storedTasks = localStorage.getItem('claim_consistency_task_history');
    if (storedTasks) {
      let tasks = JSON.parse(storedTasks);
      tasks = tasks.filter(t => t.task_id !== taskId);
      localStorage.setItem('claim_consistency_task_history', JSON.stringify(tasks));
    }
  }

  /**
   * 数据迁移：将 localStorage 数据批量导入后端
   */
  async migrateToBackend() {
    if (!this.enableBackend) {
      return { success: false, message: '后端存储未启用' };
    }

    try {
      const storedTasks = localStorage.getItem('claim_consistency_task_history');
      if (!storedTasks) {
        return { success: false, message: '没有需要迁移的数据' };
      }

      const tasks = JSON.parse(storedTasks);

      const response = await fetch(`${this.getApiBase()}/v1/tasks/migrate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-User-Scope': this.getUserScope()
        },
        body: JSON.stringify({ tasks })
      });

      if (!response.ok) {
        throw new Error(`迁移失败: ${response.statusText}`);
      }

      const result = await response.json();

      // 如果迁移成功且没有错误，清理 localStorage
      if (result.errors.length === 0) {
        localStorage.removeItem('claim_consistency_task_history');
        // console.log('[TaskHistoryAPI] 数据迁移成功，localStorage 已清理');
      }

      return {
        success: true,
        migrated: result.migrated,
        total: result.total,
        errors: result.errors
      };
    } catch (err) {
      console.error('[TaskHistoryAPI] 数据迁移失败:', err);
      return { success: false, message: err.message };
    }
  }
}

// 创建全局实例
window.taskHistoryAPI = new TaskHistoryAPI();
