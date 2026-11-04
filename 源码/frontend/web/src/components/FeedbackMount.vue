<template>
  <div aria-hidden="true"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

import '../styles/feedback.css'

const scriptId = 'claim-consistency-feedback-script'

onMounted(() => {
  if (document.getElementById(scriptId)) {
    return
  }

  const script = document.createElement('script')
  script.id = scriptId
  script.src = `${import.meta.env.BASE_URL}static/js/feedback.js`
  script.async = true
  document.body.appendChild(script)
})

onBeforeUnmount(() => {
  document.body.classList.remove('dialog-open')
})
</script>
