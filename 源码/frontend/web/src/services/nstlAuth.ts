export interface NstlUserInfo {
  userId: string
  username: string
  email?: string
}

interface StoredSession {
  version: string
  user: NstlUserInfo
  session: {
    token: string
    nonce: string
    loginTime: number
    expiresAt: number
  }
  metadata: {
    userAgent: string
    loginPage: string
    lastActivity: number
  }
}

interface AuthConfig {
  loginServiceUrl: string
  userInfoEndpoint: string
  userInfoRequestTimeout: number
  loginPollInterval: number
  loginPollTimeout: number
  loginStatusSyncTimeout: number
  fallbackSyncMaxAttempts: number
  sessionTimeout: number
  storageKey: string
  trustedOrigins: string[]
  modalConfig: LoginModalConfig
}

interface LoginModalConfig {
  iframeUrl: string
  width: string
  height: string
  zIndex: number
  timeout: number
  showLogo: boolean
  allowClose: boolean
  sandbox: string
}

interface LoginSuccessData {
  message?: string
  userId?: string
  username?: string
  email?: string
  token?: string
}

interface WxLoginResponse {
  code?: string | number | null
  msg?: string
  errorCode?: string
  [key: string]: unknown
}

const DEFAULT_CONFIG: AuthConfig = {
  loginServiceUrl: 'https://login.nstl.gov.cn',
  userInfoEndpoint: '/api/service/nstl/web/vilidate/isLogin',
  userInfoRequestTimeout: 5000,
  loginPollInterval: 2000,
  loginPollTimeout: 5 * 60 * 1000,
  loginStatusSyncTimeout: 90 * 1000,
  fallbackSyncMaxAttempts: 3,
  sessionTimeout: 24 * 60 * 60 * 1000,
  storageKey: 'cca_user_session',
  trustedOrigins: ['https://login.nstl.gov.cn', 'https://www.nstl.gov.cn'],
  modalConfig: {
    iframeUrl: 'https://login.nstl.gov.cn',
    width: '453px',
    height: '585px',
    zIndex: 10000,
    timeout: 5 * 60 * 1000,
    showLogo: false,
    allowClose: false,
    sandbox: 'allow-scripts allow-forms allow-same-origin allow-popups',
  },
}

class SessionManager {
  private cache: StoredSession | null = null
  private cacheTime = 0
  private readonly cacheDuration = 5000
  private storageWarningShown = false

  constructor(private readonly config: AuthConfig) {}

  createSession(userInfo: NstlUserInfo & { sessionToken: string; nonce: string; loginTime: number }) {
    const session: StoredSession = {
      version: '1.0',
      user: {
        userId: userInfo.userId,
        username: userInfo.username,
        email: userInfo.email,
      },
      session: {
        token: userInfo.sessionToken,
        nonce: userInfo.nonce,
        loginTime: userInfo.loginTime,
        expiresAt: userInfo.loginTime + this.config.sessionTimeout,
      },
      metadata: {
        userAgent: navigator.userAgent,
        loginPage: window.location.pathname,
        lastActivity: Date.now(),
      },
    }

    this.saveToStorage(this.config.storageKey, session)
    this.cache = session
    this.cacheTime = Date.now()
  }

  getSession(): StoredSession | null {
    if (this.cache && Date.now() - this.cacheTime < this.cacheDuration) {
      return this.cache
    }

    const session = this.loadFromStorage(this.config.storageKey)
    if (session) {
      this.cache = session
      this.cacheTime = Date.now()
    }
    return session
  }

  validateSession() {
    const session = this.getSession()
    if (!session?.user?.userId || !session.session?.token) return false

    if (this.isSessionExpired(session)) {
      this.clearSession()
      return false
    }

    return true
  }

  isSessionExpired(session = this.getSession()) {
    if (!session) return true
    return Date.now() > session.session.expiresAt
  }

  clearSession() {
    this.removeFromStorage(this.config.storageKey)
    this.cache = null
    this.cacheTime = 0
  }

  private saveToStorage(key: string, value: StoredSession) {
    const data = JSON.stringify(value)

    try {
      localStorage.setItem(key, data)
      return true
    } catch (error) {
      console.warn('[SessionManager] localStorage unavailable, trying sessionStorage', error)
      this.showStorageWarning('localStorage')
    }

    try {
      sessionStorage.setItem(key, data)
      return true
    } catch (error) {
      console.error('[SessionManager] Both localStorage and sessionStorage unavailable', error)
      this.showStorageWarning('both')
      return false
    }
  }

  private loadFromStorage(key: string): StoredSession | null {
    try {
      const data = localStorage.getItem(key) || sessionStorage.getItem(key)
      return data ? JSON.parse(data) as StoredSession : null
    } catch (error) {
      console.error('[SessionManager] Failed to load session', error)
      return null
    }
  }

  private removeFromStorage(key: string) {
    try {
      localStorage.removeItem(key)
      sessionStorage.removeItem(key)
    } catch (error) {
      console.error('[SessionManager] Failed to clear session', error)
    }
  }

  private showStorageWarning(storageType: 'localStorage' | 'both') {
    if (this.storageWarningShown) return
    this.storageWarningShown = true

    const warning = document.createElement('div')
    warning.className = 'storage-warning'
    warning.textContent = storageType === 'localStorage'
      ? '浏览器本地存储不可用，登录状态仅在当前标签页有效'
      : '浏览器存储不可用，登录状态无法保存，请检查浏览器设置'
    warning.style.cssText = `
      position: fixed;
      top: 20px;
      left: 50%;
      transform: translateX(-50%);
      padding: 12px 24px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 500;
      z-index: 10001;
      background: #f59e0b;
      color: #ffffff;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      max-width: 90%;
      text-align: center;
    `
    document.body.appendChild(warning)
    window.setTimeout(() => warning.remove(), 5000)
  }
}

class LoginModal {
  private modalElement: HTMLDivElement | null = null
  private iframeElement: HTMLIFrameElement | null = null
  private timeoutTimer = 0
  private callbacks = {
    onClose: null as null | (() => void),
    onTimeout: null as null | (() => void),
  }

  constructor(private readonly config: LoginModalConfig) {}

  show() {
    if (this.isVisible()) {
      console.warn('[LoginModal] Modal is already visible')
      return
    }

    this.createModal()
    this.startTimeout()
  }

  hide() {
    if (!this.isVisible()) return
    this.destroyModal()
  }

  isVisible() {
    return Boolean(this.modalElement && document.body.contains(this.modalElement))
  }

  get iframe() {
    return this.iframeElement
  }

  onClose(callback: () => void) {
    this.callbacks.onClose = callback
  }

  onTimeout(callback: () => void) {
    this.callbacks.onTimeout = callback
  }

  private createModal() {
    const overlay = document.createElement('div')
    overlay.className = 'login-modal-overlay'
    overlay.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.4);
      z-index: ${this.config.zIndex};
    `

    this.iframeElement = this.createIframe()
    this.iframeElement.className = 'login-modal-iframe'
    this.iframeElement.style.cssText = `
      position: absolute;
      inset: 0px;
      margin: auto;
      border: 0px;
      width: 100%;
      height: 100%;
    `

    overlay.appendChild(this.iframeElement)
    document.body.appendChild(overlay)
    document.body.style.overflow = 'hidden'
    this.modalElement = overlay
  }

  private createIframe() {
    const iframe = document.createElement('iframe')
    iframe.src = this.config.iframeUrl
    iframe.setAttribute('sandbox', this.config.sandbox)

    const loadTimeout = window.setTimeout(() => {
      console.warn('[LoginModal] Iframe load timeout:', this.config.iframeUrl)
    }, 10000)

    iframe.onload = () => {
      window.clearTimeout(loadTimeout)
      console.log('[LoginModal] Iframe loaded successfully')
    }
    iframe.onerror = () => {
      window.clearTimeout(loadTimeout)
      console.error('[LoginModal] Failed to load iframe:', this.config.iframeUrl)
    }

    return iframe
  }

  private destroyModal() {
    this.modalElement?.remove()
    this.modalElement = null
    this.iframeElement = null
    document.body.style.overflow = ''
    this.clearTimeout()
  }

  private startTimeout() {
    this.clearTimeout()
    this.timeoutTimer = window.setTimeout(() => {
      console.warn('[LoginModal] Login timeout after', this.config.timeout, 'ms')
      this.callbacks.onTimeout?.()
      this.hide()
    }, this.config.timeout)
  }

  private clearTimeout() {
    if (this.timeoutTimer) {
      window.clearTimeout(this.timeoutTimer)
      this.timeoutTimer = 0
    }
  }
}

class PostMessageHandler {
  private callbacks = {
    onLoginSuccess: null as null | ((data: LoginSuccessData) => void),
    onLoginFailure: null as null | ((error: unknown) => void),
    onLoginClosed: null as null | (() => void),
  }
  private isListening = false
  private readonly boundHandler = this.handleMessage.bind(this)

  constructor(private readonly config: AuthConfig) {}

  startListening() {
    if (this.isListening) return
    window.addEventListener('message', this.boundHandler)
    this.isListening = true
  }

  stopListening() {
    if (!this.isListening) return
    window.removeEventListener('message', this.boundHandler)
    this.isListening = false
  }

  onLoginSuccess(callback: (data: LoginSuccessData) => void) {
    this.callbacks.onLoginSuccess = callback
  }

  onLoginFailure(callback: (error: unknown) => void) {
    this.callbacks.onLoginFailure = callback
  }

  onLoginClosed(callback: () => void) {
    this.callbacks.onLoginClosed = callback
  }

  private handleMessage(event: MessageEvent) {
    if (!this.config.trustedOrigins.includes(event.origin)) {
      console.warn('[PostMessageHandler] Ignored message from untrusted origin:', event.origin)
      return
    }

    const data = event.data
    if (!this.validateMessage(data)) {
      console.warn('[PostMessageHandler] Invalid message format:', data)
      return
    }

    if (typeof data === 'string') {
      const normalized = data.toLowerCase()
      if (normalized === 'success') {
        this.callbacks.onLoginSuccess?.({ message: 'SUCCESS' })
      } else if (normalized === 'close' || normalized === 'closelogin') {
        this.callbacks.onLoginClosed?.()
      } else if (normalized === 'failure') {
        this.callbacks.onLoginFailure?.({ message: 'Login failed' })
      }
      return
    }

    if (data.type === 'loginSuccess') {
      this.callbacks.onLoginSuccess?.(data.data ?? {})
    } else if (data.type === 'loginFailure') {
      this.callbacks.onLoginFailure?.(data.error)
    } else if (data.type === 'loginClosed') {
      this.callbacks.onLoginClosed?.()
    }
  }

  private validateMessage(data: unknown) {
    if (typeof data === 'string') {
      return ['success', 'close', 'closelogin', 'failure'].includes(data.toLowerCase())
    }

    if (!data || typeof data !== 'object') return false
    const message = data as { type?: unknown; timestamp?: unknown }
    if (typeof message.type !== 'string') return false
    if (message.timestamp !== undefined && typeof message.timestamp !== 'number') return false
    return true
  }
}

export class AuthManager {
  readonly sessionManager: SessionManager
  private loginModal: LoginModal | null = null
  private postMessageHandler: PostMessageHandler
  private readonly config: AuthConfig
  private loginPollTimer = 0
  private loginPollStartedAt = 0
  private loginPollInFlight = false
  private loginCompleting = false
  private loginSyncStartedAt = 0
  private readonly boundWxRegist = this.handleWxRegist.bind(this)
  private readonly boundInitWeichatLogin = this.handleInitWeichatLogin.bind(this)

  constructor(config: Partial<AuthConfig> = {}) {
    this.config = {
      ...DEFAULT_CONFIG,
      ...config,
      modalConfig: {
        ...DEFAULT_CONFIG.modalConfig,
        ...(config.modalConfig || {}),
      },
    }
    this.sessionManager = new SessionManager(this.config)
    this.postMessageHandler = new PostMessageHandler(this.config)
    this.postMessageHandler.onLoginSuccess((data) => this.handleLoginSuccess(data))
    this.postMessageHandler.onLoginFailure((error) => this.handleLoginFailure(error))
    this.postMessageHandler.onLoginClosed(() => this.handleLoginClosed())
    this.postMessageHandler.startListening()
    this.installNstlParentCallbacks()
  }

  async fetchUserInfo(): Promise<NstlUserInfo | null> {
    const endpoint = this.config.userInfoEndpoint
    const separator = endpoint.includes('?') ? '&' : '?'
    const url = `${endpoint}${separator}t=${Date.now()}`
    const controller = new AbortController()
    const timeoutTimer = window.setTimeout(() => controller.abort(), this.config.userInfoRequestTimeout)

    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Cache-Control': 'no-cache',
          Pragma: 'no-cache',
        },
        credentials: 'include',
        mode: endpoint.startsWith('/') ? 'same-origin' : 'cors',
        signal: controller.signal,
      })

      if (!response.ok) {
        this.log('error', `NSTL API returned ${response.status}`)
        return null
      }

      const result = await response.json()
      const userInfo = normalizeNstlUserInfoResult(result)
      if (userInfo && isRealUserId(userInfo.userId)) return userInfo

      this.log('warn', 'NSTL API returned non-login status', result)
      return null
    } catch (error) {
      this.log('error', 'Failed to fetch NSTL user info', error)
      throw error
    } finally {
      window.clearTimeout(timeoutTimer)
    }
  }

  async checkAuth(): Promise<boolean> {
    try {
      let session = this.sessionManager.getSession()
      if (session && this.sessionManager.isSessionExpired(session)) {
        this.sessionManager.clearSession()
        session = null
      }

      if (session) {
        if (normalizeSessionUserId(session.user?.userId) && !isRealUserId(session.user?.userId)) {
          return this.sessionManager.validateSession()
        }

        try {
          const userInfo = await this.fetchUserInfo()
          if (!userInfo || !isRealUserId(userInfo.userId)) {
            this.sessionManager.clearSession()
            this.handleMainSystemLogout()
            return false
          }

          this.updateSessionWithUserInfo(userInfo, session)
          return true
        } catch (error) {
          this.log('warn', 'Unable to verify NSTL login status, clearing local session', error)
          this.sessionManager.clearSession()
          this.handleMainSystemLogout()
          return false
        }
      }

      try {
        const userInfo = await this.fetchUserInfo()
        if (userInfo && isRealUserId(userInfo.userId)) {
          this.updateSessionWithUserInfo(userInfo)
          return true
        }
      } catch (error) {
        this.log('warn', 'Unable to reach NSTL login status and no local session exists', error)
      }

      return false
    } catch (error) {
      this.log('warn', 'Unable to verify NSTL login status', error)
      return false
    }
  }

  async requireUserScope(): Promise<string> {
    const ok = await this.checkAuth()
    if (!ok) {
      this.showLoginModal()
      throw new Error('请先完成 NSTL 登录')
    }

    const userScope = getBusinessUserScope(this.getUserInfo()?.userId)
    if (!userScope) {
      this.sessionManager.clearSession()
      this.showLoginModal()
      throw new Error('未获取到真实 NSTL 用户')
    }
    return userScope
  }

  showLoginModal() {
    if (this.loginModal?.isVisible()) return

    this.loginCompleting = false
    this.loginSyncStartedAt = 0
    this.loginModal = new LoginModal(this.config.modalConfig)
    this.loginModal.onClose(() => this.handleLoginClosed())
    this.loginModal.onTimeout(() => this.handleLoginTimeout())
    this.loginModal.show()
    this.loginModal.iframe?.addEventListener('load', () => {
      void this.pollLoginStatus()
    })
    this.startLoginPolling()
    this.log('info', 'Login modal displayed')
  }

  hideLoginModal() {
    this.stopLoginPolling()
    this.loginModal?.hide()
    this.loginModal = null
  }

  getUserInfo() {
    return this.sessionManager.getSession()?.user ?? null
  }

  isAuthenticated() {
    const session = this.sessionManager.getSession()
    if (!session || !normalizeSessionUserId(session.user?.userId)) return false
    return this.sessionManager.validateSession()
  }

  logout() {
    const userInfo = this.getUserInfo()
    this.sessionManager.clearSession()
    this.hideLoginModal()
    this.log('info', 'User logged out', { userId: userInfo?.userId })
    window.dispatchEvent(new CustomEvent('authLogout', {
      detail: { message: 'User logged out locally' },
    }))
    const service = encodeURIComponent(window.location.href)
    window.location.href = `https://login.nstl.gov.cn/logout?service=${service}`
  }

  destroy() {
    this.postMessageHandler.stopListening()
    this.removeNstlParentCallbacks()
    this.hideLoginModal()
  }

  private async handleLoginSuccess(data: LoginSuccessData) {
    if (this.loginCompleting) return
    this.loginCompleting = true

    try {
      let userInfo: NstlUserInfo | null = null
      try {
        userInfo = await this.fetchUserInfo()
      } catch (error) {
        this.log('warn', 'Failed to fetch NSTL user info after login callback, waiting for sync', error)
      }

      if (userInfo && isRealUserId(userInfo.userId)) {
        this.completeLoginWithUserInfo(userInfo, data.token)
        return
      }

      this.showMessage('登录已确认，正在同步 NSTL 用户信息...', 'info')
      userInfo = await this.waitForMainSystemUserInfo(this.config.fallbackSyncMaxAttempts)
      if (userInfo && isRealUserId(userInfo.userId)) {
        this.completeLoginWithUserInfo(userInfo, data.token)
        return
      }

      const fallbackUserInfo = this.createFallbackUserInfo(data)
      if (fallbackUserInfo) {
        this.log('warn', 'NSTL user info unavailable after sync wait, creating fallback local session', data)
        this.showMessage('未同步到真实 NSTL 用户信息，已进入本地兜底登录', 'warning')
        this.completeLoginWithUserInfo(fallbackUserInfo, data.token)
        return
      }

      this.loginCompleting = false
      this.log('warn', 'NSTL login callback returned without usable user info', data)
      this.showMessage('登录已返回，但未获取到用户信息，请稍后重试', 'warning')
    } catch (error) {
      this.loginCompleting = false
      this.log('error', 'Failed to handle login success', error)
      this.showMessage('登录处理失败，请重试', 'error')
    }
  }

  private handleLoginFailure(error: unknown) {
    this.log('error', 'Login failed', error)
    this.showMessage('登录失败，请重试', 'error')
  }

  private handleLoginClosed() {
    this.hideLoginModal()
    window.dispatchEvent(new CustomEvent('authLoginClosed', {
      detail: { message: 'Login modal closed by user' },
    }))
  }

  private handleLoginTimeout() {
    this.stopLoginPolling()
    this.loginModal = null
    this.showMessage('登录超时，请重新尝试', 'error')
    window.setTimeout(() => this.showLoginModal(), 1000)
  }

  private startLoginPolling() {
    this.stopLoginPolling()
    this.loginPollStartedAt = Date.now()
    this.loginPollTimer = window.setInterval(() => {
      void this.pollLoginStatus()
    }, this.config.loginPollInterval)
    void this.pollLoginStatus()
  }

  private stopLoginPolling() {
    if (this.loginPollTimer) {
      window.clearInterval(this.loginPollTimer)
      this.loginPollTimer = 0
    }
    this.loginPollStartedAt = 0
    this.loginPollInFlight = false
  }

  private async pollLoginStatus() {
    if (this.loginPollInFlight || this.loginCompleting || !this.loginModal?.isVisible()) return
    const now = Date.now()

    if (this.loginSyncStartedAt && now - this.loginSyncStartedAt > this.config.loginStatusSyncTimeout) {
      this.loginSyncStartedAt = 0
      this.showMessage('已完成登录操作，但尚未同步到 NSTL 主站登录态，请稍后重试', 'warning')
      return
    }

    if (now - this.loginPollStartedAt > this.config.loginPollTimeout) {
      this.stopLoginPolling()
      this.showMessage('未获取到 NSTL 登录态，请确认微信扫码或手机验证码登录已完成', 'warning')
      return
    }

    this.loginPollInFlight = true
    try {
      const userInfo = await this.fetchUserInfo()
      if (userInfo && isRealUserId(userInfo.userId)) {
        this.completeLoginWithUserInfo(userInfo)
      }
    } catch (error) {
      this.log('warn', 'Polling NSTL login status failed', error)
    } finally {
      this.loginPollInFlight = false
    }
  }

  private completeLoginWithUserInfo(userInfo: NstlUserInfo, token?: string) {
    this.loginCompleting = true
    this.sessionManager.createSession({
      userId: userInfo.userId,
      username: userInfo.username,
      email: userInfo.email,
      sessionToken: token || this.generateNonce(),
      nonce: this.generateNonce(),
      loginTime: Date.now(),
    })
    this.hideLoginModal()
    this.loginSyncStartedAt = 0
    window.dispatchEvent(new CustomEvent('authSuccess', {
      detail: { userInfo: this.getUserInfo() },
    }))
    this.loginCompleting = false
  }

  private updateSessionWithUserInfo(userInfo: NstlUserInfo, session?: StoredSession | null) {
    this.sessionManager.createSession({
      userId: userInfo.userId,
      username: userInfo.username,
      email: userInfo.email,
      sessionToken: session?.session.token || this.generateNonce(),
      nonce: session?.session.nonce || this.generateNonce(),
      loginTime: session?.session.loginTime || Date.now(),
    })
  }

  private createFallbackUserInfo(data: LoginSuccessData): NstlUserInfo | null {
    const postMessageUserId = normalizeSessionUserId(data.userId)
    if (postMessageUserId) {
      return {
        userId: postMessageUserId,
        username: data.username || postMessageUserId,
        email: data.email,
      }
    }

    if (String(data.message || '').toUpperCase() === 'SUCCESS') {
      const userId = `nstl_user_${Date.now()}`
      return {
        userId,
        username: 'NSTL用户',
        email: '',
      }
    }

    return null
  }

  private async waitForMainSystemUserInfo(maxAttempts: number) {
    let attempt = 0

    while (attempt < maxAttempts) {
      attempt += 1
      try {
        const userInfo = await this.fetchUserInfo()
        if (userInfo && isRealUserId(userInfo.userId)) return userInfo
      } catch (error) {
        this.log('warn', 'Waiting for NSTL user info failed', error)
      }
      if (attempt < maxAttempts) {
        await delay(1000)
      }
    }

    return null
  }

  private installNstlParentCallbacks() {
    window.wxRegist = this.boundWxRegist
    window.WxRegist = this.boundWxRegist
    window.initWeichatLogin = this.boundInitWeichatLogin
  }

  private removeNstlParentCallbacks() {
    if (window.wxRegist === this.boundWxRegist) delete window.wxRegist
    if (window.WxRegist === this.boundWxRegist) delete window.WxRegist
    if (window.initWeichatLogin === this.boundInitWeichatLogin) delete window.initWeichatLogin
  }

  private handleInitWeichatLogin() {
    this.log('info', 'NSTL login iframe requested WeChat QR re-initialization')
    this.loginCompleting = false
    this.loginSyncStartedAt = 0
    const iframe = this.loginModal?.iframe
    if (!iframe) return
    iframe.src = this.config.modalConfig.iframeUrl
    this.startLoginPolling()
  }

  private handleWxRegist(response: WxLoginResponse) {
    const code = response?.code == null ? '' : String(response.code)
    this.log('info', 'NSTL WeChat login callback received', response)

    if (code === '1' || code === '') {
      this.showMessage('微信账号未绑定 NSTL 账号，请使用手机验证码登录或先完成绑定', 'warning')
      this.handleInitWeichatLogin()
      return
    }

    if (code === '2') {
      this.showMessage(response.msg || '微信登录失败，请重新扫码', 'error')
      this.handleInitWeichatLogin()
      return
    }

    this.loginSyncStartedAt = Date.now()
    this.showMessage('微信扫码已确认，正在同步 NSTL 登录态...', 'info')
    this.loginCompleting = false
    this.startLoginPolling()
  }

  private handleMainSystemLogout() {
    window.dispatchEvent(new CustomEvent('authLogout', {
      detail: { message: 'Main system logout detected' },
    }))
  }

  private generateNonce() {
    if (crypto?.getRandomValues) {
      return Array.from(crypto.getRandomValues(new Uint8Array(16)))
        .map((value) => value.toString(16).padStart(2, '0'))
        .join('')
    }
    return `${Date.now()}_${Math.random().toString(36).slice(2)}`
  }

  private showMessage(message: string, type: 'info' | 'warning' | 'error' | 'success') {
    const colors = {
      info: '#3b82f6',
      warning: '#f59e0b',
      error: '#ef4444',
      success: '#10b981',
    }
    const messageEl = document.createElement('div')
    messageEl.className = `auth-message auth-message-${type}`
    messageEl.textContent = message
    messageEl.style.cssText = `
      position: fixed;
      top: 20px;
      left: 50%;
      transform: translateX(-50%);
      padding: 12px 24px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 500;
      z-index: 10001;
      background: ${colors[type]};
      color: #ffffff;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
      max-width: min(520px, calc(100vw - 32px));
      text-align: center;
    `
    document.body.appendChild(messageEl)
    window.setTimeout(() => messageEl.remove(), 3000)
  }

  private log(level: 'debug' | 'info' | 'warn' | 'error', message: string, details: unknown = null) {
    const prefix = '[AuthManager]'
    if (level === 'error') console.error(prefix, message, details)
    else if (level === 'warn') console.warn(prefix, message, details)
    else if (level === 'info') console.log(prefix, message, details)
    else console.debug(prefix, message, details)
  }
}

let authManager: AuthManager | null = null

export function createAuthManager(config: Partial<AuthConfig> = {}) {
  if (!authManager) {
    window.SessionManager = SessionManager
    window.LoginModal = LoginModal
    window.PostMessageHandler = PostMessageHandler
    window.AuthManager = AuthManager
    window.DEFAULT_AUTH_CONFIG = DEFAULT_CONFIG

    authManager = new AuthManager({
      ...DEFAULT_CONFIG,
      ...config,
      modalConfig: {
        ...DEFAULT_CONFIG.modalConfig,
        ...(config.modalConfig || {}),
      },
    })
    window.authManager = authManager
  }
  return authManager
}

export function getAuthManager() {
  return authManager ?? createAuthManager()
}

export function getCurrentUser() {
  return getAuthManager().getUserInfo()
}

export function getUserScope() {
  const userScope = getBusinessUserScope(getCurrentUser()?.userId)
  if (!userScope) {
    throw new Error('未获取到真实 NSTL 用户')
  }
  return userScope
}

export async function requireUserScope() {
  return getAuthManager().requireUserScope()
}

function isRealUserId(userId?: string | null): userId is string {
  return Boolean(normalizeRealUserId(userId))
}

function normalizeSessionUserId(userId?: string | null) {
  if (!userId) return ''
  const normalized = userId.trim()
  const lower = normalized.toLowerCase()
  const blocked = new Set(['default', 'unknown', 'mock_user_id'])
  if (blocked.has(lower)) return ''
  if (
    lower.startsWith('mock_')
    || lower.startsWith('fake_')
    || lower.startsWith('local_')
  ) {
    return ''
  }
  return normalized
}

function getBusinessUserScope(userId?: string | null) {
  return normalizeSessionUserId(userId)
}

function normalizeRealUserId(userId?: string | null) {
  if (!userId) return ''
  const normalized = userId.trim()
  const lower = normalized.toLowerCase()
  const blocked = new Set(['default', 'unknown', 'mock_user_id'])
  if (blocked.has(lower)) return ''
  if (
    lower.startsWith('nstl_user_')
    || lower.startsWith('mock_')
    || lower.startsWith('fake_')
    || lower.startsWith('local_')
  ) {
    return ''
  }
  return normalized
}

function normalizeNstlUserInfoResult(result: unknown): NstlUserInfo | null {
  if (!result || typeof result !== 'object') return null

  const response = result as {
    code?: unknown
    data?: unknown
    user?: unknown
    userInfo?: unknown
  }
  if (response.code !== 0) return null

  const data = pickObject(response.data)
  const nestedUser = pickObject(data?.userInfo) ?? pickObject(data?.user) ?? pickObject(response.userInfo) ?? pickObject(response.user)
  const payload = nestedUser ?? data
  if (!payload) return null

  const userId = firstStringValue(payload, ['userId', 'user_id', 'id', 'uid', 'loginId', 'account'])
  if (!isRealUserId(userId)) return null

  const username = formatNstlDisplayName(firstStringValue(payload, ['userName', 'username', 'name', 'realName', 'nickName', 'displayName'])) || userId
  const email = firstStringValue(payload, ['email', 'mail']) || ''

  return { userId, username, email }
}

function formatNstlDisplayName(value?: string | null) {
  const raw = String(value || '').trim()
  if (!raw) return ''

  const unicodeDecoded = raw.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex: string) => (
    String.fromCharCode(Number.parseInt(hex, 16))
  ))

  try {
    return decodeURIComponent(unicodeDecoded)
  } catch {
    return unicodeDecoded
  }
}

function pickObject(value: unknown) {
  return value && typeof value === 'object' ? value as Record<string, unknown> : null
}

function firstStringValue(payload: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = payload[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  }
  return ''
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

declare global {
  interface Window {
    AuthManager?: typeof AuthManager
    SessionManager?: typeof SessionManager
    LoginModal?: typeof LoginModal
    PostMessageHandler?: typeof PostMessageHandler
    authManager?: AuthManager
    DEFAULT_AUTH_CONFIG?: AuthConfig
    wxRegist?: (response: WxLoginResponse) => void
    WxRegist?: (response: WxLoginResponse) => void
    initWeichatLogin?: () => void
  }
}
