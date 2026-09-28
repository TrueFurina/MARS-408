import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/styles/main.css'
// ⚠️ 不要在此处静态引入 highlight.js 主题 CSS：
// 它属于 node_modules/highlight → 会被 manualChunks 归入 highlight chunk，
// 从而使入口 chunk 静态依赖该 chunk，首屏 modulepreload 掉 ~58KB JS + 主题 CSS（落地页并不需要代码高亮）。
// 正确位置是 src/utils/markdown.ts（只被懒加载视图引用），随按需加载走。

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
