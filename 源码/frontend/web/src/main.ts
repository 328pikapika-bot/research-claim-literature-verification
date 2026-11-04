import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createAuthManager } from './services/nstlAuth'
import './styles/main.css'

createAuthManager({
  loginServiceUrl: 'https://login.nstl.gov.cn',
  userInfoEndpoint: '/api/service/nstl/web/vilidate/isLogin',
  sessionTimeout: 24 * 60 * 60 * 1000,
  storageKey: 'cca_user_session',
  trustedOrigins: ['https://login.nstl.gov.cn', 'https://www.nstl.gov.cn'],
})

createApp(App).use(router).mount('#app')
