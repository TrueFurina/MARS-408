import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 部署专用配置：强制 base='/'，避免本机环境把 base 解析成 Git 安装路径。
// 云部署前端与后端同源，资源必须从根路径加载。
// 产物目录命名为 site/（而非 dist/）：发布通道上传时会排除名为 "dist" 的
// "build output"，改名后前端产物不会被误剔除，可随包上传。
export default defineConfig({
  base: '/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    target: 'es2020',
    cssCodeSplit: true,
    sourcemap: false,
    emptyOutDir: true,
    outDir: 'deploy/career-pilot/site',
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/vue') || id.includes('node_modules/pinia') || id.includes('node_modules/vue-router') || id.includes('node_modules/@vue')) {
            return 'vue-vendor'
          }
          if (id.includes('node_modules/katex')) return 'katex'
          if (id.includes('node_modules/highlight')) return 'highlight'
          if (id.includes('node_modules/marked')) return 'marked'
        },
      },
    },
  },
})
