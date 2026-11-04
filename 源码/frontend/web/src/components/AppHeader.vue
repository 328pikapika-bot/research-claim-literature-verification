<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push({ name: 'home' })
}

function goHistory() {
  router.push({ name: 'history' })
}

</script>

<template>
  <header class="site-head">
    <div class="head-inner">
      <div class="head-brand-group">
        <a href="https://www.nstl.gov.cn/" class="brand">
          <div class="logo-wrapper">
            <img class="logo-icon" src="/static/images/logo.png" alt="NSTL Logo" />
          </div>
          <div class="logo-text-wrapper">
            <img class="logo-text" src="/static/images/logo-text.png" alt="国家科技图书文献中心" />
          </div>
        </a>
        <button class="product product-button" type="button" @click="goHome">
          <span class="product-name">创新服务助手</span>
          <img src="/static/images/icon-version-3.0.png" alt="V3.0版" />
        </button>
        <div class="mini-program-tip">
          <img class="mini-program-bg" src="/static/images/wxMini_in-BNULTIgP.png" alt="" />
          <div class="tip-badge">
            <span class="tip-text">小程序上线</span>
            <span class="tip-text-btn">欢迎体验</span>
          </div>
          <div class="qrcode-popup">
            <img src="/static/images/QRcode4-BSI3YE5n.png" alt="小程序二维码" />
          </div>
        </div>
      </div>
      <div class="head-actions">
        <button class="history-link button-link" type="button" @click="goHistory">
          <img src="/static/images/history.png" alt="" />
          任务列表
        </button>
      </div>
    </div>
  </header>
</template>
