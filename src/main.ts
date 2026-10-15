// 必须置于所有 import 之前：品牌更名后迁移旧 localStorage 键（mars408_* → mangdehenzhi_*），
// 保证在任何 store 读取 localStorage 之前执行，避免老用户丢失登录态/主题/成就。
import './utils/migrateLegacyKeys'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { probeBackend } from './utils/backendProbe'
import './assets/styles/main.css'
// ⚠️ 不要在此处静态引入 highlight.js 主题 CSS：
// 它属于 node_modules/highlight → 会被 manualChunks 归入 highlight chunk，
// 从而使入口 chunk 静态依赖该 chunk，首屏 modulepreload 掉 ~58KB JS + 主题 CSS（落地页并不需要代码高亮）。
// 正确位置是 src/utils/markdown.ts（只被懒加载视图引用），随按需加载走。

const app = createApp(App)

/**
 * 云服务（微信网页登录）回调必须在**任何路由守卫之前**处理：
 * 回调会带 ?code=&state= 落到站点根，而守卫见到未登录会把人弹去 /login，
 * 页面被拆掉后 code 就再也没机会换取会话（state 一次性，用户无法重试）。
 *
 * 这里按「URL 里确实带 code」时才加载 SDK —— 效果等同于「每次启动都跑」，
 * 但正常访问不会为此多拉一个 chunk、也不发多余请求。
 */
async function bootstrap() {
  try {
    if (/[?#&]code=/.test(window.location.search + window.location.hash)) {
      const { completeWechatRedirect } = await import('./services/cloud/auth')
      await completeWechatRedirect()
    }
  } catch {
    /* 回调失败不阻塞启动：用户仍可正常用应用，稍后可重试登录 */
  }
  app.use(createPinia())
  app.use(router)
  // 尽早开始探测后端可用性（不阻塞启动）：路由守卫与落地页共用这一判据，
  // 决定「未登录访客该进登录页还是被引导去本地运行」。
  probeBackend()
  app.mount('#app')
}

void bootstrap()

