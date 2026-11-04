/**
 * 一致性评估智能体 - 公共配置
 *
 * 统一管理 API 地址等配置项
 * 所有 HTML 页面和 JS 文件应引用此配置文件
 */

const ClaimConsistencyConfig = {
  // API 基础地址
  DEFAULT_API_BASE: "",

  // NSTL API 前缀（用于认证等接口，本地测试环境通过 hosts 解析到 127.0.0.1）
  NSTL_API_PREFIX: "",

  // 获取当前 API 基础地址
  // 优先级: 默认值 > URL参数 > localStorage
  getApiBase() {
    if (this.DEFAULT_API_BASE) {
      return this.DEFAULT_API_BASE;
    }
    const params = new URLSearchParams(window.location.search);
    const urlApiBase = params.get("api_base");
    if (urlApiBase) {
      return urlApiBase + this.NSTL_API_PREFIX;
    }
    return localStorage.getItem("claim_consistency_api_base") || "" + this.NSTL_API_PREFIX;
  },

  // 获取 NSTL API 前缀
  getNstlApiPrefix() {
    return this.NSTL_API_PREFIX;
  },

  // 设置 API 基础地址
  setApiBase(base) {
    if (base) {
      localStorage.setItem("claim_consistency_api_base", base);
    }
  },

  // LocalStorage 键名常量
  STORAGE_KEYS: {
    API_BASE: "claim_consistency_api_base",
    THREAD_ID: "claim_consistency_thread_id",
    RUN_ID: "claim_consistency_run_id",
    TASK_HISTORY: "claim_consistency_task_history",
    PENDING_API_BASE: "claim_consistency_pending_api_base"
  }
};

// 兼容旧代码
const DEFAULT_API_BASE = ClaimConsistencyConfig.DEFAULT_API_BASE;
