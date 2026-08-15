// iCore 前端 Vite 配置
// Author: OneKeyJune <onekeyjune@gmail.com>

import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// 去掉打包产物 HTML 里 <script>/<link> 上的 crossorigin 属性。
// 原因：vite 默认给 module script / modulepreload 加 crossorigin，使同源资源
// 也走 CORS 模式；在用公网 IP + HTTP 直连后端时会触发浏览器的
// Private Network Access 检查，报 "target IP address space ... resource is in
// address space unknown" 并 ERR_FAILED，导致 JS 加载失败、白屏。
// 同源加载本不需要 crossorigin，去掉后即可正常加载。
function stripCrossorigin(): Plugin {
  return {
    name: 'strip-crossorigin',
    transformIndexHtml(html) {
      return html.replace(/\s+crossorigin\b/g, '')
    },
  }
}

export default defineConfig({
  plugins: [react(), stripCrossorigin()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    // 监听端口（避开 5173 默认值，减少与其他 Vite 项目冲突）
    port: 5180,
    // 端口被占时直接报错退出，不静默换端口（避免日志里的 url 与文档对不上）
    strictPort: true,
    headers: {
      'Cache-Control': 'no-store',
    },
    // 把 /api 与 SSE 流转发到 FastAPI 后端（默认 :8000）
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2020',
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          radix: [
            '@radix-ui/react-dialog',
            '@radix-ui/react-dropdown-menu',
            '@radix-ui/react-select',
            '@radix-ui/react-popover',
            '@radix-ui/react-tooltip',
            '@radix-ui/react-tabs',
            '@radix-ui/react-scroll-area',
            '@radix-ui/react-alert-dialog',
          ],
          table: ['@tanstack/react-table'],
        },
      },
    },
  },
})
