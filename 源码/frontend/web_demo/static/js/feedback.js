(function () {
if (window.__claimConsistencyFeedbackInitialized) {
  return
}
window.__claimConsistencyFeedbackInitialized = true

const state = {
  attachments: [],
  maxFiles: 10,
  maxFileSize: 5 * 1024 * 1024
}

const submitPath = '/api/service/nstl/web/user-feedback/submit'
const defaultSystemName = 'claim-consistency-agent'
const staticBase = new URL('../', document.currentScript?.src || window.location.href).toString()
const feedbackEntryImageUrl = `${staticBase}images/feedback-entry.png`
const feedbackFolderImageUrl = `${staticBase}images/feedback-folder-opened.png`

function feedbackTemplate() {
  return `
    <div id="top-toast" class="top-toast hidden"></div>
    <button id="feedback-entry" class="feedback-entry" type="button" aria-label="意见反馈">
      <img class="feedback-entry-image" src="${feedbackEntryImageUrl}" alt="意见反馈" />
    </button>
    <div id="dialog-backdrop" class="dialog-backdrop hidden">
      <section class="feedback-dialog" aria-modal="true" role="dialog" aria-labelledby="feedback-title">
        <header class="dialog-header">
          <h2 id="feedback-title">意见反馈</h2>
          <button id="close-dialog" class="icon-close" type="button" aria-label="关闭">
            <svg viewBox="0 0 24 24" focusable="false">
              <path d="M6 6 18 18M18 6 6 18" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8" />
            </svg>
          </button>
        </header>
        <div class="dialog-body">
          <p class="intro-text">
            感谢您使用一致性评估智能体服务！为持续优化产品体验，您的反馈对我们至关重要。
            我们将认真对待每一条建议，并尽快处理。
          </p>
          <div class="select-shell hidden">
            <select id="agent" aria-label="智能体">
              <option>一致性评估智能体</option>
            </select>
          </div>
          <label class="field-label" for="description">问题 / 建议描述</label>
          <div class="textarea-shell" id="description-shell">
            <textarea
              id="description"
              maxlength="300"
              placeholder="请详细描述您遇到的问题或改进建议（如：出现场景、操作步骤、预期效果等）"
            ></textarea>
            <span id="counter" class="counter">0/300</span>
          </div>
          <p id="description-error" class="error-text hidden"></p>
          <label class="field-label">图片上传</label>
          <div class="upload-block" id="upload-block">
            <button id="upload-trigger" class="upload-button" type="button">
              <img src="${feedbackFolderImageUrl}" alt="" aria-hidden="true" />
              <span>上传图片</span>
            </button>
            <span class="upload-tip">或将图片拖拽到这里，单张最大 5MB</span>
            <input id="file-input" class="hidden-input" type="file" multiple accept="image/*" />
            <div id="file-list" class="file-list hidden"></div>
          </div>
          <p id="attachments-error" class="error-text hidden"></p>
          <label class="field-label" for="contact">联系方式（手机号 / 邮箱，可选）</label>
          <input
            id="contact"
            class="text-input"
            type="text"
            placeholder="如需我们跟进回复，请留下您的联系方式（将严格保密）"
          />
          <p id="contact-error" class="error-text hidden"></p>
          <p id="success-text" class="success-text hidden"></p>
        </div>
        <footer class="dialog-footer">
          <button id="submit-button" class="primary-button" type="button">提交</button>
          <button id="cancel-button" class="secondary-button" type="button">取消</button>
        </footer>
      </section>
    </div>
  `
}

function ensureFeedbackDom() {
  if (document.getElementById('feedback-entry') && document.getElementById('dialog-backdrop')) {
    return
  }
  const wrapper = document.createElement('div')
  wrapper.innerHTML = feedbackTemplate().trim()
  Array.from(wrapper.children).forEach((child) => {
    const id = child.id
    if (!id || !document.getElementById(id)) {
      document.body.appendChild(child)
    }
  })
}

ensureFeedbackDom()

const elements = {
  topToast: document.getElementById('top-toast'),
  feedbackEntry: document.getElementById('feedback-entry'),
  dialogBackdrop: document.getElementById('dialog-backdrop'),
  closeDialog: document.getElementById('close-dialog'),
  cancelButton: document.getElementById('cancel-button'),
  submitButton: document.getElementById('submit-button'),
  description: document.getElementById('description'),
  counter: document.getElementById('counter'),
  descriptionShell: document.getElementById('description-shell'),
  descriptionError: document.getElementById('description-error'),
  uploadTrigger: document.getElementById('upload-trigger'),
  uploadBlock: document.getElementById('upload-block'),
  attachmentsError: document.getElementById('attachments-error'),
  fileInput: document.getElementById('file-input'),
  fileList: document.getElementById('file-list'),
  contact: document.getElementById('contact'),
  contactError: document.getElementById('contact-error'),
  successText: document.getElementById('success-text'),
  agent: document.getElementById('agent')
}

if (Object.values(elements).some((element) => !element)) {
  console.error('[Feedback] required DOM nodes are missing')
  return
}

function getSubmitUrl() {
  const apiBase = window.ClaimConsistencyConfig?.getApiBase?.() || ''
  return `${apiBase}${submitPath}`
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[char]))
}

function createFileId() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    return window.crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function isImageFile(file) {
  return typeof file.type === 'string' && file.type.startsWith('image/')
}

function showToast(message) {
  elements.topToast.textContent = message
  elements.topToast.classList.remove('hidden')
  window.setTimeout(() => {
    if (elements.topToast.textContent === message) {
      elements.topToast.classList.add('hidden')
    }
  }, 2400)
}

/**
 * 检查用户是否已登录
 * 使用全局 authManager 的 isAuthenticated 方法
 */
function checkUserLoggedIn() {
  if (window.authManager && typeof window.authManager.isAuthenticated === 'function') {
    return window.authManager.isAuthenticated()
  }
  // 如果 authManager 不存在，尝试检查 sessionManager
  if (window.authManager && window.authManager.sessionManager) {
    const session = window.authManager.sessionManager.getSession()
    return session && session.userId
  }
  const storedSession = readStoredSession()
  if (storedSession?.user?.userId && !isSessionExpired(storedSession)) {
    return true
  }
  // 兜底：假设已登录（避免阻止用户操作）
  console.warn('[Feedback] authManager not found, assuming logged in')
  return true
}

function readStoredSession() {
  try {
    const raw = window.localStorage?.getItem('cca_user_session') || window.sessionStorage?.getItem('cca_user_session')
    return raw ? JSON.parse(raw) : null
  } catch (error) {
    console.warn('[Feedback] failed to read stored session', error)
    return null
  }
}

function isSessionExpired(session) {
  const expiresAt = Number(session?.session?.expiresAt || 0)
  return Boolean(expiresAt && Date.now() > expiresAt)
}

function getUserScope() {
  const session = window.authManager?.sessionManager?.getSession?.() || readStoredSession()
  const userId = session?.user?.userId?.trim?.() || ''
  if (
    userId &&
    userId !== 'mock_user_id' &&
    userId !== 'unknown' &&
    !userId.startsWith('nstl_user_')
  ) {
    return userId
  }
  return 'default'
}

/**
 * 显示登录提示
 */
function showLoginPrompt() {
  showToast('请先登录后再提交意见反馈')
  // 调用 authManager 的登录方法
  if (window.authManager && typeof window.authManager.showLoginModal === 'function') {
    window.authManager.showLoginModal()
  }
}

function openDialog() {
  // 检查用户是否已登录
  if (!checkUserLoggedIn()) {
    showLoginPrompt()
    return
  }
  
  elements.dialogBackdrop.classList.remove('hidden')
  elements.successText.classList.add('hidden')
  document.body.classList.add('dialog-open')
  window.setTimeout(() => {
    elements.description.focus()
  }, 20)
}

function resetForm() {
  state.attachments = []
  elements.description.value = ''
  elements.contact.value = ''
  elements.counter.textContent = '0/300'
  clearErrors()
  renderFiles()
  elements.fileInput.value = ''
  elements.successText.textContent = ''
}

function closeDialog() {
  elements.dialogBackdrop.classList.add('hidden')
  document.body.classList.remove('dialog-open')
  resetForm()
}

function clearErrors() {
  elements.descriptionError.textContent = ''
  elements.attachmentsError.textContent = ''
  elements.contactError.textContent = ''
  elements.descriptionError.classList.add('hidden')
  elements.attachmentsError.classList.add('hidden')
  elements.contactError.classList.add('hidden')
  elements.descriptionShell.classList.remove('has-error')
  elements.uploadBlock.classList.remove('has-error')
  elements.contact.classList.remove('has-error')
}

function showError(element, text, target) {
  element.textContent = text
  element.classList.remove('hidden')
  target.classList.add('has-error')
}

function formatSize(size) {
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function renderFiles() {
  if (!state.attachments.length) {
    elements.fileList.classList.add('hidden')
    elements.fileList.innerHTML = ''
    return
  }

  elements.fileList.classList.remove('hidden')
  elements.fileList.innerHTML = state.attachments
    .map(
      (file) => `
        <div class="file-item">
          <div>
            <strong>${escapeHtml(file.name)}</strong>
            <span>${formatSize(file.size)}</span>
          </div>
          <button type="button" data-remove="${file.id}">移除</button>
        </div>
      `
    )
    .join('')
}

function validate() {
  clearErrors()
  let valid = true
  const description = elements.description.value.trim()
  const contact = elements.contact.value.trim()

  if (!description) {
    showError(elements.descriptionError, '请填写问题描述或建议。', elements.descriptionShell)
    valid = false
  }

  if (contact && !/^1\d{10}$|^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contact)) {
    showError(elements.contactError, '请输入正确的手机号或邮箱。', elements.contact)
    valid = false
  }

  if (state.attachments.length > state.maxFiles) {
    showError(elements.attachmentsError, `最多上传 ${state.maxFiles} 张图片。`, elements.uploadBlock)
    valid = false
  }

  return valid
}

function handleFiles(files) {
  clearErrors()
  Array.from(files).forEach((file) => {
    if (state.attachments.length >= state.maxFiles) {
      showError(elements.attachmentsError, `最多上传 ${state.maxFiles} 张图片。`, elements.uploadBlock)
      return
    }

    if (!isImageFile(file)) {
      showError(elements.attachmentsError, '仅支持上传图片文件。', elements.uploadBlock)
      return
    }

    if (file.size > state.maxFileSize) {
      showError(elements.attachmentsError, '单个图片不能超过 5MB。', elements.uploadBlock)
      return
    }

    if (state.attachments.some((item) => (
      item.name === file.name &&
      item.size === file.size &&
      item.lastModified === file.lastModified
    ))) {
      showError(elements.attachmentsError, '请勿重复上传同一张图片。', elements.uploadBlock)
      return
    }

    state.attachments.push({
      id: createFileId(),
      name: file.name,
      size: file.size,
      lastModified: file.lastModified,
      raw: file
    })
  })
  renderFiles()
}

function handleEscClose(event) {
  if (event.key === 'Escape' && !elements.dialogBackdrop.classList.contains('hidden')) {
    closeDialog()
  }
}

elements.feedbackEntry.addEventListener('click', openDialog)
elements.closeDialog.addEventListener('click', closeDialog)
elements.cancelButton.addEventListener('click', closeDialog)
elements.dialogBackdrop.addEventListener('click', (event) => {
  if (event.target === elements.dialogBackdrop) {
    closeDialog()
  }
})

elements.description.addEventListener('input', () => {
  elements.counter.textContent = `${elements.description.value.length}/300`
})

elements.uploadTrigger.addEventListener('click', () => {
  elements.fileInput.click()
})

elements.fileInput.addEventListener('change', (event) => {
  handleFiles(event.target.files)
  event.target.value = ''
})

elements.uploadBlock.addEventListener('dragover', (event) => {
  event.preventDefault()
})

elements.uploadBlock.addEventListener('drop', (event) => {
  event.preventDefault()
  handleFiles(event.dataTransfer.files)
})

elements.fileList.addEventListener('click', (event) => {
  const target = event.target
  if (!(target instanceof HTMLElement)) {
    return
  }

  const fileId = target.dataset.remove
  if (!fileId) {
    return
  }

  state.attachments = state.attachments.filter((file) => file.id !== fileId)
  renderFiles()
})

elements.submitButton.addEventListener('click', async () => {
  // 再次检查登录状态（防止弹窗打开后登录状态变化）
  if (!checkUserLoggedIn()) {
    showLoginPrompt()
    closeDialog()
    return
  }

  if (!validate()) {
    return
  }

  // 使用固定的 systemName，便于反馈后台按智能体归类。
  const systemName = defaultSystemName

  elements.submitButton.disabled = true
  elements.submitButton.textContent = '提交中...'

  const formData = new FormData()
  formData.append('systemName', systemName)
  formData.append('content', elements.description.value.trim())
  formData.append('pageUrl', window.location.href)

  if (elements.contact.value.trim()) {
    formData.append('contact', elements.contact.value.trim())
  }

  state.attachments.forEach((file) => {
    formData.append('files', file.raw, file.name)
  })

  try {
    const response = await fetch(getSubmitUrl(), {
      method: 'POST',
      headers: {
        'X-User-Scope': getUserScope()
      },
      body: formData,
      credentials: 'include'
    })
    const result = await response.json().catch(() => null)

    if (!response.ok || !result || result.code !== 200) {
      showToast(result?.message || result?.detail || '提交失败，请稍后重试。')
      return
    }

    elements.successText.textContent = '提交成功，感谢你的反馈。'
    elements.successText.classList.remove('hidden')
    showToast('反馈已提交，我们会尽快处理。')
    window.setTimeout(closeDialog, 1200)
  } catch (error) {
    console.error('feedback submit failed', error)
    showToast('提交失败，请检查网络或稍后重试。')
  } finally {
    elements.submitButton.disabled = false
    elements.submitButton.textContent = '提交'
  }
})

window.addEventListener('keydown', handleEscClose)
})()
