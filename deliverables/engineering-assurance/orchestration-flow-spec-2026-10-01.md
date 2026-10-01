# 前端编排态可视化实施规格（Orchestration-Flow Visualization Spec）

> 文件：`deliverables/engineering-assurance/orchestration-flow-spec-2026-10-01.md`
> 作者：阿奇（Archi）· 系统架构师 · architect-5
> 日期：2026-10-01
> 状态：Proposed（待主理人评审，供实现 worker 落地）

---

## 📌 TL;DR

后端 `py-server` 已完成 LangGraph **11 节点**编排与 SSE 插桩（`POST /agents/langgraph/stream`，事件 `node_done` 携带节点名），但前端三处流程图（`EngineView` / `FrugalRAGPanel` / `GOMARLPanel`）仍用 `setTimeout` 硬演假动画；唯一真正消费 SSE 的 `ResourceView.vue`（464-569 行）却只把 `node_done` 映射成 5 步进度条，**没驱动 11 节点流程图**。

**最小可行实现（MVP）只改前端 4 个文件 + 新增 1 个 composable，后端零改动**：新增 `useOrchestrationFlow.ts` 作为「SSE 事件 → 节点流转状态」单一真源；扩展 `LangGraphFlow.vue` 到 11 节点并修正语义；让 `ResourceView.vue` 用它驱动真实流程图；移除 `FrugalRAGPanel`/`GOMARLPanel` 里误导性的假动画（其端点并非 11 节点图）。可选（推荐）后端删 2 行重复 `node_done` 消除误判风险。

---

## 🎯 核心结论卡片

| 维度 | 结论 |
|---|---|
| **整体评级** | 🟡 中等债 —— 展示层"演"而非"真"，但数据源已齐备，纯前端可闭环 |
| **后端是否需动** | ❌ 否（MVP 零后端改动）；🟢 可选：删 `langgraph.py` 165/220 行重复 `node_done` |
| **改动文件数** | 5 改 + 1 新增（前端）；后端可选 1 处 |
| **新增组件/composable** | 1（`useOrchestrationFlow.ts`），无新增 .vue 组件 |
| **节点映射缺口** | 后端 11（含 `triage`）vs 前端 10（缺 `triage`）→ **建议新增 `triage` 为第 0 节点** |
| **建议下一步** | 先落地 MVP（ResourceView 接真实流 + 去假动画），再按 P1/P2 增强回路可视化 |

---

## 1. 节点映射表（后端 11 `node_name` → 前端 `nodeLabels`）

后端图拓扑（`py-server/agents/graph.py:5-11`，`create_agent_graph` 99-154 行）：

```
triage → coordinator → diagnostician → planner → retriever
       → generator_cluster → assessor → critic
       → evidence_check → quality_gate → [PASS] → path_planner → END
                                          → [FIX]  → generator_cluster (重试)
                                          → [REJECT] → END
```

### 1.1 完整映射（推荐落地形态）

| idx | 后端 `node_name` | 中文标签（建议） | 图标 `icons` key | 颜色 CSS 变量 | 节点描述（建议） | 状态 |
|---|---|---|---|---|---|---|
| 0 | `triage` | 分级路由 | `compass`（复用，见 1.3） | `--agent-triage`（**新增**，见 1.4） | Triage 分级路由，低风险短路快路径 | 🆕 新增 |
| 1 | `coordinator` | 协调 | `target`（现） | `--agent-coord` | 全局协调、解析请求与画像 | 保留 |
| 2 | `diagnostician` | 诊断 | `search`（现） | `--agent-diag` | 学情诊断知识薄弱点 | 保留 |
| 3 | `planner` | 规划 | `mapPin`（现） | `--agent-plan` | 制定任务规划与检索策略 | 保留 |
| 4 | `retriever` | 检索 | `book`（现） | `--agent-retrieve` | FrugalRAG 多轮检索 | 保留 |
| 5 | `generator_cluster` | 生成 | `robot`（现） | `--agent-gen` | 7 类资源并行生成 | 保留 |
| 6 | `assessor` | 评估反馈 | `checkCircle`（现） | `--agent-eval` | 评估生成资源质量并反馈 | 🔧 改描述 |
| 7 | `critic` | 质量校验 | `eye`（现） | `--agent-quality` | 三元评审共识与一致性校验 | 🔧 改标签+描述 |
| 8 | `evidence_check` | 证据校验 | `scale`（现） | `--agent-evidence` | 证据校验与防幻觉 grounding | 保留 |
| 9 | `quality_gate` | 产物验收 | `shield`（现） | `--agent-gate` | 产物验收闸门（PASS/FIX/REJECT） | 保留 |
| 10 | `path_planner` | 路径规划 | `path`（现） | `--agent-path` | 输出最终个性化学习路径 | 保留 |

> 说明：`nodeLabels` 索引从 0 起；`LangGraphFlow.vue` 当前 `nodeIcons`/`nodeColors` 已是 10 项、按序对应上表 idx 1-10（`target/search/mapPin/book/robot/checkCircle/eye/scale/shield/path`，见 `LangGraphFlow.vue:41-57`），新增 `triage` 后整体前移/前插即可。

### 1.2 语义修正（重要）

前端现状（`LangGraphFlow.vue:35-38`、`59-71`；三处调用点各复制一份）把 `assessor` 标"评估"、`critic` 标"审核"，且把 `assessor` 描述写成"GoMARL 共识评估质量"——**这是错的**：

- 后端 `assessor` = **评估反馈**（对生成资源打分/反馈），`critic` = **质量校验**（三元评审 + consensus + 一致性消解，见 `graph.py:71-89` `route_after_critic`、`api/langgraph.py:203-213`）。
- "GoMARL 共识" 语义属于 `critic`，不属于 `assessor`。

**修正动作**：`critic` 标签"审核"→"质量校验"；`assessor` 标签"评估"→"评估反馈"（或保留"评估"但描述改为"评估生成资源质量"）；二者描述对调/重写（见上表）。此修正需同步到 `LangGraphFlow.vue` 默认值 + `EngineView.vue` 的 `flowNodeLabels`/`flowStepDetails`（`FrugalRAGPanel`/`GOMARLPanel` 的副本随移除一并消失）。

### 1.3 `triage` 处理建议：**加进流程图（作为第 0 节点）**

理由：
1. 后端 `triage` 是真实入口节点（`workflow.set_entry_point("triage")`，`graph.py:112`），且低风险短路本身就是"编排态"的一部分——展示它才能体现"流程图显示的是真实执行"。
2. 若并入 `coordinator`（不展示），会在快路径下出现"一个节点都没亮就结束"的诡异空态。
3. 代价极小：仅需前插一个节点 + 一个图标 + 一个颜色 + 处理快路径（见 §5.1）。

**不并入 coordinator**。低风险快路径（`triage_skip`）单独用 `fastPath` 标志渲染（见 §2 / §5.1）。

### 1.4 颜色 / 图标缺口

- 颜色：10 个 `--agent-*` 变量已在 `src/assets/styles/_variables.css:329-338`（浅色 526-535）定义；**缺 `--agent-triage`**。建议新增 1 个（如紫罗兰系外挑一个中性/青色，避免与 `--agent-coord` 紫罗兰冲突，例如 `#5B8C5A` 系 或复用 `--accent-warm`）。MVP 可先复用 `var(--accent-primary)` 兜底，但建议正式新增以保持语义一致。
- 图标：`icons.ts` 无 `filter`/`funnel`/`branch`/`triage` 专用图标；可用现成 `compass`（存在，`icons.ts:377`）表达"路由/分级"。可选增强：新增 `funnel` 图标。

---

## 2. 数据流设计（`node_done` 字段 → `completedNodes`/`currentNode`）

### 2.1 单一真源 composable：`useOrchestrationFlow.ts`

新建 `src/composables/useOrchestrationFlow.ts`，导出：

```ts
// 常量（图序真源，11 节点）
const NODE_ORDER: string[] = ['triage','coordinator','diagnostician','planner','retriever',
  'generator_cluster','assessor','critic','evidence_check','quality_gate','path_planner']
const NODE_INDEX: Record<string, number>   // node_name -> index

// 状态
const currentNode = ref(-1)                 // 活跃索引
const completedNodes = ref<number[]>([])    // 已完成索引（单调，只增不删）
const nodeStates = ref<Record<number, NodeVisualState>>({})
    // NodeVisualState = 'pending' | 'active' | 'completed' | 'retrying' | 'rejected'
const retryCount = ref<Record<number, number>>({})  // 回环重入计数（按节点）
const gateVerdict = ref<'pass'|'fix'|'reject'|null>(null)
const fastPath = ref(false)                 // triage_skip 快路径
const flowLoading = ref(false)
const loopLog = ref<LoopEvent[]>([])        // 回环时间线（P1 增强）

// 方法
function handleEvent(evt: SseEvent): void   // 幂等消费一条 SSE
function reset(): void
```

### 2.2 `handleEvent` 核心逻辑（伪代码级规格）

```
on evt.type === 'node_done':
  idx = NODE_INDEX[evt.field];  if idx == null: return        // 未知字段忽略
  // (a) 连续去重：retriever/evidence_check 后端会连发两次 node_done（见 §5.2）
  if evt.field === lastNodeDoneField: return                   // 忽略同字段相邻重复
  lastNodeDoneField = evt.field
  // (b) 回环检测：节点已在 completedNodes 中 → 重入
  if completedNodes.includes(idx):
      retryCount[idx] = (retryCount[idx] || 0) + 1
      nodeStates[idx] = 'retrying'
      // 视觉回退：图序 >= idx 的下游节点回到 pending，但 completedNodes 不删（保持单调）
      for j in [idx .. NODE_ORDER.length-1]: nodeStates[j] = (j === idx ? 'retrying' : 'pending')
      loopLog.push({ from: prevNode, to: evt.field, n: retryCount[idx] })
  else:
      completedNodes.push(idx)                                 // 单调追加
      nodeStates[idx] = 'completed'
  currentNode = idx;  flowLoading = true

on evt.type === 'gate_fix':      gateVerdict='fix';  nodeStates[qgIdx]='completed'
on evt.type === 'gate_pass':     gateVerdict='pass'
on evt.type === 'gate_rejected': gateVerdict='reject'; nodeStates[qgIdx]='rejected'; flowLoading=false
on evt.type === 'status' && evt.field === 'triage_skip':
      fastPath = true; completedNodes = [0]; nodeStates[0]='completed'; flowLoading=false
on evt.type === 'status' && evt.field === 'done': flowLoading = false
```

### 2.3 回路重试在「单调 completedNodes」下的表达

`completedNodes` 保持**单调只增**（供进度条 `completedNodes.length / 11` 不回退，与 `ResourceView.vue:523-524` 现有"进度单调不回退"语义一致）。**回环**用独立维度表达：

- **重入检测**：某 `node_done` 的节点已在 `completedNodes` 中 → 判为重入（回环）。这统一覆盖三处回边：
  - `retriever` 空 → 回 `planner`：`planner` 二次 `node_done`
  - `critic` 不通过 → 回 `retriever`：`retriever` 二次 `node_done`
  - `quality_gate` FIX → 回 `generator_cluster`：`generator_cluster` 二次 `node_done`
- **重入表现**：`nodeStates[idx]='retrying'` + `retryCount[idx]++`，下游（图序 ≥ idx）视觉回退为 `pending`，但**不删除 `completedNodes` 历史**。
- 结论：采纳任务提示中的「重试节点回退为 active，不删除历史」方案，并叠加 `retryCount` 标注（第 N 次）。

---

## 3. 改动文件清单（精确到文件/行）

### 3.1 新增：`src/composables/useOrchestrationFlow.ts`（🆕 1 个文件）

**做什么**：上节 §2.1/§2.2 的全部逻辑 + 11 节点常量 + 标签/图标/颜色/描述元数据（作为前端「节点元数据」单一真源，避免 `LangGraphFlow` 默认值、`EngineView` 三处各写一份继续漂移）。

**建议导出**：
```ts
export const ORCHESTRATION_NODES: Array<{
  name: string; index: number; label: string; icon: keyof typeof icons;
  color: string; description: string
}>
export function useOrchestrationFlow() { ... }
```

### 3.2 修改：`src/components/LangGraphFlow.vue`

| 位置 | 改什么 |
|---|---|
| 35-38 行 `nodeLabels` 默认值 | 10 → 11 项：前插"分级路由"；"审核"→"质量校验"；"评估"→"评估反馈" |
| 41-52 行 `nodeColors` | 前插 `'var(--agent-triage)'`（或 `var(--accent-primary)` 兜底） |
| 54-57 行 `nodeIcons` | 前插 `'compass'` |
| 59-73 行 `nodeDescriptions` 默认值 | 前插 triage 描述；修正 assessor/critic 描述（见 §1.1） |
| 顶部注释 / 105 行标题文案 | "10 节点"→"11 节点" |
| props（24-30 行） | **可选**新增 `nodeStates?: Record<number,string>` 与 `retryingNodes?: number[]`，供 retry/rejected 视觉；**向后兼容**（不传时退化为现有 completed/active/pending 三态） |
| `nodeState()`（75-79 行） | 若传 `nodeStates`/`retryingNodes`，优先用其判定 `retrying`/`rejected`，否则保持现有三态 |

**判定**：`LangGraphFlow` **需要小幅扩展 props**（不是保持原样），否则回环重入无法视觉表达；但扩展是**加法式、向后兼容**的，不影响现有调用点。

### 3.3 修改：`src/views/ResourceView.vue`（真实流核心）

| 位置 | 改什么 |
|---|---|
| 顶部 import | 新增 `import LangGraphFlow from '@/components/LangGraphFlow.vue'` 与 `import { useOrchestrationFlow } from '@/composables/useOrchestrationFlow'` |
| `<script setup>` 新增 | `const flow = useOrchestrationFlow()` |
| `generateResource()` 开头（455-461 行重置块后） | `flow.reset()` |
| SSE 解析循环内（507-567 行） | 每条 `evt` 在进入既有 `node_done/status/content/...` 分支**之前或之后**统一调用 `flow.handleEvent(evt)`（幂等，与既有逻辑并行不冲突） |
| 模板（845-881 行流水线进度块） | 在 5 步 `agentSteps` 简化条**之上或替换**新增 `<LangGraphFlow :current-node="flow.currentNode" :completed-nodes="flow.completedNodes" :node-labels="ORCHESTRATION_NODES.map(n=>n.label)" :step-details="..." :loading="loading" :node-states="flow.nodeStates" :retrying-nodes="..." />`；快路径时显示 `flow.fastPath` 提示 |

> 说明：`ResourceView` 现有 5 步 `agentSteps`（422-428 行）是**简化版阶段摘要**，与 11 节点图是两种粒度；MVP 建议**新增** LangGraphFlow 置于其上方作为"编排态真相"，简化条可保留作摘要或择一替换，避免信息重复。

### 3.4 修改：`src/views/EngineView.vue`（演示页）

| 位置 | 改什么 |
|---|---|
| 32-35 行 `flowNodeLabels` | 10 → 11 项 + 语义修正（同 §1.1/§1.2） |
| 20-31 行 `flowStepDetails` | 同上前插 triage + 修正 assessor/critic 描述 |
| 205-211 行 `<LangGraphFlow>` | 不变（props 兼容）；`loading` 可改绑演示态 |
| 215 行演示按钮 | **保留**（演示页价值），但文案改为"▶ 演示完整流转（模拟）"，与真实流区分 |
| P1 可选 | 新增"🔌 接真实流"按钮：`POST /agents/langgraph/stream` 复用 `useOrchestrationFlow` 驱动，替代 `animateFlow` |

### 3.5 修改：`src/components/FrugalRAGPanel.vue`（移除假动画）

| 位置 | 改什么 |
|---|---|
| 49-65 行 `animateFlow()` | **删除** |
| 86 行 `runSearch()` 内 `animateFlow(3000)` | **删除** |
| 130-137 行 `<LangGraphFlow>` | **删除**（其端点 `/engine/frugal-rag-full` 非 11 节点图，展示流程图属误导） |
| 5 行 import | 删除 `LangGraphFlow` import |

> 理由：`FrugalRAGPanel` 调的是 `/engine/frugal-rag-full`（检索子引擎，`FrugalRAGPanel.vue:89`），**不产生 11 节点 `node_done`**。它已有真实 `trajectory-timeline`（170-188 行）展示检索轨迹，无需假流程图。

### 3.6 修改：`src/components/GOMARLPanel.vue`（移除假动画）

| 位置 | 改什么 |
|---|---|
| 30-46 行 `animateFlow()` | **删除** |
| 72 行 `runConsensus()` 内 `animateFlow(2400)` | **删除** |
| 106-113 行 `<LangGraphFlow>` | **删除**（端点 `/engine/gomarl-consensus` 非 11 节点图） |
| 3 行 import | 删除 `LangGraphFlow` import |

### 3.7 可选（推荐）：`py-server/api/langgraph.py`（后端 1 处 2 行）

| 位置 | 改什么 |
|---|---|
| 165 行 | 删除 `yield _sse("node_done", "retriever", ...)`（与 147 行通用 `node_done` 重复） |
| 220 行 | 删除 `yield _sse("node_done", "evidence_check", ...)`（同上重复） |

> 见 §5.2：这两个节点在通用 `node_done`（147 行）之外又各发了一次 `node_done`，会污染"回环=二次 node_done"的判定。前端有连续去重兜底，后端删这 2 行更干净。

---

## 4. 回路 / 分支可视化

### 4.1 最小实现（P0，随 MVP 落地）

1. **重入态**：`retrying` 节点用橙色/琥珀呼吸环（复用 `--accent-warm` 或 `--agent-gate` 琥珀）+ 角标显示 `retryCount`（"×2"）。在 `LangGraphFlow` 新增 `.flow-circle--retrying` 样式。
2. **闸门徽标**：`LangGraphFlow` 头部或 quality_gate 节点旁，按 `gateVerdict` 显示 `PASS`（绿）/`FIX`（琥珀）/`REJECT`（红）小徽标。
3. **回环时间线**：`LangGraphFlow` 底部（或 ResourceView 的 `rv-mon-log`）追加 `loopLog` 条目，如 "`quality_gate → 回退 generator_cluster（第 2 次）`"、"`critic → 回退 retriever`"。

> 物理"曲线回边箭头"**不作为 MVP**：`LangGraphFlow` 现为线性 flex 布局（`LangGraphFlow.vue:210-217`），画回边需引入 SVG 坐标层，复杂度高、收益低。用「节点重入 + 时间线文字」即可让评审看清回环。

### 4.2 可选增强（P1/P2）

- **回边箭头**：引入 SVG overlay，把 `quality_gate→generator_cluster`、`critic→retriever`、`retriever→planner` 三条回边画成弧形虚线（用 `NODE_ORDER` 索引换算 x 坐标）。
- **节点状态机完整化**：`nodeStates` 支持 `skipped`（`triage_skip` 时其余 10 节点置 `skipped`，而非 `pending`），语义更准确。
- **grep 级自检**：落地后 `grep -rn "animateFlow\|setTimeout" src/` 确认三处调用点不再用假动画驱动流程图。

---

## 5. 风险与边界

### 5.1 `triage` 快路径（不发完整 11 节点流）

低风险请求短路（`api/langgraph.py:53-71`）：只发 `status: triage_skip` → `content: teacher` → `status: done` → `[DONE]`，**没有任何 11 节点 `node_done`**。

- **处理**：composable 在 `triage_skip` 时置 `fastPath=true`、`completedNodes=[0]`、`nodeStates[0]='completed'`、`flowLoading=false`。
- **渲染**：`LangGraphFlow` 只亮 `triage` 节点 + 显示"快速答疑（未进入完整流水线）"徽标；其余 10 节点 `skipped`（P2）或 `pending`（MVP 可接受）。
- **边界**：快路径回退流水线（`api/langgraph.py:66-67`，quick_answer 失败）时 `_triage_level` 置 high，后续正常走 11 节点流，composable 的 `fastPath` 需在收到首个非 triage `node_done` 时清回 `false`。

### 5.2 `node_done` 重复事件（回环误判风险，关键）

`api/langgraph.py` 中：
- 147 行：每个节点通用 `yield _sse("node_done", node_name, ...)`
- 165 行：`retriever` **又发一次** `node_done`（带检索命中数）
- 220 行：`evidence_check` **又发一次** `node_done`（带冲突数）

→ 若用"二次 node_done=回环"判重入，`retriever`/`evidence_check` 会在**每次正常执行**被误判为回环。**双重防护**：
1. 前端 `lastNodeDoneField` 相邻去重（§2.2 步骤 a）：同字段连续第二个忽略。
2. 后端（推荐）删 165/220 两行，从源头消除。

> 注意：`retriever` 的两条 `node_done` 是**相邻**的（147→163-167），`evidence_check` 同理（147→215-220）；真实回环的二次 `node_done` 中间必隔着其他节点的 `node_done`。相邻去重不会误杀真实回环。

### 5.3 `node_done` 与 `content` 的到达顺序

`astream(stream_mode="updates")` 下，每个节点原子产出后，`node_done`（147 行）**先于**该节点的 `content/status`（150-264 行）到达。composable 只消费 `node_done`/`gate_*`/`status`，`content`/`data`/`evidence` 仍由 `ResourceView` 既有分支处理（531-563 行），两者并行、互不依赖，无顺序冲突。仅需保证 `flow.handleEvent(evt)` 对**所有** `evt` 都被调用（或至少对 `node_done`/`gate_*`/`status` 调用）。

### 5.4 `completedNodes` 单调性 vs 回环回退

见 §2.3：`completedNodes` 单调（进度条不回退），回环用 `nodeStates`/`retryCount` 表达。二者分层，无冲突。**注意**：进度条 `completedNodes.length/11` 在回环时已到 100%，重入不使其倒退（符合现有 `progressPct` 的"单调不回退"意图）。

### 5.5 `loading` 语义耦合

`LangGraphFlow.nodeState()` 中 `active` 态**依赖 `props.loading===true`**（`LangGraphFlow.vue:77`）。ResourceView 的 `loading` ref 在生成期间恰为 `true`，直接绑定即可；EngineView 演示态需把 `loading` 绑到演示/真实流进行中标志（当前写死 `:loading="false"`，`EngineView.vue:210`，导致 active 态从不显示——修正时应一并处理）。

### 5.6 两面板端点非 11 节点图（语义陷阱）

`FrugalRAGPanel`（`/engine/frugal-rag-full`）与 `GOMARLPanel`（`/engine/gomarl-consensus`）**不是** LangGraph 11 节点流水线，它们挂 `<LangGraphFlow>` 属误导。**处置：移除**（§3.5/§3.6），而非试图"由父级传入真实流转状态"——因为这两个端点根本没有 11 节点流可传。

---

## 6. 验收标准

落地后按下述逐条验证「流程图显示的是真实执行而非假动画」：

1. **逐节点推进**：在 `ResourceView` 输入真实主题（如"TCP 三次握手"）触发 `generateResource()`，流程图应随 `node_done` 从 `triage`→…→`path_planner` 逐节点亮起；用 DevTools Network 面板可见 `POST /api/agents/langgraph/stream` 的 SSE 帧与节点点亮一一对应。
2. **无假动画残留**：`grep -rn "animateFlow\|setTimeout" src/views/ResourceView.vue src/views/EngineView.vue src/components/FrugalRAGPanel.vue src/components/GOMARLPanel.vue` 确认不再有 `setTimeout` 驱动流程图（`ResourceView`/`EngineView` 的其它非流程图 `setTimeout` 允许存在，但流程图相关必须来自 `useOrchestrationFlow`）。
3. **回环可观测**：用能触发 `quality_gate` FIX 的输入（或临时调严 `quality_gate` 阈值），`generator_cluster` 节点应显示重入态 + `retryCount`（"×2"），回环时间线出现 "`quality_gate → 回退 generator_cluster`"。
4. **快路径兼容**：输入"你好"触发 `triage_skip`，流程图只亮 `triage` + "快速答疑"徽标，不出现 11 节点全亮；无 JS 报错。
5. **重复事件不误判**：正常生成时 `retriever`/`evidence_check` 不应显示 `retrying` 态（连续去重生效，或后端已删重复行）。
6. **语义正确**：流程图 `assessor` 显示"评估反馈"、`critic` 显示"质量校验"，与后端职责一致。

---

## ✅ 行动清单

| 优先级 | 动作 | 负责角色 | 精确改动点 |
|---|---|---|---|
| **P0** | 新增 `useOrchestrationFlow.ts` | 前端实现 | `src/composables/useOrchestrationFlow.ts`（§3.1，含 11 节点常量+`handleEvent`+`reset`） |
| **P0** | 扩展 `LangGraphFlow.vue` 到 11 节点 + 语义修正 + retry 视觉 | 前端实现 | `src/components/LangGraphFlow.vue` 35-79 行 + 新增 `.flow-circle--retrying` 样式（§3.2） |
| **P0** | `ResourceView` 接真实流驱动流程图 | 前端实现 | `src/views/ResourceView.vue` import + `generateResource()` 喂 `flow.handleEvent` + 模板新增 `<LangGraphFlow>`（§3.3） |
| **P0** | 移除 `FrugalRAGPanel`/`GOMARLPanel` 假动画与流程图 | 前端实现 | `FrugalRAGPanel.vue` 49-65/86/130-137 行；`GOMARLPanel.vue` 30-46/72/106-113 行（§3.5/§3.6） |
| **P0** | `EngineView` 标签/描述对齐 11 节点真值 + 演示按钮标注"模拟" | 前端实现 | `EngineView.vue` 20-35 行、215 行、210 行 `loading` 绑定（§3.4） |
| **P1** | 新增 `--agent-triage` 颜色变量（两套主题） | 前端实现 | `src/assets/styles/_variables.css:329-338`、`526-535` 两处 |
| **P1** | 后端删重复 `node_done`（消除回环误判源头） | 后端实现 | `py-server/api/langgraph.py:165`、`:220`（§3.7） |
| **P1** | `EngineView` 新增"接真实流"模式 | 前端实现 | `EngineView.vue` 复用 `useOrchestrationFlow`（§3.4 P1） |
| **P2** | 回边弧形箭头 + `skipped` 节点态 + `funnel` 图标 | 前端实现 | `LangGraphFlow.vue` SVG overlay；`icons.ts` 新增图标（§4.2） |

---

## ⚠️ 待完善 / 已知局限

1. **回边无物理箭头（MVP）**：用"重入态 + 时间线"表达回环，非曲线箭头；若答辩需"看得见回路"的强视觉，需 P2 的 SVG overlay。
2. **`triage_skip` 的其余节点语义**：MVP 下为 `pending`，`skipped` 态属 P2，视觉上"未进入"表达略弱。
3. **`EngineView` 暂无输入口**触发真实生成（演示页无 topic 输入框），"接真实流"需复用 ResourceView 的入参或新增输入框（P1 决策点）。
4. **两面板删除流程图后**，其"LangGraph 协同流程"信息在引擎页消失——若需保留"全景示意"，应由 `EngineView` 的流程图统一承载，而非散落三处。
5. **图标 `compass` 复用** triage 属语义近似，非专用；追求精确需新增 `funnel`/`filter` 图标。
6. 本规格为**只读研究产出**，未修改任何源文件；行号以 2026-10-01 工作树为准，落地前建议实现 worker 按 `grep` 复核行号是否漂移。

---

## 📚 数据来源 & 成员产出索引

**读过的文件（本次规格事实锚点）**：

| 文件 | 关键行 | 用途 |
|---|---|---|
| `py-server/agents/graph.py` | 1-161（全文） | 11 节点拓扑 + 3 处条件边/回环 |
| `py-server/api/langgraph.py` | 1-299（全文，重点 53-71、147、165、203-264、284-299） | SSE 事件类型 + `node_done` 重复 + triage 快路径 + `_node_summary` |
| `src/views/ResourceView.vue` | 1-60、380-447、449-569、843-898 | 真实 SSE 消费方（`stageMap`/`contentAgentMap`/5 步 `agentSteps`） |
| `src/components/LangGraphFlow.vue` | 1-424（全文） | 纯展示组件 props/三态判定/图标/颜色/描述 |
| `src/views/EngineView.vue` | 1-250（重点 16-54、205-217） | 硬演调用点 1 |
| `src/components/FrugalRAGPanel.vue` | 1-137（重点 49-65、79-103、130-137） | 硬演调用点 2（端点 `/engine/frugal-rag-full`） |
| `src/components/GOMARLPanel.vue` | 1-113（重点 30-46、67-87、106-113） | 硬演调用点 3（端点 `/engine/gomarl-consensus`） |
| `src/utils/api.ts` | 225-249 | `postStream` 契约（支持 AbortSignal） |
| `src/components/icons.ts` | 69-377 | 可用图标 key（无 `triage`/`filter`/`funnel`） |
| `src/assets/styles/_variables.css` | 329-338、526-535 | 10 个 `--agent-*` 变量（缺 `--agent-triage`） |

**成员产出索引**：本文件为 architect-5 唯一交付物；上游侦察结论由 team-lead 提供（已抽查复核，未发现与侦察不符的事实）。
