/**
 * 一致性评估智能体 - 用户认证模块
 *
 * 本模块提供统一的用户认证功能，包括：
 * - SessionManager: 会话管理器
 * - LoginModal: 登录模态窗口
 * - PostMessageHandler: 跨域消息处理器
 * - AuthManager: 认证管理器主类
 *
 * @version 1.0
 */

(function(window) {
  'use strict';
  
  // ============================================================================
  // SessionManager 类 - 会话管理
  // ============================================================================
  
  /**
   * SessionManager 负责管理用户会话的创建、验证、过期检查和清理
   * 
   * 功能特性：
   * - 会话数据的持久化存储（localStorage/sessionStorage）
   * - 会话有效性验证（时间戳、令牌格式检查）
   * - 缓存机制优化性能（5秒缓存）
   * - 存储降级策略（localStorage → sessionStorage）
   * 
   * 验证需求：4.1, 4.2, 4.3, 4.4, 4.7, 7.4, 10.5
   */
  class SessionManager {
    /**
     * 构造函数
     * @param {Object} config - 配置对象
     * @param {number} config.sessionTimeout - 会话超时时间（毫秒）
     * @param {string} config.storageKey - localStorage 存储键名
     */
    constructor(config) {
      this.config = config;
      this.cache = null;
      this.cacheTime = 0;
      this.CACHE_DURATION = 5000; // 5秒缓存，满足需求 10.5
    }
    
    /**
     * 创建新会话
     * 
     * 将用户信息存储到 localStorage，包含所有必需字段：
     * - userId: 用户 ID
     * - username: 用户名
     * - loginTime: 登录时间戳
     * - sessionToken: 会话令牌
     * - nonce: 随机数（用于安全验证）
     * 
     * 验证需求：4.1, 4.2, 8.3
     * 
     * @param {Object} userInfo - 用户信息对象
     * @param {string} userInfo.userId - 用户 ID
     * @param {string} userInfo.username - 用户名
     * @param {string} [userInfo.email] - 邮箱（可选）
     * @param {string} userInfo.sessionToken - 会话令牌
     * @param {string} userInfo.nonce - 随机数
     * @param {number} userInfo.loginTime - 登录时间戳
     */
    createSession(userInfo) {
      const session = {
        version: '1.0',
        user: {
          userId: userInfo.userId,
          username: userInfo.username,
          email: userInfo.email
        },
        session: {
          token: userInfo.sessionToken,
          nonce: userInfo.nonce,
          loginTime: userInfo.loginTime,
          expiresAt: userInfo.loginTime + this.config.sessionTimeout
        },
        metadata: {
          userAgent: navigator.userAgent,
          loginPage: window.location.pathname,
          lastActivity: Date.now()
        }
      };
      
      this.saveToStorage(this.config.storageKey, session);
      this.cache = session;
      this.cacheTime = Date.now();
    }
    
    /**
     * 获取当前会话
     * 
     * 使用缓存机制优化性能：
     * - 如果缓存有效（5秒内），直接返回缓存
     * - 否则从存储读取并更新缓存
     * 
     * 验证需求：4.3, 10.5
     * 
     * @returns {Object|null} 会话对象，如果不存在则返回 null
     */
    getSession() {
      // 使用缓存优化性能（需求 10.5）
      if (this.cache && (Date.now() - this.cacheTime) < this.CACHE_DURATION) {
        return this.cache;
      }
      
      const session = this.loadFromStorage(this.config.storageKey);
      if (session) {
        this.cache = session;
        this.cacheTime = Date.now();
      }
      return session;
    }
    
    /**
     * 验证会话有效性
     * 
     * 检查项：
     * 1. 会话是否存在
     * 2. 必需字段是否完整（userId, token）
     * 3. 会话是否过期（检查时间戳）
     * 
     * 验证需求：4.4
     * 
     * @returns {boolean} 会话是否有效
     */
    validateSession() {
      const session = this.getSession();
      if (!session) return false;
      
      // 检查必需字段
      if (!session.user?.userId || !session.session?.token) {
        return false;
      }
      
      // 检查是否过期
      if (this.isSessionExpired(session)) {
        this.clearSession();
        return false;
      }
      
      return true;
    }
    
    /**
     * 检查会话是否过期
     * 
     * 会话过期时间为 24 小时（由配置决定）
     * 
     * 验证需求：4.7
     * 
     * @param {Object} [session] - 会话对象，如果不提供则获取当前会话
     * @returns {boolean} 会话是否过期
     */
    isSessionExpired(session = null) {
      const sess = session || this.getSession();
      if (!sess) return true;
      
      const now = Date.now();
      return now > sess.session.expiresAt;
    }
    
    /**
     * 清除会话
     * 
     * 从 localStorage 和 sessionStorage 中删除会话数据，
     * 并清空缓存
     * 
     * 验证需求：4.7
     */
    clearSession() {
      this.removeFromStorage(this.config.storageKey);
      this.cache = null;
      this.cacheTime = 0;
    }
    
    /**
     * 获取会话年龄（自登录以来的时间）
     * 
     * @returns {number} 会话年龄（毫秒），如果会话不存在则返回 0
     */
    getSessionAge() {
      const session = this.getSession();
      if (!session) return 0;
      
      return Date.now() - session.session.loginTime;
    }
    
    /**
     * 保存数据到存储
     * 
     * 实现存储降级策略：
     * 1. 首先尝试使用 localStorage
     * 2. 如果失败（如隐私模式、空间已满），尝试 sessionStorage
     * 3. 如果都失败，记录错误并返回 false
     * 
     * 验证需求：7.4
     * 
     * @param {string} key - 存储键名
     * @param {*} value - 要存储的值（将被 JSON 序列化）
     * @returns {boolean} 是否保存成功
     */
    saveToStorage(key, value) {
      const data = JSON.stringify(value);
      
      try {
        localStorage.setItem(key, data);
        return true;
      } catch (e) {
        console.warn('[SessionManager] localStorage unavailable, trying sessionStorage', e);
        
        // 显示警告提示（需求 7.4）
        this.showStorageWarning('localStorage');
        
        try {
          sessionStorage.setItem(key, data);
          return true;
        } catch (e2) {
          console.error('[SessionManager] Both localStorage and sessionStorage unavailable', e2);
          
          // 显示错误提示（需求 7.4）
          this.showStorageWarning('both');
          
          return false;
        }
      }
    }
    
    /**
     * 显示存储不可用警告
     * 
     * 当浏览器存储不可用时，显示警告提示
     * 
     * 验证需求：7.4
     * 
     * @param {string} storageType - 存储类型：'localStorage' | 'both'
     */
    showStorageWarning(storageType) {
      // 避免重复显示警告
      if (this._storageWarningShown) return;
      this._storageWarningShown = true;
      
      let message = '';
      if (storageType === 'localStorage') {
        message = '浏览器本地存储不可用，登录状态仅在当前标签页有效';
      } else {
        message = '浏览器存储不可用，登录状态无法保存，请检查浏览器设置';
      }
      
      // 创建警告提示
      const warningEl = document.createElement('div');
      warningEl.className = 'storage-warning';
      warningEl.textContent = message;
      warningEl.style.cssText = `
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
      `;
      
      document.body.appendChild(warningEl);
      
      // 5 秒后移除
      setTimeout(() => {
        warningEl.remove();
      }, 5000);
    }
    
    /**
     * 从存储加载数据
     * 
     * 按优先级尝试：localStorage → sessionStorage
     * 
     * 验证需求：4.3, 7.4
     * 
     * @param {string} key - 存储键名
     * @returns {*|null} 解析后的数据，如果不存在或解析失败则返回 null
     */
    loadFromStorage(key) {
      try {
        const data = localStorage.getItem(key) || sessionStorage.getItem(key);
        return data ? JSON.parse(data) : null;
      } catch (e) {
        console.error('[SessionManager] Failed to load from storage', e);
        return null;
      }
    }
    
    /**
     * 从存储中删除数据
     * 
     * 同时从 localStorage 和 sessionStorage 中删除
     * 
     * @param {string} key - 存储键名
     */
    removeFromStorage(key) {
      try {
        localStorage.removeItem(key);
        sessionStorage.removeItem(key);
      } catch (e) {
        console.error('[SessionManager] Failed to remove from storage', e);
      }
    }
  }
  
  // 导出到全局
  window.SessionManager = SessionManager;

  // ============================================================================
  // LoginModal 类 - 登录模态窗口
  // ============================================================================
  
  /**
   * LoginModal 负责创建和管理登录模态窗口
   * 
   * 功能特性：
   * - 创建全屏遮罩层和模态窗口容器
   * - 嵌入 NSTL 登录服务的 iframe
   * - 提供关闭按钮和超时机制
   * - 平滑的淡入淡出动画效果（200ms）
   * 
   * 验证需求：2.1, 2.2, 2.3, 2.4, 2.5, 7.2, 9.2, 10.3
   */
  class LoginModal {
    /**
     * 构造函数
     * @param {Object} config - 配置对象
     * @param {string} config.iframeUrl - iframe 加载的 URL
     * @param {string} config.width - 模态窗口宽度
     * @param {string} config.height - 模态窗口高度
     * @param {number} config.zIndex - z-index 层级
     * @param {number} config.timeout - 超时时间（毫秒）
     * @param {boolean} config.showLogo - 是否显示 Logo
     * @param {boolean} config.allowClose - 是否允许关闭
     */
    constructor(config) {
      this.config = {
        iframeUrl: 'https://login.nstl.gov.cn',
        width: '400px',
        height: '500px',
        zIndex: 10000,
        timeout: 5 * 60 * 1000, // 5分钟
        showLogo: true,
        allowClose: true,
        ...config
      };
      
      this.modalElement = null;
      this.iframeElement = null;
      this.timeoutTimer = null;
      this.callbacks = {
        onClose: null,
        onTimeout: null
      };
    }
    
    /**
     * 显示登录模态窗口
     * 
     * 创建包含以下元素的完整 UI：
     * - 全屏遮罩层（z-index > 9999）
     * - 居中的模态窗口容器
     * - 头部（Logo、标题、关闭按钮）
     * - iframe 容器
     * 
     * 使用 200ms 淡入动画效果
     * 
     * 验证需求：2.1, 2.2, 2.4, 9.2, 10.3
     */
    show() {
      if (this.isVisible()) {
        console.warn('[LoginModal] Modal is already visible');
        return;
      }
      
      this.createModal();
      this.startTimeout();
    }
    
    /**
     * 隐藏登录模态窗口
     * 
     * 使用 200ms 淡出动画效果，动画完成后销毁 DOM 元素
     * 
     * 验证需求：2.5, 10.3
     */
    hide() {
      if (!this.isVisible()) {
        console.warn('[LoginModal] Modal is not visible');
        return;
      }
      
      this.destroyModal();
    }
    
    /**
     * 检查模态窗口是否可见
     * 
     * @returns {boolean} 模态窗口是否可见
     */
    isVisible() {
      return this.modalElement !== null && document.body.contains(this.modalElement);
    }
    
    /**
     * 创建模态窗口 DOM 结构
     * 
     * 创建完整的 UI 结构：
     * 1. 全屏遮罩层（z-index: 10000）
     * 2. 模态窗口容器（居中、圆角、阴影）
     * 3. 头部（Logo、标题、关闭按钮）
     * 4. iframe 容器
     * 
     * 验证需求：2.1, 2.2, 2.4, 9.2
     */
    createModal() {
      // 创建遮罩层
      const overlay = document.createElement('div');
      overlay.className = 'login-modal-overlay';
      overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.4);
        z-index: ${this.config.zIndex};
      `;
      
      // 创建 iframe
      this.iframeElement = this.createIframe();
      this.iframeElement.className = 'login-modal-iframe';
      this.iframeElement.style.cssText = `
      position: absolute;
    inset: 0px;
    margin: auto;
    border: 0px;
        width: 100%;
    height: 100%;
      `;
      
      overlay.appendChild(this.iframeElement);
      document.body.appendChild(overlay);
      document.body.style.overflow = 'hidden';
      this.modalElement = overlay;
    }
    
    /**
     * 创建模态窗口头部
     * 
     * 包含：
     * - NSTL Logo（如果 showLogo 为 true）
     * - 标题文本
     * - 关闭按钮（如果 allowClose 为 true）
     * 
     * 验证需求：2.4, 9.2
     * 
     * @returns {HTMLElement} 头部元素
     */
    createHeader() {
      const header = document.createElement('div');
      header.className = 'login-modal-header';
      // header.style.cssText = `
      //   padding: 20px;
      //   border-bottom: 1px solid #e5e7eb;
      //   display: flex;
      //   align-items: center;
      //   justify-content: space-between;
      // `;
      
      // 左侧：Logo 和标题
      const title = document.createElement('div');
      title.style.cssText = `
        display: flex;
        align-items: center;
        gap: 12px;
      `;
      
      // Logo（如果启用）
      // if (this.config.showLogo) {
      //   const logo = document.createElement('img');
      //   logo.src = 'static/images/logo.png';
      //   logo.alt = 'NSTL Logo';
      //   logo.style.cssText = 'width: 32px; height: 32px;';
      //   logo.onerror = () => {
      //     // 如果 Logo 加载失败，隐藏图片元素
      //     logo.style.display = 'none';
      //   };
      //   title.appendChild(logo);
      // }
      
      // 标题文本
      // const titleText = document.createElement('span');
      // titleText.textContent = 'NSTL 统一登录';
      // titleText.style.cssText = `
      //   font-size: 18px;
      //   font-weight: 600;
      //   color: #1f2937;
      // `;
      // title.appendChild(titleText);
      
      header.appendChild(title);
      
      // 右侧：关闭按钮（如果允许）
      if (this.config.allowClose) {
        const closeBtn = document.createElement('button');
        closeBtn.className = 'login-modal-close';
        closeBtn.innerHTML = 'X';
        closeBtn.style.cssText = `
          background: none;
          border: none;
          font-size: 24px;
          color: #6b7280;
          cursor: pointer;
          padding: 4px 8px;
          line-height: 1;
          transition: color 0.2s;
        `;
        
        // 鼠标悬停效果
        closeBtn.onmouseover = () => closeBtn.style.color = '#1f2937';
        closeBtn.onmouseout = () => closeBtn.style.color = '#6b7280';
        
        // 点击关闭
        closeBtn.onclick = () => {
          this.hide();
          if (this.callbacks.onClose) {
            this.callbacks.onClose();
          }
        };
        
        header.appendChild(closeBtn);
      }
      
      return header;
    }
    
    /**
     * 创建 iframe 元素
     * 
     * iframe 加载 NSTL 登录服务页面
     * 设置 sandbox 属性以限制权限（允许 scripts、forms、same-origin）
     * 
     * 验证需求：2.2, 2.3, 7.1, 8.6
     * 
     * @returns {HTMLIFrameElement} iframe 元素
     */
    createIframe() {
      const iframe = document.createElement('iframe');
      iframe.src = this.config.iframeUrl;
      iframe.style.cssText = `
        width: 100%;
        height: 100%;
        border: none;
      `;
      
      // 设置 sandbox 属性以限制权限
      iframe.setAttribute('sandbox', 'allow-scripts allow-forms allow-same-origin allow-popups');
      
      // 添加加载错误处理（需求 7.1）
      iframe.onerror = () => {
        console.error('[LoginModal] Failed to load iframe:', this.config.iframeUrl);
        this.showIframeError();
      };
      
      // 添加加载超时检测（需求 7.1）
      const loadTimeout = setTimeout(() => {
        if (!iframe.contentDocument || iframe.contentDocument.readyState !== 'complete') {
          console.error('[LoginModal] Iframe load timeout:', this.config.iframeUrl);
          this.showIframeError();
        }
      }, 10000); // 10秒超时
      
      iframe.onload = () => {
        clearTimeout(loadTimeout);
        console.log('[LoginModal] Iframe loaded successfully');
      };
      
      return iframe;
    }
    
    /**
     * 显示 iframe 加载错误提示
     * 
     * 当 NSTL 登录服务无法加载时，显示错误提示和重试按钮
     * 
     * 验证需求：7.1
     */
    showIframeError() {
      if (!this.modalElement) return;
      
      // 查找 iframe 容器
      const iframeContainer = this.modalElement.querySelector('.login-modal-body');
      if (!iframeContainer) return;
      
      // 清空容器
      iframeContainer.innerHTML = '';
      
      // 创建错误提示界面
      const errorDiv = document.createElement('div');
      errorDiv.className = 'login-modal-error';
      errorDiv.style.cssText = `
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100%;
        padding: 40px;
        text-align: center;
      `;
      
      // 错误图标
      const icon = document.createElement('div');
      icon.innerHTML = '⚠️';
      icon.style.cssText = `
        font-size: 48px;
        margin-bottom: 16px;
      `;
      
      // 错误标题
      const title = document.createElement('h3');
      title.textContent = '无法连接到登录服务';
      title.style.cssText = `
        font-size: 18px;
        font-weight: 600;
        color: #1f2937;
        margin: 0 0 8px 0;
      `;
      
      // 错误描述
      const description = document.createElement('p');
      description.textContent = '请检查网络连接，或稍后再试';
      description.style.cssText = `
        font-size: 14px;
        color: #6b7280;
        margin: 0 0 24px 0;
      `;
      
      // 重试按钮
      const retryBtn = document.createElement('button');
      retryBtn.textContent = '重试';
      retryBtn.style.cssText = `
        background: #3b82f6;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 10px 24px;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        transition: background 0.2s;
      `;
      
      retryBtn.onmouseover = () => retryBtn.style.background = '#2563eb';
      retryBtn.onmouseout = () => retryBtn.style.background = '#3b82f6';
      
      retryBtn.onclick = () => {
        // 重新加载 iframe
        this.hide();
        setTimeout(() => this.show(), 300);
      };
      
      // 组装错误界面
      errorDiv.appendChild(icon);
      errorDiv.appendChild(title);
      errorDiv.appendChild(description);
      errorDiv.appendChild(retryBtn);
      
      iframeContainer.appendChild(errorDiv);
    }
    
    /**
     * 销毁模态窗口
     * 
     * 从 DOM 中移除所有相关元素（遮罩层、iframe）
     * 清除超时定时器
     * 
     * 验证需求：2.5
     */
    destroyModal() {
      if (this.modalElement) {
        this.modalElement.remove();
        this.modalElement = null;
      }
      
      if (this.iframeElement) {
        this.iframeElement = null;
      }
      
      document.body.style.overflow = '';
      this.clearTimeout();
    }
    
    /**
     * 启动超时定时器
     * 
     * 如果超过配置的超时时间（默认 5 分钟）无响应，
     * 触发超时回调并关闭模态窗口
     * 
     * 验证需求：7.2
     */
    startTimeout() {
      const timeout = this.config.timeout;
      
      this.timeoutTimer = setTimeout(() => {
        console.warn('[LoginModal] Login timeout after', timeout, 'ms');
        
        if (this.callbacks.onTimeout) {
          this.callbacks.onTimeout();
        }
        
        this.hide();
      }, timeout);
    }
    
    /**
     * 清除超时定时器
     */
    clearTimeout() {
      if (this.timeoutTimer) {
        clearTimeout(this.timeoutTimer);
        this.timeoutTimer = null;
      }
    }
    
    /**
     * 注册关闭回调
     * 
     * @param {Function} callback - 关闭时调用的回调函数
     */
    onClose(callback) {
      this.callbacks.onClose = callback;
    }
    
    /**
     * 注册超时回调
     * 
     * @param {Function} callback - 超时时调用的回调函数
     */
    onTimeout(callback) {
      this.callbacks.onTimeout = callback;
    }
  }
  
  // 导出到全局
  window.LoginModal = LoginModal;

  // ============================================================================
  // PostMessageHandler 类 - 跨域消息处理
  // ============================================================================
  
  /**
   * PostMessageHandler 负责处理来自 NSTL 登录服务的跨域消息
   * 
   * 功能特性：
   * - 监听 window 的 message 事件
   * - 验证消息来源（只接受信任域）
   * - 验证消息格式（检查必需字段）
   * - 消息类型分发（loginSuccess、loginFailure、loginClosed）
   * - 提供回调注册机制
   * 
   * 验证需求：3.1, 3.2, 3.3, 3.4, 3.5, 8.1
   */
  class PostMessageHandler {
    /**
     * 构造函数
     * @param {Object} config - 配置对象
     * @param {string[]} config.trustedOrigins - 信任的消息来源列表
     */
    constructor(config) {
      this.config = config;
      this.callbacks = {
        onLoginSuccess: null,
        onLoginFailure: null,
        onLoginClosed: null
      };
      this.isListening = false;
      this.boundHandler = this.handleMessage.bind(this);
    }
    
    /**
     * 开始监听 postMessage 事件
     * 
     * 在 window 上添加 message 事件监听器
     * 
     * 验证需求：3.1
     */
    startListening() {
      if (this.isListening) {
        console.warn('[PostMessageHandler] Already listening');
        return;
      }
      
      window.addEventListener('message', this.boundHandler);
      this.isListening = true;
      console.log('[PostMessageHandler] Started listening for messages');
    }
    
    /**
     * 停止监听 postMessage 事件
     * 
     * 从 window 移除 message 事件监听器
     */
    stopListening() {
      if (!this.isListening) {
        console.warn('[PostMessageHandler] Not listening');
        return;
      }
      
      window.removeEventListener('message', this.boundHandler);
      this.isListening = false;
      console.log('[PostMessageHandler] Stopped listening for messages');
    }
    
    /**
     * 处理接收到的 postMessage 事件
     * 
     * 处理流程：
     * 1. 验证消息来源（必须来自信任域）
     * 2. 验证消息格式（检查必需字段）
     * 3. 根据消息类型分发到相应的回调
     * 
     * 支持两种消息格式：
     * - 标准JSON对象：{type: 'loginSuccess', data: {...}}
     * - NSTL简单字符串：'SUCCESS', 'CLOSE', 'FAILURE'
     * 
     * 验证需求：3.2, 3.3, 3.4, 3.5, 8.1
     * 
     * @param {MessageEvent} event - postMessage 事件对象
     */
    handleMessage(event) {
      // 验证消息来源（需求 3.2, 3.5, 8.1）
      if (!this.validateOrigin(event.origin)) {
        console.warn('[PostMessageHandler] Ignored message from untrusted origin:', event.origin);
        return;
      }
      
      const data = event.data;
      const normalizedString = typeof data === 'string' ? data.toLowerCase() : '';
      
      // 验证消息格式
      if (!this.validateMessage(event)) {
        console.warn('[PostMessageHandler] Invalid message format:', event.data);
        return;
      }
      
      // 处理NSTL简单字符串格式
      if (typeof data === 'string') {
        console.log('[PostMessageHandler] Received NSTL string message:', data);
        
        switch (normalizedString) {
          case 'success':
            // 登录成功 - 从URL参数中提取用户信息
            if (this.callbacks.onLoginSuccess) {
              // NSTL登录成功后，用户信息通常在URL参数中
              // 这里我们触发回调，让AuthManager从iframe的URL中提取信息
              this.callbacks.onLoginSuccess({ message: 'SUCCESS' });
            }
            break;
            
          case 'close':
          case 'closelogin':
            // 用户关闭登录窗口
            if (this.callbacks.onLoginClosed) {
              this.callbacks.onLoginClosed();
            }
            break;
            
          case 'failure':
            // 登录失败
            if (this.callbacks.onLoginFailure) {
              this.callbacks.onLoginFailure({ message: 'Login failed' });
            }
            break;
        }
        return;
      }
      
      // 处理标准JSON对象格式
      const message = data;
      console.log('[PostMessageHandler] Received JSON message:', message.type);
      
      // 根据消息类型分发（需求 3.3, 3.4）
      switch (message.type) {
        case 'loginSuccess':
          // 登录成功消息（需求 3.3）
          if (this.callbacks.onLoginSuccess) {
            this.callbacks.onLoginSuccess(message.data);
          }
          break;
          
        case 'loginFailure':
          // 登录失败消息
          if (this.callbacks.onLoginFailure) {
            this.callbacks.onLoginFailure(message.error);
          }
          break;
          
        case 'loginClosed':
          // 登录窗口关闭消息（需求 3.4）
          if (this.callbacks.onLoginClosed) {
            this.callbacks.onLoginClosed();
          }
          break;
          
        default:
          console.warn('[PostMessageHandler] Unknown message type:', message.type);
      }
    }
    
    /**
     * 验证消息来源
     * 
     * 只接受来自信任域（https://login.nstl.gov.cn）的消息
     * 
     * 验证需求：3.2, 3.5, 8.1
     * 
     * @param {string} origin - 消息来源的 origin
     * @returns {boolean} 来源是否可信
     */
    validateOrigin(origin) {
      return this.config.trustedOrigins.includes(origin);
    }
    
    /**
     * 验证消息格式
     * 
     * 支持两种消息格式：
     * 1. 标准JSON对象格式：{type: 'loginSuccess', data: {...}}
     * 2. NSTL简单字符串格式：'SUCCESS' 或 'CLOSE'
     * 
     * 验证需求：3.2
     * 
     * @param {MessageEvent} event - postMessage 事件对象
     * @returns {boolean} 消息格式是否有效
     */
    validateMessage(event) {
      const data = event.data;
      
      // 支持NSTL的简单字符串格式，按参考组件统一转小写处理
      if (typeof data === 'string') {
        const normalizedString = data.toLowerCase();
        const validStrings = ['success', 'close', 'closelogin', 'failure'];
        return validStrings.includes(normalizedString);
      }
      
      // 检查标准JSON对象格式
      if (!data || typeof data !== 'object') {
        return false;
      }
      
      // 检查必需字段：type
      if (!data.type || typeof data.type !== 'string') {
        return false;
      }
      
      // 检查时间戳（可选字段）
      if (data.timestamp !== undefined && typeof data.timestamp !== 'number') {
        return false;
      }
      
      return true;
    }
    
    /**
     * 注册登录成功回调
     * 
     * 当接收到 loginSuccess 消息时调用此回调
     * 
     * 验证需求：3.3
     * 
     * @param {Function} callback - 回调函数，接收用户数据作为参数
     */
    onLoginSuccess(callback) {
      this.callbacks.onLoginSuccess = callback;
    }
    
    /**
     * 注册登录失败回调
     * 
     * 当接收到 loginFailure 消息时调用此回调
     * 
     * @param {Function} callback - 回调函数，接收错误信息作为参数
     */
    onLoginFailure(callback) {
      this.callbacks.onLoginFailure = callback;
    }
    
    /**
     * 注册登录关闭回调
     * 
     * 当接收到 loginClosed 消息时调用此回调
     * 
     * 验证需求：3.4
     * 
     * @param {Function} callback - 回调函数，无参数
     */
    onLoginClosed(callback) {
      this.callbacks.onLoginClosed = callback;
    }
  }
  
  // 导出到全局
  window.PostMessageHandler = PostMessageHandler;

  // ============================================================================
  // InputValidator 类 - 输入验证工具
  // ============================================================================
  
  /**
   * InputValidator 提供输入验证和字符串清理功能
   * 
   * 功能特性：
   * - 验证用户 ID、用户名、邮箱、令牌的格式
   * - 清理字符串，防止 XSS 攻击
   * - 所有方法都是静态方法，无需实例化
   * 
   * 验证需求：8.1, 8.2, 8.5
   */
  class InputValidator {
    /**
     * 验证用户 ID
     * 
     * 规则：
     * - 只允许字母（a-z, A-Z）、数字（0-9）、下划线（_）
     * - 长度：1-50 字符
     * 
     * 验证需求：8.1, 8.2
     * 
     * @param {string} userId - 用户 ID
     * @returns {boolean} 是否有效
     */
    static validateUserId(userId) {
      if (!userId || typeof userId !== 'string') {
        return false;
      }
      
      // 只允许字母、数字、下划线，长度 1-50
      return /^[a-zA-Z0-9_]{1,50}$/.test(userId);
    }
    
    /**
     * 验证用户名
     * 
     * 规则：
     * - 允许中文字符（\u4e00-\u9fa5）、字母（a-z, A-Z）、数字（0-9）
     * - 长度：1-50 字符
     * 
     * 验证需求：8.1, 8.2
     * 
     * @param {string} username - 用户名
     * @returns {boolean} 是否有效
     */
    static validateUsername(username) {
      if (!username || typeof username !== 'string') {
        return false;
      }
      
      // 允许中文、字母、数字，长度 1-50
      return /^[\u4e00-\u9fa5a-zA-Z0-9]{1,50}$/.test(username);
    }
    
    /**
     * 验证邮箱地址
     * 
     * 规则：
     * - 基本的邮箱格式验证
     * - 格式：xxx@xxx.xxx
     * 
     * 验证需求：8.1, 8.2
     * 
     * @param {string} email - 邮箱地址
     * @returns {boolean} 是否有效
     */
    static validateEmail(email) {
      if (!email || typeof email !== 'string') {
        return false;
      }
      
      // 基本的邮箱格式验证
      return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }
    
    /**
     * 验证令牌格式
     * 
     * 规则：
     * - JWT 格式验证：三段式结构，用点号分隔
     * - 每段由字母、数字、连字符、下划线组成
     * - 格式：xxx.xxx.xxx
     * 
     * 验证需求：8.1, 8.2
     * 
     * @param {string} token - 令牌字符串
     * @returns {boolean} 是否有效
     */
    static validateToken(token) {
      if (!token || typeof token !== 'string') {
        return false;
      }
      
      // JWT 格式验证：三段式结构
      return /^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$/.test(token);
    }
    
    /**
     * 清理字符串，防止 XSS 攻击
     * 
     * 将潜在危险的 HTML 字符转义为 HTML 实体：
     * - < 转义为 &lt;
     * - > 转义为 &gt;
     * - " 转义为 &quot;
     * - ' 转义为 &#39;
     * - & 转义为 &amp;
     * 
     * 验证需求：8.1, 8.2, 8.5
     * 
     * @param {string} str - 要清理的字符串
     * @returns {string} 清理后的字符串
     */
    static sanitizeString(str) {
      if (!str || typeof str !== 'string') {
        return '';
      }
      
      // 移除潜在的危险字符，转义为 HTML 实体
      return str.replace(/[<>"'&]/g, (char) => {
        const entities = {
          '<': '&lt;',
          '>': '&gt;',
          '"': '&quot;',
          "'": '&#39;',
          '&': '&amp;'
        };
        return entities[char];
      });
    }
    
    /**
     * 验证并清理用户输入
     * 
     * 组合验证和清理功能，用于处理用户输入
     * 
     * @param {string} input - 用户输入
     * @param {string} type - 输入类型：'userId' | 'username' | 'email' | 'token' | 'string'
     * @returns {Object} 验证结果对象 { valid: boolean, sanitized: string, error?: string }
     */
    static validateAndSanitize(input, type) {
      const result = {
        valid: false,
        sanitized: '',
        error: null
      };
      
      // 首先清理输入
      const sanitized = this.sanitizeString(input);
      result.sanitized = sanitized;
      
      // 根据类型进行验证
      switch (type) {
        case 'userId':
          result.valid = this.validateUserId(sanitized);
          if (!result.valid) {
            result.error = '用户 ID 格式无效：只允许字母、数字、下划线，长度 1-50 字符';
          }
          break;
          
        case 'username':
          result.valid = this.validateUsername(sanitized);
          if (!result.valid) {
            result.error = '用户名格式无效：只允许中文、字母、数字，长度 1-50 字符';
          }
          break;
          
        case 'email':
          result.valid = this.validateEmail(sanitized);
          if (!result.valid) {
            result.error = '邮箱格式无效';
          }
          break;
          
        case 'token':
          result.valid = this.validateToken(sanitized);
          if (!result.valid) {
            result.error = '令牌格式无效';
          }
          break;
          
        case 'string':
          // 对于普通字符串，只清理不验证
          result.valid = true;
          break;
          
        default:
          result.error = `未知的验证类型：${type}`;
      }
      
      return result;
    }
  }
  
  // 导出到全局
  window.InputValidator = InputValidator;
  
  // ============================================================================
  // 默认配置常量
  // ============================================================================
  
  /**
   * 默认认证配置
   * 
   * 包含所有认证相关的配置项：
   * - 登录服务配置
   * - 会话配置
   * - 安全配置
   * - UI 配置
   * - 开发配置
   */
  const DEFAULT_CONFIG = {
    // 登录服务配置（本地测试通过 hosts 将 nstl.gov.cn 指向 127.0.0.1）
    loginServiceUrl: 'https://login.nstl.gov.cn',

    // 会话配置
    sessionTimeout: 24 * 60 * 60 * 1000,  // 24 小时
    storageKey: 'cca_user_session',

    // 安全配置
    trustedOrigins: ['https://login.nstl.gov.cn'],

    // UI 配置
    modalConfig: {
      iframeUrl: 'https://login.nstl.gov.cn',
      width: '453px',
      height: '585px',
      zIndex: 10000,
      timeout: 5 * 60 * 1000,  // 5 分钟
      showLogo: false,
      allowClose: false
    },

    // 开发配置
    enableDevMode: false,
    dev: {
      bypassAuth: false,
      mockUser: null,
      logLevel: 'info'  // 'debug' | 'info' | 'warn' | 'error'
    }
  };
  
  // ============================================================================
  // AuthManager 类 - 认证管理器主类
  // ============================================================================
  
  /**
   * AuthManager 是认证系统的核心类，负责协调所有子模块
   * 
   * 功能特性：
   * - 统一管理所有页面的认证逻辑
   * - 协调 SessionManager、LoginModal 和 PostMessageHandler
   * - 提供公共 API 供页面调用
   * - 实现快速认证检查（100ms 内完成）
   * - 支持开发模式（绕过认证）
   * - 完整的日志记录功能
   * 
   * 验证需求：1.1, 1.2, 1.3, 1.4, 1.5, 6.2, 6.3, 6.4, 6.5, 6.6, 7.5, 10.1, 10.2
   */
  class AuthManager {
    /**
     * 构造函数
     * @param {Object} config - 配置对象（可选），将与默认配置合并
     */
    constructor(config = {}) {
      // 合并配置
      this.config = {
        ...DEFAULT_CONFIG,
        ...config,
        modalConfig: {
          ...DEFAULT_CONFIG.modalConfig,
          ...(config.modalConfig || {})
        },
        dev: {
          ...DEFAULT_CONFIG.dev,
          ...(config.dev || {})
        }
      };
      
      // 初始化子模块
      this.sessionManager = new SessionManager(this.config);
      this.loginModal = null;
      this.postMessageHandler = null;
      this.isInitialized = false;
      
      // 初始化
      this.init();
    }
    
    /**
     * 初始化认证管理器
     * 
     * 设置 postMessage 处理器并注册回调函数
     * 
     * 验证需求：3.1, 3.3, 3.4, 7.1
     */
    init() {
      if (this.isInitialized) {
        console.warn('[AuthManager] Already initialized');
        return;
      }
      
      // 初始化 postMessage 处理器
      this.postMessageHandler = new PostMessageHandler(this.config);
      this.postMessageHandler.onLoginSuccess(this.handleLoginSuccess.bind(this));
      this.postMessageHandler.onLoginFailure(this.handleLoginFailure.bind(this));
      this.postMessageHandler.onLoginClosed(this.handleLoginClosed.bind(this));
      this.postMessageHandler.startListening();
      
      this.isInitialized = true;
      this.log('info', 'AuthManager initialized', {
        loginServiceUrl: this.config.loginServiceUrl,
        sessionTimeout: this.config.sessionTimeout,
        enableDevMode: this.config.enableDevMode
      });
    }
    
    /**
     * 从 NSTL API 获取用户详细信息
     *
     * 调用 NSTL 登录验证 API 获取当前登录用户的详细信息，包括 userId、username 等。
     *
     * 注意：NSTL 请求走独立代理路径，使用完整 URL
     *
     * @returns {Promise<Object|null>} 用户信息对象或 null（如果未登录或获取失败）
     */
    async fetchUserInfo() {
      try {
        const timestamp = Math.random();
        // 从配置文件读取 NSTL API 前缀
        // 默认为空字符串，表示使用当前域名（通过代理访问）
        let nstlApiPrefix = '';
        if (typeof ClaimConsistencyConfig !== 'undefined' && typeof ClaimConsistencyConfig.getNstlApiPrefix === 'function') {
          nstlApiPrefix = ClaimConsistencyConfig.getNstlApiPrefix();
        } else if (typeof ClaimConsistencyConfig !== 'undefined' && ClaimConsistencyConfig.NSTL_API_PREFIX !== undefined) {
          nstlApiPrefix = ClaimConsistencyConfig.NSTL_API_PREFIX;
        }

        const url = `https://www.nstl.gov.cn/api/service/nstl/web/vilidate/isLogin?${timestamp}`;

        this.log('debug', `调用 NSTL API: ${url}`);

        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
          },
          credentials: 'include', // 必须使用 include 来携带 Cookie
          mode: 'cors'
        });

        if (!response.ok) {
          this.log('error', `NSTL API 返回错误: ${response.status}`);
          return null;
        }

        const result = await response.json();

        // code === 0 表示已登录
        if (result && result.code === 0 && result.data) {
          // 尝试多个可能的字段名
          return {
            userId: result.data.userId || result.data.id || result.data.user_id || 'unknown',
            username: result.data.userName || result.data.username || result.data.name || 'unknown',
            email: result.data.email || ''
          };
        }

        this.log('warn', 'NSTL API 返回非登录状态', result);
        return null;
      } catch (error) {
        // 网络/CORS 错误时抛出，让调用方区分"API 不可达"和"未登录"
        this.log('error', '获取用户信息失败（网络错误）', error);
        throw error;
      }
    }

    /**
     * 检查用户认证状态
     *
     * 性能要求：必须在 100ms 内完成检查
     *
     * ✅ 新增: 主动同步主系统登录状态
     *
     * 检查流程：
     * 1. 如果开发模式启用且 bypassAuth 为 true，直接返回 true
     * 2. 调用 SessionManager 验证会话有效性
     * 3. ✅ 新增: 主动调用 NSTL API 验证主系统登录状态
     * 4. 如果主系统已退出登录，清除本地会话
     * 5. 如果 NSTL API 不可达（网络错误），信任本地会话
     * 6. 如果本地会话无效，尝试从 NSTL 获取用户信息
     * 7. 记录检查耗时
     * 8. 处理会话错误（过期、无效令牌等）
     *
     * 验证需求：1.1, 1.4, 7.1, 7.2, 7.3, 10.1, 10.2
     *
     * @returns {Promise<boolean>} 用户是否已认证
     */
    async checkAuth() {
      const startTime = performance.now();

      try {
        // 开发模式绕过认证（需求 10.2）
        if (this.config.enableDevMode && this.config.dev?.bypassAuth) {
          this.log('debug', 'Dev mode: bypassing auth');
          return true;
        }

        // 1. 检查本地会话是否有效
        const session = this.sessionManager.getSession();

        if (session && !this.sessionManager.isSessionExpired(session)) {
          // 会话存在且未过期
          const userId = session.user?.userId;

          // ✅ 主动验证主系统登录状态
          this.log('info', '本地会话有效，验证主系统登录状态');
          let userInfo;
          try {
            userInfo = await this.fetchUserInfo();
          } catch (networkError) {
            // NSTL API 不可达（网络/CORS 错误），信任本地会话
            this.log('warn', '无法连接主系统验证登录状态，信任本地会话');
            if (userId &&
                userId !== 'mock_user_id' &&
                userId !== 'unknown' &&
                !userId.startsWith('nstl_user_')) {
              return true;
            }
            // 即使是临时 userId，有会话就信任
            return true;
          }

          if (!userInfo || userInfo.userId === 'unknown') {
            // 主系统已退出登录，清除本地会话
            this.log('warn', '主系统已退出登录，清除本地会话');
            this.sessionManager.clearSession();
            this.handleMainSystemLogout();
            return false;
          }

          // 主系统仍在登录状态
          // 如果会话中已有真实的 userId，直接返回
          if (userId &&
              userId !== 'mock_user_id' &&
              userId !== 'unknown' &&
              !userId.startsWith('nstl_user_')) {
            this.log('info', '会话有效，用户已登录', { userId });
            return true;
          }

          // 如果会话中的 userId 是临时值，更新用户信息
          this.log('info', '会话有效但 userId 为临时值，更新用户信息');

          // 更新会话中的用户信息
          this.sessionManager.createSession({
            userId: userInfo.userId,
            username: userInfo.username,
            email: userInfo.email,
            sessionToken: session.session.token,
            nonce: session.session.nonce,
            loginTime: session.session.loginTime
          });

          this.log('info', '用户信息已更新', { userId: userInfo.userId });
          return true;
        }

        // 2. 本地会话无效或已过期，尝试从 NSTL 获取用户信息
        this.log('info', '本地会话无效，尝试从 NSTL 获取用户信息');
        let userInfo;
        try {
          userInfo = await this.fetchUserInfo();
        } catch (networkError) {
          // NSTL API 不可达且无本地会话，返回 false
          this.log('warn', '无法连接主系统且无有效本地会话');
          return false;
        }

        if (userInfo && userInfo.userId !== 'unknown') {
          // 创建新会话
          this.sessionManager.createSession({
            userId: userInfo.userId,
            username: userInfo.username,
            email: userInfo.email,
            sessionToken: this.generateNonce(),
            nonce: this.generateNonce(),
            loginTime: Date.now()
          });

          this.log('info', '用户已登录，会话已创建', { userId: userInfo.userId });

          // 记录性能
          const elapsed = performance.now() - startTime;
          if (elapsed > 100) {
            this.log('warn', `Auth check exceeded 100ms threshold: ${elapsed.toFixed(2)}ms`);
          }

          return true;
        }

        // 3. 未登录
        this.log('info', '用户未登录');
        return false;
      } catch (error) {
        this.log('error', 'Auth check failed', error);

        // 显示错误提示（需求 7.1）
        this.showMessage('认证检查失败，请刷新页面重试', 'error');

        return false;
      }
    }
    
    /**
     * 显示登录模态窗口
     * 
     * 如果模态窗口已经显示，则不重复创建
     * 
     * 验证需求：1.2, 2.1, 2.2, 2.4, 6.3
     */
    showLoginModal() {
      if (this.loginModal && this.loginModal.isVisible()) {
        this.log('debug', 'Login modal already visible');
        return;
      }
      
      // 创建登录模态窗口
      this.loginModal = new LoginModal(this.config.modalConfig);
      
      // 注册关闭回调
      this.loginModal.onClose(() => this.handleLoginClosed());
      
      // 注册超时回调
      this.loginModal.onTimeout(() => this.handleLoginTimeout());
      
      // 显示模态窗口
      this.loginModal.show();
      
      this.log('info', 'Login modal displayed');
    }
    
    /**
     * 隐藏登录模态窗口
     * 
     * 验证需求：1.3, 2.5, 6.4
     */
    hideLoginModal() {
      if (this.loginModal) {
        this.loginModal.hide();
        this.loginModal = null;
        this.log('info', 'Login modal hidden');
      }
    }
    
    /**
     * 获取当前用户信息
     * 
     * 从会话中读取用户信息，如果会话不存在或无效则返回 null
     * 
     * 验证需求：6.5
     * 
     * @returns {Object|null} 用户信息对象，包含 userId、username、email 等字段
     */
    getUserInfo() {
      const session = this.sessionManager.getSession();
      return session ? session.user : null;
    }

    /**
     * 获取用于页面展示的当前账号信息。
     *
     * 优先使用认证会话中的真实用户；如果会话暂不可用，则回退到最近任务的用户标识、
     * 登录配置或默认 NSTL 用户，保证统一页头始终有明确的账号提示。
     *
     * @returns {{userId: string, username: string, email: string, isFallback: boolean}}
     */
    getDisplayUserInfo() {
      const invalidValues = new Set(['', 'unknown', 'default', 'mock_user_id']);
      const normalize = (value) => String(value || '').trim();
      const isUsable = (value) => !invalidValues.has(normalize(value));

      const sessionUser = this.getUserInfo();
      if (sessionUser) {
        const userId = normalize(sessionUser.userId || sessionUser.id || sessionUser.uid);
        const username = normalize(sessionUser.username || sessionUser.userName || sessionUser.name);
        const email = normalize(sessionUser.email);

        if (isUsable(username) || isUsable(userId) || email) {
          return {
            userId: isUsable(userId) ? userId : (isUsable(username) ? username : email),
            username: isUsable(username) ? username : (isUsable(userId) ? userId : email),
            email,
            isFallback: false
          };
        }
      }

      let storedUserScope = '';
      try {
        storedUserScope =
          normalize(localStorage.getItem('claim_consistency_pending_user_scope')) ||
          normalize(sessionStorage.getItem('user_scope'));
      } catch (error) {
        this.log('warn', '读取本地降级账号信息失败', { error: error?.message || String(error) });
      }

      const mockUser = this.config.dev?.mockUser || {};
      const configuredUser =
        normalize(this.config.virtualLogin?.username) ||
        normalize(mockUser.username || mockUser.userId);
      const fallbackName = isUsable(storedUserScope)
        ? storedUserScope
        : (isUsable(configuredUser) ? configuredUser : 'NSTL用户');

      return {
        userId: isUsable(storedUserScope)
          ? storedUserScope
          : (isUsable(configuredUser) ? configuredUser : 'nstl_user'),
        username: fallbackName,
        email: '',
        isFallback: true
      };
    }
    
    /**
     * 用户登出
     * 
     * 清除会话数据并重新显示登录窗口
     * 
     * 验证需求：6.6, 7.5
     */
    logout() {
      const userInfo = this.getUserInfo();
      
      // 清除会话
      this.sessionManager.clearSession();
      
      // 隐藏登录窗口（如果存在）
      this.hideLoginModal();
      
      this.log('info', 'User logged out', { userId: userInfo?.userId });
      
      // 触发登出事件
      const event = new CustomEvent('authLogout', {
        detail: { message: 'User logged out locally' }
      });
      window.dispatchEvent(event);
      
      // 重新显示登录窗口
      this.showLoginModal();
    }
    
    /**
     * ✅ 新增: 处理主系统登出
     * 
     * 当检测到主系统退出登录时,通知页面并显示提示
     */
    handleMainSystemLogout() {
      this.log('info', 'Handling main system logout');
      
      // 触发登出事件
      const event = new CustomEvent('authLogout', {
        detail: { message: 'Main system logout detected' }
      });
      window.dispatchEvent(event);
      
      // 显示提示信息
//      this.showMessage('您已在主系统退出登录,请重新登录', 'warning');
      
      // 如果当前不是首页,跳转到首页
      const currentPage = window.location.pathname.split('/').pop();
      if (currentPage !== 'index.html') {
        setTimeout(() => {
          window.location.href = 'index.html?show_login=1';
        }, 2000);
      } else {
        // 如果是首页,显示登录窗口
        setTimeout(() => {
          this.showLoginModal();
        }, 1000);
      }
    }
    
    /**
     * 检查用户是否已认证
     * 
     * 这是 checkAuth() 的同步版本，仅检查会话有效性
     * 
     * 验证需求：6.2
     * 
     * @returns {boolean} 用户是否已认证
     */
    isAuthenticated() {
      return this.sessionManager.validateSession();
    }
    
    /**
     * 处理登录成功事件
     *
     * 当接收到 NSTL 登录服务的 loginSuccess 消息时调用
     *
     * 处理流程：
     * 1. 调用 NSTL API 获取真实用户信息
     * 2. 如果获取成功，使用真实用户信息创建会话
     * 3. 如果获取失败，使用降级方案（postMessage 数据或临时会话）
     * 4. 隐藏登录模态窗口
     * 5. 触发页面内容加载
     *
     * 验证需求：3.3, 3.6, 4.1, 4.2, 5.5, 8.3
     *
     * @param {Object} data - 登录成功返回的用户数据
     * @param {string} data.userId - 用户 ID
     * @param {string} data.username - 用户名
     * @param {string} [data.email] - 邮箱（可选）
     * @param {string} data.token - 会话令牌
     */
    async handleLoginSuccess(data) {
      try {
        this.log('info', '登录成功，正在获取用户信息...');

        // 尝试从 NSTL API 获取真实的用户信息
        let userInfo;
        try {
          userInfo = await this.fetchUserInfo();
        } catch (networkError) {
          // NSTL API 不可达，走降级方案
          this.log('warn', '获取用户信息失败（网络错误），使用降级方案');
          userInfo = null;
        }

        let sessionData;

        if (userInfo && userInfo.userId !== 'unknown') {
          // 使用真实的用户信息
          sessionData = {
            userId: userInfo.userId,
            username: userInfo.username,
            email: userInfo.email,
            sessionToken: data.token || this.generateNonce(),
            nonce: this.generateNonce(),
            loginTime: Date.now()
          };

          this.log('info', '会话已创建，用户 ID', { userId: userInfo.userId });
        } else {
          // 降级方案：使用 postMessage 传递的数据或创建临时会话
          this.log('warn', '获取用户信息失败，使用降级方案');

          if (data && data.message === 'SUCCESS') {
            // 尝试从 iframe 提取用户信息
            const extractedInfo = this.extractUserInfoFromIframe();

            if (extractedInfo) {
              sessionData = extractedInfo;
            } else {
              // 创建临时会话
              sessionData = {
                userId: 'nstl_user_' + Date.now(),
                username: 'NSTL用户',
                email: '',
                sessionToken: this.generateNonce(),
                nonce: this.generateNonce(),
                loginTime: Date.now(),
                isTemporary: true
              };
            }
          } else if (data && data.userId) {
            // 使用 postMessage 传递的标准格式数据
            sessionData = {
              userId: data.userId,
              username: data.username,
              email: data.email,
              sessionToken: data.token,
              nonce: this.generateNonce(),
              loginTime: Date.now()
            };
          } else {
            throw new Error('Invalid login data format');
          }
        }

        // 创建会话（需求 3.3）
        this.sessionManager.createSession(sessionData);

        // 隐藏登录模态窗口
        this.hideLoginModal();

        this.log('info', 'Login successful', {
          userId: sessionData.userId,
          username: sessionData.username,
          isTemporary: sessionData.isTemporary || false
        });

        // 触发页面内容加载（需求 3.6, 5.5）
        this.triggerPageLoad();
      } catch (error) {
        this.log('error', 'Failed to handle login success', error);
        this.showMessage('登录处理失败，请重试', 'error');
      }
    }
    
    /**
     * 从iframe的URL中提取用户信息
     * 
     * NSTL登录成功后，用户信息可能在iframe的URL参数中
     * 
     * @returns {Object|null} 用户信息对象，如果提取失败则返回null
     */
    extractUserInfoFromIframe() {
      try {
        if (!this.loginModal || !this.loginModal.iframe) {
          return null;
        }
        
        // 尝试访问iframe的contentWindow（可能因跨域限制失败）
        const iframe = this.loginModal.iframe;
        let iframeUrl = null;
        
        try {
          // 尝试获取iframe的URL
          iframeUrl = iframe.contentWindow.location.href;
        } catch (e) {
          // 跨域限制，无法访问iframe的URL
          this.log('warn', 'Cannot access iframe URL due to CORS', e);
          return null;
        }
        
        if (!iframeUrl) {
          return null;
        }
        
        // 解析URL参数
        const url = new URL(iframeUrl);
        const params = new URLSearchParams(url.search);
        
        // 尝试提取常见的用户信息参数
        const userId = params.get('userId') || params.get('uid') || params.get('user_id');
        const username = params.get('username') || params.get('name') || params.get('user_name');
        const email = params.get('email') || params.get('mail');
        const token = params.get('token') || params.get('sessionToken') || params.get('session_token');
        
        if (userId || username) {
          return {
            userId: userId || 'nstl_user_' + Date.now(),
            username: username || 'NSTL用户',
            email: email || '',
            sessionToken: token || this.generateNonce(),
            nonce: this.generateNonce(),
            loginTime: Date.now()
          };
        }
        
        return null;
      } catch (error) {
        this.log('error', 'Failed to extract user info from iframe', error);
        return null;
      }
    }
    
    /**
     * 处理登录失败事件
     * 
     * 当 NSTL 登录服务返回登录失败消息时调用
     * 
     * 验证需求：7.1
     * 
     * @param {Object} error - 错误信息对象
     * @param {string} error.code - 错误代码
     * @param {string} error.message - 错误消息
     */
    handleLoginFailure(error) {
      this.log('error', 'Login failed', error);
      
      // 根据错误代码显示不同的提示
      let message = '登录失败，请重试';
      
      if (error) {
        switch (error.code) {
          case 'INVALID_CREDENTIALS':
            message = '用户名或密码错误';
            break;
          case 'ACCOUNT_LOCKED':
            message = '账户已被锁定，请联系管理员';
            break;
          case 'NETWORK_ERROR':
            message = '网络连接失败，请检查网络';
            break;
          case 'SERVICE_UNAVAILABLE':
            message = '登录服务暂时不可用，请稍后再试';
            break;
          default:
            message = error.message || '登录失败，请重试';
        }
      }
      
      // 显示错误提示（需求 7.1）
      this.showMessage(message, 'error');
    }
    
    /**
     * 处理登录关闭事件
     * 
     * 当用户关闭登录窗口时调用
     * 
     * 验证需求：3.4, 7.3
     */
    handleLoginClosed() {
      this.hideLoginModal();
      this.log('info', 'Login cancelled by user');
      
      // ✅ 新增: 触发登录关闭事件,通知页面
      const event = new CustomEvent('authLoginClosed', {
        detail: { message: 'Login modal closed by user' }
      });
      window.dispatchEvent(event);
    }
    
    /**
     * 处理登录超时事件
     * 
     * 当登录操作超过 5 分钟无响应时调用
     * 
     * 验证需求：7.2
     */
    handleLoginTimeout() {
      this.log('warn', 'Login timeout after 5 minutes');
      
      // 显示超时提示（需求 7.2）
      this.showMessage('登录超时，请重新尝试', 'error');
      
      // 允许用户重试
      setTimeout(() => {
        this.showLoginModal();
      }, 1000);
    }
    
    /**
     * 触发页面内容加载
     * 
     * 通过自定义事件通知页面可以加载内容
     * 
     * 验证需求：5.5
     */
    triggerPageLoad() {
      // 触发自定义事件
      const event = new CustomEvent('authSuccess', {
        detail: { userInfo: this.getUserInfo() }
      });
      window.dispatchEvent(event);
      
      this.log('debug', 'Page load triggered');
    }
    
    /**
     * 生成随机 nonce 值
     * 
     * 使用 Web Crypto API 生成 16 字节的随机数，
     * 转换为十六进制字符串
     * 
     * 验证需求：8.3
     * 
     * @returns {string} 32 字符的十六进制字符串
     */
    generateNonce() {
      return Array.from(crypto.getRandomValues(new Uint8Array(16)))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
    }
    
    /**
     * 显示消息提示
     * 
     * 在页面上显示临时消息提示（3 秒后自动消失）
     * 
     * @param {string} message - 消息内容
     * @param {string} type - 消息类型：'info' | 'warning' | 'error' | 'success'
     */
    showMessage(message, type = 'info') {
      // 创建消息元素
      const messageEl = document.createElement('div');
      messageEl.className = `auth-message auth-message-${type}`;
      messageEl.textContent = message;
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
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        animation: slideDown 0.3s ease-out;
      `;
      
      // 根据类型设置颜色
      const colors = {
        info: { bg: '#3b82f6', text: '#ffffff' },
        warning: { bg: '#f59e0b', text: '#ffffff' },
        error: { bg: '#ef4444', text: '#ffffff' },
        success: { bg: '#10b981', text: '#ffffff' }
      };
      
      const color = colors[type] || colors.info;
      messageEl.style.backgroundColor = color.bg;
      messageEl.style.color = color.text;
      
      document.body.appendChild(messageEl);
      
      // 3 秒后移除
      setTimeout(() => {
        messageEl.style.animation = 'slideUp 0.3s ease-out';
        setTimeout(() => {
          messageEl.remove();
        }, 300);
      }, 3000);
    }
    
    /**
     * 记录日志
     * 
     * 根据日志级别和配置决定是否输出日志
     * 
     * 验证需求：7.5
     * 
     * @param {string} level - 日志级别：'debug' | 'info' | 'warn' | 'error'
     * @param {string} message - 日志消息
     * @param {*} details - 详细信息（可选）
     */
    log(level, message, details = null) {
      const logEntry = {
        timestamp: Date.now(),
        level,
        action: message,
        details,
        userId: this.getUserInfo()?.userId
      };
      
      // 根据级别输出日志
      if (level === 'error') {
        console.error('[AuthManager]', message, details);
      } else if (level === 'warn') {
        console.warn('[AuthManager]', message, details);
      } else if (level === 'debug' && this.config.enableDevMode) {
        console.debug('[AuthManager]', message, details);
      } else if (level === 'info') {
        console.log('[AuthManager]', message, details);
      }
    }
  }
  
  // 导出到全局
  window.AuthManager = AuthManager;
  window.DEFAULT_AUTH_CONFIG = DEFAULT_CONFIG;
  
})(window);
