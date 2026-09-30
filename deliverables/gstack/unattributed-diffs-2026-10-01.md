# 未认领改动 Diff 核实 — 2026-10-01

分支: career-literacy | 构建门禁: vue-tsc EXIT=0 / vite build EXIT=0 / vitest 120/120 通过

## 文件清单（改动行数）
 DESIGN.md                                 |  14 +++
 py-server/scripts/verify_app_wiring.py    |  18 ++-
 py-server/scripts/verify_auth_coverage.py |  30 +++--
 src/components/icons.ts                   |   7 ++
 src/data/capabilityComparison.ts          |   4 +-
 src/views/DashboardView.vue               | 193 +++++++++++-------------------
 src/views/DesignSystemView.vue            |  11 +-
 src/views/LandingView.vue                 |  14 +--
 8 files changed, 143 insertions(+), 148 deletions(-)

## 完整 Diff
diff --git a/DESIGN.md b/DESIGN.md
index 73182d8..c0f5b26 100644
--- a/DESIGN.md
+++ b/DESIGN.md
@@ -2,6 +2,8 @@
 
 > 本文件是 AI 编码代理生成 UI 时的**唯一设计规范**。任何新增/修改界面都必须遵循此处约定。
 > 设计令牌的**数值真值源**是 `src/assets/styles/_variables.css`（v10「砚 · Ink & Clay」）。本文件描述"怎么用"，不重复定义十六进制值；组件一律引用语义令牌（`--color-*` / `--subject-*` / `--space-*` / `--radius-*` / `--transition`），**禁止在组件里写死颜色或间距**。
+>
+> **版本说明**：令牌基底当前为 **v10「砚 · Ink & Clay」**；本文 §4 的「设计升级原语（Bento / 状态胶囊 / 微交互 / 动效 / 无障碍）」为 **v11.1**，二者是不同维度（令牌基底 vs 增量原语），**并存不冲突**。页面不再另写版本号，统一以本文件为准——此前 `DesignSystemView` 自写的 `v8` 无源可溯，已移除。
 
 ## 1. 视觉基调与氛围（Visual Theme）
 
@@ -70,6 +72,18 @@
 ### 导航（Navigation）
 - 侧栏 220px（折叠 72px），顶栏 64px（移动端转顶+底栏）。导航项 `color: var(--color-text-2)`，Hover/Active → `var(--color-text)` 且左/下缘 `2px solid var(--color-accent)`。当前项可加 `var(--color-accent-subtle)` 淡底。
 
+### 设计升级原语（v11.1 · 取自《AI 做 UI 总差点意思》30 关键词）
+> 来源：Pixso《AI 做 UI 总差点意思？这 30 个设计关键词》。落地集中在 5 个关键词，全部走现有令牌、零硬编码、只动 GPU 属性。
+> 实现位置：`src/assets/styles/_components.css`（「设计升级 · 可复用原语 v11.1」块）；交互样片：`src/views/DesignUpgradeView.vue`（路由 `/design-upgrade`，公开）。
+
+- **便当盒网格（Bento Box Grid · 关键词 01）**：`.bento-grid` + `.bento-cell` + 区域类（`.bento-hero` / `.bento-kpi1~4` / `.bento-todos` / `.bento-weak` / `.bento-agents` / `.bento-recents`）。主卡 `bento-hero` 占 2×2，KPI 小卡 1×1，用 `grid-template-areas` 表达主次；1024px 退化为 2 列、640px 退化为单列流。用途：首页/总览的「主次更清楚」重排。**已落地（2026-09-28）**：`DashboardView.vue` 顶部新增「今日速览」区块（`hero 2×2` + 4 KPI + 四科掌握度 + 最近练习），复用了全局 `.bento-cell` 玻璃质感、配 Dashboard 专属作用域网格 `.dash-bento`（不改动 sample 那套写死的 areas）。
+- **AI 原生状态（AI-Native UI · 关键词 25）**：交互层用状态机 `idle → thinking → streaming → done / error`（见 `DesignUpgradeView.vue` 的 `AiState`）。`.ai-stage` 边框随状态换色（`--color-border-focus` / `rgba(var(--accent-rgb),.3)` / `--color-success-border` / `--color-danger-border`）；流式逐字用 `.stream-caret`（已存在）。失败提供「重试」入口，不让用户猜「点了之后发生了什么」。
+- **微交互（Micro-interactions · 关键词 27）**：
+  - 按钮三态 `.btn.is-loading`（内置 spinner，`color:transparent`）/ `.btn.is-success` / `.btn.is-error`，让一次操作有清楚回应。
+  - 收藏四态 `.like-btn`（`.idle`/`.busy`/`.active`/`.failed`），失败时保留重试入口。
+- **动效驱动（Motion-Driven · 关键词 28）**：`.motion-card` + `.motion-card-trigger` / `.motion-card-detail`，卡片内联展开只用 `transform`（scale）+ `opacity`（GPU），不触 `height`/`top`/`left`；详情浮层 `position:absolute; inset:0` 覆盖，解释「刚才的东西去了哪里」。
+- **无障碍状态（Accessible & Ethical Design · 关键词 30）**：`.status-pill` + 变体（`.success`/`.warning`/`.danger`/`.info`/`.neutral`）一律 **图标 + 文字** 双重表达，绝不只靠颜色区分色觉障碍用户；焦点环由全局 `:focus-visible` 兜底，减弱动效由 `prefers-reduced-motion` 兜底（已存在）。
+
 ## 5. 布局原则（Layout）
 
 - **间距 = 4px 刻度**：只用 `--space-1`(4) … `--space-12`(48) 及 `--space-14/16/20/24/32`。**禁止**出现 5/6/10/14/18px 等随意间距；需要 6px 时用 `--space-2`(8) 或 `--space-1`(4)。
diff --git a/py-server/scripts/verify_app_wiring.py b/py-server/scripts/verify_app_wiring.py
index 288282a..1ea6b50 100644
--- a/py-server/scripts/verify_app_wiring.py
+++ b/py-server/scripts/verify_app_wiring.py
@@ -84,9 +84,23 @@ def main():
 
     app = main.app
     check("app 组装成功", app is not None)
-    check("路由数量 > 200（业务路由确实注册）", len(app.routes) > 200, f"routes={len(app.routes)}")
 
-    paths = {getattr(r, "path", "") for r in app.routes}
+    # 路由枚举走 verify_auth_coverage 的**跨 fastapi 版本**实现（单一真值源）：
+    # fastapi 0.141+ 起 include_router 不再把子路由拍平进 app.routes，而是放一个
+    # _IncludedRouter 包装对象（且它不保证有 .path）。直接 `for r in app.routes`
+    # 取属性会 AttributeError；用 len(app.routes) 计数则会**严重低估**（实测
+    # 0.141.1 下 app.routes 只剩 {'Route':4,'_IncludedRouter':1,'APIRoute':2}），
+    # 让下面这条「> 200」变成假红。故统一改用 iter_route_entries。
+    from verify_auth_coverage import iter_route_entries
+
+    route_entries = iter_route_entries(app)
+    check(
+        "路由数量 > 200（业务路由确实注册）",
+        len(route_entries) > 200,
+        f"routes={len(route_entries)}",
+    )
+
+    paths = {e.path for e in route_entries}
     for expected in ("/api/status", "/api/status/competition", "/metrics"):
         check(f"运维端点存在：{expected}", expected in paths)
 
diff --git a/py-server/scripts/verify_auth_coverage.py b/py-server/scripts/verify_auth_coverage.py
index c6f46fd..0359bff 100644
--- a/py-server/scripts/verify_auth_coverage.py
+++ b/py-server/scripts/verify_auth_coverage.py
@@ -99,8 +99,8 @@ def _is_protected(route) -> bool:
     )
 
 
-def _iter_api_route_entries(app):
-    """跨 fastapi 版本枚举 /api 路由条目（元素兼容 APIRoute 与 RouteContext）。
+def iter_route_entries(app, only_api: bool = False, endpoints_only: bool = False):
+    """跨 fastapi 版本枚举路由条目（元素兼容 APIRoute 与 RouteContext）。
 
     为什么必须做版本适配（2026-09-29 实锤，含 fastapi 0.141.1 对照实验）：
 
@@ -122,7 +122,13 @@ def _iter_api_route_entries(app):
         故 `_is_protected()` 无需改动即可继续按依赖树判定鉴权。
 
     兼容策略：有 iter_route_contexts 就用它（新版）；没有则回退到平铺分支（旧版）。
-    两条分支都**只认带 .path 的条目**，避免再对不保证该属性的对象取属性。
+    两条分支都**只认带 str 型 .path 的条目**，避免再对不保证该属性的对象取属性。
+
+    Args:
+        app: FastAPI 实例。
+        only_api: True 时只保留 path 以 "/api" 开头的条目。
+        endpoints_only: True 时只保留**端点**（有 .methods 的 Route/APIRoute），
+            排除 Mount 等非端点条目 —— 供「业务路由是否真的注册」这类计数使用。
     """
     try:
         from fastapi.routing import iter_route_contexts  # noqa: PLC0415
@@ -130,21 +136,27 @@ def _iter_api_route_entries(app):
         iter_route_contexts = None
 
     entries = []
-    if iter_route_contexts is not None:
-        candidates = iter_route_contexts(app.routes)
-    else:
-        candidates = app.routes
+    candidates = iter_route_contexts(app.routes) if iter_route_contexts else app.routes
 
     for route in candidates:
         if iter_route_contexts is None and not isinstance(route, APIRoute):
-            continue  # 旧版：Mount / 文档路由不计入 API 面
+            continue  # 旧版平铺分支：Mount / 文档路由不计入 API 面
         path = getattr(route, "path", None)
-        if not isinstance(path, str) or not path.startswith("/api"):
+        if not isinstance(path, str):
+            continue
+        if only_api and not path.startswith("/api"):
+            continue
+        if endpoints_only and not getattr(route, "methods", None):
             continue
         entries.append(route)
     return entries
 
 
+def _iter_api_route_entries(app):
+    """/api 路由条目（collect() 专用入口，语义见 iter_route_entries）。"""
+    return iter_route_entries(app, only_api=True)
+
+
 def collect():
     import main  # noqa: PLC0415 —— 需先设好 sys.path，且 import 会执行环境引导
 
diff --git a/src/components/icons.ts b/src/components/icons.ts
index bc4126b..945102c 100644
--- a/src/components/icons.ts
+++ b/src/components/icons.ts
@@ -375,4 +375,11 @@ export const icons = {
   zoomOut: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>`,
   link: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
   compass: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z"/><circle cx="12" cy="12" r="10"/></svg>`,
+
+  // ── 增补：收藏 / 信息 / 中性 / 折叠（lucide 风格 · currentColor）──
+  heart: `<svg viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`,
+  heartOutline: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`,
+  info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
+  minus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
+  chevron: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`,
 }
diff --git a/src/data/capabilityComparison.ts b/src/data/capabilityComparison.ts
index 9c7b009..cae031c 100644
--- a/src/data/capabilityComparison.ts
+++ b/src/data/capabilityComparison.ts
@@ -13,7 +13,7 @@ export const capabilityComparison: ComparisonItem[] = [
     category: 'FrugalRAG 检索引擎',
     items: [
       { other: '普通RAG：直接向量检索', ours: 'FrugalRAG：E5向量+BM25融合 → 启发式停止决策 → 个性化重排', tag: '核心创新' },
-      { other: '固定 top-k 检索', ours: '动态停止决策：基于覆盖率阈值的启发式判断，平均减少30%冗余调用', tag: '创新' },
+      { other: '固定 top-k 检索', ours: '动态停止决策：基于覆盖率阈值的启发式判断，命中足够覆盖即停止检索', tag: '创新' },
       { other: '检索结果千篇一律', ours: '5因子个性化重排：薄弱点+15% / 已掌握-10% / 考查权重 / 难度匹配 / 目标分数', tag: '独创' },
     ],
   },
@@ -36,7 +36,7 @@ export const capabilityComparison: ComparisonItem[] = [
   {
     category: 'LLM 集成',
     items: [
-      { other: '单通道LLM', ours: '三通道容灾：讯飞星火X2 → DeepSeek → Qwen2.5', tag: '合规' },
+      { other: '单通道LLM', ours: '三通道容灾：讯飞星火X2 → DeepSeek → Qwen3.8-Max', tag: '合规' },
       { other: '无合规考量', ours: '出题企业讯飞工具深度整合', tag: '合规' },
     ],
   },
diff --git a/src/views/DashboardView.vue b/src/views/DashboardView.vue
index ae6b7e9..42533d8 100644
--- a/src/views/DashboardView.vue
+++ b/src/views/DashboardView.vue
@@ -53,6 +53,7 @@ const heatmapRows = computed(() => {
       return {
         level: Math.min(5, Math.max(1, Math.floor(score / 20) + 1)),
         seq: i + 1,
+        score,
         label: `第 ${i + 1} 次练习 · 得分 ${score}`,
       }
     })
@@ -192,6 +193,15 @@ const judgePortals = [
 
 function go(route: string) { router.push(route) }
 
+// Bento 层级（关键词 01）：协调 Agent 是任务分派中枢 → 占 2×2 主块；
+// 路径 Agent 是最终产出（MAPPO 选档）→ 跨 2 列；其余等大。
+// 只表达「结构主次」，不引入任何运行时状态（沿用 8-Agent 静态声明的证据纪律）。
+function agentSpan(i: number): string {
+  if (i === 0) return 'ag-span-hub'
+  if (i === agents.length - 1) return 'ag-span-wide'
+  return ''
+}
+
 onMounted(async () => {
   try {
     const [s, ses, t] = await Promise.all([
@@ -236,7 +246,7 @@ onMounted(async () => {
     </div>
 
     <!-- 空状态：后端未运行 -->
-    <EmptyState v-else-if="!stats && !sessions.length && !tasks.length" :icon="icons.dashboard" title="欢迎来到 MARS-408" description="启动后端服务后，这里将展示你的学习数据、最近学习记录和推荐任务。">
+    <EmptyState v-else-if="!stats && !sessions.length && !tasks.length" :icon="icons.dashboard" title="欢迎来到芒得很职" description="启动后端服务后，这里将展示你的学习数据、最近学习记录和推荐任务。">
       <template #action>
         <button class="hero-cta" @click="go('/profile/build')">开始构建学习画像</button>
         <button class="hero-cta secondary" @click="go('/chat')">进入智能对话</button>
@@ -396,32 +406,6 @@ onMounted(async () => {
       </div>
     </section>
 
-    <!-- 学习数据总览 -->
-    <section v-if="stats" class="data-section">
-      <div class="data-label">学习数据总览</div>
-      <div class="data-grid">
-        <div class="data-card">
-          <div class="data-icon" v-html="icons.book"></div>
-          <div class="data-value">{{ stats.studyTime }}h</div>
-          <div class="data-label-text">今日学习时长</div>
-        </div>
-        <div class="data-card">
-          <div class="data-icon" v-html="icons.pen"></div>
-          <div class="data-value">{{ stats.questionsDone }}</div>
-          <div class="data-label-text">今日完成题目</div>
-        </div>
-        <div class="data-card mastery-card">
-          <RingProgress :value="stats.mastery" :size="116" :stroke="9" />
-          <div class="data-caption">知识点整体掌握率</div>
-        </div>
-        <div class="data-card">
-          <div class="data-icon" v-html="icons.fire"></div>
-          <div class="data-value">{{ stats.streak }}天</div>
-          <div class="data-label-text">连续学习</div>
-        </div>
-      </div>
-    </section>
-
     <!-- 学科掌握度分布 -->
     <section v-if="stats" class="mastery-section">
       <div class="data-label">学科掌握度分布</div>
@@ -441,7 +425,7 @@ onMounted(async () => {
         <span class="tag-demo">静态结构 · 无运行时数据</span>
       </div>
       <div class="agent-grid">
-        <div v-for="ag in agents" :key="ag.role" class="agent-card">
+        <div v-for="(ag, i) in agents" :key="ag.role" class="agent-card" :class="agentSpan(i)">
           <div class="agent-info">
             <div class="agent-name" :style="{ color: ag.color }">{{ ag.name }} Agent</div>
             <div class="agent-role">{{ ag.role }}</div>
@@ -467,8 +451,10 @@ onMounted(async () => {
               class="heatmap-cell"
               :style="{ background: cell.level === 0 ? 'var(--chart-grid)' : `var(--seq-${cell.level})` }"
               :title="cell.label"
+              role="img"
+              :aria-label="row.name + ' · ' + cell.label"
             >
-              <span class="heatmap-cell-text" :style="{ color: cell.level >= 4 ? 'var(--color-text-invert)' : 'var(--color-text-2)' }">{{ cell.level === 0 ? '—' : cell.seq }}</span>
+              <span class="heatmap-cell-text" :style="{ color: cell.level >= 4 ? 'var(--color-text-invert)' : 'var(--color-text-2)' }">{{ cell.level === 0 ? '—' : cell.score }}</span>
             </div>
           </div>
         </div>
@@ -492,7 +478,7 @@ onMounted(async () => {
           <div class="alert-body">
             <div class="alert-topic">
               {{ al.topic }}
-              <span class="alert-level" :class="'lv-' + al.level">{{ al.level === 'danger' ? '高危' : '薄弱' }}</span>
+              <span class="status-pill" :class="al.level === 'danger' ? 'danger' : 'warning'"><span v-html="al.level === 'danger' ? icons.warning : icons.info"></span>{{ al.level === 'danger' ? '高危' : '薄弱' }}</span>
             </div>
             <div class="alert-action">{{ al.action }}</div>
           </div>
@@ -871,12 +857,9 @@ onMounted(async () => {
 .bonus-card:hover svg:last-child { opacity: 1; }
 
 /* ── Data ── */
-.data-section {
-  padding:var(--space-6) var(--space-8);
-  max-width:75rem;
-  margin:0 auto;
-}
-
+/* 注：原「学习数据总览」区块（.data-section / .data-grid / .data-card 系列）已于 2026-09-29
+   被顶部 Bento「今日速览」取代——两者展示完全相同的 4 个指标，一页重复属设计硬伤。
+   区块与其专用样式已一并移除（非误删）。`.data-label` 仍被其余区块共用，保留。 */
 .data-label {
   font-size:var(--text-xs);
   color: var(--text-muted);
@@ -885,89 +868,6 @@ onMounted(async () => {
   letter-spacing:0.0312rem;
 }
 
-/* Bento Box Grid（文章词 01）：重要内容多占位，相关内容靠一起，先让人看见"今天怎么样" */
-.data-grid {
-  display: grid;
-  grid-template-columns: repeat(6, 1fr);
-  gap:var(--space-3);
-}
-.data-card:nth-child(1) { grid-column: span 2; }               /* 今日学习时长：小卡 */
-.data-card:nth-child(2) { grid-column: span 2; }               /* 今日完成题目：小卡 */
-.data-card:nth-child(3) { grid-column: span 2; grid-row: span 2; } /* 掌握率：主卡（跨 2 行） */
-.data-card:nth-child(4) { grid-column: span 4; }               /* 连续学习：通栏副卡 */
-
-/* 通栏副卡改横向排布，避免大卡里只有一个数字 */
-.data-card:nth-child(4) {
-  display: flex; align-items: center; justify-content: center; gap: var(--space-4); text-align: left;
-}
-.data-card:nth-child(4) .data-icon { margin-bottom: 0; }
-.data-card:nth-child(4) .data-label-text { margin-top: 0; }
-
-@media (max-width: 900px) {
-  .data-grid { grid-template-columns: repeat(2, 1fr); }
-  .data-card:nth-child(1), .data-card:nth-child(2) { grid-column: span 1; }
-  .data-card:nth-child(3) { grid-column: span 2; grid-row: span 1; }
-  .data-card:nth-child(4) { grid-column: span 2; }
-}
-@media (max-width: 480px) {
-  .data-grid { grid-template-columns: 1fr; }
-  .data-card:nth-child(n) { grid-column: span 1; }
-}
-
-.data-card {
-  background: var(--bg-secondary);
-  border: 1px solid var(--border-color);
-  border-radius:var(--radius-md);
-  padding:var(--space-4);
-  text-align: center;
-  transition: var(--transition);
-}
-
-.data-card:hover {
-  border-color: var(--color-glass-border);
-}
-
-.data-icon {
-  display: flex;
-  align-items: center;
-  justify-content: center;
-  margin-bottom:var(--space-2);
-  color: var(--accent-primary);
-}
-
-.data-icon svg { width:1.25rem; height:1.25rem; }
-
-.data-value {
-  font-size:var(--text-3xl);
-  font-weight: 800;
-  color: var(--text-primary);
-  letter-spacing:-0.0312rem;
-}
-
-.data-label-text {
-  font-size:var(--text-xs);
-  color: var(--text-muted);
-  margin-top:var(--space-1);
-}
-
-/* ── Mastery rings ── */
-.data-card.mastery-card {
-  display: flex;
-  flex-direction: column;
-  align-items: center;
-  justify-content: center;
-  gap:var(--space-2);
-  /* Bento 主卡：给一点视觉权重，让人第一眼落在"掌握率" */
-  background: linear-gradient(180deg, var(--accent-primary-10), var(--bg-secondary) 55%);
-  border-color: var(--accent-primary-20);
-}
-.data-card.mastery-card .data-caption { font-size: var(--text-sm); color: var(--text-secondary); }
-.data-card.mastery-card:hover { border-color: var(--accent-primary); }
-.data-caption {
-  font-size:var(--text-xs);
-  color: var(--text-muted);
-  font-weight: var(--weight-medium);
-}
 .mastery-section {
   padding:0 var(--space-8) var(--space-6);
   max-width:75rem;
@@ -1261,7 +1161,6 @@ onMounted(async () => {
 /* ── Responsive ── */
 @media (max-width: 1024px) {
   .portals-grid { grid-template-columns: repeat(2, 1fr); }
-  .data-grid { grid-template-columns: repeat(2, 1fr); }
   .recent-grid { grid-template-columns: 1fr; }
   .agent-grid { grid-template-columns: repeat(2, 1fr); }
 }
@@ -1277,8 +1176,6 @@ onMounted(async () => {
   .portal-card { padding:var(--space-5) var(--space-4); }
   .bonus-section { padding:var(--space-3) var(--space-5); }
   .bonus-row { flex-direction: column; }
-  .data-section { padding:var(--space-4) var(--space-5); }
-  .data-grid { grid-template-columns: repeat(2, 1fr); }
   .recent-section { padding:var(--space-3) var(--space-5) var(--space-5); }
 }
 
@@ -1287,7 +1184,6 @@ onMounted(async () => {
   .hero-title { font-size:var(--text-3xl); }
   .hero-stats-row { flex-wrap: wrap; gap:var(--space-3); }
   .hero-stat-divider { display: none; }
-  .data-grid { grid-template-columns: 1fr 1fr; }
   .agent-grid { grid-template-columns: 1fr; }
   .heatmap-cells { grid-template-columns: repeat(4, 1fr); }
   .heatmap-subj-label { width: 3.5rem; font-size: var(--text-2xs); }
@@ -1342,4 +1238,55 @@ onMounted(async () => {
   .dash-bento{grid-template-columns:1fr;grid-template-areas:none}
   .db-area-hero,.db-area-kpi1,.db-area-kpi2,.db-area-kpi3,.db-area-mastery,.db-area-subjects,.db-area-recent{grid-area:auto}
 }
+
+/* ── 多智能体协作架构：Bento 层级（关键词 01）──
+   协调=分派中枢占 2×2 主块，路径=最终产出跨 2 列，其余等大。 */
+.ag-span-hub{grid-column:span 2;grid-row:span 2}
+.ag-span-wide{grid-column:span 2}
+.ag-span-hub .agent-name{font-size:var(--text-lg)}
+@media (max-width:1024px){
+  .ag-span-hub{grid-row:span 1}
+}
+@media (max-width:640px){
+  .ag-span-hub,.ag-span-wide{grid-column:span 1;grid-row:span 1}
+}
+
+/* ── 微交互（关键词 27）：可点击项给出「按下」反馈 ──
+   只用 transform（GPU），不改变布局尺寸。 */
+.alert-item:active{transform:scale(.995)}
+.subject-quick-card:active{transform:scale(.985)}
+@media (prefers-reduced-motion:reduce){
+  .alert-item:active,.subject-quick-card:active{transform:none}
+}
+
+/* ── Motion-Driven 入场揭示（设计升级 v11.1 · 关键词 09/28 滚动揭示）──
+   仅动 transform + opacity（GPU，不触发重排）；尊重系统「减弱动效」。 */
+@keyframes dash-reveal-up{
+  from{opacity:0;transform:translateY(10px)}
+  to{opacity:1;transform:none}
+}
+/* 区块级：柔和淡入上移，让首页「活」起来 */
+.hero-content,
+.rec-section,.judge-section,.mastery-section,.agent-status-section,
+.heatmap-section,.alert-section,.recent-section,.bonus-section{
+  opacity:0;
+  animation:dash-reveal-up var(--duration-slow) var(--ease-out) .08s forwards;
+}
+/* 今日速览七格错峰（替代容器整体动画，逐格浮现更显层次） */
+.dash-bento .bento-cell{
+  opacity:0;
+  animation:dash-reveal-up var(--duration-slow) var(--ease-out) forwards;
+}
+.dash-bento .bento-cell:nth-child(1){animation-delay:.06s}
+.dash-bento .bento-cell:nth-child(2){animation-delay:.10s}
+.dash-bento .bento-cell:nth-child(3){animation-delay:.14s}
+.dash-bento .bento-cell:nth-child(4){animation-delay:.18s}
+.dash-bento .bento-cell:nth-child(5){animation-delay:.22s}
+.dash-bento .bento-cell:nth-child(6){animation-delay:.26s}
+.dash-bento .bento-cell:nth-child(7){animation-delay:.30s}
+@media (prefers-reduced-motion:reduce){
+  .hero-content,.rec-section,.judge-section,.mastery-section,.agent-status-section,
+  .heatmap-section,.alert-section,.recent-section,.bonus-section,
+  .dash-bento .bento-cell{animation:none;opacity:1;transform:none}
+}
 </style>
diff --git a/src/views/DesignSystemView.vue b/src/views/DesignSystemView.vue
index 207407d..a349ea1 100644
--- a/src/views/DesignSystemView.vue
+++ b/src/views/DesignSystemView.vue
@@ -79,8 +79,8 @@ function chipStyle(tok: string) {
     <!-- 顶栏 -->
     <div class="topbar">
       <div class="brandmark">
-        <span class="dot"></span>MARS-408 设计系统
-        <span class="src-note">v8 · 应用内 Living Style Guide</span>
+        <span class="dot"></span>芒得很职 设计系统
+        <span class="src-note">应用内 Living Style Guide</span>
       </div>
       <button class="theme-toggle" @click="toggleTheme" :title="themeLabel">
         <svg v-if="theme === 'dark'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
@@ -93,7 +93,7 @@ function chipStyle(tok: string) {
       <!-- HERO -->
       <div class="hero-band">
         <h1>克制深色 · 玻璃态 · 学科分色</h1>
-        <p>MARS-408 前端设计系统 v8。语义化双主题 token，组件只引用 <code>--color-*</code> 语义层，<code>[data-theme="light"]</code> 覆盖即双主题。本页所有元素实时响应右上角主题切换，且与全局导航栏主题键（mars408-theme）完全一致。</p>
+        <p>芒得很职 前端设计系统。语义化双主题 token，组件只引用 <code>--color-*</code> 语义层，<code>[data-theme="light"]</code> 覆盖即双主题。本页所有元素实时响应右上角主题切换，且与全局导航栏主题键（mars408-theme）完全一致。</p>
         <div class="glass-card">
           <div class="gc-k">GLASSMORPHISM</div>
           <div class="gc-v">backdrop-filter: blur(12px)</div>
@@ -147,7 +147,7 @@ function chipStyle(tok: string) {
           <div v-for="r in typeScale" :key="r[0]" class="type-row">
             <div class="lvl">{{ r[0] }}</div>
             <div class="samp" :style="{ 'font-size': r[1], 'font-weight': r[2], 'line-height': r[3], 'letter-spacing': r[4] }">
-              MARS-408 个性化学习系统 <span style="font-size:12px;color:var(--color-text-3);font-weight:400;">— {{ r[5] }}</span>
+              芒得很职 个性化学习系统 <span style="font-size:12px;color:var(--color-text-3);font-weight:400;">— {{ r[5] }}</span>
             </div>
           </div>
         </div>
@@ -287,7 +287,8 @@ function chipStyle(tok: string) {
       </section>
 
       <footer>
-        MARS-408 设计系统 v8 · 单源真理 <code>DESIGN.md</code> 与 <code>src/assets/styles/_variables.css</code> · AI 可读，供 Cursor / Claude Code / Google Stitch 直接消费。<br/>
+        芒得很职 设计系统 · 单源真理 <code>DESIGN.md</code> 与 <code>src/assets/styles/_variables.css</code> · AI 可读，供 Cursor / Claude Code / Google Stitch 直接消费。<br/>
+        版本号以 <code>DESIGN.md</code> 为准，本页不复写（曾因页面另写一份而漂移成与文档不一致的旧号）。<br/>
         本页为应用内正式路由页，所有 token 直接引用全局 <code>_variables.css</code>；切换右上角主题可见全部元素实时双主题渲染，且与全局导航主题键（mars408-theme）一致。
       </footer>
     </div>
diff --git a/src/views/LandingView.vue b/src/views/LandingView.vue
index 9d3bc7b..70dfe50 100644
--- a/src/views/LandingView.vue
+++ b/src/views/LandingView.vue
@@ -8,9 +8,9 @@ const router = useRouter()
 // ── 数据指标药丸 ──
 const metrics = [
   { value: '8', label: '协作 Agent', color: 'var(--accent-primary)' },
-  { value: '≥10', label: '资源类型', color: 'var(--accent-cyan)' },
-  { value: '1883', label: '知识 chunks', color: 'var(--accent-blue)' },
-  { value: '613', label: '图谱节点', color: 'var(--accent-pink)' },
+  { value: '7', label: '资源类型', color: 'var(--accent-cyan)' },
+  { value: '2122', label: '知识 chunks', color: 'var(--accent-blue)' },
+  { value: '86', label: '图谱节点', color: 'var(--accent-pink)' },
 ]
 
 // ── 三大创新亮点 ──
@@ -46,9 +46,9 @@ const innovations = [
     badge: '创新 03',
     title: '408 领域知识图谱',
     subtitle: 'Domain Knowledge Graph',
-    desc: '构建覆盖计算机考研 408 全科的知识图谱视图——26 大知识群组、2083 条知识向量，四科分色着色，支撑知识点关联浏览与个性化路径规划（v1 规则原型）。',
+    desc: '构建覆盖计算机考研 408 全科的知识图谱视图——26 大知识群组、2122 条知识向量，四科分色着色，支撑知识点关联浏览与个性化路径规划（v1 规则原型）。',
     stat: '26',
-    statLabel: '知识群组 / 2083 向量',
+    statLabel: '知识群组 / 2122 向量',
     accent: 'var(--accent-pink)',
     gradient: 'linear-gradient(135deg, color-mix(in srgb, var(--accent-pink) 12%, transparent), color-mix(in srgb, var(--accent-pink) 2%, transparent))',
     iconSvg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><line x1="12" y1="7" x2="5" y2="17"/><line x1="12" y1="7" x2="19" y2="17"/><line x1="5" y1="19" x2="19" y2="19"/></svg>`,
@@ -207,7 +207,7 @@ function goToSkills() {
     <section class="bottom-cta">
       <div class="bottom-cta-inner">
         <h2 class="bottom-title">让每一道错题，都成为成长的起点</h2>
-        <p class="bottom-desc">10 Agent 协作 · 10 项多模态能力 · 无限可扩展教学技能 · 26 大知识群组</p>
+        <p class="bottom-desc">8 Agent 协作 · 10 项多模态能力 · 无限可扩展教学技能 · 26 大知识群组</p>
         <button class="cta-primary cta-large" @click="enterSystem">
           <span>立即体验</span>
           <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
@@ -217,7 +217,7 @@ function goToSkills() {
 
     <footer class="landing-footer">
       <span>芒得很职 · 基于大模型的个性化资源生成与学习多智能体系统</span>
-      <span class="footer-tech">Vue 3 + Vite + TypeScript · 玻璃态发光设计系统 v8</span>
+      <span class="footer-tech">Vue 3 + Vite + TypeScript · 玻璃态发光设计系统</span>
     </footer>
   </div>
 </template>
