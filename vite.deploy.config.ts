import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 部署专用配置：强制 base='/'，避免本机环境把 base 解析成 Git 安装路径。
// 云部署前端与后端同源，资源必须从根路径加载。
// 产物目录 = deploy/career-pilot/backend/site（与后端同根）：
//   ① 命名 site/ 而非 dist/ —— 发布通道上传时会排除名为 "dist" 的 "build output"；
//   ② 放进 backend/ 内 —— 发布时 directory=backend，CWD 即包根，
//      STATIC_DIR=site 相对包根恒定解析，入口不依赖外部 CWD。
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
    outDir: 'deploy/career-pilot/backend/site',
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
