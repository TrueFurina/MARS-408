# MARS-408 · 动效与交互规范（纯 CSS 方案）

> 版本：v10「砚 · Ink & Clay」　日期：2026-09-12
> 配套文件：`src/assets/styles/_variables.css`（令牌源）、`src/assets/styles/main.css`（全局基类）
> 适用范围：`src/` 下 72 个组件 + 40+ 页面
> 约束来源：项目前端规范 —— 不引入动画库（零新增 npm 依赖）、只动 GPU 属性、必须支持 `prefers-reduced-motion`、触屏降级

---

## 0. 三条铁律

1. **零依赖**：不引入 GSAP / Framer Motion / Animate.css / auto-animate。全部用 CSS `transition` + `@keyframes`
   + 极少量 `IntersectionObserver` / Vue 内置 `<Transition>` 触发类名。
2. **只动 GPU 属性**：`transform` / `opacity` / `filter` / `clip-path` 可以动。
   颜色类（`background-color` / `border-color` / `color` / `box-shadow`）允许做**短过渡**（140ms），
   因为它们是绘制属性、不触发重排。
   **严禁过渡**：`width` `height` `top` `left` `right` `bottom` `margin` `padding` `font-size`
   `flex` `grid-template-*` —— 这些会触发 layout，长列表/图谱页会掉帧。
3. **一切走令牌**：时长、缓动、位移距离都引用 `--duration-*` / `--ease-*` / `--distance-*`，
   禁止在组件里写死 `0.3s`、`ease-in-out`。这样 `--motion-scale` 一处改动即可全站降级。

---

## 1. 令牌速查

### 1.1 时长（已乘总闸 `--motion-scale`）

| 令牌 | 基准值 | 层级 | 用途 |
|---|---|---|---|
| `--duration-instant` | 80ms | micro | 按压/tap 反馈 |
| `--duration-fast` | 140ms | micro | hover、focus、颜色过渡 |
| `--duration-normal` | 220ms | transition | 入场、下拉展开、折叠 |
| `--duration-slow` | 340ms | emphasis | 抽屉、模态、页面转场 |
| `--duration-slower` | 520ms | emphasis | 首屏 Hero 编排 |
| `--duration-enter` | 400ms | 兼容旧令牌 | 列表入场 |

### 1.2 缓动

| 令牌 | 值 | 何时用 |
|---|---|---|
| `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | 默认。起步快、收尾稳，交互反馈用这个 |
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | **入场**专用（元素进入视口/挂载） |
| `--ease-in` | `cubic-bezier(0.4, 0, 1, 1)` | **退场**专用 |
| `--ease-emphasized` | `cubic-bezier(0.05, 0.7, 0.1, 1)` | 大位移转场（抽屉、路由） |
| `--ease-spring` | `cubic-bezier(0.34, 1.42, 0.64, 1)` | 轻微回弹，**只允许作用于 transform** |
| `--ease-linear` | `linear` | 循环动画（shimmer、进度） |

> 规则：**进场用 out，退场用 in**。反了会显得"黏"。

### 1.3 组合令牌（推荐新代码直接用）

```css
--motion-micro      /* transform+opacity 140ms — hover / 按压 */
--motion-transition /* transform+opacity 220ms ease-out — 入场 / 展开 */
--motion-emphasis   /* transform 340ms emphasized + opacity 220ms — 转场 */
--motion-gpu        /* transform + opacity + filter — 需要模糊过渡时 */
--motion-colors     /* 仅颜色与描边 140ms */
```

### 1.4 兼容旧令牌（**已改语义，务必注意**）

`--transition` / `--transition-slow` / `--transition-bounce` 原值是 `all 0.2s ...`。
`all` 会连 `width/height/top/left/margin/padding` 一起过渡，违反铁律 2，**已改为显式安全属性清单**。

| 旧令牌 | 新值 | 引用数 |
|---|---|---|
| `--transition` | transform/opacity/背景/描边/文字/阴影 @140ms | 139 处 |
| `--transition-slow` | 同上 @340ms | 6 处 |
| `--transition-bounce` | 同上 @340ms + spring 曲线 | 12 处 |

**迁移影响**：任何依赖 `transition: all` 做**尺寸动画**的元素会变成"瞬跳"。逐处改为 `transform`：

```css
/* ✗ 错误：动画 height，触发重排 */
.bar { height: 0; transition: var(--transition); }
.bar.open { height: 200px; }

/* ✓ 正确：容器定高，内部用 scaleY */
.bar-wrap { height: 200px; }
.bar { transform: scaleY(0); transform-origin: top; transition: var(--motion-transition); }
.bar.open { transform: scaleY(1); }
```

```css
/* ✗ 错误：进度条动画 width */
.progress-fill { width: 0; transition: var(--transition); }
/* ✓ 正确：scaleX（父级定宽）*/
.progress-track { width: 100%; }
.progress-fill { width: 100%; transform: scaleX(0); transform-origin: left;
                 transition: transform var(--duration-slow) var(--ease-out); }
```

已知需处理的点：`_components.css` 的 `.stat-card:hover::before`（height）、
进度条类组件、`.conv-panel` / `.profile-panel` 的展开（后者已是 transform，OK）。

---

## 2. 分场景规范

### 2.1 入场 / 退场（组件挂载、列表出现）

**首屏关键内容不要入场动画**（会拖慢 LCP 感知）。只对"次级内容"做入场。

```css
/* 卡片 / 区块入场：淡入 + 上移 8~16px */
.enter {
  animation: mars-fade-up var(--duration-normal) var(--ease-out) both;
}
.enter-lg {                       /* 大区块用 16px 位移 */
  animation: mars-fade-up-lg var(--duration-normal) var(--ease-out) both;
}
.scale-in {                       /* 弹窗 / 气泡 */
  animation: mars-scale-in var(--duration-normal) var(--ease-out) both;
}
```

**列表错峰（stagger）**——只给前 8 项，超过不加延迟（否则长列表要等太久）：

```css
.list > * { animation: mars-fade-up var(--duration-normal) var(--ease-out) both; }
.list > *:nth-child(1) { animation-delay: 0ms;   }
.list > *:nth-child(2) { animation-delay: 30ms;  }
.list > *:nth-child(3) { animation-delay: 60ms;  }
.list > *:nth-child(4) { animation-delay: 90ms;  }
.list > *:nth-child(5) { animation-delay: 120ms; }
.list > *:nth-child(6) { animation-delay: 150ms; }
.list > *:nth-child(n+7) { animation-delay: 180ms; }
```

> 延迟必须用 `animation-delay` 而不是 JS 定时器；且 `animation-delay` **不受** `--motion-scale` 影响，
> 所以在 reduced-motion 分支里要单独清零（见 §4）。

**退场**：Vue `<Transition>` 的 `leave-active` 用 `--ease-in` + `--duration-fast`，
并加 `position: absolute` 或用 grid 塌陷，避免退场元素占位导致跳动。

### 2.2 滚动揭示（Scroll Reveal）

**不用 JS 库**。用 `IntersectionObserver` 加一个 class，动画交给 CSS：

```ts
// composables/useReveal.ts —— 约 15 行，无依赖
export function useReveal(selector = '[data-reveal]', root?: Element) {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) { e.target.classList.add('is-revealed'); io.unobserve(e.target) }
    }
  }, { rootMargin: '0px 0px -10% 0px', threshold: 0.05 })
  onMounted(() => document.querySelectorAll(selector).forEach(el => io.observe(el)))
  onUnmounted(() => io.disconnect())
}
```

```css
[data-reveal] {
  opacity: 0;
  transform: translate3d(0, var(--distance-enter-lg), 0);
  transition: opacity var(--duration-slow) var(--ease-out),
              transform var(--duration-slow) var(--ease-out);
}
[data-reveal].is-revealed { opacity: 1; transform: translate3d(0, 0, 0); }
```

要点：
- **禁止视差（parallax）**——本项目是学习工具，滚动视差会加剧眩晕且移动端必然掉帧。
- `unobserve` 必须调用，只播一次；重复播放会让人焦虑。
- 首屏元素直接加 `is-revealed`，不等 observer。

### 2.3 骨架屏（loading）

骨架屏的用途是**占位**，不是装饰。面积与真实内容对齐，避免加载完"跳一下"。

```html
<div class="skeleton skeleton-title"></div>   <!-- 标题 -->
<div class="skeleton skeleton-text"></div>    <!-- 一行文字 -->
<div class="skeleton skeleton-card"></div>    <!-- 卡片 -->
```

`_variables.css` 已提供 `.skeleton` 基类（`mars-shimmer`，动 `background-position`）；
`main.css` 保留 `.skeleton-stack / -text / -title / -card / -avatar / -chart` 尺寸类。

底色/高光：`--skeleton-base` / `--skeleton-sheen`，深浅主题自动切换。

**纯 GPU 变体**（长列表/大图表页用它，避免重绘整块背景）：

```css
.skeleton-gpu {
  position: relative; overflow: hidden;
  background: var(--skeleton-base); border-radius: var(--radius-sm);
}
.skeleton-gpu::after {
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent, var(--skeleton-sheen), transparent);
  animation: mars-sheen 1.4s var(--ease-linear) infinite;   /* 只动 transform */
}
```

> 骨架屏 `animation` **不要**放进 `prefers-reduced-motion` 的"完全静止"里——
> 用户仍需知道"在加载"。降级做法是**去掉位移、保留极缓的透明度呼吸**，或干脆静态底块 + 一行"加载中"文字。
> 本系统采用：reduced-motion 下 shimmer 关闭，显示为静态 `--skeleton-base` 底块。

### 2.4 页面转场（路由切换）

`App.vue` 已有 `.route-loader`（顶部 3px 进度条，z-index 9999 → 改用 `--z-top`）。
路由切换**不做整页淡入淡出**（会闪），做法是：

1. 顶部进度条：`transform: scaleX()` 推进，**禁止动画 width**。
2. 内容区：`<RouterView v-slot>` + `<Transition name="page">`，只做 8px 上移 + 淡入，220ms。
3. 不确定进度用 `mars-progress-indeterminate`（translate3d + scaleX）。

```css
.page-enter-active { transition: opacity var(--duration-normal) var(--ease-out),
                                 transform var(--duration-normal) var(--ease-out); }
.page-leave-active { transition: opacity var(--duration-fast) var(--ease-in);
                     position: absolute; inset: 0; }
.page-enter-from   { opacity: 0; transform: translate3d(0, var(--distance-enter), 0); }
.page-leave-to     { opacity: 0; }
```

### 2.5 hover / tap 触觉反馈

| 交互 | 做法 | 令牌 |
|---|---|---|
| 卡片 hover | `transform: translateY(-2px)` + 阴影升到 `--shadow-card-hover` | `--motion-micro` |
| 按钮 hover | 背景换 `--color-accent-hover`；**不要**放大整块按钮 | `--motion-colors` |
| 按钮 tap/active | `transform: scale(var(--scale-press))`（0.97），80ms | `--duration-instant` |
| 图标按钮 | 只变 `color` / 背景，位移 ≤ 1px | `--motion-colors` |
| 输入框 focus | 描边 → `--color-border-focus` + `--focus-ring`（3px 外环） | `--motion-colors` |
| 导航项 active | 左侧 3px 指示条用 `transform: scaleY()`，**不要**动画 height | `--motion-micro` |

```css
.btn-primary {
  transition: var(--motion-micro), var(--motion-colors);
}
.btn-primary:hover  { background: var(--color-accent-hover); }
.btn-primary:active { transform: scale(var(--scale-press)); transition-duration: var(--duration-instant); }
```

**禁止**：hover 时动画 `box-shadow` 的**模糊半径**做"发光"（重绘开销大且是霓虹观感）。
阴影切换只在两个定值（`--shadow-card` ↔ `--shadow-card-hover`）之间过渡，140ms 内完成。

### 2.6 流式输出 / 思考中

```css
.stream-caret { animation: mars-caret-blink var(--cursor-blink) steps(1, end) infinite; }
.thinking     { animation: mars-pulse-soft 1.6s var(--ease-standard) infinite; }
```

- 打字机光标：`--cursor-color` + `--cursor-blink`（1.1s），reduced-motion 下改为常亮。
- "思考中"呼吸：只动 `opacity`（`mars-pulse-soft`）。
  **不得**用 `pulse-glow`（旧 keyframes 动画 box-shadow 模糊半径，已列入待清理项）。

---

## 3. 关键帧清单（`_variables.css` 第 5 节，全局可用）

| 名称 | 动画属性 | 用途 |
|---|---|---|
| `mars-fade-in` | opacity | 最简淡入 |
| `mars-fade-up` | opacity + translate3d(8px) | 元素入场 |
| `mars-fade-up-lg` | opacity + translate3d(16px) | 区块入场 |
| `mars-scale-in` | opacity + scale(0.97) | 弹窗 / 气泡 |
| `mars-slide-in-right` / `-left` | opacity + translate3d(16px) | 抽屉 / 侧栏 |
| `mars-shimmer` | background-position | 骨架屏（绘制层） |
| `mars-sheen` | translate3d | 骨架屏 GPU 变体 |
| `mars-pulse-soft` | opacity | 思考中 / 流式 |
| `mars-progress-indeterminate` | translate3d + scaleX | 不确定进度条 |
| `mars-caret-blink` | opacity | 流式光标 |

全部加 `mars-` 前缀，与 `main.css` 中已有的 `fade-in` / `shimmer` / `pulse-glow` 不冲突。

> **待清理**：`main.css` 的 `@keyframes pulse-glow` 与 `@keyframes gradient-shift` 硬编码了
> 已废弃的紫色 `rgba(124,106,242,...)`，且 `pulse-glow` 动画 box-shadow 模糊半径。
> 后续实施阶段应删除 `pulse-glow`，相关引用改指 `mars-pulse-soft`。

---

## 4. 降级规则

### 4.1 `prefers-reduced-motion: reduce`（WCAG 2.3.3）

`_variables.css` 第 7.1 节把总闸 `--motion-scale` 置 **0**，所有 `calc(基准 × 0)` 的时长归零，
全站过渡即时完成。同时：

- `--cursor-blink: 0s` → 光标常亮不闪
- `--distance-enter / -lg: 0px`、`--scale-hover / --scale-press: 1` → 位移与缩放归零
- `.skeleton` 关闭 shimmer，退化为静态底块
- `main.css` 另有 `*` 选择器 + `!important` 的全局兜底（含 `scroll-behavior: auto`），两层保险

**补充（需实施阶段加到 main.css）**——`animation-delay` 不受 `--motion-scale` 影响，要单独清零：

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-delay: 0ms !important; animation: none !important; }
}
```

### 4.2 `pointer: coarse`（触屏 / 移动端）

- `--motion-scale: 0.7` → 所有动画提速 30%，观感更"跟手"
- `--distance-enter: 6px`、`--distance-enter-lg: 10px` → 位移减半
- `--glass-blur: 6px` / `--glass-blur-heavy: 10px` → **毛玻璃必须降级**
  （移动端 `backdrop-filter` 全屏模糊是主要掉帧源）
- **禁止**任何视差与滚动联动动画
- hover 态在触屏上会"粘住"，交互态统一改用 `:active` 表达

### 4.3 `prefers-reduced-transparency: reduce`

玻璃态退化为实色：`--color-glass` → 实色表面，`--glass-blur: 0px`。保证可读性优先。

---

## 5. 实施检查清单

- [ ] 全局替换 `transition: all` → `--motion-*` 组合令牌
- [ ] 进度条 / 折叠面板：width|height 动画 → `transform: scaleX()/scaleY()`
- [ ] 删除 `main.css` 的 `pulse-glow`、`gradient-shift`（硬编码紫 + 动阴影模糊）
- [ ] `.route-loader`（`App.vue:426`）z-index 9999 → `var(--z-top)`
- [ ] `_layout.css` / `_components.css` 中 **69 处硬编码紫色**
      （`rgba(124,106,242,*.**)`、`#7c6af2`）→ 改为 `rgba(var(--accent-rgb), α)` 或语义令牌
- [ ] 长列表页改用 `.skeleton-gpu` 变体
- [ ] 触屏下复核 `backdrop-filter` 使用点（顶栏、侧栏、悬浮按钮）
- [ ] 跑一遍 `prefers-reduced-motion` 与移动端真机验证

---

## 6. 反模式（Review 时直接打回）

| 反模式 | 为什么 |
|---|---|
| `transition: all` | 会连带布局属性，掉帧 |
| 动画 `width` / `height` / `top` / `left` | 触发 layout |
| 动画 `box-shadow` 模糊半径做发光 | 重绘开销大 + 霓虹观感（本项目已明令禁止） |
| 写死 `0.3s ease-in-out` | 绕过 `--motion-scale`，降级失效 |
| 入场用 `--ease-in` / 退场用 `--ease-out` | 方向反了，手感发黏 |
| 列表 stagger 延迟 > 200ms 或不限项数 | 长列表等待过久 |
| 滚动视差 | 学习工具易致眩晕，移动端必掉帧 |
| 重复播放入场动画（不 `unobserve`） | 分散注意力 |
| hover 放大整块按钮 | 视觉噪音 |
| 首屏关键内容加入场动画 | 拖慢 LCP 感知 |

---

## 7. Emoji 清理规范（ANTI-EMOJI）

> 本节由主理人补写（原 designer 因额度中断，Emoji 一节缺失）。
> 依据 `frontend-dev` 规范：**UI 图形一律用图标承担，禁止 emoji 充当图标**。

### 7.1 为什么禁 emoji

| 维度 | 问题 |
|---|---|
| **可控性** | emoji 字形由系统字体决定，Windows/macOS/Linux/Android 渲染差异大，无法统一 sizing / 颜色 / stroke |
| **主题适配** | emoji 是彩色位图，深色主题下会「发光撞色」，无法跟随 `currentColor` 与品牌色 |
| **可访问性** | 屏幕阅读器会把 emoji 读成一段冗长描述（"raising hands"），噪化朗读 |
| **专业观感** | 竞赛评审场景下，正文/按钮/导航夹 emoji 显得业余 |
| **对齐** | emoji 基线、行高不可控，混排时文字抖动 |

**结论**：任何**承担信息/操作语义**的位置（导航、按钮、标签、分组标题、状态徽标、空态指引）一律用 `icons.ts` 中的 lucide SVG；emoji **不得**出现在这些位置。

### 7.2 分级处置策略

| 层级 | 位置 | 处置 |
|---|---|---|
| **L1 交互层（硬约束）** | 导航项 / 按钮 / 分组标题 / Tab / 徽标 / 表单标签 | **必须**换成 lucide 图标，不得留任何 emoji。**已达标**：`src/router/navConfig.ts` 全量 0 emoji。 |
| **L2 内容层（建议清理）** | 成就名、等级名、种子数据、演示文案、卡片标题中的装饰 emoji | 移除 emoji 字符，保留纯文字；若该处需要图形，另加 lucide 图标 |
| **L3 数据层（保持不动）** | 用户输入、导入的题库原文、`seedTextbooks.ts` 教材原文字符串 | **不改**（属原始数据，改动会破坏可追溯性） |

### 7.3 emoji → lucide 对照表（本项目高频）

| emoji | 语义 | lucide 图标（`icons.*`） |
|---|---|---|
| 🏆 🏅 🎖️ | 成就 / 奖牌 | `star` / `award` |
| 🎯 | 目标 / 素养对抗 | `target` |
| 🚀 | 快速开始 / 启动 | `rocket` |
| 📚 📖 | 知识库 / 教材 | `book` / `bookOpen` |
| 🔍 | 检索 / 复盘 | `search` |
| 💡 ✨ | 灵感 / 生成 | `sparkle` |
| ⚡ 🔥 | 性能 / 热点 | `zap` / `flame` |
| ✅ | 通过 / 正确 | `check`（`checkCircle`） |
| ❌ | 失败 / 错误 | `x`（`xCircle`） |
| ⚠️ | 警告 | `alertTriangle` |
| 📊 📈 📉 | 数据 / 趋势 | `barChart` / `trendUp` / `trendDown` |
| 🧠 | 记忆 / 学情 | `brain` |
| 🎓 | 学习 / 教学 | `graduation` |
| 🛡️ | 安全 / 审计 | `shield` |
| 🧪 🔬 | 实验室 | `flask` / `microscope` |
| 📝 | 记录 / 笔记 | `fileText` / `edit` |
| ⚙️ 🔧 | 设置 / 工坊 | `setting` / `wrench` |
| 💬 | 对话 | `chat` |
| 🤖 | 智能体 / AI | `agent` / `bot` |
| 🧩 | 模块 / 技能 | `puzzle` |
| 🧭 | 浏览 / 导航 | `compass` |
| 🕸️ | 知识图谱 | `knowledge`（图网络） |
| 💻 | 代码沙箱 | `terminal` / `code` |
| 🐛 | 缺陷 | `bug` |
| 📅 ⏱️ | 计划 / 时间 | `calendar` / `clock` |
| 🔄 ♻️ | 重建 / 刷新 | `refresh` |
| 👤 | 用户 / 画像 | `user` |
| ⭐ ❤️ 👍 | 收藏 / 点赞 | `star` / `heart` / `thumbsUp` |

> 若 `icons.ts` 暂无匹配项，**新增 SVG 图标**，不要退回 emoji。

### 7.4 当前存量（2026-09-12 扫描）

- **L1 交互层：0 残留** ✅（`navConfig.ts` 已验证；App.vue / MoreMenu.vue 已改为纯图标 + 纯文字）
- **L2 内容层存量**（按出现数降序，待下一轮清理）：
  `ProfileView.vue(39)` · `SkillStudioView.vue(31)` · `ShowcaseView.vue(29)` · `achievementStore.ts(27)` ·
  `seedTextbooks.ts(24)` · `KnowledgeGraph.vue(22)` · `EvidenceCheckPanel.vue(20)` · `XfyunWorkshop.vue(19)` …
  全量约 **60 个文件**，多为成就/等级/演示文案中的装饰 emoji。

### 7.5 安全清理流程（机械替换前必读）

1. **只删字符，不改结构**：`name: '🏆 初出茅庐'` → `name: '初出茅庐'`。**禁止**把 emoji 当 key / index / 匹配条件使用（先 `grep` 确认该 emoji 未参与逻辑比较）。
2. **逐文件、小批量**：单文件改完立即 `npx vite build` 验证，不要一次性 sed 全仓。
3. **不要用管道过滤判成败**（缓冲会吞失败行）——改用 `cmd > out.txt 2>&1` 落盘后统计。
4. **含反引号/反斜杠的文本不要用 heredoc/sed 搬运**（MSYS 会静默改写），一律用编辑器逐条改。
5. **`seedTextbooks.ts` 等 L3 数据不动**。
6. 完成后跑扫描确认：`grep -rlP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}]" src/`
