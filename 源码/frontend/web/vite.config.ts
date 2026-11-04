import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'

const localNstlHost = 'www.nstl.gov.cn'
const localCertPath = path.resolve(__dirname, `certs/${localNstlHost}.pfx`)
const localHttps = fs.existsSync(localCertPath)
  ? {
      pfx: fs.readFileSync(localCertPath),
      passphrase: 'goodidea-local',
    }
  : undefined

export default defineConfig(({ mode }) => {
  const useNstlLocalHost = mode === 'nstl-local'
  const backendTarget = process.env.VITE_PROXY_BACKEND || 'http://127.0.0.1:17608'
  const frontendBase = normalizeBasePath(
    process.env.VITE_FRONTEND_BASE || '/ai/agent/claim_consistency/',
  )

  return {
    base: frontendBase,
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 18094,
      strictPort: true,
      https: useNstlLocalHost ? localHttps : undefined,
      allowedHosts: useNstlLocalHost ? [localNstlHost] : ['www.nstl.gov.cn', 'localhost', '127.0.0.1'],
      hmr: useNstlLocalHost
        ? {
            host: localNstlHost,
          }
        : undefined,
      proxy: {
        '/api/service/nstl/web/user-feedback/submit': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/api/service/nstl/web/': {
          target: 'https://127.0.0.1',
          changeOrigin: true,
          secure: false,
          configure: (proxy) => {
            proxy.on('proxyReq', (proxyReq) => {
              proxyReq.setHeader('Host', 'www.nstl.gov.cn')
            })
          },
        },
        '/v1': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/system': {
          target: backendTarget,
          changeOrigin: true,
        },
      },
    },
  }
})

function normalizeBasePath(path: string): string {
  let normalized = path.trim() || '/'
  if (!normalized.startsWith('/')) {
    normalized = `/${normalized}`
  }
  if (!normalized.endsWith('/')) {
    normalized = `${normalized}/`
  }
  return normalized
}
