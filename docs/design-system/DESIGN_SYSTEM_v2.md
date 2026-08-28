# MARS-408 设计系统规范 v2（单一真相源）

> 整合自 `DESIGN.md` + `DESIGN_TOKENS.md` + `src/assets/styles/_variables.css` + 2026-07-15 审计报告修正。
> **本文件是所有 UI 开发的权威参考**，任何组件、页面、新手都必须先读本节再动手。
> 配套可视化：见 `design-system/showcase.html`（浏览器直接打开预览）。

---

## 0. 设计哲学（不可动摇）

克制深色 · 玻璃态 · 学科分色 · 微交互。去"AI 感"，追求专业教育 SaaS 的冷静与精密（参考 Linear / Stripe 仪表盘美学）。

- **彩色只作信号**：主色紫 `#7c6af2` + 408 四科分色（数据结构紫 / 计网蓝 / 计组青 / 操作系统粉）。
- **纵深靠阴影与玻璃**，不靠粗边框（边框 0.06–0.10 低存在感）。
- **层级靠字号 + 字重 + 负字距**，不依赖颜色。
- **零加载依赖**：中文字体栈只用系统字体，禁止引入 web font。

---

## 1. 令牌系统（Token System）

> 所有变量定义在 `src/assets/styles/_variables.css` 的 `:root` 与 `[data-theme="light"]`。
> **组件只引用语义层或别名层变量，禁止在任何 `.vue` / `.css` 中硬编码 `hex` / `rgba` 裸值。**

### 1.1 语义层（画布 / 表面 / 文本 / 边框）

| 角色 | Dark (默认) | Light | 变量 |
|------|--------------|-------|------|
| 页面底色 | `#080812` | `#f5f6fb` | `--color-canvas` / `--bg-primary` |
| 卡片/玻璃表面 | `rgba(255,255,255,.03)` | `#ffffff` | `--color-surface` / `--bg-card` |
| 侧栏/输入底 | `#0f0f1a` | `#eef0f6` | `--color-surface-2` / `--bg-secondary` |
| 抬升层(弹层) | `#1c1c2b` | `#ffffff` | `--color-elevated` / `--bg-tertiary` |
| 悬停表面 | `rgba(255,255,255,.06)` | `#e7eaf3` | `--color-surface-hover` / `--bg-card-hover` |
| 遮罩 | `rgba(0,0,0,.55)` | `rgba(15,18,40,.32)` | `--color-overlay` / `--bg-overlay` |
| 玻璃态底 | `rgba(15,15,26,.65)` | `rgba(255,255,255,.72)` | `--color-glass` / `--glass-bg` |
| 玻璃态边框 | `rgba(255,255,255,.08)` | `rgba(15,18,40,.10)` | `--color-glass-border` / `--glass-border` |
| 默认边框 | `rgba(255,255,255,.06)` | `rgba(15,18,40,.10)` | `--color-border` / `--border-color` |
| 聚焦边框 | `rgba(124,106,242,.45)` | `rgba(124,106,242,.50)` | `--color-border-focus` / `--border-focus` |
| 主文本 | `#f8fafc` | `#1a1d2e` | `--color-text` / `--text-primary` |
| 次文本 | `#94a3b8` | `#525a72` | `--color-text-2` / `--text-secondary` |
| 弱文本(标签/说明) | `#7c8aa0` | `#8a92a8` | `--color-text-3` / `--text-muted` |

### 1.2 品牌色（双主题恒定，禁止双主题覆盖）

| 用途 | HEX | 变量 |
|------|-----|------|
| 主色·紫（主按钮/激活态/细线） | `#7c6af2` | `--accent` / `--accent-primary` |
| 辅助·蓝（渐变收尾/次级信号） | `#5b8bd8` | `--accent-blue` / `--accent-secondary` |
| 青（渐变中点/信息） | `#06b6d4` | `--accent-cyan` / `--accent-tertiary` |
| 琥珀（**仅高亮/警告**，勿作错误） | `#f59e0b` | `--accent-warm` |
| 成功（通过/正向） | `#22c55e` | `--accent-success` |
| 危险（错误/删除/校验失败） | `#ef4444` | `--accent-danger` |
| 粉（强调点缀） | `#f472b6` | `--accent-pink` |

> 半透明派生：`--accent-primary-10/20/30`、`--accent-danger-10/20`、`--accent-success-10/20`、`--text-danger`（danger 文字，Light 下转 `#dc2626`）。

### 1.3 408 四科色（恒定，着色用 `color-mix` 14%）

| 科目 | HEX | 变量 |
|------|-----|------|
| 数据结构 | `#8b5cf6` | `--subject-ds` |
| 计网 | `#3b82f6` | `--subject-cn` |
| 计组 | `#06b6d4` | `--subject-co` |
| 操作系统 | `#f472b6` | `--subject-os` |

### 1.4 圆角 / 间距 / 阴影 / 发光（引用变量，勿散写）

- **圆角**：`--radius-xs(6)` `--radius-sm(10)` `--radius-md(14)` `--radius-lg(18)` `--radius-xl(24)` `--radius-full(9999)`。卡片用 lg，按钮用 md，小元素用 sm，胶囊用 full。
- **间距**（4 倍数）：`--space-1(4)` … `--space-24(96)`。组件内距统一 20px（落地页 24px），区块间距 16–24px，列表项 4–12px。
- **阴影**：`--shadow-sm/md/lg/xl`、`--shadow-card`、`--shadow-card-hover`、`--shadow-glow`。
- **发光（克制）**：`--glow-primary`、`--glow-primary-strong`、`--glow-secondary`、`--glow-success`。
- **渐变**：`--gradient-primary`(紫→蓝) `--gradient-text` `--gradient-hero` `--gradient-border` `--gradient-progress`(三色) `--gradient-warm`。
- **动效**：`--transition`(200ms) `--transition-slow`(350ms) `--transition-bounce`(400ms) `--duration-*`。

### 1.5 排版

- 字体栈：`--font-sans`（系统中文栈，零加载）；`--font-mono`（代码/数值）。
- 层级：**Display 32 / H1 24 / H2 20 / H3·卡片 16 / Body 14 / Caption 13 / Nano·标签 12**。字重 400/500/600/700；大字号配 `-0.5px ~ -0.8px` 负字距。
- **单位用 `rem` 而非 `px`**，以支持浏览器 200% 文本缩放（`html { font-size: 16px }`，组件 `1rem = 16px`）。历史 `px` 已于 2026-07-17 全量迁移为 `rem`（见 1.7）。

### 1.6 层级 Z-index

`sidebar 100` · `topbar 90` · `bottom-nav 200` · `dropdown 200` · `overlay 900` · `panel 950` · `tooltip 1000`。

### 1.7 单位换算与 px→rem 迁移（2026-07-17 全量完成）

- **基准**：`html` 未重置 `font-size`，浏览器默认 `16px`，故 `1rem = 16px`，`px ÷ 16 = rem`。迁移后渲染尺寸与迁移前**完全一致**（仅新增"跟随根字号缩放"的无障碍能力，支持浏览器 200% 文本缩放）。
- **换算表（常用）**：

  | px | rem | px | rem | px | rem |
  |----|-----|----|-----|----|-----|
  | 1 | 0.0625 | 12 | 0.75 | 28 | 1.75 |
  | 2 | 0.125 | 14 | 0.875 | 32 | 2 |
  | 3 | 0.1875 | 16 | 1 | 36 | 2.25 |
  | 4 | 0.25 | 18 | 1.125 | 44 | 2.75 |
  | 6 | 0.375 | 20 | 1.25 | 48 | 3 |
  | 8 | 0.5 | 24 | 1.5 | 64 | 4 |
  | 10 | 0.625 | 26 | 1.625 | 90 | 5.625 |

- **安全迁移规则（脚本 `scripts/px_to_rem.py` 已落地，40 文件）**：
  - ✅ 转 `rem`：用户可见尺寸属性 —— `font-size` / `line-height` / `width` / `height` / `min-max-width/height` / `padding*` / `margin*` / `top-bottom-left-right-inset` / `gap*` / `border-radius*` / `border-width*` / `letter-spacing` / `flex-basis`。`calc()`/`clamp()` 内 px 一并转；`0px`→`0`。
  - ❌ 保留 `px`（不转）：`@media` 断点、`box-shadow`/`text-shadow`、`1–2px` hairline `border`、`outline`、`transform`(动画位移)、`filter`、`clip-path`、`z-index`、`grid-template`、`--var:` **令牌定义行**。
- **间距令牌（新代码优先）**：`--space-1(4)`…`--space-24(96)` 已在 1.4 定义；存量 px 间距属可选优化，新组件优先引 `--space-*`。

---

## 2. 组件库（Component Library）

### 2.1 按钮（标准 `.btn` 体系 —— 唯一合法按钮类）

```css
.btn { /* 全局已定义：inline-flex, gap:8, radius-md, radius 按尺寸 */ }
.btn-primary   /* 紫→蓝渐变 + 白字（主操作） */
.btn-secondary /* surface-hover 底 + 边框（次操作） */
.btn-ghost     /* 透明 + 次文本色（低调） */
.btn-soft      /* accent-10 底 + accent 字（选中/温和） */
.btn-danger    /* danger-10 底 + danger 字（删除/危险） */
.btn-sm / .btn-lg / .btn-block
```

- **禁止**新增 `.xxx-btn` 散落类（历史 `.engine-btn`/`.rag-btn`/`.answer-submit-btn`/`.hero-cta-btn` 为过渡期别名，**新代码一律用 `.btn`**，存量按迁移表逐步替换）。
- 图标按钮：用 `<button class="btn btn-ghost" aria-label="发送">`，图标 `currentColor` + `18–22px`。**必须有 `aria-label`**。
- 触摸目标：所有按钮/可点击项 **最小 44×44px**（移动端放宽不低于 40px）。

### 2.2 卡片（玻璃态）

`.card` / `.glass-card` / `.stat-card` / `.feature-card` 共用玻璃底 + blur(12px) + 1px 玻璃边框 + `--shadow-card`。hover：`transform: scale(1.02)`（上限）+ `--shadow-card-hover` + 1px accent 描边。**切勿超过 1.02**。

### 2.3 标签 / 徽章（学科 & 状态）

`.tag-purple/.tag-blue/.tag-cyan/.tag-pink`（四科，背景 `color-mix(in srgb, var(--subject-x) 14%, transparent)`，字色原色）· `.tag-warm/.tag-green/.tag-primary`。**错误提示用 `.tag-*` 危险红系或 `engine-error` 样式，绝不用琥珀(`--accent-warm`)作错误文字色。**

### 2.4 表单

`.rag-select` / `.answer-input` / `.conv-search-input` 统一：surface 底 + 1px 边框 + radius-md + focus 时 `--border-focus` + `0 0 0 3px var(--accent-primary-10)` 光环。**每个输入必须有关联 `<label>` 或 `aria-label`**。

### 2.5 反馈

- 错误条：`engine-error`（danger-10 底 + danger-20 边 + `--text-danger` 字），可点击关闭。
- 告警/ Toast / Modal：`.panel-overlay`(blur4) + `.profile-panel`(玻璃 blur20, 宽 400px/`90vw`, slide-in)。

### 2.6 数据展示

- `.stat-card`：顶部 3px 渐变条 + 图标 + 数值(30px/700/-0.5px) + 变化标签（success/danger）。
- 进度/掌握度条：`--progress-bar-gradient`（四色）或单科 `color-mix` 着色。
- 骨架屏：`.skeleton*` 系列（shimmer 动画）。空状态：`.empty-state`（玻璃卡 + fade-up）。

### 2.7 导航

侧栏 `.nav-item`（可点击项必须是 `<a>`/`<button>` 或带 `role="button" tabindex="0"` + 键盘 handler）；激活态 accent 10 底 + accent 字 + 左侧 3px 渐变条；学科激活用 `.nav-subject-0..3` 四科色。**移动端转顶栏汉堡 + 底栏 5 项 tab**。

---

## 3. 双主题（Dark 默认 / Light 可选）

- 仅覆盖 `_variables.css` 的 `[data-theme="light"]` **语义层**即可，别名/品牌色自动跟随。
- 初始化顺序：`localStorage` → `matchMedia(prefers-color-scheme)` → dark。
- **自检规则**：每写一组件，脑内渲染一次 Light 主题（白底），确认边框可见（≥`rgba(15,18,40,.10)`）、文字对比度达标。

---

## 4. 响应式（Responsive）

| 断点 | 范围 | 行为 |
|------|------|------|
| Desktop | >1024px | 侧栏 220px 常驻；顶/底栏隐藏 |
| Tablet | ≤1024px | grid-4→2 列 |
| Mobile | ≤768px | 侧栏隐藏；顶栏 64 + 底栏 64 接管；`.page-section` padding 收窄 16px |
| Small | ≤480px | grid→1 列；hero 32→22px；输入区收窄 |

网格默认 4 列，必须补 `@media (max-width:1024px){2列}` 与 `480px{1列}`。容器 `max-width:1200px`。

---

## 5. 无障碍基线（A11y Baseline —— v2 新增，强制）

1. **焦点可见（WCAG 2.4.7）**：全局定义 `:focus-visible { outline: 2px solid var(--accent-primary); outline-offset: 2px; }`，所有可交互元素键盘聚焦时可见。**禁止用 `outline:none` 后不补等价焦点指示。**
2. **动效敏感（WCAG 2.3.3 / 用户偏好）**：全局 `@media (prefers-reduced-motion: reduce)` 关闭非必要动画（fade/stagger/pulse/gradient-shift/typing）。
3. **语义结构**：用原生 `<button>`/`<a>`/`<nav>`/`<main>`；装饰性 `<div @click>` 必须补 `role="button"` + `tabindex="0"` + 键盘 `Enter/Space` handler。
4. **ARIA**：图标按钮 `aria-label`；折叠/下拉 `aria-expanded` + `aria-controls`；`<video>`/`<img>` 必须有 `aria-label` 或 `alt`；告知性提示用 `role="status"`/`aria-live="polite"`。
5. **触摸目标（WCAG 2.5.5）**：可点击元素 ≥ 44×44px。
6. **对比度（WCAG 1.4.3 AA）**：正文 ≥ 4.5:1，大文本 ≥ 3:1。`--accent-primary` 仅用于 UI/大字号，不作正文色；错误用 `--text-danger`，不用琥珀。
7. **表单标签**：每个 `<input>/<textarea>/<select>` 关联 `<label>` 或 `aria-label`；错误信息 `aria-describedby` 关联。
8. **文本缩放**：单位用 `rem`；支持浏览器 200% 缩放不破版。

---

## 6. Do's & Don'ts v2

**Do's**
1. 组件只引 `--color-*`/`--accent-*`/`--subject-*`/`--bg-*`/`--text-*` 变量，零裸 `hex`/`rgba`。
2. 新按钮一律 `.btn` + 变体；存量历史类按迁移表替换。
3. 学科/状态着色用 `color-mix(in srgb, VAR 14%, transparent)`。
4. 圆角走 `--radius-*` 刻度；阴影走 `--shadow-*` 刻度。
5. 间距用 4 倍数（`--space-*`）。
6. 图标 `currentColor` + `18–22px`。
7. 每个交互元素补 `:focus-visible` 可见焦点 +（若非原生）`role`/`tabindex`/`aria-label`。
8. 写组件先想 Light 主题对比度。

**Don'ts**
1. 勿在 CSS / 内联 `style` 硬编码 `rgba`/`hex` 裸值。**合规例外**：SVG 图标用 `fill="currentColor"`（继承文字色、随主题变化，是推荐做法）；Canvas 绘图调色板需具体色值是合理存在，不改。
2. 勿新增 `.xxx-btn` 散落按钮类（历史别名过渡期满即删）。
3. 勿 `transform:scale()` 超 1.02。
4. Light 主题勿用强彩色发光（已降级柔和投影）。
5. 勿把主色 `#7c6af2` 作大面正文填充。
6. 勿在中文字体栈写非系统字体。
7. 勿用 `!important` 覆盖（除 `.btn:disabled` 必要场景）。
8. **勿用 `--accent-warm`(琥珀) 作错误/危险文字色** —— 错误必须 danger 系。
9. 勿省略 `:focus-visible` / `prefers-reduced-motion` / `aria-label`。

---

## 7. 历史按钮类迁移表（消除技术债）

| 旧类 | 替换为 | 备注 |
|------|--------|------|
| `.engine-btn` | `.btn .btn-primary` | 视觉一致，圆角改 md |
| `.rag-btn` / `.answer-submit-btn` | `.btn .btn-primary` | XfyunWorkshop 9 处优先迁移 |
| `.hero-cta-btn` | `.btn .btn-primary` + `btn-lg` | Dashboard hero |
| `.deep-think-btn` / `.agent-btn` | `.btn .btn-soft .btn-sm` | ChatInput 开关 |
| `.send-btn` / `.input-action-btn` | `.btn .btn-primary` / `.btn .btn-ghost`（含 `aria-label`，尺寸≥44px） | ChatInput |

---

## 8. Agent / 开发者消费指引

生成任何组件前：
1. 读 `_variables.css` 的 `:root` + `[data-theme="light"]`，只引已定义变量。
2. 写 `.btn` 体系，不造新按钮类。
3. 补 `:focus-visible` + `aria-label`/(role,tabindex)；非原生可点击元素加键盘 handler。
4. Light 主题自检对比度。
5. 间距 4 倍数、圆角刻度、阴影刻度。
6. 补 `@media (max-width:1024px)` 与 `480px` 响应式收口。
7. 包裹 `@media (prefers-reduced-motion: reduce)` 降级。

**一致性目标**：组件令牌引用率 95%+，裸值 0，`.btn` 体系覆盖 100%，WCAG AA 全过。
