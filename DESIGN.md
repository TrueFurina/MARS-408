# DESIGN.md — 芒得很职 / NetLearn 前端设计语言

> 本文件是 AI 编码代理生成 UI 时的**唯一设计规范**。任何新增/修改界面都必须遵循此处约定。
> 设计令牌的**数值真值源**是 `src/assets/styles/_variables.css`（v10「砚 · Ink & Clay」）。本文件描述"怎么用"，不重复定义十六进制值；组件一律引用语义令牌（`--color-*` / `--subject-*` / `--space-*` / `--radius-*` / `--transition`），**禁止在组件里写死颜色或间距**。

## 1. 视觉基调与氛围（Visual Theme）

- **深色原生（dark-first）**：画布是蓝灰近黑 `#0E1217`，不是纯黑。信息密度优先，靠明度分层（canvas → surface-1 → surface-2 → surface-3）与间距/字重分组，不靠装饰。
- **单一强调色（克制紫罗兰 `#7c6af2`）**：全站只有一个色相用于交互/强调/品牌；四科分色是"数据色"不是"装饰色"，只出现在学科标签、图表系列、知识图谱节点。
- **零霓虹**：禁止彩色发光（glow）；高度只靠中性投影 + 1px 描边表达。
- **设计取向 = Linear 精度 × Stripe 渐变质感**：
  - 借用 **Linear** 的"暗原生 + 极细半透明白描边 + 单一紫罗兰强调 + 明度阶梯 + 签名字重"工程感；
  - 借用 **Stripe** 的"轻字重标题 + 大字号负字距收紧 + 双主题恒定品牌色 + 克制的渐变与聚焦环"craft。
- **动效只动 GPU**：所有过渡只允许 `transform / opacity / background-color / border-color / color / box-shadow / filter`；**严禁** `transition: width/height/top/left/margin/padding/font-size`（进度条改用 `transform: scaleX()`）。

## 2. 调色板与角色（Color Palette & Roles）

所有值见 `_variables.css`；此处只列语义角色与对应令牌名。

| 角色 | 令牌 | 用法 |
|---|---|---|
| 画布 Canvas | `--color-canvas` | 页面底色（深 `#0E1217` / 浅 `#F5F6F7`） |
| 表面 Surface-1 | `--color-surface` | 卡片、输入底 |
| 表面 Surface-2 | `--color-surface-2` | 嵌套块、侧栏、代码区 |
| 表面 Surface-3 | `--color-surface-3` | 最高层（选中、代码高亮） |
| 玻璃态 | `--color-glass` / `--color-glass-border` | 顶栏、抽屉、悬浮按钮（配 `backdrop-filter: blur(var(--glass-blur))`） |
| 边框 | `--color-border` / `--color-border-light` / `--color-border-strong` | 默认 / 细 / 强 |
| 文本 | `--color-text` / `--color-text-2` / `--color-text-3` / `--color-text-disabled` | 主 / 次 / 弱 / 禁用 |
| 强调（双色调） | `--color-accent`（墨色·文字/图标/描边/焦点环）· `--color-accent-solid`（实底·白字） | 唯一品牌色相 |
| 强调悬浮/按下 | `--color-accent-hover` / `--color-accent-active` / `--color-accent-text`（深底上的强调文字） | |
| 白字（实底上） | `--color-text-on-accent`（= `#FFFFFF`） | 渐变/实底按钮、头像内的文字 |
| 语义状态 | `--color-success/warning/danger/info`（含 `-bg`/`-border` 淡底变体） | 只表达状态 |
| 408 四科（数据色） | `--subject-ds`(数据结构·紫) / `--subject-cn`(计网·蓝) / `--subject-co`(计组·青) / `--subject-os`(操作系统·粉) | 学科标签/图表/图谱；浅色主题自动压暗 |
| 掌握度 | `--mastery-low` / `--mastery-mid` / `--mastery-high` / `--mastery-none` | 知识图谱掌握度分段 |
| 多智能体/流程 | `--agent-*` / `--flow-*` | 流程可视化，勿用于常规 UI |

**四科分色是唯一容易漂移的地方**：永远用 `--subject-*`，不要在任何视图里硬编码 `#06b6d4 / #f59e0b / #22c55e / #7c6af2 / #3b82f6 / #8b5cf6` 等。改四科色只改 `_variables.css` 一处。

## 3. 字体排印（Typography）

- **字族**：`--font-sans`（首选 Geist / Outfit / Satoshi / Space Grotesk，中文回退 PingFang SC / Microsoft YaHei / Noto Sans SC）。**禁用 Inter。** 代码用 `--font-mono`（Geist Mono / JetBrains Mono）。
- **签名字重（关键）**：正文用 `--weight-regular`(400)，强调/UI 用 `--weight-medium`(500)，强强调用 `--weight-semibold`(600)。**不要用 700 作为常规强调**——6/700 仅留给 KPI 数值等极少数场景。
- **大字号负字距收紧**（Linear/Stripe 同款）：字号越大，字距越紧。
  - Hero (≥36px)：`letter-spacing: -0.02em ~ -0.03em`
  - 页面标题 (24–32px)：`-0.01em ~ -0.015em`
  - ≤16px：字距归零（`--tracking-normal`）
- **字号阶梯**：`--text-2xs`(11) → `--text-6xl`(44)，正文基准 `--text-base`(14)。数字用 `tabular-nums`（`--font-numeric`）便于纵向对齐。
- **行高**：大标题 `--leading-tight`(1.2)，正文 `--leading-normal`(1.55)，长段落 `--leading-relaxed`(1.7)。

## 4. 组件样式（Component Stylings）

### 按钮（三档，足够覆盖 99% 场景）
- **Primary（实底渐变）**：`background: var(--gradient-primary); color: var(--color-text-on-accent);` 字号 `--text-base`，圆角 `--radius-md`，内边距 `var(--space-3) var(--space-5)`。Hover：`transform: translateY(-1px)` + `box-shadow: var(--shadow-3)`（只动 GPU）。**不要用纯色实底（如 `#533afd`）**——用令牌。
- **Ghost / 次级**：`background: var(--color-surface-2); color: var(--color-text-2); border: 1px solid var(--color-border);` Hover：`background: var(--color-surface-hover); color: var(--color-text);`。
- **Pill / 标签按钮**：圆角 `--radius-full`，`border: 1px solid var(--color-border)`，`color: var(--color-text-2)`，内边距 `var(--space-1) var(--space-3)`。

### 卡片（Card）
- 背景 `var(--color-surface)`（或 `var(--color-glass)` + blur 用于浮层），**1px `var(--color-border)` 描边**（这是暗色下的"高度"主信号），圆角 `--radius-lg`。
- Hover：`background: var(--color-surface-hover)` + `box-shadow: var(--shadow-card-hover)` + 可选 `border-color: var(--color-border-strong)`。**不要**靠阴影制造深度，靠明度递进 + 描边。
- 避免 `box-shadow` 彩色泛光；用中性 `--shadow-*`。

### 输入（Input）
- `background: var(--color-surface-2); border: 1px solid var(--color-border); border-radius: var(--radius-md); color: var(--color-text);`
- **聚焦**：`border-color: var(--color-border-focus); box-shadow: var(--focus-ring);`（3px 环绕，品牌紫半透明）。绝不用纯 `outline`（除非 `:focus-visible` 全局已处理）。

### 徽章 / 标签（Badge / Pill）
- 状态：`background: var(--color-success-bg); color: var(--color-success); border: 1px solid var(--color-success-border);` 圆角 `--radius-2xs`/`--radius-full`。
- 学科标签：用 `--subject-*` 作文字/描边色，背景用其 14% 淡底（`color-mix(in srgb, var(--subject-ds) 14%, transparent)` 或现成 `--color-accent-subtle` 思路）。

### 导航（Navigation）
- 侧栏 220px（折叠 72px），顶栏 64px（移动端转顶+底栏）。导航项 `color: var(--color-text-2)`，Hover/Active → `var(--color-text)` 且左/下缘 `2px solid var(--color-accent)`。当前项可加 `var(--color-accent-subtle)` 淡底。

## 5. 布局原则（Layout）

- **间距 = 4px 刻度**：只用 `--space-1`(4) … `--space-12`(48) 及 `--space-14/16/20/24/32`。**禁止**出现 5/6/10/14/18px 等随意间距；需要 6px 时用 `--space-2`(8) 或 `--space-1`(4)。
- 内容最大宽度 `--content-max-width`(1280px)；卡片栅格 `grid` + `gap: var(--space-4)`。
- 留白哲学（Linear）：暗色即留白——大段 padding 撑出呼吸感；区块间用充足纵向间距（桌面 ≥ `--space-12`），不用可见分隔线。

## 6. 深度与高度（Depth & Elevation）

- **阴影 = 中性**，无彩色：`--shadow-1`…`--shadow-5`、`--shadow-card` / `--shadow-card-hover`。浮层用 `--shadow-4`/`--shadow-5`。
- **描边即高度**：暗色下 1px 半透明白边（`--color-border`）比阴影更能表达层级；悬浮时升级到 `--color-border-strong` 或加极淡 `var(--shadow-card-hover)`。
- **聚焦环**：`--focus-ring`（3px 品牌紫半透明），所有可交互元素 `:focus-visible` 可见。

## 7. 准则（Do's and Don'ts）

**Do**
- 组件只引用 `--color-*` / `--subject-*` / `--space-*` / `--radius-*` / `--transition` 等语义令牌。
- 四科色永远走 `--subject-*`。
- 大标题用负字距收紧；强调用 500/600 字重而非 700。
- 按钮实底用 `--gradient-primary`；白字用 `--color-text-on-accent`。
- 间距只用 `--space-N`；过渡只用 `--transition` / `--motion-*`。
- 暗色下用半透明白边表达层级，而非重阴影。

**Don't**
- 不要在组件里写死十六进制（`#7c6af2`、`#fff`、`rgba(255,255,255,.08)` 等）——用令牌。
- 不要引入第二品牌色或暖色（橙/黄）做装饰；紫罗兰是唯一强调。
- 不要用 `transition: all` 或 `transition: width/height`（reflow）；用 `--transition`。
- 不要纯色实底按钮（`#533afd` 之类）；用 `--gradient-primary` 或 `--color-accent-solid`。
- 不要纯黑 `#000` 标题 / 纯白 `#fff` 正文（用 `--color-text` 近白即可）。
- 不要 pill/大圆角（> `--radius-2xl`）于正式卡片；卡片 `--radius-lg`(18) 封顶。

## 8. 响应式（Responsive）

- 断点令牌：`--bp-sm`(480) / `--bp-md`(768) / `--bp-lg`(1024) / `--bp-xl`(1280)。
- **768px** = 侧栏 ⇄ 顶栏+底栏总开关；**1024px** = 图标栏/全侧栏分界。
- 触控目标 ≥ 40×40px；导航链接 ≥ 14px 且间距充足。
- 折叠策略：Hero 44px→32px→24px；卡片栅格 3→2→1 列；区块纵向间距桌面 ≥ `--space-12`、移动 ≥ `--space-8`。

## 9. Agent 提示指南（Agent Prompt Guide）

### 快捷取色
- 主 CTA 实底：`var(--gradient-primary)`，其上文字 `var(--color-text-on-accent)`
- 画布：`var(--color-canvas)`　表面：`var(--color-surface)`　描边：`var(--color-border)`
- 主文本：`var(--color-text)`　次文本：`var(--color-text-2)`
- 强调：`var(--color-accent)`（墨色）/ `var(--color-accent-solid)`（实底）
- 四科：ds `var(--subject-ds)` · cn `var(--subject-cn)` · co `var(--subject-co)` · os `var(--subject-os)`
- 聚焦环：`var(--focus-ring)`

### 生成组件示例（直接照抄结构）
- **Hero**：`background: var(--color-canvas)`；标题 `font-size: var(--text-5xl); font-weight: var(--weight-semibold); letter-spacing: -0.025em; color: var(--color-text);`；副标 `font-size: var(--text-md); color: var(--color-text-2); line-height: var(--leading-relaxed);`。CTA 用 `.btn-primary` 范式（上），次级用 ghost。
- **卡片**：`background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: var(--space-6);`；标题 `font-size: var(--text-xl); font-weight: var(--weight-semibold); color: var(--color-text);`；正文 `font-size: var(--text-base); color: var(--color-text-2);`。Hover 加 `var(--shadow-card-hover)` + `background: var(--color-surface-hover)`。
- **输入**：`background: var(--color-surface-2); border: 1px solid var(--color-border); border-radius: var(--radius-md); color: var(--color-text);`；`:focus` → `border-color: var(--color-border-focus); box-shadow: var(--focus-ring);`。
- **学科标签**：`color: var(--subject-ds); border: 1px solid color-mix(in srgb, var(--subject-ds) 35%, transparent); background: color-mix(in srgb, var(--subject-ds) 14%, transparent); border-radius: var(--radius-full); padding: var(--space-1) var(--space-3); font-size: var(--text-xs);`

> 记住：本文件是"味道"，`_variables.css` 是"数值"。改颜色/间距只动 `_variables.css`，不要在本文件或组件里硬编码。
