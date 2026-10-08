import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  // GitHub Pages 双层部署（deploy-pages.yml）：site/ 静态官网发 gh-pages 根，SPA 发 gh-pages/app/。
  // 本地 dev 访问 http://localhost:5173/MARS-408/app/；官网 https://truefurina.github.io/MARS-408/（CTA 跳 app/）。
  base: '/MARS-408/app/',
  plugins: [
    vue(),
  ],
  server: {
    port: 5173,
    // 端口被占用时显式报错而非静默漂移，避免"打不开/页面不对"（配合 start 脚本先杀旧实例）
    strictPort: true,
    host: true,
    // C/C++ 实验室 WASI（SharedArrayBuffer）依赖跨源隔离；生产网关/反向代理也必须保留这两个头
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    proxy: {
      '/api': { target: 'http://127.0.0.1:8002', changeOrigin: true },
      '/plots': { target: 'http://127.0.0.1:8002', changeOrigin: true },
      '/media': { target: 'http://127.0.0.1:8002', changeOrigin: true },
    },
  },
  preview: {
    port: 5173,
    strictPort: true,
    host: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8002', changeOrigin: true },
      '/plots': { target: 'http://127.0.0.1:8002', changeOrigin: true },
      '/media': { target: 'http://127.0.0.1:8002', changeOrigin: true },
    },
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  build: {
    target: 'es2020',
    cssCodeSplit: true,
    cssMinify: 'lightningcss',
    sourcemap: false,
    chunkSizeWarningLimit: 500,
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/vue') || id.includes('node_modules/pinia') || id.includes('node_modules/vue-router') || id.includes('node_modules/@vue')) {
            return 'vue-vendor'
          }
          if (id.includes('node_modules/katex')) {
            return 'katex'
          }
          if (id.includes('node_modules/highlight')) {
            return 'highlight'
          }
          if (id.includes('node_modules/marked')) {
            return 'marked'
          }
        },
      },
    },
  },
})
