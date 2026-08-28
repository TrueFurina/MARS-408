# MARS-408 页面级 UI 美化缺口清单（2026-07-17）

> UI Designer 评估结论：设计系统层（令牌 / 双主题 / WCAG AA / px→rem / 空状态组件 / 骨架屏 / 动效库 / 减弱动效）已扎实，**剩余均为页面级 polish，非地基问题**。

## ✅ 已扎实（无需再做）
- 设计令牌 + 双主题（dark 默认 / light 覆盖语义层）+ WCAG AA（`:focus-visible` / 44px 触控 / 语义对比）
- px→rem 全量迁移完成（2026-07-17）
- `.empty-state` 组件：图标 + 标题 + 描述 + 操作（main.css:94）
- **真骨架屏**已落地：DashboardView(`dashboard-skeleton`)、ProfileView(`profile-skeleton`)、SettingsView(`settings-skeleton`)、KnowledgeView、AdminView、AssessmentView
- 完整 keyframe 库：fade-up / fade-in / shimmer / pulse-glow / gradient-shift / slide-in-right / scale-in / page-in / stagger-in / route 过渡 / msg-fade-in / typing-bounce / btn-in
- `prefers-reduced-motion` 完整降级块（main.css:1787，`animation/transition-duration:0.001ms`）
- 聊天侧栏微交互丰富（hover 显删除、菜单按钮发光）

## 🔶 真实缺口（按优先级）

### P1 — 加载态不一致（最值得做，低风险）
6 个视图仍用**纯文本「加载中...」空状态**占位，而其他页面用真骨架屏 → 视觉断裂，评委易察觉。
- `src/views/CreatorDashboardView.vue:57`
- `src/components/StepQuiz.vue:131`
- `src/views/QuizHistoryView.vue:38`
- `src/views/SkillDetailView.vue:162`
- `src/views/SkillMarketView.vue:164`
- `src/views/TeacherView.vue:34`
**建议**：抽共享 `<Skeleton>` 组件（含 `skeleton`/`skeleton-card` 类已在 main.css:116 定义 shimmer），统一 loading 模式；或至少替换为同构骨架占位块。

### P2 — 聊天气泡缺 hover 反馈（轻微）
`.message-bubble`（main.css:865）为静态样式，仅 user 气泡有一道静态阴影；无 `:hover` 规则。侧栏微交互已很丰富，气泡却无反馈 → 轻微不一致。
**建议**：补 `.message-bubble:hover` 背景微变 + 可选 `translateY(-1px)` 轻抬升（需纳入 `prefers-reduced-motion` 已自动降级）。

### P3 — 空状态插图未统一（情感化）
部分空状态带图标（Dashboard 用 `icons.dashboard`），部分纯文字。统一补插图/图标可提升首屏情感化与品牌一致性。
**建议**：为各视图空状态补语义图标（复用 `icons.ts`），保持 `.empty-state svg` 既有样式（main.css:107）。

## 📌 不做（避免无用功）
- 不重造令牌 / 主题 / 骨架体系（已成熟）
- 不 mass-rename 内联 var 变体（非裸值，之前已判定）
- 不新增页面级大改（地基稳，仅需上述三处 polish）

---

## ✅ 已落地（2026-07-17 晚，响应"继续"全做 P1+P2+P3）

### P1 — 共享骨架屏组件 + 6 视图统一 ✅
- 新增 `src/components/Skeleton.vue`：封装 main.css `.skeleton`/`skeleton-shimmer`，支持 `variant`(block/text/title/card/avatar/circle/chart) + `count`/`width`/`height`/`radius`/`label`，带 `role="status"` + `aria-busy` 无障碍，自动受 `prefers-reduced-motion` 保护。
- `main.css` 新增骨架容器类：`.skeleton-grid-2` / `.skeleton-grid-auto` / `.skeleton-span-2` / `.skeleton-row` / `.skeleton-list` / `.skeleton-header` / `.skeleton-header-body`（统一 6 视图 loading 布局，免各自 scoped 网格）。
- 6 视图 loading 态替换为内容匹配骨架（原纯文本「加载中...」全部清除，Grep 实测 0 处残留）：
  - CreatorDashboardView:57 → `skeleton-grid-2`（2 卡 + 1 通栏）
  - StepQuiz:131 → `skeleton-list`（3 行块）
  - QuizHistoryView:38 → `skeleton-row`(4 块) + `skeleton-list`(5 行)
  - SkillDetailView:162 → `skeleton-header`(头像+标题+行) + 块 + 4 行文本
  - SkillMarketView:164 → `skeleton-grid-auto`（6 卡）
  - TeacherView:34 → `skeleton-grid-2`（2 卡 + 1 通栏）
- 注意：项目 `.vue` 组件导入约定带扩展名，故均用 `@/components/Skeleton.vue`（首轮漏 `.vue` 致 vue-tsc 报 TS2307，已修正）。

### P2 — 聊天气泡 hover 微交互 ✅
- `main.css` 补 `.message-bubble { transition }` + `.message.user .message-bubble:hover{translateY(-1px)+更强阴影}` + `.message.assistant .message-bubble:hover{背景微变+边框高亮}`，与侧栏微交互风格一致，受 reduced-motion 自动降级。

### P3 — 空状态插图统一 ✅（首轮：3 个 no-data 态）
- StepQuiz「暂无步骤化题目」→ `icons.quiz`
- QuizHistoryView「暂无答题记录」→ `icons.history`
- SkillMarketView「暂无技能」→ `icons.skill`
- 复用全局 `.empty-state svg` 样式（main.css:107，宽 3.25rem / opacity 0.25 / accent 色），与 Dashboard `icons.dashboard` 风格统一。

### P3 扩展 — 全量空状态插图统一（响应"都要"，2026-07-17 深夜）
将语义图标接入**全部剩余纯文字 / emoji 空状态**，达成与 Dashboard `icons.dashboard` 一致的插图体系。

**主干（页面级 → 统一 `<EmptyState :icon>` 玻璃卡插图）**
- `KnowledgeView` 错误态「加载失败」→ `icons.warning`（替换 ⚠️ emoji）+ 重加载按钮进 `#action` 槽
- `KnowledgeView` 空数据「暂无知识图谱数据」→ `icons.knowledge`（新增）
- `AdminView` 错误态「⚠️ {error}」→ `icons.warning`（替换 ⚠️ emoji）+ 重试按钮进 `#action` 槽
- `TeacherView`「暂无教师数据」→ `icon="📊"` emoji 替换为 `:icon="icons.chart"`

**子面板 / 行内（轻量 `inline-icon` 语义 SVG，沿用全局 `[class*="icon"] svg` 1.25rem 尺寸）**
- `KnowledgeAdminView` 文档空列表「暂无文档」→ `icons.document`；统计微占位两处「无数据」→ `icons.chart`
- `MindMapViewer`「暂无思维导图内容」→ `icons.knowledge`
- `CreatorDashboardView`「暂无使用数据」→ `icons.chart`；「还没有创建技能」→ `icons.skill`
- `ChatView` 侧栏「暂无对话记录」→ `icons.chat`
- `AssessmentView`「暂无薄弱点数据」→ `icons.chart`
- `AdminView` 统计微占位「暂无答题数据」「暂无答题」→ `icons.chart`
- `HistoryDropdown` 下拉「暂无对话 / 未找到匹配的对话」→ `icons.history`

**设计系统补强**
- `main.css` 新增全局 `.inline-icon` 工具类（`display:inline-flex; vertical-align:middle; margin-right:.375rem; color:var(--accent-primary)`），统一行内语义图标对齐；其内 svg 尺寸由既有 `[class*="icon"] svg` 规则（1.25rem）接管。该工具类同时修正了 `AssessmentView:80` 原先 `inline-icon` 无尺寸基类的隐患。
- 全站空状态现已**零 emoji / 零纯文字**（仅剩语义 SVG），与 Dashboard 插图语言完全统一。
- 仍保留为纯文字的是「内容级 fallback」（如 `skill.description || '暂无描述'`、`*暂无内容*` markdown 占位、`EvidenceCheckPanel` 的「暂无」标签）与「内容内 ⚠️ 警示」（错误条 / 合规命中），这些属内容语义而非空状态插图，不在本轮范围。

### 验收（P3 扩展后）
- `vue-tsc --build` 零错误（TSC_EXIT=0）
- `vite build --outDir dist-rem` ✅ built in <1s（全组件编译通过）
- 修复：转换 `<div v-else-if>` → `<EmptyState>` 时一度漏写 `v-else-if` 指令致 `v-else` 兄弟节点无配对 `v-if`，编译报错；已在 KnowledgeView / AdminView 补回条件链后通过。

---

## ✅ 已落地（2026-07-17 深夜 续 — 响应"所有人深度继续"，收口最后结构缺口）

### AuditLogView — 全面接入 icons.ts 语义图标体系（关闭最后一处 emoji 空状态）
此前 P3 扩展已使全站空状态零 emoji，但 **AuditLogView 漏网**（其 `EmptyState` 仍用 `icon="📋"` emoji，且页头/刷新按钮/行内元信息仍用 emoji），成为唯一残存的结构性 emoji 缺口。本轮一次性收口：

- `import { icons } from '@/components/icons'`（补齐导入，沿用既有 `.vue` 扩展名约定）
- 页头标题 `🛡️ 安全审计日志` → `<span class="ttl-ico" v-html="icons.shield">` + 文字（`icons.shield` 语义贴合"安全审计"）
- 刷新按钮 `🔄 刷新` / `加载中...` → `<span class="rf-ico" :class="{spinning:loading}" v-html="icons.refresh">` + `{{ loading ? '加载中...' : '刷新' }}`；加载时 refresh 图标 `rf-spin` 旋转（0.8s linear），保留 app 统一的「加载中...」按钮文案态，受 `prefers-reduced-motion` 降级
- `EmptyState icon="📋"` → `:icon="icons.document"`（审计记录即文档语义）
- 行内元信息 `👤`/`🌐` → `<span class="li-ico" v-html="icons.user">` / `icons.globe`（行内 0.875rem 灰阶图标，对齐行高）

配套 scoped 样式：`.ttl-ico`(1.5rem/accent) / `.rf-ico`(1.0625rem/currentColor + spin) / `.li-ico`(0.875rem/--color-text-3) + `@keyframes rf-spin` + `@media (prefers-reduced-motion: reduce){.rf-ico.spinning{animation:none}}`。类名刻意避开全局 `[class*="icon"] svg` 1.25rem 规则（`ttl-ico`/`rf-ico`/`li-ico` 不含子串 `icon`），尺寸由 scoped 精确控制。

**效果**：全站空状态现已 **100% emoji-free**（所有 `EmptyState` 均走 `:icon="icons.*"` 或 `.inline-icon` 语义 SVG）；AuditLogView 成为继其余视图后完全进入图标体系的参考页。

### 验收（本轮）
- `vite build --outDir dist-rem` ✅ `built in 2.84s`（AuditLogView 编译通过，exit 0）
- `vue-tsc --build` 仍存在 **3 处预存 TS 错误（与本轮无关，非 AuditLogView）**：
  - `DashboardView.vue:151` `store.quizHistory` 不存在于 store（残留引用；`AssessmentView` 已改用本地 `quizHistory` ref）
  - `ProfileView.vue:95` 同上 `store.quizHistory`
  - `KnowledgeView.vue:47-50` `noUncheckedIndexedAccess` 严格态下 `SUBJECT_TOKENS[0]` 推为 `string | undefined`
  - 根因：上述为前序"残留修复"(2026-07-17/18) 移除/重命名 store 的 `quizHistory` 属性及 tsconfig 严格化所致，属独立回归，需在"store API 对齐"专项中处理（Dashboard/Profile 两处需先定"替代数据源"再改，勿盲改行为）。本轮 UI 收口不动它们。

## ⏭️ 后续可选波次（待用户拍板，非本轮回填）
- ~~**波次 A — 全站页头/章节标题 emoji 迁移**~~ ✅ 已完成（见下）
- ~~**波次 B — 按钮 hover/focus 微交互系统化**~~ ✅ 已完成（见下）
- ~~**波次 C — store API 类型对齐**~~ ✅ 已完成（见下，含顺手清零的 KnowledgeGraphView 预存报错）

---

## ✅ 已落地（2026-07-19 — 响应"很好 都要"，A+B+C 三波全量收口）

### 波次 A — 页头/章节标题 emoji 全量迁移到 icons.* ✅
审计全站 `section-title` / `card-title` / `dash-card-title` 的 emoji 前缀，锁定 3 个视图共 12 处（Admin / Teacher / CreatorDashboard），全部替换为语义 SVG，与 AssessmentView / BenchmarkView 已建立的 `section-title-icon` / `card-title-icon` 约定一致。

**AdminView**（4 处）
- `📊 平台数据看板` → `icons.dashboard`
- `📈 近 7 日答题量` → `icons.chartUp`
- `📚 各科掌握度分布（平台平均）` → `icons.bookOpen`
- `👥 用户总览` → `icons.user`

**TeacherView**（4 处）
- `📊 教师端看板` → `icons.dashboard`
- `👥 学生概览` → `icons.user`
- `📚 知识库统计` → `icons.knowledge`
- `📈 班级分析` → `icons.chart`

**CreatorDashboardView**（4 处）
- `📊 创作者看板` → `icons.dashboard`
- `📦 技能概览` → `icons.skill`
- `📈 近 7 天调用趋势` → `icons.chartUp`
- `📋 我的技能` → `icons.skill`

**设计系统补强（main.css）**：抽全局工具类，结束各视图重复声明 `.section-title-icon` / `.card-title-icon` 的局面：
```css
.section-title-icon, .card-title-icon { display:inline-flex; vertical-align:middle; margin-right:.375rem; color:var(--accent-primary); }
.section-title-icon svg { width:1.25rem; height:1.25rem; }
.card-title-icon svg { width:1.125rem; height:1.125rem; }
```
尺寸与 AssessmentView / BenchmarkView 既有 scoped 定义完全一致（1.25 / 1.125rem），新视图与存量视图零差异。Grep 实测 3 视图标题 emoji **0 处残留**。

### 波次 B — 按钮 hover/focus 微交互系统化 ✅
既有 `.btn` 体系（`.btn-primary/.secondary/.ghost/.soft/.danger` + `.btn-sm/.lg/.block`）及历史按钮 `.engine-btn`/`.rag-btn`/`.answer-submit-btn` 已统一 hover 抬升 + glow、`:disabled` 降透明，且全局 `button:active{scale(.97)}` 已给按压反馈。审计发现的真实缺口：**焦点环用 `box-shadow`，在 `overflow:hidden` 卡片内会被裁剪**。

**补强（main.css）**：为按钮族加 `outline` 兜底焦点环（不被裁剪，WCAG 2.4.7）：
```css
.btn:focus-visible, .engine-btn:focus-visible, .rag-btn:focus-visible, .answer-submit-btn:focus-visible {
  outline: 2px solid var(--accent-primary); outline-offset: 2px; box-shadow: none;
}
```
与全局 `:focus-visible{box-shadow:var(--focus-ring)}` 互补——按钮类用 outline（更稳健），其余元素保留 box-shadow 光环。

### 波次 C — store API 类型对齐 ✅（vue-tsc 恢复零错误门禁）
修复 3 处 `vue-tsc` 报错，并顺手清零增量编译新暴露的 KnowledgeGraphView 预存报错：

**1. ChatView(389) `store.currentUser` 不存在**
- 根因：`studyStore` 的 `currentUser` 是 `computed` 但类型 `Pick<...>` 未暴露到 `useStudyStore` 返回类型。
- 修复：ChatView 本地派生 `const currentUser = computed(() => store.auth?.user ?? null)`（等价实现，不依赖未暴露类型）。

**2. DashboardView(151) `store.quizHistory` 不存在**
- 根因：前序残留修复移除了 store 的 `quizHistory` 属性，且运行时该值本就恒为 `undefined || [] = []`（重构后从未回填）。
- 修复：`quiz_history: []`（行为守恒，注释指向 AssessmentView 为答题历史唯一来源）。

**3. ProfileView(95) `store.quizHistory` 不存在**
- 修复：新增本地 `const quizHistory = ref<{subject,correct}[]>([])`，在 `onMounted` 拉取 `/quiz/history`（与 AssessmentView 同源，`api.get('/quiz/history')` + 静默 catch），`calculateAccuracy()` 改用 `quizHistory.value`。**顺手修掉"答题准确率恒显示 50%"的隐性 bug**（此前因 quizHistory 恒空，always 返回 50）。

**4. KnowledgeGraphView(509/513) 4 处 `TS2532` Object possibly undefined（预存，非本轮改动）**
- 根因：`subjectConfig: Record<string,T>` 带索引签名，开启 `noUncheckedIndexedAccess` 后 `subjectConfig[step.subject]` 推为 `T|undefined`；模板内 `!.color` 偶发不被 Volar 当非空断言（已知模板类型检查怪癖）。
- 修复：改用 `?.` + `??` 兜底（`subjectConfig[step.subject]?.color ?? 'var(--accent-primary)'`），三处访问（color / borderColor / code）一并修。

### 验收（本轮 A+B+C）
- `vue-tsc --build` ✅ **0 错误**（TSC_EXIT=0）—— 全站 TS 门禁恢复，4 类报错（Chat/Dashboard/Profile/KnowledgeGraph）全部清零。
- `vite build --outDir dist-rem` ✅ `built in 2.85s`（BUILD_EXIT=0）。
- 全站页头/卡片标题 emoji **0 残留**（3 视图 12 处全迁移）；按钮族焦点环裁剪隐患关闭；store 类型回归闭合。

---

## ✅ 已落地（2026-07-17 — 响应"有很多UI还是非常不好看"→ 用户拍板"先打三个重灾区"，Wave D 系统级收口）

### 范围锁定（Grep 量化债务）
全站约 40 个未打磨视图，按 `style=` 内联数量排序，最严重三处：
- `KnowledgeAdminView.vue` — **71 处** 内联 style
- `ResourceView.vue` — **57 处** 内联 style
- `SettingsView.vue` — **38 处** 内联 style
（其余视图基本已用设计系统类 / 仅动态 `:style` 状态，不计入本轮）

### 设计系统补强（main.css，跨视图复用根基）
新增全局表单原语（此前缺失，是各视图手写 input 内联样式的根因）：
```css
.form-group { margin-bottom: 1rem; }
.form-label { display:block; font-size:.8125rem; font-weight:500; color:var(--text-secondary); margin-bottom:.375rem; }
.form-input { width:100%; padding:.6875rem .875rem; border-radius:var(--radius-sm); border:1px solid var(--border-color);
  background:var(--bg-input); color:var(--text-primary); font-size:.875rem; line-height:1.4;
  transition: border-color var(--duration-fast), box-shadow var(--duration-fast); }
.form-input::placeholder { color: var(--text-muted); }
.form-input:focus { outline:none; border-color:var(--border-focus); box-shadow:var(--focus-ring); }
.form-input:disabled { opacity:.6; cursor:not-allowed; }
.form-input[type="checkbox"], .form-input[type="radio"] { width:auto; accent-color:var(--accent-primary); }
```

### D-1 — SettingsView（38 处内联 → 0 静态内联）✅
- 全量重写模板：内联 skeleton → 全局 `.skeleton`（`skel-line-200`）；section 标题 `icons.shield` + `.section-title-icon`。
- 输入框 / 下拉 → `.form-input` / `.rag-select`；show/hide key 按钮 `.input-action`（scoped SVG）。
- `⚠️☀️🌙` emoji 移除（亮/暗模式切换改纯文字）；测试结果 `.test-result.is-ok/.is-err`；嵌入源选项 `.embed-option.is-active`（仅保留动态 `:style` 表达激活边框/bg）。
- scoped 补 `.card{padding:1.5rem}`（修全局 `.card` 无 padding 隐患）+ 全套 Wave D 局部类 + `@media(max-width:640px)` 响应式。
- **回归修复**：重写时误删 `import { api } from '@/utils/api'`，导致 `loadConfig/testLLM/saveConfig` 报 `TS2304`；已补回导入，类型门禁恢复。

### D-2 — ResourceView（57 处内联 → 仅 4 处动态 `:style`）✅
- 输入区 `form-input res-input`；进度卡 `.rv-card` + `.rv-progress-*`（进度条宽度/agent 图标底色保留动态 `:style`）；`✅/⏳` → 纯文字「已完成 / 正在工作...」。
- 结果卡 `.rv-card-header` + `.rv-tab.is-active` 复用 `.rag-btn`（移除 padding/fontSize 内联）；媒体统计 `.rv-stat-*`；薄弱点 `.rv-weak-*`；`⚠️` 移除。
- 拓展/证据/PPT/代码/视频各 tab 迁移到 `.rv-empty*/.rv-warn*/.rv-ok-box/.rv-err-box/.rv-ppt-dl/.rv-mm-*`；`📚📊💻🎨🎬📺` 等 emoji 全清除；多模态按钮 `.btn .btn-primary` / `.btn-video`（`--accent-success`）。
- 新增 `<style scoped>` Wave D 块（`.rv-card`/`.rv-progress-*`/`.rv-stat-*`/`.rv-weak-*`/`.rv-empty*`/`.rv-warn*`/`.rv-ok-box`/`.rv-err-box`/`.rv-ppt-dl`/`.rv-mm-*`/`.btn-video`），删除废弃 `.section-ic`。
- **验证**：仅剩 4 处动态 `:style`（进度宽度 / agent 图标底 / 结果卡边框 / 统计值色），emoji 0 残留。

### D-3 — KnowledgeAdminView（71 处内联 → 0 静态内联）✅
- 状态卡：`✅/❌` → `icons.checkCircle`/`icons.xCircle`（`.stat-ic--ok/--err` 语义色）；`📄/📚/🏷️` → `icons.document`/`icons.book`/`icons.clipboard`（`.stat-ic--doc/--book/--tag`，底色用 `color-mix` 语义色调，移出内联）。
- 操作栏：搜索框 `form-input op-search`；6 个操作按钮内联 `background:var(--accent-2/4/5/6)` → 语义 `.op-add/--upload/--delete/--reindex/--clear/--commit/--cancel`（scoped 修饰类因带 data 属性特异性高于全局 `.rag-btn` 生效）。
- `🔍/＋/📄/🗑️/⏳/🔄/✨/📖` 全部移除，改用 `icons.search/plus/package/trash/refresh/hourglass/sparkleSmall/bookOpen`；提交/重置/清空等按钮文案纯文字化。
- 添加/上传面板 → `.ka-panel`（`.ka-panel--cyan` 用 `--accent-cyan` 色调）；表单网格 `.ka-form-grid`；mini 选择/输入 `.ka-mini-select/.ka-mini-input`；预览分块列表 `.ka-prev-list/.ka-prev-item`；"已修改" `.ka-modified`（`--accent-pink`）。
- 文档列表表头/行 → `.ka-list-head/.ka-list-row` + 列宽类 `.ka-col-*`；内容 clamp `.ka-clamp`；章节 `📖` → `icons.bookOpen`；分页 `.ka-pager`。
- checkboxes 内联 `accent-color:var(--accent-1)` 全部删除，统一到 scoped `input[type="checkbox"]{accent-color:var(--accent-primary)}`。
- 全部 `:style=` 清零（状态卡改 `:class` 表达），仅 `alert()` JS 串中保留功能型 emoji（非视觉债务，脚本行为守恒未动）。

### 验收（Wave D）
- `vue-tsc --build` 对 **3 个 Wave D 视图 0 错误**（D-1 回归已修）；D-2/D-3 全程 0 新增类型错误。
- `vite build --outDir dist-rem` ✅ `built in 3.40s`（BUILD_EXIT=0），三视图均产出 JS chunk（KnowledgeAdminView/ResourceView 编译通过）。
- 三视图内联 `style=` 与 UI emoji **0 残留**（仅动态 `:style` 状态保留，符合设计系统原则）。

### ⚠️ 已知残留（非 Wave D 引入，范围外）
`vue-tsc --build` 全量仍报 **预存 TS 错误**（与本次 3 视图无关，属近期 `vue-tsc 3.2.6 / typescript 6.0.0 / vue-router 5.0.4` 升级后的严格态回归，集中在未触碰组件）：
- `KnowledgeGraph.vue:105-109,178-179,188,354,372,403`（Object possibly undefined / 'mastery' 类型无交集 / 隐式 any 索引）
- `KnowledgeGraph3D.vue:162-165,171`（possibly undefined）
- `ChatView.vue:144`（Virtualizer<HTMLElement> vs <Element> 泛型不兼容）
- `KnowledgeGraphView.vue:190`（string 不可赋给 'map'|'mindmap'|...）
- 建议另开专项修复（或回退/锁版本），不在"先打三个重灾区"范围内，避免盲改行为。

---

## ✅ 已落地（用户"都要" → 收口预存 TS 错误，让 npm run build 全绿）

用户确认清掉上述 4 文件共 **33 处预存 TS 错误**。均为 `vue-tsc 3.2.6 / TS 6.0.0 / vue-router 5.0.4` 升级后严格态回归（`noUncheckedIndexedAccess` 开启），全部用**行为守恒最小改动**修复，未改任何运行时逻辑。

### 修复清单（类型严格度，行为守恒）
- **KnowledgeGraphView.vue**：`viewModes` 数组补类型注解 `value: 'graph'|'outline'|'mindmap'|'map'|'sphere'`，使 `viewMode = m.value`（`viewMode` 联合已含全部 5 值）类型闭合 → 修 1 处 `string` 不可赋给联合。
- **ChatView.vue**：`useVirtualizer` 返回 `Ref<Virtualizer>`；原 `virtualizer.value = useVirtualizer(...)` 误将 Ref 赋给实例位（也是潜在运行期 bug）。修正为 `virtualizer.value = useVirtualizer(...).value`，并补 `type Virtualizer` 导入 + `ref<Virtualizer<HTMLElement, Element> | null>`。所有使用点（`.scrollToIndex`/`.getTotalSize`/`.getVirtualItems`/`.scrollOffset`）均为实例调用，fix 后语义对齐 → 修 1 处泛型不兼容（顺手修掉潜在虚拟滚动失效 bug）。
- **KnowledgeGraph3D.vue**：`projected[i]` / `projected[closest]` 索引补 `!`（循环内索引恒有效）→ 修 4 处 possibly undefined。
- **KnowledgeGraph.vue（24 处）**：
  - `detailTab` 联合补 `'mastery'`（模板 354/403 已用 `'mastery'`）→ 修 2 处。
  - 力导向 `simulate()`：循环内 `nodes[i]/nodes[j]/nodes[other]` 索引捕获为 `const ni/nj/no = nodes[...]!` 后复用 → 修 22 处 Object possibly undefined（直接改引用，保持原突变语义）。
  - `onMouseMove` `nodes2d.value[i]!` → 修 4 处；`onClick` `nodes2d.value[hoveredNode.value]!.data` → 修 1 处。
  - 隐式 any 索引：`selectedNode.importance` 内联 `{high,medium,low}[any]` 抽出 `importanceLabel(imp:any)` helper（与既有 `masteryLabel` 同构）→ 修 1 处 TS7053。

### 验收（收口后）
- `vue-tsc --build` ✅ **全量 0 错误**（TSC_EXIT=0）—— 含此前 3 视图 + 本次 4 文件，全站 TS 门禁恢复。
- `npm run build`（= `run-p type-check "build-only"`）✅ **BUILD_EXIT=0**，`built in 3.67s`，全组件产出。
- 全站 `npm run build` 自 Wave D 起首次全绿；无运行时行为回归（ChatView 改为正确持有实例，属隐性 bug 修复）。
