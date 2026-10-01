# 学枢「墨与朱批」设计系统 → 芒得很职（study-help-pro）设计令牌转译报告

> 工程保障团队 · 技术文档师（Docu）
> 交付日期：2026-10-01
> 性质：**只读研究**（未修改任何源文件），仅新增本交付文件
> 参考项目（设计系统来源）：`E:\Program\学枢\frontend`（React / Next.js / Tailwind v4 / shadcn 风格）
> 目标项目（受益方）：`E:\Program\MARL\study-help-pro\src`（Vue 3 / Vite / 自绘 SVG / 无图表库）

---

## 📌 TL;DR

学枢的「墨与朱批」是一套**语义驱动**的纸墨美学：中性墨色承载界面、**朱红只用于"批改"语义**（驳回/薄弱/错题/当前）、墨绿=过审、赭石=待定，并配以「宋体标题 / 楷体批注声线」的双声线字体与「朱印/印章」品牌母题。它最值得借鉴的**不是色值本身，而是"颜色与语义强绑定"的纪律**——目标项目目前的 `--color-danger` 既当 UI 错误红、又当批改错误红，语义混用。结论：**色板不能照搬**（学枢是暖纸浅色系，目标项目是 dark-first 蓝灰 + 克制紫罗兰，两者哲学冲突），但**"批改专用朱红 + 楷体批注声线 + 朱印认证母题"这三点可低成本增量落地**，且与现有 v10「砚 · Ink & Clay」设计系统完全兼容、无需推翻任何现有令牌。

---

## 🎯 核心结论卡片

| 维度 | 结论 |
|---|---|
| **整体评级** | ★★★★☆（语义纪律与字体声线极佳；色彩方向与目标项目冲突，不能整体迁移） |
| **可迁移令牌数** | 色彩 3 枚新增（朱批红 / 墨绿过审 / 赭石待定）+ 字体 2 枚新增（楷体批注 / 宋体讲义标题）+ 动效 1 组对齐 ≈ **6 枚增量令牌 + 1 张语义映射表** |
| **高价值视觉点** | ① 朱红只承载批改语义；② 楷体 blockquote = 教师批注声线；③ 朱印/印章认证母题；④ 思考态三圆点 + aria-live 无障碍 |
| **落地成本** | **低**。全部为"新增令牌 + 新增组件"，零破坏；不动现有 72 个组件的任何引用 |
| **建议下一步** | 先落 P0「批改语义红」令牌 + P0「楷体批注声线」CSS，再落 P1「朱印 Seal」SVG 组件 + 画像雷达 SVG 组件 |

---

## 1. 色彩系统：学枢「墨与朱批」完整色板

### 1.1 设计哲学（学枢 globals.css 文件头注释，原文转述）

> 「墨与朱批」：中性墨色承载界面，朱红只用于"批改"语义（驳回 / 薄弱 / 错题 / 当前），墨绿=过审，赭石=待定。暗色 = 晚自习墨色（默认），浅色 = 纸面讲义。

这条纪律是整套设计系统的灵魂：**朱红不是"危险/错误"的通用红，而是专属于"批改动作"的语义红**。

### 1.2 完整色板（hex，来自 `app/globals.css` 的 `.desktop-scope` 块，最接近"墨与朱批"落地态）

**浅色 · 纸面讲义**（`.desktop-scope`，globals.css L101–127）：

| 令牌（学枢） | Hex | 语义角色 | 备注 |
|---|---|---|---|
| `--background` | `#f4efe4` | 暖纸底（宣纸米白） | 核心"纸"色 |
| `--foreground` | `#2b241a` | 浓墨正文 | 核心"墨"色 |
| `--card` | `#fcfaf4` | 纸面卡片 | 比底更亮一档 |
| `--surface-2` | `#ebe3d4` | 二级表面 | |
| `--popover` | `#fffdf7` | 浮层 | |
| `--primary` | `#76501f` | 深墨棕（主操作） | "墨"的实体承载 |
| `--primary-foreground` | `#fffaf0` | 墨底上的纸白字 | |
| `--secondary` | `#eee3cf` | 次级表面 | |
| `--muted` | `#eee8dc` | 弱化底 | |
| `--muted-foreground` | `#746b5e` | 淡墨灰（次文本） | |
| `--accent` | `#ead8b9` | 赭石浅底 | |
| `--accent-foreground` | `#3e2d18` | 赭石深字 | |
| **`--destructive` / `--danger`** | **`#a84436`** | **朱批红** | 全系统唯一"批改红" |
| `--border` | `#d8cebd` | 纸纹边框 | |
| `--input` | `#d4c9b8` | 输入边框 | |
| `--ring` | `#a26d28` | 聚焦环 | |
| **`--success`** | **`#3f7b4d`** | **墨绿·过审** | |
| **`--warning`** | **`#9a651f`** | **赭石·待定** | |
| `--info` | `#68664d` | 苔灰绿 | |

**补充色值**（散落在组件内，同样是"墨与朱批"体系的一部分）：
- `--desk-cinnabar: #bd392c`（`desktop-home-dossier.module.css` L8）——更鲜的朱批强调红，用于激活态/主 CTA。
- `--cinnabar: #a84436`（`marketing-home.module.css` L9）——营销页的朱批红。

**暗色 · 晚自习墨色**（`.dark .desktop-scope`，globals.css L128–151）：

| 令牌 | Hex | 语义 |
|---|---|---|
| `--background` | `#1d1a15` | 晚自习墨底 |
| `--foreground` | `#eee7d8` | 纸白字 |
| `--card` | `#27231c` | 墨色卡片 |
| `--primary` | `#c08a3d` | 暖金（晚自习下"灯"色） |
| `--danger` | `#df7768` | 朱批红（暗色提亮） |
| `--success` | `#72a97a` | 墨绿（暗色提亮） |
| `--warning` | `#d5a154` | 赭石（暗色提亮） |
| `--border` | `#4a4136` | 墨色边框 |

### 1.3 与目标项目现有色板的差异（关键判断）

目标项目（`study-help-pro/src/assets/styles/_variables.css` v10「砚 · Ink & Clay」）：

| 维度 | 学枢「墨与朱批」 | 目标项目现状 | 差异结论 |
|---|---|---|---|
| 主题取向 | 浅色纸面为主 + 晚自习暗色 | **dark-first**（画布 `#0E1217` 蓝灰近黑） | 方向相反，不可整体迁移 |
| 强调色 | 深墨棕 `#76501f` | 克制紫罗兰 `#7c6af2` | 各有品牌，保留各自 |
| 危险/错误红 | 朱批红 `#a84436`（只用于批改） | 通用 `--color-danger` `#E0685E`（dark）/ `#B8392F`（light） | **语义混用**：UI 错误与批改错误共用一色 |
| 成功绿 | 墨绿过审 `#3f7b4d` | `--color-success` `#4FA96B` | 基本对齐 |
| 警告 | 赭石待定 `#9a651f` | `--color-warning` `#DCA03C` | 基本对齐 |
| 数据色 | 无固定科目色 | 408 四科 `--subject-*` | 目标项目更成熟，保留 |

**核心建议**：不搬学枢的暖纸色板，而是**新增一枚"批改语义专用红"令牌**，把"批改/错题/驳回"从通用 `--color-danger` 中剥离出来，复刻学枢"朱红只承载批改"的语义纪律。落地代码见 §5。

---

## 2. 字体系统：宋体标题 / 楷体批注声线

### 2.1 学枢字体令牌（`app/globals.css` `@theme inline` L1737–1742）

```css
--font-sans:   "Inter", "PingFang SC", "HarmonyOS Sans SC", "MiSans",
               "Microsoft YaHei UI", "Microsoft YaHei", system-ui, sans-serif;
--font-mono:   "JetBrains Mono", "Cascadia Code", Consolas, "Microsoft YaHei", monospace;
--font-display: Georgia, "Songti SC", "STSong", SimSun, "宋体", serif;   /* 宋体标题 */
--font-kai:    "Kaiti SC", "STKaiti", KaiTi, "楷体", "Songti SC", serif; /* 楷体批注声线 */
```

> 注：源文件里 `宋体`/`楷体` 因编码显示为乱码（瀹嬩綋 / 妤蜂綋），但语义明确是「宋体」与「楷体」。

### 2.2 声线分工（学枢用法）

- **`--font-display`（宋体）**：标题、试卷题头《》、封面标题、大数字 KPI——营造"讲义/试卷"的印刷感。
- **`--font-kai`（楷体）**：`.chat-prose blockquote`（引用块 = 教师批注声线）、教师点评——营造"朱笔旁批"的手写感。
- **`--font-sans` / `--font-mono`**：正文 / 代码，与主流无衬线一致。

### 2.3 目标项目现状与差异

目标项目（`_variables.css` L46–52）**明确禁用衬线**：`--font-display: var(--font-sans)`，注释"仪表盘一律无衬线、禁用衬线体"。

**结论与建议**：不要动现有 `--font-sans/--font-mono`（仪表盘保持无衬线是对的）。但可**增量新增两枚"声线"令牌**，只用于教学/批改场景（试卷、讲义、点评、引文），不与仪表盘冲突：

```css
/* 建议新增（加在 _variables.css 第 1.1 节，主题无关原语）*/
--font-annotation: "Kaiti SC", "STKaiti", KaiTi, "楷体", "Noto Serif SC", serif; /* 教师批注/点评声线 */
--font-display-serif: "Songti SC", "STSong", SimSun, "宋体", "Noto Serif SC", serif; /* 讲义/试卷标题声线 */
```

### 2.4 中文 webfont 建议（授权需确认）

- **楷体（批注）**：推荐开源 **霞鹜文楷 LXGW WenKai**（SIL OFL 免费可商用），渲染稳定且"手写批注感"强于系统楷体。
- **宋体（讲义标题）**：推荐开源 **思源宋体 Source Han Serif / Noto Serif SC**（SIL OFL），替代系统 SimSun/Songti 的跨平台渲染差异。
- **系统字体回退**：macOS 有 `Kaiti SC`/`Songti SC`，Windows 有 `KaiTi`/`STKaiti`/`SimSun`，不引 webfont 也能跑，但三端字形粗细不一致。
- ⚠️ **授权/体积待确认**：引入 webfont 需确认 OFL 合规与打包体积（单个中文 webfont 通常 3–8MB，建议按需 subset）。

---

## 3. 品牌标识：朱印「智」字章 —— 勘误与对齐

### 3.1 重要勘误（诚实修正上游假设）

上游任务假设学枢的品牌标识是「朱印『智』字章」。**经核验，此假设不成立**：

1. 学枢的品牌标识是 **「学枢 / XUESHU」字标 + 红熊猫（red panda）吉祥物**（`public/brand/xueshu-app-icon.png`，2.4MB 吉祥物图标），见 `brand-lockup.tsx`、`layout.tsx`。
2. 全文 grep `智`：**不存在**「智」字章 logo；`智` 仅作为"智能体/智能教师/智能服务"的普通汉字出现。
3. `tests/brand-identity.test.mjs` 显式断言 `doesNotMatch(/智学伴|SMARTLEARN/)`——说明学枢项目**自己就是从旧品牌「智学伴 SmartLearn」迁移到「学枢 Xueshu」的**，"智"是旧品牌的痕迹而非现行标识。

### 3.2 "朱印/印章"的真实形态（可借鉴母题）

"朱印"在学枢里**不是一个 logo，而是一套"认证/批改时刻"的视觉母题**：

| 出现位置 | 实现 | 语义 |
|---|---|---|
| `paper-cover.tsx` 的 `Seal()` | 红熊猫图标放在试卷封面顶栏 | 试卷封皮的"落款章" |
| `marketing-home.module.css` `.artworkSeal` | 朱红描边 + 朱红小字印章块（`border:1px solid rgba(118,80,31,.28)` + `color: var(--cinnabar)`） | 营销插画上的"朱印" |
| `public/brand/discover/discover-seal-v1.png` | 独立印章图片 | 发现页的印章母题 |

### 3.3 对目标项目的对齐建议

目标项目已有 `芒得很职 + 芒小橙（mangxiaocheng.png）` 字标+吉祥物 lockup（`App.vue` L169–170），结构上与学枢一致，**无需改品牌**。建议只引入"朱印 Seal"组件母题，用于**认证/批改/已完成**时刻：

- 一个轻量 `<SealStamp>` Vue 组件：朱红圆角方框 + 白字（`已评` / `✓` / `过审` / 学科首字），颜色用 §5 新增的 `--color-annotation-red`。
- 使用场景：试卷批改完成、证据校验通过、知识掌握度"已掌握"等——**把"权威认证"从通用绿色对勾中区隔出来**。

---

## 4. 可视化范式（recharts → Vue3 对应实现）

目标项目 `package.json` **无 echarts / d3 / recharts / three 等图表库**，现有 `RingProgress.vue` / `ForceGraph.vue` / `KnowledgeGraph.vue` 全部为**自绘 SVG**。因此 recharts 的等价物问题是"要不要引入库"，而非"用哪个库"。

### 4.1 画像雷达（学枢 `profile-panel.tsx` 的 recharts `RadarChart`）

学枢实现要点（可逐条移植到 Vue3 自绘 SVG 雷达）：
- 描边色 `var(--chart-1)`，填充 `fillOpacity: 0.3`（已构建）/ `0.1`（未构建）。
- `PolarGrid stroke="var(--border)"`；`PolarAngleAxis tick fill="var(--muted-foreground)" fontSize 11`。
- `PolarRadiusAxis domain=[0,100]` 且隐藏刻度轴。
- `animationDuration={800}`；`DeltaChip`：涨 `text-success` + ↑、跌 `text-warning` + ↓、`tabular-nums`。

**Vue3 建议**：
- **首选**：手绘 SVG 雷达组件（6 维内），与 `RingProgress` 同风格，零新依赖，主题自动跟随 `--series-*`。
- **次选**（若需交互/缩放/大量系列）：引入 **ECharts + vue-echarts**，用 `--series-1..6` 映射 color 数组，`Radar` 系列 `areaStyle.opacity=0.3`。

### 4.2 思考态动效（学枢 `thinking.tsx` 的"思考中…"）

学枢实现：文本 + 三个 `animate-bounce` 圆点，`animationDelay: i*160ms`、`animationDuration: 1s`，`role="status" aria-live="polite"`。

**Vue3 建议**：目标项目已有 `.typing-indicator`（3 圆点、`typing-bounce 1.4s`，`_components.css` L108–109），但**缺 `aria-live="polite"` 与 160ms 错峰**。建议收敛为一个 `<ThinkingDots>` 组件：`aria-live="polite"` + 160ms 错峰，替代散落各处的打字指示器。

### 4.3 图表 frame（学枢 `chart-frame.tsx`）

学枢用 `useMounted()` 门控 + 固定高度占位，规避 Next SSR/hydration 的 `width(-1)` 告警。**Vue3 SPA 无 hydration 问题**，此门控 N/A；但"**固定高度占位、避免图表挂载前布局跳动**"的约定值得沿用（雷达/图表容器先预留高度）。

### 4.4 其它动效对齐（学枢 globals.css 动效区）

| 学枢动效 | 目标项目对应 | 对齐情况 |
|---|---|---|
| `agent-pulse`（思考脉冲 1.6s） | 已有 `mars-pulse-soft` | 基本对齐 |
| `edge-flowing`（图谱流动边 dasharray 6 10） | `KnowledgeGraph` 已自绘流动边 | 已对齐 |
| `progress-shimmer`（进度微光 1.4s） | `loader-slide` / skeleton sheen | 已对齐 |
| `prefers-reduced-motion` 全局降级 | `--motion-scale` 总闸 | 目标项目更成熟 |

---

## 5. 设计令牌转译表（学枢 Tailwind → 目标项目 CSS 变量）

### 5.1 语义映射表（可直接落地）

| 学枢令牌（Tailwind semantic） | 学枢值（浅色 hex） | 目标项目令牌 | 是否直接映射 | 说明 |
|---|---|---|---|---|
| `--color-background` | `#f4efe4` | `--color-canvas` | ⚠️ 仅语义对应 | 值不迁移（暖纸 vs 蓝灰） |
| `--color-foreground` | `#2b241a` | `--color-text` | ✅ 语义对应 | |
| `--color-card` | `#fcfaf4` | `--color-surface` | ✅ 语义对应 | |
| `--color-card-foreground` | `#2b241a` | `--color-text` | ✅ | |
| `--color-popover` | `#fffdf7` | `--color-elevated` | ✅ | |
| `--color-primary` | `#76501f` | `--color-accent` | ⚠️ 语义不同 | 各自品牌色，不互换 |
| `--color-primary-foreground` | `#fffaf0` | `--color-text-on-accent` | ✅ | |
| `--color-secondary` | `#eee3cf` | `--color-surface-2` | ✅ | |
| `--color-muted` | `#eee8dc` | `--color-surface-2` | ✅ | |
| `--color-muted-foreground` | `#746b5e` | `--color-text-3` | ✅ | |
| `--color-accent`（赭石浅底） | `#ead8b9` | `--color-surface-hover` | ≈ | 近似，可不着重 |
| `--color-destructive` / `--color-danger` | `#a84436` | `--color-danger` | ⚠️ **需拆分** | 见 §5.2 新增批改红 |
| `--color-border` | `#d8cebd` | `--color-border` | ✅ | |
| `--color-input` | `#d4c9b8` | `--color-border` | ✅ | |
| `--color-ring` | `#a26d28` | `--color-border-focus` | ✅ | |
| `--color-success` | `#3f7b4d` | `--color-success` | ✅ | |
| `--color-warning` | `#9a651f` | `--color-warning` | ✅ | |
| `--color-info` | `#68664d` | `--color-info` | ✅ | |
| `--color-chart-1..5` | 见 §1.2 | `--series-1..6` | ✅ | 目标项目已有 6 系列 |
| `--radius`（0.55–0.625rem） | — | `--radius-md`（14px） | ≈ | |
| `--font-sans` | Inter/PingFang | `--font-sans` | ✅ 保留 | |
| `--font-mono` | JetBrains Mono | `--font-mono` | ✅ 保留 | |
| `--font-display`（宋体） | Songti/STSong/SimSun | **新增** `--font-display-serif` | ➕ 新增 | 仅讲义/试卷标题 |
| `--font-kai`（楷体） | Kaiti/STKaiti/KaiTi | **新增** `--font-annotation` | ➕ 新增 | 教师批注声线 |
| `--ease-out-quart/quint` | cubic-bezier | `--ease-out` / `--ease-emphasized` | ✅ | |
| `--dur-fast/base/slow` | 150/200/300ms | `--duration-fast/normal/slow` | ✅ | |

### 5.2 建议新增令牌（可直接粘贴到 `_variables.css`）

```css
/* ===== 学枢「墨与朱批」语义增量（新增，不改任何既有令牌）=====
   理念来源：学枢 globals.css「朱红只承载批改语义，墨绿=过审，赭石=待定」。
   目标：把"批改/错题/驳回"从通用 --color-danger 中剥离，建立批改专用语义。 */

/* 深色主题（默认）· 追加到 [data-theme="dark"] 块内 */
--color-annotation-red:   #C05B4D;                 /* 朱批红 · 批改/错题/驳回/薄弱点 */
--color-annotation-red-bg: rgba(192, 91, 77, 0.14);
--color-annotation-red-border: rgba(192, 91, 77, 0.34);
--color-pass-green:       #4FA96B;                 /* 墨绿过审 · 复用 success 也可，独立命名更清晰 */
--color-pending-ochre:    #DCA03C;                 /* 赭石待定 · 复用 warning 也可 */

/* 浅色主题 · 追加到 [data-theme="light"] 块内 */
--color-annotation-red:   #B8392F;                 /* 朱批红（浅色压暗）*/
--color-annotation-red-bg: rgba(184, 57, 47, 0.09);
--color-annotation-red-border: rgba(184, 57, 47, 0.26);
--color-pass-green:       #2F7D4F;
--color-pending-ochre:    #8A6210;
```

> 说明：色值已按目标项目现有的 `--color-danger`（dark `#E0685E` / light `#B8392F`）与 `--color-success`/`--color-warning` 体系**就近取值**，未直接照搬学枢暖纸色值，保证在蓝灰画布上对比度达标、且与四科/语义色不冲突。

---

## ✅ 行动清单（P0 / P1 / P2）

| 优先级 | 行动 | 负责角色 |
|---|---|---|
| **P0** | 在 `_variables.css` 新增 `--color-annotation-red*` / `--color-pass-green` / `--color-pending-ochre` 令牌（§5.2），双主题各一套 | 前端（架构师确认 + 技术文档师同步 DESIGN.md） |
| **P0** | 新增 `--font-annotation`（楷体批注）/ `--font-display-serif`（宋体讲义标题）两枚声线令牌，并把 `.markdown-body blockquote` 的字体改为 `var(--font-annotation)`，复刻"批注声线" | 前端 |
| **P1** | 新增 `<ThinkingDots>` Vue 组件：三圆点 160ms 错峰 + `aria-live="polite"` + `role="status"`，替换散落的 `.typing-indicator` | 前端 |
| **P1** | 新增 `<SealStamp>` Vue 组件（朱印母题）：朱红圆角方框 + 白字（已评/过审/✓），用于批改完成/证据通过/已掌握 | 前端 + 设计 |
| **P1** | 新增手绘 SVG 画像雷达组件（零依赖），描边 `--series-1`、填充 opacity 0.3、`animationDuration 800ms`，替代/补充 ProfilePanel 的数值列表 | 前端 |
| **P2** | 在 DESIGN.md 追加「批改语义色」「字体声线」「朱印母题」三小节，与 §5 映射表同步，作为 AI 编码代理的唯一规范增量 | 技术文档师 |
| **P2** | 评估引入 霞鹜文楷 / 思源宋体 webfont（OFL 授权 + subset 体积确认后） | 前端 + 法务/合规 |
| **P2** | 全站扫描 `--color-danger` 的"批改"语义误用点，逐点替换为 `--color-annotation-red` | 前端（配合 code-reviewer） |

---

## ⚠️ 待完善 / 已知局限

1. **未实际渲染两项目**：本报告基于源码静态阅读（globals.css / 组件 / 测试），未启动前端截图比对，色板观感（如暖纸 `#f4efe4` 与蓝灰 `#0E1217` 的实际对比）需渲染后复核。
2. **中文 webfont 授权需确认**：霞鹜文楷 / 思源宋体虽为 SIL OFL，但具体打包/嵌入方式与子集体积未验证。
3. **"朱印『智』字章"为上游假设，已勘误**（§3.1）：学枢现行品牌是「学枢 + 红熊猫」，"朱印"是视觉母题而非 logo；若上游确有「智」字章素材，未在本仓库内找到，需另行提供。
4. **学枢 globals.css 存在三套主题并存**（`:root` OKLCH 默认 / `.dark` / `.desktop-scope` 暖纸），本报告以 `.desktop-scope`（最贴"墨与朱批"）为主，`:root` OKLCH 值与部分 `desk-study.css` 未逐一展开。
5. **色值建议为"就近取值"**：§5.2 新增令牌基于目标项目现有语义色体系推算，未经 WCAG 逐条机验，落地前建议跑一轮对比度校验（项目已有 `gate:a11y`）。
6. **recharts 等价物结论基于"目标项目零图表库"现状**：若后续引入 ECharts，需另行评估包体积与 SSR/懒加载策略。

---

## 📚 数据来源 & 成员产出索引

**参考项目（学枢）关键文件**：
- `E:\Program\学枢\frontend\app\globals.css`（L6–9 设计哲学注释；L11–61 `:root` OKLCH；L96–151 `.desktop-scope` 暖纸色板；L1704–1743 `@theme` 映射 + 字体令牌；L1761–1818 动效；L1820–1915 Markdown/批注声线）
- `E:\Program\学枢\frontend\app\layout.tsx`（品牌元数据 + KaTeX 引入）
- `E:\Program\学枢\frontend\components\thinking.tsx`、`markdown.tsx`、`chart-frame.tsx`、`profile-panel.tsx`
- `E:\Program\学枢\frontend\components\paper-cover.tsx`（朱印 Seal）、`components\layout\brand-lockup.tsx`、`components\marketing\marketing-home.module.css`（`--cinnabar`）、`components\desktop\desktop-home-dossier.module.css`（`--desk-cinnabar`）
- `E:\Program\学枢\frontend\tests\brand-identity.test.mjs`（品牌迁移证据：否定旧「智学伴/SmartLearn」）
- `E:\Program\学枢\frontend\public\brand\`（红熊猫图标、discover-seal-v1.png 等）

**目标项目（study-help-pro）关键文件**：
- `E:\Program\MARL\study-help-pro\src\assets\styles\_variables.css`（v10「砚 · Ink & Clay」完整令牌，深/浅双主题）
- `E:\Program\MARL\study-help-pro\src\assets\styles\_components.css`（`.typing-indicator`、`.markdown-body blockquote` 等）
- `E:\Program\MARL\study-help-pro\src\views\DesignSystemView.vue`（Living Style Guide）、`src\views\DesignUpgradeView.vue`（v11.1 升级原语）
- `E:\Program\MARL\study-help-pro\src\App.vue`（品牌 `芒得很职` + `mangxiaocheng.png`）、`src\components\RingProgress.vue`、`src\components\GlassCard.vue`
- `E:\Program\MARL\study-help-pro\DESIGN.md`、`package.json`

**团队成员产出索引（本交付）**：
- 本报告由 tech-writer-4（Docu）产出，聚焦**色彩 / 字体 / 品牌 / 可视化 / 令牌转译**五维度；架构与状态管理不在本文档范围（由 architect 系列成员负责）。
