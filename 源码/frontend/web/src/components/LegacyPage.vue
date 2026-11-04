<script setup lang="ts">
import DOMPurify from 'dompurify'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

type LegacyPageName = 'index' | 'task_detail' | 'history'

const props = defineProps<{
  page: LegacyPageName
}>()

const route = useRoute()
const router = useRouter()
const hostRef = ref<HTMLElement | null>(null)
const loading = ref(true)
const error = ref('')

const loadedScripts = new Set<string>()
const legacyBase = `${import.meta.env.BASE_URL}legacy/`.replace(/\/+/g, '/')
let cleanupNodes: HTMLElement[] = []

// Legacy pages are static files, so expose the sanitizer before their inline scripts run.
;(window as typeof window & { DOMPurify?: typeof DOMPurify }).DOMPurify = DOMPurify

onMounted(loadLegacyPage)
watch(
  () => [props.page, route.fullPath],
  () => {
    void loadLegacyPage()
  },
)

onBeforeUnmount(() => {
  cleanupLegacyDom()
})

async function loadLegacyPage() {
  loading.value = true
  error.value = ''
  cleanupLegacyDom()
  try {
    installLegacyNavigation()
    installLegacySearch()
    installLegacyDomReady()
    const html = await fetchLegacyHtml()
    const documentSnapshot = new DOMParser().parseFromString(html, 'text/html')
    injectLegacyStyles(documentSnapshot)
    injectLegacyBody(documentSnapshot)
    await runLegacyScripts(documentSnapshot)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function fetchLegacyHtml(): Promise<string> {
  const htmlFile = props.page === 'index' ? 'index.html' : `${props.page}.html`
  const response = await fetch(`${legacyBase}${htmlFile}`, { cache: 'no-cache' })
  if (!response.ok) {
    throw new Error(`旧页面加载失败: ${htmlFile}`)
  }
  return response.text()
}

function injectLegacyStyles(snapshot: Document) {
  const styleSources = [
    ...Array.from(snapshot.querySelectorAll<HTMLLinkElement>('link[rel="stylesheet"]')),
    ...Array.from(snapshot.querySelectorAll<HTMLLinkElement>('link[rel="icon"]')),
  ]
  for (const link of styleSources) {
    const href = link.getAttribute('href')
    if (!href) continue
    const cloned = document.createElement('link')
    cloned.rel = link.rel
    cloned.href = resolveLegacyUrl(href)
    cloned.setAttribute('data-legacy-page', props.page)
    document.head.appendChild(cloned)
    cleanupNodes.push(cloned)
  }

  for (const style of Array.from(snapshot.querySelectorAll('style'))) {
    const cloned = document.createElement('style')
    cloned.textContent = rewriteLegacyAssetReferences(style.textContent || '')
    cloned.setAttribute('data-legacy-page', props.page)
    document.head.appendChild(cloned)
    cleanupNodes.push(cloned)
  }
}

function injectLegacyBody(snapshot: Document) {
  const body = snapshot.body.cloneNode(true) as HTMLElement
  body.querySelectorAll('script, style').forEach((node) => node.remove())
  body.querySelectorAll<HTMLElement>('#app').forEach((node) => {
    node.id = legacyMountId()
  })
  rewriteElementAssets(body)

  const host = hostRef.value
  if (!host) return
  host.innerHTML = ''
  while (body.firstChild) {
    host.appendChild(body.firstChild)
  }
}

async function runLegacyScripts(snapshot: Document) {
  const scripts = Array.from(snapshot.querySelectorAll<HTMLScriptElement>('script'))
  for (const script of scripts) {
    const src = script.getAttribute('src')
    if (src) {
      await loadScript(resolveLegacyUrl(src))
    } else if (script.textContent?.trim()) {
      runInlineScript(script.textContent)
      await nextTick()
    }
  }
}

function runInlineScript(source: string) {
  const transformed = transformLegacyScript(source)
  const script = document.createElement('script')
  script.textContent = `(function(){\n${transformed}\n})();`
  document.body.appendChild(script)
  script.remove()
}

function transformLegacyScript(source: string): string {
  return rewriteLegacyAssetReferences(source)
    .replace(
      /const\s*\{\s*createApp\s*\}\s*=\s*Vue\s*;/,
      `const { createApp: __legacyVueCreateApp } = Vue;
const createApp = (...args) => {
  const app = __legacyVueCreateApp(...args);
  const originalMount = app.mount.bind(app);
  app.mount = (...mountArgs) => {
    const proxy = originalMount(...mountArgs);
    window.__legacyVueApp = app;
    window.__legacyMountedProxy = proxy;
    return proxy;
  };
  window.__legacyVueApp = app;
  return app;
};`,
    )
    .replace(/mount\((['"])#app\1\)/g, `mount('#${legacyMountId()}')`)
    .replace(/new URLSearchParams\(window\.location\.search\)/g, 'new URLSearchParams(window.__legacySearch || window.location.search)')
    .replace(/document\.addEventListener\(\s*(['"])DOMContentLoaded\1\s*,/g, 'window.__legacyOnReady(')
    .replace(/window\.location\.href\s*=\s*([^;]+);/g, 'window.__legacySetLocation($1);')
    .replace(/window\.open\(/g, 'window.__legacyOpen(')
}

async function loadScript(src: string) {
  if (loadedScripts.has(src) || document.querySelector(`script[data-legacy-src="${cssEscape(src)}"]`)) {
    loadedScripts.add(src)
    return
  }
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = src
    script.async = false
    script.setAttribute('data-legacy-src', src)
    script.onload = () => {
      loadedScripts.add(src)
      resolve()
    }
    script.onerror = () => reject(new Error(`脚本加载失败: ${src}`))
    document.body.appendChild(script)
  })
}

function installLegacyNavigation() {
  ;(window as any).__claimConsistencyLegacyBase = legacyBase
  ;(window as any).__legacySetLocation = (target: unknown) => {
    const mapped = mapLegacyNavigation(String(target || ''))
    if (mapped.external) {
      window.location.href = mapped.url
      return
    }
    void router.push(mapped.url)
  }
  ;(window as any).__legacyOpen = (target: unknown, targetName = '_blank', features?: string) => {
    const mapped = mapLegacyNavigation(String(target || ''))
    if (mapped.external) {
      window.open(mapped.url, targetName, features)
      return
    }
    void router.push(mapped.url)
  }
}

function installLegacySearch() {
  if (props.page !== 'task_detail') {
    ;(window as any).__legacySearch = window.location.search
    return
  }
  const params = new URLSearchParams(window.location.search)
  if (!params.get('task_id') && route.params.taskId) {
    params.set('task_id', String(route.params.taskId))
  }
  ;(window as any).__legacySearch = `?${params.toString()}`
}

function installLegacyDomReady() {
  ;(window as any).__legacyOnReady = (handler: (event: Event) => unknown) => {
    const runHandler = () => {
      try {
        const result = handler(new Event('DOMContentLoaded'))
        if (result && typeof (result as Promise<unknown>).catch === 'function') {
          ;(result as Promise<unknown>).catch((err) => {
            console.error('[LegacyPage] DOMContentLoaded handler failed', err)
          })
        }
      } catch (err) {
        console.error('[LegacyPage] DOMContentLoaded handler failed', err)
      }
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', runHandler, { once: true })
      return
    }
    queueMicrotask(runHandler)
  }
}

function mapLegacyNavigation(rawUrl: string): { external: boolean; url: string } {
  const trimmed = rawUrl.trim()
  if (!trimmed) return { external: false, url: router.resolve({ name: 'home' }).fullPath }
  if (/^(https?:)?\/\//i.test(trimmed)) {
    return { external: true, url: trimmed }
  }

  const url = new URL(trimmed, `${window.location.origin}${import.meta.env.BASE_URL}`)
  const fileName = url.pathname.split('/').pop() || ''
  if (fileName === 'task_detail.html') {
    const taskId = url.searchParams.get('task_id') || url.searchParams.get('run_id') || url.searchParams.get('report') || ''
    const query: Record<string, string> = {}
    const threadId = url.searchParams.get('thread_id')
    if (threadId) query.thread_id = threadId
    return { external: false, url: router.resolve({ name: 'task-detail', params: { taskId }, query }).fullPath }
  }
  if (fileName === 'history.html') {
    return { external: false, url: router.resolve({ name: 'history' }).fullPath }
  }
  if (fileName === 'index.html' || fileName === '') {
    const query = Object.fromEntries(url.searchParams.entries())
    return { external: false, url: router.resolve({ name: 'home', query }).fullPath }
  }
  return { external: false, url: trimmed }
}

function rewriteElementAssets(root: HTMLElement) {
  root.querySelectorAll<HTMLElement>('[src], [href]').forEach((element) => {
    for (const attr of ['src', 'href']) {
      const value = element.getAttribute(attr)
      if (!value) continue
      element.setAttribute(attr, resolveLegacyUrl(value))
    }
  })
}

function rewriteLegacyAssetReferences(value: string): string {
  return value
    .replace(/(["'(])static\//g, `$1${legacyBase}static/`)
    .replace(/(["'(])\.\/report-data\.js/g, `$1${legacyBase}report-data.js`)
}

function resolveLegacyUrl(value: string): string {
  const trimmed = value.trim()
  if (!trimmed || /^(https?:)?\/\//i.test(trimmed) || /^(data:|mailto:|tel:|#)/i.test(trimmed)) {
    return trimmed
  }
  if (trimmed.startsWith('/')) {
    return trimmed
  }
  return `${legacyBase}${trimmed.replace(/^\.\//, '')}`
}

function legacyMountId(): string {
  return `legacy-app-${props.page}`
}

function cleanupLegacyDom() {
  const legacyAuthManager = (window as any).authManager
  const legacyApp = (window as any).__legacyVueApp
  const mountedProxy = (window as any).__legacyMountedProxy
  try {
    legacyAuthManager?.hideLoginModal?.()
    legacyAuthManager?.postMessageHandler?.stopListening?.()
    if (legacyApp?.unmount) {
      legacyApp.unmount()
    } else {
      mountedProxy?.$?.appContext?.app?.unmount?.()
    }
  } catch (err) {
    console.warn('[LegacyPage] legacy app unmount failed', err)
  }
  delete (window as any).__legacyVueApp
  delete (window as any).__legacyMountedProxy
  for (const node of cleanupNodes) {
    node.remove()
  }
  cleanupNodes = []
  if (hostRef.value) {
    hostRef.value.innerHTML = ''
  }
}

function cssEscape(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}
</script>

<template>
  <div class="legacy-page-shell">
    <div v-if="error" class="legacy-page-error">{{ error }}</div>
    <div ref="hostRef" class="legacy-page-host" :aria-busy="loading"></div>
  </div>
</template>
