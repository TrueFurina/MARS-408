# 前端性能体检报告 — 2026-10-04

> 分支 `career-literacy`（对外名「芒得很职」）。方法：生产构建实测 + 依赖/引入扫描；
> 所有结论均可用文末命令复现，未做任何无依据的优化改动。

## 结论（先看这里）

- **首屏加载健康**：gzip ≈ 100 kB（JS ≈ 86 kB + CSS ≈ 15 kB），处于良好区间。
- **分包与按需加载已到位**：路由级懒加载（每个页面独立 chunk）；`katex` / `highlight` / `marked`
  **均不进首屏**；`ChatView` 已用虚拟滚动。
- **未发现重大性能问题**，没有重量级库被"背进首屏"。
- 可动项只有两处（详见 §可选项）：
  - `lucide-vue-next` 是运行时**零引用的死依赖**（仅依赖卫生，不影响产物体积）。
  - 首屏含 `DOMPurify`（≈8 kB gzip）——系竞赛评审「所有 v-html 须净化」的**合规成本**，不建议移除。

## 实测产物体积（Top 6）

| chunk | 原始 | gzip | 是否进首屏 |
|---|---|---|---|
| katex | 261.17 kB | 77.58 kB | 否（按需：仅在文本含 LaTeX 时加载） |
| index（入口） | 122.37 kB | 40.83 kB | **是** |
| vue-vendor | 116.08 kB | 45.21 kB | **是**（Vue+Pinia+Router，必要） |
| index.css | 78.61 kB | 14.80 kB | **是** |
| highlight | 58.44 kB | 20.60 kB | 否（按需） |
| marked | 39.17 kB | 12.05 kB | 否（按需） |

## 首屏加载清单（读 `dist/index.html` 实测）

- `<script>`：`index-*.js`（122.37 kB）
- `modulepreload`：`vue-vendor-*.js`（116.08 kB）
- `<link rel=stylesheet>`：`index-*.css`（78.61 kB）
- 其余全部按需（**无** katex / highlight / marked 预加载）。

## 已到位的优化（无需再动）

- **路由级懒加载**：每个 view 独立 chunk（LandingView / ChatView / ResourceView …）。
- **大依赖按需**：`katex`（含其 CSS）与 `marked-katex` 扩展仅在文本含公式时动态 `import`
  （`src/utils/markdown.ts`）。
- **虚拟滚动**：`ChatView` 使用 `@tanstack/vue-virtual`。
- **构建配置**（`vite.config.ts`）：`manualChunks` 分包（vue-vendor / katex / highlight / marked）、
  `lightningcss` 压缩、`cssCodeSplit`、`target: es2020`。

## 可选项（各自收益 / 风险）

1. **清理 `lucide-vue-next` 死依赖** —— 收益：依赖卫生、减小供应链面。
   代价：需更新 lockfile（pnpm）。**不影响任何运行体积**（未使用 → 已被 tree-shaking 剔除）；
   注意保留 `OPENSOURCE_LICENSES.md` 中对 lucide 的许可声明（`icons.ts` 的 SVG path 仍源自 lucide）。
2. **App.vue 三个常驻浮层异步化**（`ProfilePanel` / `HistoryDropdown` / `MoreMenu`）——
   收益 ≈ 首屏 JS −5 kB gzip；但它们以 `:open` prop 控制滑出动画、属**常驻挂载**，
   异步化收益有限且可能触及滑出动画 —— **建议暂缓**。
3. **大列表虚拟滚动扩面**（Dashboard / CareerTraining 等）——需先有运行时列表长度数据，
   否则属无依据优化 —— **建议先度量再动**。

## 复现命令

```bash
# 1) 产物体积（输出到全新目录，避免安全删除守卫拦截 dist 清空）
npx vite build --outDir _dist_check
# 2) 类型 + 测试 + 全部门禁
npm run verify
```

> 注：`_dist_check/` 已加入 `.gitignore`（临时构建产物，不入库）。
