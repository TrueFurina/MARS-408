# MARS-408 DESIGN.md — 设计系统规范 (v10)

> **版本：v11「砚 · Ink & Violet」** ｜ 权威真相源：`src/assets/styles/_variables.css`（唯一可改处）
> 生成基线：以 `_variables.css` 的 `:root` / `[data-theme="light"]` 为唯一输入机械对齐 ｜ 更新：2026-09-14
> AI 可读：供 Cursor / Claude Code / Google Stitch 直接消费。**本文档为派生消费者，若与 `_variables.css` 不一致，以 `_variables.css` 为准。**
> ⚠️ 旧文档 `DESIGN_SYSTEM_v2.md` / `DESIGN_TOKENS*.md` 描述的是 **v7/v8 紫主色系统**，已于 2026-09-12 被本版取代，勿再引用。

---

## 1. Visual Theme & Atmosphere

- **设计哲学**：**阅读优先 · 信息密度优先 · 克制用色 · 零霓虹**。这是单次 1–3 小时的高强度学习工具，一切以降低长时间阅读的眩光与疲劳为先。
- **视觉基调**：专业、克制、陪伴。冷蓝灰画布 + 紫罗兰强调色——「深夜台灯下的一支紫笔」。
- **核心视觉特征**：`flat-surfaces`（明度分层）、`clay-accent`（唯一强调色）、`subject-colored`（四科数据色）、`neutral-depth`（中性投影，无彩色发光）、`micro-interaction`（仅 GPU 属性微动效）。
- **光影与质感**：**零霓虹**——已删除全部彩色 glow，改用中性多层投影 + 1px 描边表达高度；玻璃态仅顶栏/抽屉/悬浮按钮使用（`backdrop-filter: blur(10–18px)`）。
- **用色纪律**：全站只有 **1 个强调色（紫罗兰 Violet `#7c6af2` / 深紫 `#6b5cdb`）**；四科分色是"数据色"非"装饰色"（只出现在学科标签、图表、掌握度）；语义色只表达状态。

---

## 2. Color Palette & Roles

### 2.1 画布与表面（明度递进，不靠彩色）

| Token | Dark（默认） | Light | 角色 |
|-------|--------------|-------|------|
| `--color-canvas` | `#0E1217` | `#F5F6F7` | 页面底色（蓝灰，非纯黑） |
| `--color-surface` | `#151A20` | `#FFFFFF` | surface-1：卡片 |
| `--color-surface-2` | `#1B2129` | `#EFF1F3` | surface-2：嵌套块 / 输入区 |
| `--color-surface-3` | `#232A34` | `#E5E8EB` | surface-3：最高层（选中、代码区） |
| `--color-surface-hover` | `#1D242C` | `#EDF0F2` | 卡片悬浮态 |
| `--color-elevated` | `#1B2129` | `#FFFFFF` | 浮层：弹窗 / 菜单 / 下拉 |
| `--color-overlay` | `rgba(6,9,13,.62)` | `rgba(20,24,30,.34)` | 遮罩 |

### 2.2 玻璃态（克制：仅顶栏 / 侧边抽屉 / 悬浮按钮）

| Token | Dark | Light |
|-------|------|-------|
| `--color-glass` | `rgba(21,26,32,.72)` | `rgba(255,255,255,.78)` |
| `--color-glass-hover` | `rgba(29,36,44,.86)` | `rgba(255,255,255,.92)` |
| `--color-glass-border` | `rgba(255,255,255,.09)` | `rgba(16,20,26,.10)` |
| `--glass-blur` / `--glass-blur-heavy` | `10px` / `18px` | 同左 |

### 2.3 边框

| Token | Dark | Light |
|-------|------|-------|
| `--color-border` | `rgba(255,255,255,.09)` | `rgba(16,20,26,.11)` |
| `--color-border-light` | `rgba(255,255,255,.05)` | `rgba(16,20,26,.06)` |
| `--color-border-strong` | `rgba(255,255,255,.16)` | `rgba(16,20,26,.20)` |
| `--color-border-focus` | `rgba(124,106,242,.55)` | `rgba(107,92,219,.55)` |
| `--color-border-glow` | `rgba(206,130,86,.22)` | `rgba(158,90,48,.24)` |

### 2.4 文本层级（对比度为对画布实测值）

| Token | Dark | Light | 对比度 |
|-------|------|-------|--------|
| `--color-text` | `#E6E9ED` | `#16191D` | 15.4:1 / 17.6:1 |
| `--color-text-2` | `#9AA4B0` | `#545B66` | 7.4:1 / 6.9:1 |
| `--color-text-3` | `#79838F` | `#6E7783` | 4.9:1 / 4.5:1 |
| `--color-text-disabled` | `#565F6B` | `#A3ABB5` | 2.9:1 / 2.3:1 |
| `--color-text-invert` | `#0E1217` | `#FFFFFF` | 反色 |
| `--color-text-on-accent` | `#FFFFFF` | `#FFFFFF` | 强调实底上的白字 |

### 2.5 强调色（全站唯一色相 · 双色调 ink/solid）

> **为什么拆两调**：深色下，作为**文字**与作为**承载白字的实底**对亮度的要求方向相反，故拆 `ink`（文字/图标/描边，较亮）与 `solid`（按钮/头像实底，较深，其上永远白字）。浅色主题下 ink 与 solid 同为深紫 `#6b5cdb`，三态共用同一色调。

| Token | Dark | Light | 用途 |
|-------|------|-------|------|
| `--color-accent` (ink) | `#7c6af2` | `#6b5cdb` | 文字 / 链接 / 图标 / 描边 / 焦点环 |
| `--color-accent-hover` | `#8b7bf5` | `#7c6af2` | 紫罗兰悬浮 |
| `--color-accent-active` | `#6b5cdb` | `#5a4cc4` | 紫罗兰按下 |
| `--color-accent-text` | `#a99ff7` | `#6b5cdb` | 深底上的强调文字（更亮，长文更舒适） |
| `--color-accent-solid` | `#6b5cdb` | `#6b5cdb` | 实底（其上永远白字） |
| `--color-accent-solid-hover` | `#7c6af2` | `#7c6af2` | 实底悬浮 |
| `--color-accent-solid-active` | `#5a4cc4` | `#5a4cc4` | 实底按下 |
| `--color-accent-subtle` | `rgba(124,106,242,.14)` | `rgba(107,92,219,.10)` | 选中态淡底 |
| `--accent-rgb` | `124,106,242` | `107,92,219` | 供 `rgba(var(--accent-rgb),α)` |

> 主色选择理由：**克制紫罗兰 Violet `#7c6af2` / 深紫 `#6b5cdb`**——品牌调性为「专业 / 克制 / 陪伴」的低饱和紫罗兰，取偏蓝、中等饱和的紫以避开廉价 AI 渐变感；与四科数据色中的 DS 紫 `#A98CDD`（更浅的薰衣草，专用于学科标签/图表）靠亮度与用法二次区隔。
> 历史说明：曾一度改用暖陶土棕 `#CE8256` 以规避「AI 紫」，产品负责人判定棕色观感不佳且偏离原始紫罗兰品牌，故于 v11 回退为紫罗兰。

### 2.6 语义色

| Token | Dark | Light | 用途 |
|-------|------|-------|------|
| `--color-success` | `#4FA96B` | `#2F7D4F` | 成功 / 通过 |
| `--color-warning` | `#DCA03C` | `#8A6210` | 警告 / 高亮（**不可作错误色**） |
| `--color-danger` | `#E0685E` | `#B8392F` | 错误 / 删除 / 校验失败 |
| `--color-info` | `#5E93C4` | `#2F6DA8` | 信息 |

> 每个语义色均派生 `-bg`（`.14`/`.10` α）与 `-border`（`.32`/`.26` α），以及 `--{success,warning,danger,info}-rgb` 供透明叠加。

### 2.7 408 四科分色（数据色）

| 科目 | Token | Dark | Light |
|------|-------|------|-------|
| 数据结构 | `--subject-ds` | `#A98CDD` | `#6B52B8` |
| 计算机网络 | `--subject-cn` | `#6E9BD9` | `#2F6BB8` |
| 计算机组成原理 | `--subject-co` | `#4FA9B8` | `#1F7E8C` |
| 操作系统 | `--subject-os` | `#DE85AC` | `#B2477F` |

> 着色用 `color-mix(in srgb, var(--subject-x) 14%, transparent)`；每科另有 `--subject-{ds,cn,co,os}-rgb`。

### 2.8 多智能体 / 流程 / 图表色（Dark；Light 有对应覆盖）

`--agent-coord #7c6af2` · `--agent-plan #C9A45E` · `--agent-diag #A98CDD` · `--agent-gen #6E9BD9` · `--agent-retrieve #4FA9B8` · `--agent-eval #DE85AC` · `--agent-quality #7FA98C` · `--agent-path #9A93B8` · `--agent-evidence #5AA396` · `--agent-gate #DCA03C`
`--flow-data/-control/-consensus` · `--nm-mix-from/-to` · `--mastery-low/mid/high/none` · `--edge-prereq/-related` · `--series-1..6` · `--seq-1..6`（连续色阶，基于 `--accent-rgb`）。

---

## 3. Typography Rules

- **Font Family**：`--font-sans: 'Geist','Outfit','Satoshi','Space Grotesk', -apple-system, BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei','Noto Sans SC', sans-serif`（**禁用 Inter**）；`--font-display = --font-sans`；`--font-mono: 'Geist Mono','SF Mono','JetBrains Mono','Fira Code',Consolas`。
- **设计哲学**：中文用系统字体栈零加载；层级靠**字号 + 字重 + 负字距**建立，不依赖颜色。数字用 `--font-numeric: tabular-nums` 等宽对齐。
- **单位**：优先 `rem`（`1rem = 16px`），支持浏览器 200% 文本缩放。

| 层级 | Token | Size |
|------|-------|------|
| Hero | `--text-6xl` / `--text-5xl` | 44px / 36px |
| Display | `--text-4xl` | 30px |
| H1 / 页面标题 | `--text-3xl` | 24px |
| H2 / 区块标题 | `--text-2xl` | 20px |
| H3 / 卡片标题 | `--text-xl` | 18px |
| 小标题 | `--text-lg` | 16px |
| 强调正文 | `--text-md` | 15px |
| **正文基准** | `--text-base` | 14px |
| 次要正文 | `--text-sm` | 13px |
| 辅助说明 | `--text-xs` | 12px |
| 角标 / 徽章 | `--text-2xs` | 11px |

**行高**：`--leading-none 1` / `tight 1.2`（大标题）/ `snug 1.35`（小标题）/ `normal 1.55`（正文）/ `relaxed 1.7`（讲解长段）。
**字重**：`--weight-regular 400` / `medium 500` / `semibold 600` / `bold 700`。
**字距**：`--tracking-tighter -0.022em`（大标题）/ `tight -0.011em` / `normal 0` / `wide 0.03em` / `caps 0.08em`（全大写 overline）。

---

## 4. Component Stylings

### Buttons（标准 `.btn` 体系 —— 唯一合法按钮类）

```css
.btn { display:inline-flex; align-items:center; justify-content:center; gap:.5rem;
  font-size:.875rem; font-weight:600; line-height:1; padding:.625rem 1.25rem;
  border-radius:var(--radius-md); border:1px solid transparent; cursor:pointer; transition:var(--transition); }
.btn-primary   { background:var(--gradient-primary); color:#fff; }          /* 实底 → 白字 */
.btn-primary:hover { opacity:.92; transform:translateY(-1px); box-shadow:var(--shadow-3); }
.btn-secondary { background:var(--color-surface-hover); color:var(--color-text); border-color:var(--color-border); }
.btn-ghost     { background:transparent; color:var(--color-text-2); }
.btn-soft      { background:var(--accent-primary-10); color:var(--accent-primary); }
.btn-danger    { background:var(--accent-danger-10); color:var(--accent-danger); }
.btn-sm / .btn-lg / .btn-block  /* 尺寸变体 */
.btn:disabled  { opacity:.5; cursor:not-allowed; transform:none !important; }
```

### Cards（玻璃态）

```css
.card,.stat-card,.feature-card { padding:1.25rem; border-radius:var(--radius-md);
  background:var(--glass-bg); border:1px solid var(--glass-border); box-shadow:var(--shadow-card);
  backdrop-filter:blur(var(--glass-blur)); transition:var(--transition); }
.card:hover { border-color:transparent; transform:scale(1.02);
  box-shadow:var(--shadow-card-hover), 0 0 0 1px var(--color-border-glow); }
```

### Inputs

```css
.rag-select,.answer-input,.conv-search-input { padding:.625rem .875rem;
  border-radius:var(--radius-sm); border:1px solid var(--color-border);
  background:var(--bg-input); color:var(--color-text); font-size:.875rem; transition:var(--transition); }
.rag-select:focus { border-color:var(--color-border-focus); box-shadow:0 0 0 3px var(--accent-primary-10); }
```

### Navigation（侧栏 `.nav-item`）

```css
.nav-item { display:flex; align-items:center; gap:.75rem; padding:.6875rem .75rem;
  border-radius:var(--radius-sm); color:var(--text-secondary); font-size:.875rem; font-weight:500; }
.nav-item:hover { background:var(--bg-card-hover); color:var(--text-primary); }
.nav-item.active { background:var(--accent-primary-10); color:var(--accent-primary); }
.nav-item.active::before { content:''; position:absolute; left:0; width:.1875rem; height:1.125rem;
  border-radius:0 .1875rem .1875rem 0; background:var(--gradient-primary); }
/* 学科色激活：.nav-item.active.nav-subject-0..3 → 对应 --subject-* */
```

### Badges / Tags（双主题自适应，勿硬编码 rgba）

```css
.tag-purple { background:color-mix(in srgb,var(--subject-ds) 14%,transparent); color:var(--subject-ds); }
.tag-blue   { background:color-mix(in srgb,var(--subject-cn) 14%,transparent); color:var(--subject-cn); }
.tag-cyan   { background:color-mix(in srgb,var(--subject-co) 14%,transparent); color:var(--subject-co); }
.tag-pink   { background:color-mix(in srgb,var(--subject-os) 14%,transparent); color:var(--subject-os); }
.tag-warm / .tag-green / .tag-primary   /* → --accent-warm / --accent-success / --accent-primary-10 */
```

### Modals / Drawers（`.panel-overlay` + 滑出面板）

```css
.panel-overlay { position:fixed; inset:0; background:var(--bg-overlay); z-index:300;
  opacity:0; pointer-events:none; transition:var(--transition-slow); backdrop-filter:blur(4px); }
.panel-overlay.open { opacity:1; pointer-events:auto; }
.profile-panel { position:fixed; top:0; right:0; bottom:0; width:25rem; max-width:90vw; z-index:400;
  transform:translateX(100%); transition:transform var(--duration-slow) var(--ease-emphasized);
  background:var(--glass-bg); backdrop-filter:blur(var(--glass-blur-heavy));
  border-left:1px solid var(--glass-border); box-shadow:var(--shadow-4); }
.profile-panel.open { transform:translateX(0); }
```

### Streaming / 状态基类（v9 流式三件套）

`.typing-indicator`（三点思考）/ `.stream-caret`（打字光标，`--cursor-color` + `mars-caret-blink`）/ `.skeleton*`（shimmer）/ `.empty-state` / `.error-bar` / `.engine-error`。

---

## 5. Layout Principles

- **Spacing System**：基准 **4px**，`--space-0(0)` … `--space-32(128)`（`--space-N == N×4px`）。**组件只允许使用本刻度，禁止 5px/13px/18px 等随意间距。**
- **圆角刻度**：`--radius-2xs 4` / `xs 6` / `sm 10` / `md 14` / `lg 18` / `xl 24` / `2xl 32` / `full 9999`。卡片 md，按钮 md，小元素 sm，胶囊 full。
- **App Shell**：侧栏 `--sidebar-width 220px`（折叠 `--sidebar-collapsed 72px`）+ 主区；顶栏 `--topbar-height 64px`；底栏 `--bottom-nav-height 64px`；内容 `--content-max-width 1280px`；对话 `--chat-max-width 900px`。
- **留白哲学**：卡片内距 20px（`1.25rem`），区块间距 16–24px，列表项 4–12px。**纵深靠阴影而非粗边框**——边框保持 0.09–0.11 低存在感。

---

## 6. Depth & Elevation

- **Shadow System**（纯中性，无彩色泛光）：

```css
--shadow-1: 0 1px 2px rgba(0,0,0,.40);
--shadow-2: 0 2px 4px rgba(0,0,0,.32), 0 1px 2px rgba(0,0,0,.24);
--shadow-3: 0 4px 12px rgba(0,0,0,.36), 0 1px 3px rgba(0,0,0,.28);
--shadow-4: 0 12px 28px rgba(0,0,0,.44), 0 2px 6px rgba(0,0,0,.30);
--shadow-5: 0 24px 56px rgba(0,0,0,.52);
--shadow-card:       0 1px 2px rgba(0,0,0,.34), 0 0 0 1px rgba(255,255,255,.04);
--shadow-card-hover: 0 8px 24px rgba(0,0,0,.42), 0 0 0 1px rgba(255,255,255,.07);
```
（Light 主题全部换为 `rgba(16,20,26,x)` 更淡、更扩散的柔和投影。）

- **Surface Layers**：`--color-canvas` → `--color-surface(-2/-3)` → `--color-elevated` → `--color-overlay`。
- **Z-index Scale**：`base 0` · `raised 10` · `sticky 100` · `dropdown 200` · `overlay 300` · `modal 400` · `popover 500` · `toast 600` · `tooltip 700` · `top 1000`。
- **Backdrop Effects**：玻璃 `backdrop-filter: blur(var(--glass-blur))`（10px）/**heavy**（18px）；遮罩 `blur(4px)`；`--glass-saturate 115%`。
- **兼容别名**：`--glow-primary/-strong/-secondary/-success` 保留令牌名（33 处引用），值已退化为中性投影（**非霓虹**）。

---

## 7. Do's and Don'ts

**Do's**
1. 组件只引用语义层 `--color-*` / `--subject-*` / `--accent-*` 变量，零裸 `hex`/`rgba`（唯一例外见 Don'ts 1）。
2. 新按钮一律 `.btn` + 变体；勿新增散落按钮类。
3. 学科/状态着色用 `color-mix(in srgb, var(--subject-x) 14%, transparent)`，自动适配明暗。
4. 圆角走 `--radius-*` 刻度；阴影走 `--shadow-*` 刻度；间距走 `--space-*`（4 倍数）。
5. 动效只动 GPU 属性：`transform / opacity / filter / clip-path` 与色彩类属性；时长用 `--duration-*`（受 `--motion-scale` 总闸控制）。
6. 图标 `currentColor` + 18–22px，随文本色变化。
7. 非原生可点击元素补 `role="button" tabindex="0"` + 键盘 handler；图标按钮补 `aria-label`。
8. 写组件先脑内渲染一遍 Light 主题，确认对比度与边框可见。

**Don'ts**
1. 勿直接写 `rgba(255,255,255,.06)` 这类裸值——改用 `--color-border` 等语义变量。**合规例外**：SVG `fill="currentColor"`；Canvas/内联 `:style` 的数据可视化运行时调色板；mask 用的 `#fff`；有色底上的 `color:#fff`。
2. 勿新增 `.xxx-btn` 散落按钮类（历史 `.engine-btn`/`.rag-btn` 已对齐 `.btn`）。
3. 勿用 `transform:scale()` 超 **1.02**。
4. Light 主题勿用强彩色发光（已降级为柔和中性投影）。
5. **勿把主色紫罗兰 `#7c6af2` 用于大面积填充**（仅按钮/激活态/细线），大面积用 surface 层级。
6. 勿在中文字体栈写非系统字体（零加载是核心约束）。
7. 勿用 `!important` 覆盖（除 `.btn:disabled` 必要场景）。
8. **勿用 `--color-warning`（琥珀）作错误/危险文字色**——错误必须 danger 系。
9. 勿用 `--color-accent`（ink 调）承载白字实底——实底必须用 `--color-accent-solid`。
10. 勿过渡 `width/height/top/left/margin/padding/font-size`（只动 GPU 属性）。

---

## 8. Responsive Behavior

| Breakpoint | Token | 范围 | 行为 |
|-----------|-------|------|------|
| Wide | `--bp-xl` | ≥1280px | 侧栏(220px)常驻 + 内容居中 |
| Desktop | `--bp-lg` | >1024px | 侧栏 220px 常驻；顶/底栏隐藏 |
| Tablet | `--bp-lg` | 769–1024px | 侧栏收为 72px 图标栏；`.grid-4` 4→2 列 |
| Mobile | `--bp-md` | ≤768px | 侧栏隐藏；顶栏(64px) + 底栏(64px) 接管；`.page-section` padding 收窄 |
| Small | `--bp-sm` | ≤480px | `.grid-4` → 1 列；hero 字号下调；输入区内距收窄 |

- **Touch Targets**：可点击元素最小 **44×44px**（移动端不低于 40px）。
- **折叠策略**：桌面侧栏 → 平板图标栏 → 移动顶栏汉堡 + 底栏 5 项 tab；对话历史桌面内联 → 移动全屏滑出(`100vw`)。
- **Font Scaling**：字号用 `rem`，支持浏览器 200% 缩放不破版；移动端 `--text-4xl` 等大字号逐级下调。
- **主题跟随**：`[data-theme="light"]` 仅覆盖语义层；初始化 `localStorage['mars408-theme'] > matchMedia(prefers-color-scheme) > dark`（由 `App.vue` 的 `applyTheme()` 写入 `document.documentElement.dataset.theme`）。
- **降级**：`prefers-reduced-motion` → `--motion-scale: 0`；`pointer: coarse` → `0.7`；`prefers-reduced-transparency` → 玻璃退化为实色 + `blur(0)`。

---

## 9. Agent Prompt Guide

### Quick Reference
MARS-408 设计系统 = **v11「砚 · Ink & Violet」**：克制深色 + **紫罗兰强调色 `#7c6af2` / 深紫 `#6b5cdb`** + 408 四科分色（数据结构 `#A98CDD` / 计网 `#6E9BD9` / 计组 `#4FA9B8` / 操作系统 `#DE85AC`）+ 零霓虹中性投影。**唯一真相源**：`src/assets/styles/_variables.css` 的 `:root` 语义变量。组件只引用变量，双主题（`:root` dark / `[data-theme="light"]`）自动适配。标准按钮 `.btn`，卡片 `.card`/`.glass-card`，标签 `.tag-*`，模态 `.panel-overlay` + `.profile-panel`。

### Component Prompts（可直接复制给 AI 代理）
```
1. 生成一个主操作按钮：class="btn btn-primary"，文字"开始学习"，左侧加 lucide 'play' 图标，圆角 --radius-md。
2. 生成一个资源卡片：外层 .card（padding 1.25rem，radius-md），内含 .card-header（标题 + 链接）、正文、底部 .tag-cyan 学科标签。
3. 生成一个学科筛选标签组：用 .tag-purple/.tag-blue/.tag-cyan/.tag-pink 表示数据结构/计网/计组/操作系统，背景用 color-mix 14% tint。
4. 生成一个错误提示条：class="error-bar"（danger-10 底 + danger-20 边 + --text-danger 文字），含关闭按钮。
5. 生成一个右侧滑出抽屉：结构 .panel-overlay(遮罩 blur4px) + .profile-panel(玻璃 blur18px, 宽 25rem, slide-in transform)，激活加 .open。
6. 生成一个统计卡片网格：父 .grid-4（4列 gap 1rem），子 .stat-card（顶部 3px 渐变条 opacity 过渡 + 图标 + 数值 1.875rem/700 + 变化标签）。
```

### Iteration Guide
1. **先读变量**：生成任何组件前，先读 `_variables.css` 的 `:root` 与 `[data-theme="light"]`，只引用已定义的 `--color-*`/`--subject-*`/`--radius-*`/`--shadow-*`/`--space-*`。
2. **禁止裸值**：若提示里写 `background:#7c6af2`，改为 `background:var(--color-accent)`；实底按钮用 `var(--gradient-primary)`。
3. **双主题自检**：每生成一个组件，脑内渲染一次 light 主题（白底），确认对比度与边框可见。
4. **按钮走标准**：新按钮一律 `.btn` 变体；除非改历史视图，否则不写 `.new-btn` 类。
5. **标签走 color-mix**：学科/状态标签用 `color-mix(in srgb, var(--subject-x) 14%, transparent)`，勿写死 `rgba`。
6. **圆角刻度**：卡片 md(14) / 按钮 md(14) / 小元素 sm(10) / 胶囊 full——勿用 12px 等非刻度值。
7. **阴影刻度**：优先 `--shadow-card` / `--shadow-3`，手写投影仅限特殊 hover（如 `--shadow-card-hover`）。
8. **间距 4 倍数**：padding/margin 用 4/8/12/16/20/24（`--space-*`）；避免 10/14/18 等非刻度值。
9. **图标 currentColor**：SVG 用 `stroke="currentColor"`，尺寸 18–22px，颜色随父文本变量。
10. **响应式收口**：新网格默认 4 列，补 `@media (max-width:1024px){2列}` 与 `480px{1列}`，对齐 `--bp-*` 断点。
11. **动效只动 GPU**：过渡用 `var(--transition)` 或 `--motion-*`，勿过渡 width/height。
12. **可达性**：可点击元素补 `:focus-visible` + 非原生元素补 `role/tabindex` + 图标按钮补 `aria-label`。
