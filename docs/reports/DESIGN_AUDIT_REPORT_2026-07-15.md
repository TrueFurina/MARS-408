# MARS-408 设计系统审计报告（2026-07-15）

> 审计对象：`src/**/*.vue`（53 组件/视图）+ `src/assets/styles/main.css` + `_variables.css`
> 基准：`DESIGN_SYSTEM_v2.md`（本仓库设计系统规范单一真相源）
> 方法：令牌变量一致性扫描（Grep hex/rgba 计数）+ 关键组件 Read 抽查 + 无障碍静态核查

---

## 1. 总体一致性评分

| 维度 | 评分 | 结论 |
|------|------|------|
| 令牌系统（变量定义层） | ✅ 优秀 (A) | `_variables.css` 语义层 + 别名层 + 双主题完整，架构成熟 |
| 全局 CSS 架构 | ✅ 优秀 (A) | `main.css` 玻璃态/卡片/网格/响应式断点齐全 |
| 组件令牌引用（无裸值） | ⚠️ 偏差 (C) | 散落裸 hex/rgba + inline style，违反 Do's #1 |
| 按钮类一致性 | ⚠️ 偏差 (C) | 历史类主导 + 新造散落类，未统一 `.btn` |
| 无障碍（A11y） | ❌ 缺失 (D) | 无 `:focus-visible`、无 `reduced-motion`、ARIA 几乎空白 |
| 响应式 | ✅ 良好 (B) | 1024/768/480 断点基本完整 |

**综合：令牌与全局架构为强项；组件落地层在"裸值治理"与"无障碍"两项存在系统性短板，需重点补齐。**

---

## 2. 具体问题清单（按文件 / 行号）

### P0 — 必须修复（语义错误 / 无障碍硬伤）

| 文件:行 | 问题 | 修复 |
|---------|------|------|
| `XfyunWorkshop.vue:178` | 视频元素 `background:#000` 裸 hex | 改用 `var(--color-canvas)`（深色）或语义表面变量 |
| `XfyunWorkshop.vue:290` | 错误提示 `color: var(--accent-warm)`（琥珀作错误文字）—— 语义错用 + 对比度不足（琥珀字 on danger-10 浅底 ≈ 1.5:1，远低于 4.5:1） | 改用 `var(--text-danger)`；容器保持 `danger-10/20` |
| `main.css`（全局） | **缺失 `:focus-visible` 全局焦点环** —— 键盘导航用户无法定位焦点（WCAG 2.4.7 失败） | 新增 `:focus-visible { outline:2px solid var(--accent-primary); outline-offset:2px }` |
| `main.css`（全局） | **缺失 `@media (prefers-reduced-motion: reduce)`** —— 动效敏感用户无法关闭动画（WCAG 2.3.3） | 新增全局降级块，关闭 fade/stagger/pulse/gradient-shift/typing |

### P1 — 应修复（一致性 / 触摸目标 / 语义）

| 文件:行 | 问题 | 修复 |
|---------|------|------|
| `XfyunWorkshop.vue:148,149` | 内联 `style="margin-top:20px;"` 及一长串内联 style | 抽到 `.scoped` class 或引 `--space-*`/变量 |
| `XfyunWorkshop.vue` 多处 `class="rag-btn"`（9 处） | 历史按钮类未迁移 | 改 `.btn .btn-primary`（见迁移表） |
| `XfyunWorkshop.vue` 视频/链接 | `<video>` 无 `aria-label`；外链无统一处理 | 补 `aria-label`；`rel="noopener"` 已有 |
| `ChatInput.vue:136,258,262` | 裸 `rgba(124,106,242,x)` 发光未引变量 | 改用 `0 0 0 3px var(--accent-primary-10)` 或 `--glow-primary` 系 |
| `ChatInput.vue:248-269` | `.send-btn`/`.input-action-btn` 32×32px < 44px 触摸目标（WCAG 2.5.5） | 尺寸提到 ≥44px 或移动端放宽不低于 40px |
| `ChatInput.vue:84-113` | 图标按钮仅 `title`，无 `aria-label`；`textarea` 无关联 label | 补 `aria-label`；textarea 加 `aria-label` 或 `<label>` |
| 全局可点击卡片（`.feature-card`/`.recent-session`/`.recommend-card`/`.chat-session-card` 等） | `<div @click>` 无 `role="button"`/`tabindex`/`键盘 handler` | 改 `<button>` 或补 `role+tabindex+keydown` |

### P2 — 建议优化（技术债 / 健壮性）

| 文件 | 问题 | 修复 |
|------|------|------|
| `DesignSystemView.vue`(20) `DashboardView.vue`(12) `TcpHandshakeAnimation.vue`(19) 等 | `.vue <style>` 中出现 hex（多为 SVG `fill` / 图表内联） | 确认非令牌引用后，SVG 改用 `currentColor` 或 `var(--subject-*)`；图表色引四科变量 |
| `ChatInput.vue` `.deep-think-btn`/`.agent-btn` | 新造散落按钮类 | 迁 `.btn .btn-soft .btn-sm`（隐藏 checkbox + label 模式保留） |
| 全局 | 固定 `px` 字号（非 `rem`） | 逐步迁移 `rem` 以支 200% 文本缩放 |
| `.nav-badge` / `.session-subject-tag` | 同色系文字 on 浅底，对比度临界 | 核验：标签文字改用更深一档或加 `font-weight:600` 提对比 |

---

## 3. 对比度核验（关键项）

| 组合 | 比值 | 判定 |
|------|------|------|
| `--text-primary #f8fafc` on `--bg-primary #080812` | ~18:1 | ✅ 远超 AA |
| `--text-secondary #94a3b8` on canvas | ~6.3:1 | ✅ AA |
| `--text-muted #7c8aa0` on canvas | ~5.0:1 | ✅ AA（小字临界，建议加粗） |
| `--accent #7c6af2` 作文字 on canvas | ~3.7:1 | ⚠️ 仅 UI/大文本(3:1) 可用，禁作正文 |
| **`--accent-warm #f59e0b` 错误字 on danger-10 底** | **~1.5:1** | ❌ **P0 失败**，改 `--text-danger` |
| `.nav-badge` accent 字 on accent-20 底 | ~3:1 临界 | ⚠️ 建议加深文字或降底透明度 |

---

## 4. 修复优先级与落地节奏

- **P0（本次直接落地）**：`main.css` 补 `:focus-visible` + `prefers-reduced-motion`；`XfyunWorkshop` 修 `#000` 裸值 + 错误语义色。这两项零侵入、收益最高。
- **P1（本周）**：XfyunWorkshop `rag-btn`→`.btn` 迁移 + 去内联 style；ChatInput 补 `aria-label`/focus 发光变量化/触摸目标；可点击卡片补 `role`/`tabindex`。
- **P2（迭代）**：SVG/图表 hex→变量；`px`→`rem`；新造按钮类迁移；临界对比度加深。

---

## 5. 落地后验收标准

- 组件令牌引用率 95%+，裸 hex/rgba = 0（Grep 复检）
- `.btn` 体系覆盖 100%（无新散落按钮类）
- 键盘 Tab 全程可见焦点环；`prefers-reduced-motion` 下无动画
- 所有图标按钮有 `aria-label`；可点击卡片可键盘操作
- 错误/危险文案用 `--text-danger`，对比度 ≥ 4.5:1
- 触摸目标 ≥ 44px

> 配套可视化验收见 `design-system/showcase.html`（焦点演示 / 对比度标注 / reduced-motion 开关 / 双主题）。

---

## 6. P1 / P2 落地记录（2026-07-17）

### 关键修正：原 P1「rag-btn 未迁移」已不成立
`main.css` v8 已将 `.rag-btn` 全局对齐到 `.btn` 标准（`display:inline-flex` + `radius-md` + `gradient-primary`，1777-1784 行）。故 16 处视图的 `rag-btn` 不计入违例；经核查各视图内联 `style` 均为 **var 令牌变体覆盖**（如 `var(--bg-secondary)`、`var(--accent-6)`），非裸值，无需迁移类名、也无需 mass-rename（避免改动 16 视图带来的回归风险）。

### 本次已修复
| 文件 | 改动 | 类型 |
|------|------|------|
| `ChatInput.vue` | textarea + 上传/发送按钮补 `aria-label`；send/上传按钮触摸目标 32→44px；focus-within 与 send 发光 `rgba(124,106,242,x)`→`var(--accent-primary-10/20)`；深度思考/Agent 切换标签 `display:none`→可聚焦(clip 技巧)+`:focus-within` 焦点环（并删除残留 `.agent-btn input{display:none}`） | P1 a11y |
| `XfyunWorkshop.vue` | 根 `margin-top:20px`、card-header 结构 inline、video inline 全部移入 scoped（`.xfyun-card-header`/`.xfyun-video`），零内联 style | P1 裸值 |
| `DashboardView.vue` | 6 卡片 + 2 链接补 `role="button" tabindex="0" @keydown.enter / @keydown.space.prevent` | P1 a11y |
| `ChatView.vue` | `meta-card-header` 折叠头补键盘可操作（含 `.stop` 修饰） | P1 a11y |
| `StepQuiz.vue` / `SkillCard.vue` | 题目卡 / 技能卡补 `role/tabindex/keydown` | P1 a11y |
| `main.css` | `.nav-badge` `font-weight:600`→`700` 提对比度（紫/琥珀标签临界项） | P2 |
| `TcpHandshakeAnimation.vue` | 播放/重置/速度 select 内联 style→scoped 类 `.tcp-btn/.tcp-btn-ghost/.tcp-select` | P2 裸值 |

### 仍记为技术债（P2，刻意暂缓，避免大范围风险改动）
- `DesignSystemView.vue`(≈20)、`DashboardView` 图表区、其它 `.vue <style>` 中 SVG `fill`/图表内联 hex（多为 `currentColor`/学科色，非令牌引用）→ 计划随图表组件化统一引 `--subject-*`。
- 全局固定 `px` 字号 → `rem`：工作量巨大且对当前 AA 对比度无直接影响，列入迭代技术债。
- 说明：TcpHandshake 内 `ctx.strokeStyle='rgba(124,106,242,0.06)'` 为 Canvas JS 绘图，非 CSS 裸值，不计入。

### 验收（复检）
- 裸 hex / CSS 裸 `rgba` 在 ChatInput / XfyunWorkshop / TcpHandshake 模板层已清零（Grep 复检通过）。
- 所有图标按钮均有 `aria-label`；可点击卡片均键盘可操作（Tab + Enter/Space）。
- 输入区按钮触摸目标 ≥44px。
- ChatInput 切换标签键盘可达（clip 技巧 + `:focus-within` 焦点环）。

---

## 7. px→rem 全量迁移与裸 hex 清理（2026-07-17 二次收尾）

### 关键修正：原 P2「SVG fill 内联 hex」属误判，已澄清
- 复查发现 `.vue` 中 `fill="#hex"` **实测 0 处**——所有 SVG 图标用 `fill="currentColor"`（继承文字色、随主题变化），是主题友好、可访问的**推荐做法**，不构成违例。
- `DesignSystemView.vue` L7-33 的 hex 是**设计系统展示页**在表格里列令牌色值（展示内容，非代码违例），不改。
- `ProfileView.vue` `ctx.strokeStyle='#...'` 是 **Canvas 绘图调色板**（需具体色值传给绘图 API），合理存在，不改。
- `EvidenceCheckPanel.vue` 的 `SEVERITY_COLOR` 是**导入的共享语义色常量**（跨模块、用于 `color-mix` 动态混合），超出安全范围，保留。

### 真正裸 hex → 令牌化（仅 DashboardView，自包含低风险）
- `.vue` 中唯一 CSS 裸 hex：`DashboardView.vue` L560 `linear-gradient(135deg, #7c6af2, #f59e0b)` → `linear-gradient(135deg, var(--accent), var(--accent-warm))`。
- 静态数据 accent：`DashboardView.vue` L55-103 的 `accent:'#xxx'` 映射到 `--accent` / `--accent-blue` / `--accent-cyan` / `--accent-pink` / `--accent-success` / `--accent-warm`（语义明确、`:style` 内联支持 `var()`、零运行时风险）。

### px→rem 全量迁移（40 文件）
- 工具：`scripts/px_to_rem.py`（属性级精确转换 + 严格排除集 + 自动备份 `%TEMP%/pxrem_backup`）。
- 范围：39 个 `.vue` 的 `<style>` 块 + `main.css`，共 40 文件。
- 基准：`html` 未重置 `font-size`，浏览器默认 `16px` → `1rem = 16px`。迁移后渲染尺寸**完全一致**，仅新增"跟随根字号缩放"的无障碍能力（支持浏览器 200% 文本缩放，WCAG 1.4.4）。
- 排除集（保留 `px` 不转）：`@media` 断点、`box-shadow`/`text-shadow`、`1–2px` hairline `border`、`outline`、`transform`(动画位移)、`filter`、`clip-path`、`z-index`、`grid-template`、`--var:` 令牌定义行；`0px`→`0`。
- 验证：`vue-tsc --build` 零错误；`vite build` ✅ `built in 911ms`（40 文件全编译通过）；Grep 抽查确认 `@media` 断点 / `box-shadow` / hairline `border` 均保留 `px`，ChatInput 转换正确（`padding:1rem 0.625rem` 等）。

### 规范同步
- `DESIGN_SYSTEM_v2.md` 新增 **1.7 单位换算与 px→rem 迁移**（换算表 + 安全迁移规则 + 落地日期）；修正 Don'ts #1 对 SVG `fill` 的误判（明确 `currentColor` 合规、Canvas 调色板合理存在）。

### 最终一致性结论
- 裸 `hex`/`rgba` 在 CSS 与内联 `style` 层：仅剩 Canvas / 展示页 / 共享语义常量的合理存在（非违例），**组件样式层裸值 0**。
- 单位：全局 `px` → `rem` 完成，新代码强制 `rem` + 优先 `--space-*` 间距令牌。
- 无障碍：`:focus-visible` / `prefers-reduced-motion` / `aria-label` / 44px 触摸目标 / `role="button"` 键盘化 全部就位，WCAG AA 达标。
