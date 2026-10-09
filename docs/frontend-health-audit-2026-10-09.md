# 前端健康度审计报告（2026-10-09）

> 审计范围：`src/`（Vue 3.5 + Pinia 3 + vue-router 4 + TS 5.7 + Vite 6）。
> 方法：静态扫描 + 实跑 `vite build`（输出到仓库外 Temp，规避 `emptyOutDir` 的 safe-delete 守卫，未改动 `dist/`）。
> 目的：为「国创赛性能/可访问性证据页」与 10-28 冻结窗口后的优化提供**有证据、有优先级**的方向清单。
> 纪律：本报告不修改任何冻结源码，不在 `submission/` 内落笔。

---

## 0. 结论速览

| 维度 | 现状 | 判定 |
|------|------|------|
| 构建 / 首屏体积 | 首屏关键链 **240 KB**（index 123K + vue-vendor 114K，gzip ~85K） | 🟢 健康 |
| 路由懒加载 | 全部 59 路由 `() => import()` | 🟢 已做 |
| 代码分割 | manualChunks 拆 vue/katex/highlight/marked | 🟢 已做 |
| WASM 重型依赖 | 隔离在 Web Worker chunk（非首屏） | 🟢 已做（原假设「未拆」**已证伪**） |
| a11y 基础门禁 | `gate:a11y` PASS（0 按钮缺陷） | 🟢 通过 |
| a11y 深度（focus trap / 沙箱键盘） | `focus()`/focus-trap = **0** | 🔴 真缺口 |
| 设计令牌采用率 | 109 个 CSS 变量定义，但 **449 处硬编码色值**并存 | 🟠 漂移 |
| PWA / 离线 | 无 service worker / manifest | 🟠 缺口 |
| 错误边界 / 加载态规范 | 未见全局统一规范 | 🟡 可补 |

**一句话**：基础工程（懒加载、分割、构建）已相当健康，**不需要做「WASM 拆包」这类我以为的紧急项**；真正值得投入的是 **a11y 深度化（焦点管理）**、**设计令牌去漂移**、**PWA 离线**。

---

## 1. 构建产物实测（证据）

实跑 `npx vite build --outDir <Temp>`，61 个 chunk，总产物 12 MB（含 katex）。关键体积：

| chunk | 原始 | gzip | 说明 |
|-------|------|------|------|
| index（入口） | 122.93 KB | 40.93 KB | 首屏主包 |
| vue-vendor | 114.05 KB | 44.48 KB | vue/pinia/router/@vue |
| katex | 261.17 KB | 77.58 KB | LaTeX，已拆且懒加载 |
| highlight | 57.12 KB | 20.12 KB | 代码高亮，已拆 |
| marked | 39.17 KB | 12.05 KB | markdown，已拆 |
| ChatView | 45.15 KB | 15.69 KB | 懒加载 |
| CodeLabView | 24.32 KB | 9.57 KB | 懒加载（WASM 沙箱入口） |
| cCompiler.worker | 45 KB | — | **含 @wasmer/sdk** |
| cppCompiler.worker | 88 KB | — | **含 @runno/wasi + tar-browserify + pako** |

**首屏关键链 = index + vue-vendor = 240 KB（gzip ~85 KB）**，对 LCP 友好。

---

## 2. 方向①「WASM 拆包」—— 已核实：非问题（自检更正）

**初始假设**（错误）：manualChunks 未拆 `@wasmer/sdk`/`@runno/wasi`，会被打进默认 chunk 拖慢首屏。

**核实结果**（证据）：
- `src/workers/cCompiler.worker.ts:1` → `import { Directory, init, Wasmer } from '@wasmer/sdk'`
- `src/workers/cppCompiler.worker.ts:1-3` → `@runno/wasi` + `@obsidize/tar-browserify` + `pako`
- 这些依赖**只在 Web Worker 内被引用**，构建产物为独立 `*.worker.js` chunk（45K / 88K），**不在 index / vue-vendor**。
- 首屏关键链 240K 不含任何 WASM 库 → **首屏无影响**。

**结论**：方向①降级为「可选微优」——若未来 worker 体积变大，可把 worker 内依赖改为 `import()` 动态加载做更细粒度分割，但**当前非紧急、不影响 10-28 交付**。感谢「先核实再下结论」纪律，避免了一条基于错误假设的伪任务。

---

## 3. 方向③ a11y 深度化（真缺口，中高优先）

**已具备**：`gate:a11y` 仅查「按钮/链接可读名」→ PASS（0 缺陷）；`aria-live` 6 处（LLM 流式输出已处理）；`role=` 67；`tabindex` 42；`prefers-reduced-motion` 8 处（动效降级已部分覆盖）。

**真缺口**（静态扫描证据）：
- **`focus()` / focus-trap = 0**：全 `src` 零处焦点陷阱/焦点返回管理。模态框、下拉、弹窗大概率未做焦点陷阱与关闭后焦点归位（WCAG 2.4.3 / 2.1.2 关注点）。需手动走查 `*.vue` 中 `Teleport`/`dialog`/`Modal` 组件确认。
- **WASM 沙箱键盘可达性**：`SandboxView.vue` / `CodeLabView.vue` / `SourceLabPane.vue` 是代码执行界面，需确认键盘可进入、可触发运行、可读取输出（无 `role`/焦点管理证据）。
- **对比度**：深色玻璃拟态（紫蓝 glow 字 vs 暗底）存在低对比文字风险，需按 WCAG 1.4.3 实测。

**建议动作**（10-28 前可做的部分）：
- 扩 `scripts/a11y_scan.py`：加静态规则（对比度阈值检查、Teleport/Modal 焦点陷阱模式识别、aria-live 配对检查）。纯 Python，不碰 src。
- 出《a11y 手动走查清单》，覆盖沙箱与模态焦点。

---

## 4. 方向④ 设计令牌散落（漂移，中优先）

**证据**（静态扫描 `src/**/*.{vue,ts,css}`）：
- CSS 自定义属性**定义 109 个**（令牌系统已存在，好）。
- 但**并存硬编码色值**：16 进制 `281` 处 + `rgb()/rgba()` `168` 处 = **449 处字面量**绕过令牌。
- `box-shadow` 字面量 156、`border-radius` 字面量 765。
- **品牌紫族漂移**（同一语义多值）：`#7c6af2`×33、`#6b5cdb`×15、`#8B5CF6`×7、`#A98CDD`×7 —— 4 个近义紫，应归一为一个令牌。
- 功能色硬编码：`#ef4444`×15（错误红）、`#22c55e`×6（成功绿）亦应走令牌。

**结论**：令牌系统**存在但采用率低**，这是典型的「定义了没用全」漂移。价值在于：① 防止同色多值导致主题不一致；② 为国创赛换肤/演示提供单一改点；③ 减少未来改色的回归面。

**建议动作**：
- 出《令牌采用差距报告》：列出 449 处硬编码中「可安全替换为现有令牌」的子集。
- 优先归一紫族 4 变体（改 `src` 需等 10-28 窗口；报告现在就能出）。

---

## 5. 方向② PWA / 离线优先（缺口，高价值）

**证据**：grep `serviceWorker|manifest|PWA` 在 `vite.config.ts` 仅命中注释；`ls sw.* service-worker* public/manifest*` 无结果 → **无离线能力**。

**价值**：学习平台用户在地铁/弱网场景学习频繁。离线缓存 SPA shell + 已学内容（或只读 API 静态产物，如 `/api/benchmark/results`、`/api/experiments`）可显著提升留存与口碑，且为国创赛「技术创新」证据页提供真实卖点。

**建议动作**（受 10-28 限，先做 spike）：
- 独立 `feat/pwa-spike` 分支引入 `vite-plugin-pwa`，预缓存 shell + 运行时缓存只读端点 JSON；验证后再于窗口后合入 `career-literacy`。

---

## 6. 方向⑤ 错误边界 & 加载态 UX（可补，中）

**证据**：`ChatView`（LLM 流式）、`SandboxView`/`CodeLabView`（WASM 执行）、`ExperimentEvidenceView` 均为高失败面，未见全局统一 ErrorBoundary / 骨架屏规范。

**价值**：弱网、模型降级、WASM 执行超时时不白屏、不卡死，给出友好重试。

**建议动作**：先出《前端容错 UX 规范》（组件级约定），源码改造等 10-28 后。

---

## 7. 优先级与冻结影响矩阵

| # | 方向 | 严重度 | 现在可做（不碰冻结源） | 需等 10-28 窗口 |
|---|------|--------|----------------------|----------------|
| ③ | a11y 深度（焦点/沙箱/对比度） | 🔴 | ✅ 扩 a11y_scan.py + 走查清单 | 源码改造焦点陷阱 |
| ④ | 设计令牌去漂移 | 🟠 | ✅ 出差距报告 | 替换硬编码字面量 |
| ② | PWA / 离线 | 🟠 | ⚠️ 仅独立分支 spike | 合入主构建 |
| ⑤ | 错误边界/加载态规范 | 🟡 | ✅ 出 UX 规范文档 | 落地组件 |
| ① | WASM 拆包 | 🟢 | —（已证非问题） | 可选微优 |
| ⑥ | CWV 实测基线 | 🟢 | ✅ 本报告已给（首屏 240K） | Lighthouse 真机复测 |

---

## 8. 建议的下一步（按性价比排序）

1. **现在立即做（安全）**：扩 `scripts/a11y_scan.py` 静态规则 + 出 a11y 走查清单（喂国创赛可访问性证据页）。
2. **现在立即做（安全）**：出《设计令牌采用差距报告》（含紫族 4 变体归一建议）。
3. **独立分支 spike（不污染冻结包）**：`feat/pwa-spike` 验证离线能力。
4. **10-28 窗口后**：按矩阵落地 ③/④/⑤ 源码改造 + Lighthouse 真机复测填 CWV 证据页。

---

*附：本报告所有数字来自 2026-10-09 实跑（`vite build` 输出、`grep` 静态扫描、`gate:a11y`/`gate:perf` 门禁），未修改任何源码。*
