/**
 * 一致性评估智能体 - 通用 JavaScript 工具库
 * 
 * 注意: DEFAULT_API_BASE 和 ClaimConsistencyConfig 需要在使用前通过引入 config.js 定义
 */

const qs = (selector) => document.querySelector(selector);
const getParam = (key) => new URLSearchParams(window.location.search).get(key);

// ============ 步骤字段映射配置 ============
const STEP_FIELD_MAP = {
  1: { trace: 'requirement_trace', markdown: 'requirement_markdown', title: '需求解析智能体' },
  2: { trace: 'topic_analysis_trace', markdown: 'topic_analysis_markdown', title: '主题勘探智能体' },
  3: { trace: 'framework_trace', markdown: 'outline_markdown', title: '框架规划智能体' },
  4: { trace: 'retrieval_trace', markdown: null, title: '混合检索智能体' },
  5: { trace: null, markdown: null, title: '文献筛选智能体' },
  6: { trace: 'draft_trace', markdown: 'draft_report_markdown', title: '内容合成智能体' },
  7: { trace: 'logic_trace', markdown: 'validated_report_markdown', title: '逻辑验证智能体' },
  8: { trace: 'formatting_trace', markdown: 'formatted_outputs', title: '格式编排智能体' },
  9: { trace: 'quality_trace', markdown: null, title: '质量评估智能体' },
  10: { trace: 'final_trace', markdown: 'output', title: '最终化' }
};

// ============ 流式事件管理器 ============
const StreamingManager = {
  // 当前步骤的思考内容缓冲区
  buffer: new Map(),
  // 当前活动的事件源
  eventSource: null,
  // 当前显示的节点
  currentNode: null,
  
  // 初始化
  init() {
    this.buffer.clear();
    this.currentNode = null;
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  },
  
  // 连接事件流
  connect(threadId, runId, apiBase, onEvent) {
    this.init();
    const url = `${apiBase}/v1/threads/${threadId}/runs/${runId}/events?after_sequence=0`;
    
    console.log("[SSE] 连接到:", url);
    this.eventSource = new EventSource(url);
    
    // 更新连接状态
    this.updateConnectionStatus('connecting');
    
    // 监听所有类型的事件
    this.eventSource.onopen = () => {
      console.log("[SSE] 连接已建立");
      this.updateConnectionStatus('connected');
    };
    
    this.eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log("[SSE] 收到消息:", data);
        this.handleEvent(data, onEvent);
      } catch (err) {
        console.error("[SSE] 解析事件失败:", err);
      }
    };
    
    this.eventSource.onerror = (err) => {
      console.error("[SSE] 连接错误:", err);
      this.updateConnectionStatus('error');
      // 如果连接已关闭，尝试重新连接
      if (this.eventSource?.readyState === EventSource.CLOSED) {
        console.log("[SSE] 连接已关闭");
        this.updateConnectionStatus('disconnected');
      }
    };
    
    // 特定事件类型监听（用于更精细的控制）
    this.eventSource.addEventListener("response.created", (event) => {
      console.log("[SSE] Run 开始:", JSON.parse(event.data));
      this.appendSystemLog("Run 开始执行");
    });
    
    this.eventSource.addEventListener("state.values", (event) => {
      const data = JSON.parse(event.data);
      console.log("[SSE] 状态值:", data);
      this.updateThinkingProcess(data);
    });

    this.eventSource.addEventListener("state_values", (event) => {
      const data = JSON.parse(event.data);
      console.log("[SSE] 状态值(v3.4):", data);
      this.updateThinkingProcess(data);
    });
    
    this.eventSource.addEventListener("state.updates", (event) => {
      const data = JSON.parse(event.data);
      console.log("[SSE] 状态更新:", data);
      this.updateThinkingProcess(data);
    });

    this.eventSource.addEventListener("state_updates", (event) => {
      const data = JSON.parse(event.data);
      console.log("[SSE] 状态更新(v3.4):", data);
      this.updateThinkingProcess(data);
    });
    
    this.eventSource.addEventListener("debug", (event) => {
      const data = JSON.parse(event.data);
      console.log("[SSE] 调试信息:", data);
      if (!this.updateThinkingProcessFromDebug(data)) {
        this.appendDebugLog(data);
      }
    });
    
    this.eventSource.addEventListener("response.requires_action", (event) => {
      const data = JSON.parse(event.data);
      console.log("[SSE] 收到 HITL 中断:", data);
      this.handleRequiresAction(data, onEvent);
    });
    
    this.eventSource.addEventListener("response.completed", (event) => {
      console.log("[SSE] Run 完成");
      this.appendSystemLog("Run 执行完成");
      this.updateConnectionStatus('completed');
      this.close();
    });
  },
  
  // 处理事件
  handleEvent(data, callback) {
    if (callback) callback(data);
  },
  
  // 更新连接状态显示
  updateConnectionStatus(status) {
    const statusEl = qs("#connectionStatus");
    if (!statusEl) return;
    
    const statusMap = {
      'connecting': { text: '连接中...', class: 'connecting' },
      'connected': { text: '已连接', class: 'connected' },
      'error': { text: '连接错误', class: 'error' },
      'disconnected': { text: '已断开', class: 'disconnected' },
      'completed': { text: '已完成', class: 'completed' },
    };
    
    const info = statusMap[status] || statusMap['disconnected'];
    statusEl.textContent = info.text;
    statusEl.className = `connection-status ${info.class}`;
  },
  
  // 更新思考过程显示
  updateThinkingProcess(data) {
    // 从数据中提取节点信息和状态
    let nodeName = null;
    let state = null;
    
    if (data.node) {
      nodeName = data.node;
    } else if (data.data?.node) {
      nodeName = data.data.node;
    }
    
    if (data.state) {
      state = data.state;
    } else if (data.updates) {
      state = data.updates;
    } else if (data.data?.state) {
      state = data.data.state;
    }
    
    if (!state) return;
    
    // 根据节点名确定要显示的 trace 字段
    const traceField = this.getTraceFieldForNode(nodeName);
    if (!traceField) return;
    
    // 从 state 中提取 trace 内容
    let traceContent = '';
    if (typeof state === 'object') {
      traceContent = state[traceField] || '';
    }
    
    if (traceContent) {
      // 实时更新到对应的步骤
      this.buffer.set(nodeName, traceContent);
      this.renderThinkingProcess(nodeName, traceContent);
    }
  },

  // 从 debug 事件流中增量更新思考过程
  updateThinkingProcessFromDebug(data) {
    const nodeName = data.node || data.data?.node;
    if (!nodeName) return false;

    const delta = data.delta || data.data?.delta || "";
    const message = data.message || data.data?.message || "";
    if (!delta && !message) return false;

    const prev = this.buffer.get(nodeName) || "";
    let next = prev;
    if (message) {
      next = `${prev}${prev ? "\n" : ""}${message}`;
    }
    if (delta) {
      next = `${next}${delta}`;
    }
    this.buffer.set(nodeName, next);
    this.renderThinkingProcess(nodeName, next);
    return true;
  },
  
  // 获取节点对应的 trace 字段名
  getTraceFieldForNode(nodeName) {
    const mapping = {
      'collect_and_analyze_requirements': 'requirement_trace', // 重构后
      'hitl_confirm_requirements_unified': 'requirement_trace', // 重构后
      'topic_landscape': 'topic_analysis_trace',
      'outline_planning': 'framework_trace',
      'hybrid_retrieval': 'retrieval_trace',
      'content_synthesis': 'draft_trace',
      'logic_validation': 'logic_trace',
      'quality_evaluation': 'quality_trace',
      'format_layout': 'formatting_trace',
      'finalize': 'final_trace',
    };
    return mapping[nodeName] || null;
  },
  
  // 渲染思考过程到页面
  renderThinkingProcess(nodeName, content) {
    const analysisTrace = qs("#analysisTrace");
    if (!analysisTrace) return;
    
    // 如果是新节点，添加分隔线
    if (this.currentNode !== nodeName) {
      this.currentNode = nodeName;
    }
    
    // 格式化显示内容
    const timestamp = new Date().toLocaleTimeString();
    const nodeDisplayName = this.getNodeDisplayName(nodeName);
    const header = `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n【${timestamp}】${nodeDisplayName}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n`;
    
    analysisTrace.textContent = header + content;
    
    // 添加流式更新动画效果
    analysisTrace.classList.add('streaming-update');
    setTimeout(() => {
      analysisTrace.classList.remove('streaming-update');
    }, 500);
    
    // 自动滚动到底部
    analysisTrace.scrollTop = analysisTrace.scrollHeight;
  },
  
  // 获取节点显示名称
  getNodeDisplayName(nodeName) {
    const displayNames = {
      'collect_and_analyze_requirements': '📥 需求收集与分析', // 重构后
      'hitl_confirm_requirements_unified': '✅ 确认需求', // 重构后
      'topic_landscape': '🌐 主题勘探',
      'outline_planning': '📋 框架规划',
      'hybrid_retrieval': '🔍 混合检索',
      'content_synthesis': '📝 内容合成',
      'logic_validation': '✓ 逻辑验证',
      'format_layout': '📄 格式编排',
      'quality_evaluation': '⭐ 质量评估',
      'finalize': '🎯 最终化',
    };
    return displayNames[nodeName] || nodeName;
  },
  
  // 追加系统日志
  appendSystemLog(message) {
    const analysisTrace = qs("#analysisTrace");
    if (!analysisTrace) return;
    
    const timestamp = new Date().toLocaleTimeString();
    const logEntry = `\n[${timestamp}] 🔔 ${message}\n`;
    
    analysisTrace.textContent += logEntry;
    analysisTrace.scrollTop = analysisTrace.scrollHeight;
  },
  
  // 追加调试日志
  appendDebugLog(data) {
    const analysisTrace = qs("#analysisTrace");
    if (!analysisTrace) return;
    
    const timestamp = new Date().toLocaleTimeString();
    const eventType = data.event_type || data.type || 'debug';
    const payload = { ...data };
    delete payload.run_id;
    delete payload.thread_id;
    delete payload.sequence_number;
    delete payload.created_at;
    delete payload.type;
    const logData = JSON.stringify(payload, null, 2).substring(0, 300);
    const logEntry = `\n[${timestamp}] [DEBUG] ${eventType}: ${logData}...`;
    
    analysisTrace.textContent += logEntry;
    analysisTrace.scrollTop = analysisTrace.scrollHeight;
  },
  
  // 处理 HITL 中断
  handleRequiresAction(data, callback) {
    console.log("[SSE] 收到 HITL 中断:", data);
    if (data.required_action) {
      const actionPayload = unwrapRequiredAction(data.required_action);
      if (actionPayload?.step) {
        updateStepUI(actionPayload.step);
        renderStepContent(actionPayload);
      }
    }
    if (callback) callback(data);
  },
  
  // 关闭连接
  close() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
};

function getApiBase() {
  return ClaimConsistencyConfig.getApiBase();
}

function setApiBase(base) {
  if (base) {
    localStorage.setItem("claim_consistency_api_base", base);
  }
}

function buildInputParts(formData) {
  const topic = formData.get("topic").trim();
  const researchType = formData.get("researchType");
  const reportLength = formData.get("reportLength");
  const yearStart = Number(formData.get("yearStart"));
  const yearEnd = Number(formData.get("yearEnd"));
  const languagePref = formData.get("languagePref");

  return {
    topic,
    structured: {
      research_type: researchType,
      report_length: reportLength,
      year_range: [yearStart, yearEnd],
      language_pref: languagePref,
    },
  };
}

function persistRun(threadId, runId) {
  localStorage.setItem("claim_consistency_thread_id", threadId);
  localStorage.setItem("claim_consistency_run_id", runId);
}

function getPersistedRun() {
  return {
    threadId: localStorage.getItem("claim_consistency_thread_id"),
    runId: localStorage.getItem("claim_consistency_run_id"),
  };
}

async function createRun(threadId, payload, apiBase) {
  const body = {
    input: [
      {
        type: "message",
        role: "user",
        content: [
          { type: "input_text", text: payload.topic },
          { type: "input_json", json: payload.structured },
        ],
      },
    ],
  };

  const resp = await fetch(`${apiBase}/v1/threads/${threadId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(await resp.text());
  }
  return resp.json();
}

async function fetchRunStatus(threadId, runId, apiBase) {
  const resp = await fetch(`${apiBase}/v1/threads/${threadId}/runs/${runId}`);
  if (!resp.ok) {
    throw new Error(await resp.text());
  }
  return resp.json();
}

async function submitResume(threadId, runId, value, apiBase) {
  const body = {
    resume: {
      run_id: runId,
      value,
    },
  };
  const resp = await fetch(`${apiBase}/v1/threads/${threadId}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw new Error(await resp.text());
  }
  return resp.json();
}

async function cancelRun(threadId, runId, apiBase) {
  const resp = await fetch(`${apiBase}/v1/threads/${threadId}/runs/${runId}/cancel`, {
    method: "POST",
  });
  if (!resp.ok) {
    throw new Error(await resp.text());
  }
  return resp.json();
}

function unwrapRequiredAction(requiredAction) {
  if (!requiredAction) return null;

  // 调试：打印原始数据
  console.log("[DEBUG] unwrapRequiredAction input:", JSON.stringify(requiredAction, null, 2));

  // API 返回的 required_action 结构:
  // { type: "human_review", payload: {key: "confirm_input", payload: {...}}, resume_schema: {...} }

  // 获取内层 payload（包含 key 和 HITL 数据）
  const innerPayload = requiredAction.payload;
  if (!innerPayload) {
    console.log("[DEBUG] No inner payload found");
    return null;
  }

  // 检查内层 payload 是否有 key 字段（HITL 中断数据）
  if (innerPayload.key) {
    console.log("[DEBUG] Found HITL data with key:", innerPayload.key);
    // 合并 step 等信息到 payload 中，方便前端使用
    return {
      ...innerPayload,
      // 确保 payload.payload 里的数据也能直接访问
      ...(innerPayload.payload || {})
    };
  }

  console.log("[DEBUG] Returning inner payload as-is");
  return innerPayload;
}

function renderOutput(output) {
  const container = qs("#outputView");
  if (!container) return;
  if (!output || output.length === 0) {
    container.textContent = "暂无输出";
    return;
  }
  const lines = output.map((item) => {
    if (item.type === "message") {
      return item.content.map((part) => part.text || part).join("\n");
    }
    if (item.type === "artifact") {
      return `产物: ${item.artifact_type} (${item.mime})`;
    }
    return JSON.stringify(item);
  });
  container.textContent = lines.join("\n\n");
}

function updateStepUI(step) {
  const list = qs("#stepList");
  if (!list) return;
  const items = list.querySelectorAll("li");
  items.forEach((li) => {
    const stepNum = Number(li.dataset.step);
    li.classList.toggle("active", stepNum === Number(step));
    li.classList.toggle("completed", stepNum < Number(step));
  });
}

/**
 * 根据步骤号渲染对应的内容
 */
function renderStepContent(payload) {
  if (!payload) return;

  const step = payload.step || 1;
  const fieldMap = STEP_FIELD_MAP[step];

  // 更新标题和说明
  const stepTitle = qs("#stepTitle");
  const stepInstruction = qs("#stepInstruction");
  if (stepTitle) stepTitle.textContent = payload.title || fieldMap?.title || '处理中';
  if (stepInstruction) stepInstruction.textContent = payload.instruction || '正在处理...';

  // 更新思考过程
  const analysisTrace = qs("#analysisTrace");
  if (analysisTrace) {
    let traceContent = '';
    if (fieldMap?.trace && payload[fieldMap.trace]) {
      traceContent = payload[fieldMap.trace];
    } else {
      // 尝试查找任何可用的trace字段
      const traceFields = ['requirement_trace', 'topic_analysis_trace', 'framework_trace', 'retrieval_trace', 'draft_trace', 'logic_trace', 'formatting_trace'];
      for (const tf of traceFields) {
        if (payload[tf]) {
          traceContent = payload[tf];
          break;
        }
      }
    }
    analysisTrace.textContent = traceContent || '暂无思考过程';
  }

  // 更新解析结果
  const analysisResult = qs("#analysisResult");
  if (analysisResult) {
    let markdownContent = '';
    if (fieldMap?.markdown && payload[fieldMap.markdown]) {
      markdownContent = payload[fieldMap.markdown];
    } else {
      // 尝试查找任何可用的markdown字段
      const markdownFields = ['requirement_markdown', 'topic_analysis_markdown', 'outline_markdown', 'draft_report_markdown', 'validated_report_markdown'];
      for (const mf of markdownFields) {
        if (payload[mf]) {
          markdownContent = payload[mf];
          break;
        }
      }
    }
    analysisResult.innerHTML = markdownContent ? formatMarkdown(markdownContent) : '暂无解析结果';
  }

  // 控制输出预览显示（仅在第9步）
  const outputPreviewBlock = qs("#outputPreviewBlock");
  if (outputPreviewBlock) {
    outputPreviewBlock.style.display = step === 9 ? 'block' : 'none';
  }

  // 渲染HITL表单
  renderHitlForm(payload);
}

/**
 * 渲染HITL待确认表单
 * 直接展示payload中的原始结构，默认可编辑
 */
function renderHitlForm(payload) {
  const container = qs("#hitlFormContainer");
  const actionInput = qs("#hitlAction");
  if (!container) return;

  // 调试：打印 payload
  console.log("[DEBUG] renderHitlForm payload:", JSON.stringify(payload, null, 2));

  // 从 payload 中获取关键信息
  const stepKey = payload.key;
  const hitlPayload = payload.payload || {};

  console.log("[DEBUG] stepKey:", stepKey);
  console.log("[DEBUG] hitlPayload:", JSON.stringify(hitlPayload, null, 2));

  // 如果没有待确认内容，显示占位符
  if (!stepKey || Object.keys(hitlPayload).length === 0) {
    console.log("[DEBUG] No HITL content found, showing placeholder");
    container.innerHTML = '<p class="placeholder-text">暂无待确认内容</p>';
    if (actionInput) actionInput.value = 'approve';
    return;
  }

  // 构建表单HTML - 直接展示原始payload结构
  let formHtml = '<div class="hitl-form">';

  // 遍历payload中的所有字段，直接展示
  Object.entries(hitlPayload).forEach(([key, value]) => {
    // 跳过内部trace字段（已在思考过程展示）
    if (key.endsWith('_trace')) return;

    const label = key.replace(/_/g, ' ');
    const fieldId = `hitl_field_${key}`;

    // 根据值类型选择展示方式
    if (typeof value === 'object' && value !== null) {
      // JSON对象类型 - 使用textarea展示可编辑的JSON
      const jsonValue = JSON.stringify(value, null, 2);
      formHtml += `
        <div class="hitl-field">
          <label>${label}</label>
          <textarea id="${fieldId}" class="hitl-json-field" rows="6" data-field-key="${key}">${escapeHtml(jsonValue)}</textarea>
        </div>
      `;
    } else {
      // 简单类型 - 使用textarea展示
      formHtml += `
        <div class="hitl-field">
          <label>${label}</label>
          <textarea id="${fieldId}" class="hitl-text-field" rows="4" data-field-key="${key}">${escapeHtml(String(value || ''))}</textarea>
        </div>
      `;
    }
  });

  formHtml += '</div>';
  container.innerHTML = formHtml;

  // 设置action为edit（因为有可编辑内容）
  if (actionInput) actionInput.value = 'edit';
}

/**
 * 格式化Markdown显示
 */
function formatMarkdown(text) {
  if (!text) return '';
  // 简单的markdown格式化
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

/**
 * HTML转义
 */
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * 根据当前表单构建resume payload
 * 收集所有编辑后的字段值
 */
function buildResumePayload() {
  const action = qs("#hitlAction")?.value || 'approve';
  const payload = { action };

  // 提取所有字段的值
  document.querySelectorAll('.hitl-field textarea').forEach(el => {
    const key = el.dataset.fieldKey;
    if (!key) return;

    const value = el.value;

    // 尝试解析JSON值
    if (el.classList.contains('hitl-json-field')) {
      try {
        payload[key] = JSON.parse(value);
      } catch (e) {
        // 如果解析失败，保存为字符串
        payload[key] = value;
      }
    } else {
      // 文本字段直接使用
      payload[key] = value;
    }
  });

  return payload;
}

function setupIndexPage() {
  const form = qs("#researchForm");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const apiBase = getApiBase();
    setApiBase(apiBase);

    const payload = buildInputParts(data);
    const threadId = `thread_${Date.now()}`;

    try {
      const result = await createRun(threadId, payload, apiBase);
      const runId = result.run_id || result.id || "";
      persistRun(threadId, runId);
      window.location.href = `task_detail.html?task_id=${encodeURIComponent(runId)}&thread_id=${encodeURIComponent(threadId)}`;
    } catch (err) {
      alert(`启动失败: ${err.message}`);
    }
  });
}

function setupFlowPage() {
  const threadId = getParam("thread_id") || getPersistedRun().threadId;
  const runId = getParam("run_id") || getPersistedRun().runId;
  const apiBase = getApiBase();

  const threadBox = qs("#threadId");
  const runBox = qs("#runId");
  const statusBox = qs("#runStatus");
  const apiBaseBox = qs("#apiBaseLabel");

  if (threadBox) threadBox.textContent = threadId || "-";
  if (runBox) runBox.textContent = runId || "-";
  if (apiBaseBox) apiBaseBox.textContent = apiBase;

  const refreshBtn = qs("#refreshStatus");
  const subscribeBtn = qs("#subscribeEvents");
  const cancelBtn = qs("#cancelRun");
  const resumeBtn = qs("#submitResume");

  async function refresh() {
    if (!threadId || !runId) {
      if (statusBox) statusBox.textContent = "缺少 thread/run id";
      return;
    }
    try {
      const data = await fetchRunStatus(threadId, runId, apiBase);
      console.log("[DEBUG] fetchRunStatus response:", JSON.stringify(data, null, 2));

      if (statusBox) statusBox.textContent = data.status || "unknown";

      const actionPayload = unwrapRequiredAction(data.required_action);
      console.log("[DEBUG] actionPayload after unwrap:", JSON.stringify(actionPayload, null, 2));

      renderOutput(data.output);
      if (actionPayload?.step) updateStepUI(actionPayload.step);
      renderStepContent(actionPayload);
    } catch (err) {
      if (statusBox) statusBox.textContent = "查询失败";
    }
  }

  refreshBtn?.addEventListener("click", refresh);
  cancelBtn?.addEventListener("click", async () => {
    if (!threadId || !runId) return;
    try {
      await cancelRun(threadId, runId, apiBase);
      refresh();
    } catch (err) {
      alert(`取消失败: ${err.message}`);
    }
  });

  subscribeBtn?.addEventListener("click", () => {
    if (!threadId || !runId) {
      alert("缺少 thread_id 或 run_id");
      return;
    }
    
    // 使用新的 StreamingManager 连接事件流
    StreamingManager.connect(threadId, runId, apiBase, (data) => {
      console.log("[StreamingManager] 收到事件:", data);
    });
    
    // 更新按钮状态
    subscribeBtn.textContent = "已订阅";
    subscribeBtn.disabled = true;
    subscribeBtn.classList.add("subscribed");
  });
  
  // 页面加载时自动订阅（如果已有 threadId 和 runId）
  if (threadId && runId) {
    console.log("[FlowPage] 自动订阅事件流");
    StreamingManager.connect(threadId, runId, apiBase, (data) => {
      console.log("[Auto-Subscribe] 收到事件:", data);
    });
    
    // 更新按钮状态
    if (subscribeBtn) {
      subscribeBtn.textContent = "已订阅";
      subscribeBtn.disabled = true;
      subscribeBtn.classList.add("subscribed");
    }
  }

  resumeBtn?.addEventListener("click", async () => {
    if (!threadId || !runId) return;
    try {
      const value = buildResumePayload();
      const result = await submitResume(threadId, runId, value, apiBase);
      if (statusBox) statusBox.textContent = result.status || "unknown";
      renderOutput(result.output);
      const actionPayload = unwrapRequiredAction(result.required_action);
      if (actionPayload?.step) updateStepUI(actionPayload.step);
      renderStepContent(actionPayload);
    } catch (err) {
      alert(`提交失败: ${err.message}`);
    }
  });

  refresh();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    setupIndexPage();
    setupFlowPage();
  });
} else {
  setupIndexPage();
  setupFlowPage();
}
