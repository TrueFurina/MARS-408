// copy-spa-404.mjs
// GitHub Pages 是纯静态服务器，不支持 SPA history-mode 深链接回退。
// 把构建产物 dist/index.html 复制为 dist/404.html：
//   对任意未匹配路径（如 /MARS-408/login），Pages 回退到 404.html（内容即 SPA 壳），
//   SPA 启动后 createWebHistory 读取 location.pathname 渲染对应路由，深链接可用。
// 资产用绝对路径 /MARS-408/assets/... 引用，不受 404.html 位置影响。
import { copyFileSync, existsSync } from 'node:fs';

const src = 'dist/index.html';
const dst = 'dist/404.html';

if (!existsSync(src)) {
  console.error('[copy-spa-404] dist/index.html 不存在，请先 vite build');
  process.exit(1);
}
copyFileSync(src, dst);
console.log('[copy-spa-404] ✓ dist/index.html -> dist/404.html (SPA fallback for GitHub Pages)');
