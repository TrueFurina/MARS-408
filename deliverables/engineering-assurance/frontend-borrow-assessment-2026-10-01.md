# 前端借鉴评估报告：学枢（React）→ study-help-pro（Vue3）

> 评估人：阿奇（Archi）· 系统架构师 · 工程保障团队
> 日期：2026-10-01
> 范围：只读跨代码库工程借鉴评估，未修改任何源文件，仅产出本交付文档
> 参考项目：`E:\Program\学枢`（Next.js 16 + React 19 + Tailwind v4 + Electron）
> 目标项目：`E:\Program\MARL\study-help-pro`（Vue3 + Vite + Pinia + vue-router + TypeScript，85 个 .vue）

---

## 📌 TL;DR

**能借，且"值得借的东西几乎全部框架无关"。** 学枢前端最有价值的资产不是 React 组件本身，而是三套**框架无关的范式**：①run-scoped 的编排态数据模型（`run_id / span_id / parent_span_id / sequence / attempt / status` + reducer 归并）；②`plan / progress / content / review / done` 的 SSE 事件协议；③"Provider 提升 + 服务端 SQLite 单一真源 + 防抖落盘"的会话态分层。这三样在 Vue3 + Pinia 里都能 1:1 照搬，**不存在技术栈鸿沟**。

**最值得借的前 3 项**：
1. **把"编排态"从"假动画"升级为"真事件流"**——你项目 `LangGraphFlow.vue` 目前是 `animateFlow()` 用 `setTimeout` 演的线性 10 节点动画，而后端其实有 11 节点 + `generator_cluster` 7 路并行扇出 + `critic`/`quality_gate` 驳回重做。学枢用 `AgentRunStore` + `AgentRunInspector`/`AgentPanel` 把 Supervisor→并行扇出→Reviewer 驳回画出来了，这是你项目最大、最显眼的能力缺口。
2. **SSE 事件协议升级**——你项目 `/chat/stream` 只发 `reasoning/tool_call/tool_result/content/error`，**没有编排事件**；学枢的 `plan/progress/content/review/done` 协议可直接映射到你后端已有的 LangGraph 11 节点。
3. **会话态分层与"单会话全站联动"**——你项目只有 4 个 store 且对话态只在 `studyStore`；学枢把编排态/会话态/资源规划态/路径态拆成独立 reducer 并用单一 Provider 提升，刷新与跨端由 SQLite 兜底。

**技术栈鸿沟：几乎没有。** 唯一"不可移植"的是 React Server Components、Tailwind 原子类、`framer-motion`、`lucide-react` 这些实现载体——它们承载的**设计决策（状态机、事件协议、数据模型）全部可移植**。你项目已有 Pinia + `@tanstack/vue-virtual` + `api.postStream`，落地所需的全部地基都在。

---

## 🎯 核心结论卡片

| 维度 | 评级 |
|------|------|
| **整体可借鉴度** | ★★★★★（高）——范式级可移植，非样式级可移植 |
| **技术栈鸿沟** | 极低——框架无关范式为主，React 特有部分占比 <15% |
| **可借鉴项数** | 6 个维度 / 21 个可落地点（见正文对照表） |
| **高价值项（P0）** | 3 项：编排态事件流化、SSE 协议升级、会话态分层 |
| **中价值项（P1）** | 3 项：资源查看器全屏化、防幻觉角标、事件回放 |
| **低价值/暂缓（P2）** | 3 项：SQLite 单源、路径树、视频任务流 |
| **建议下一步** | 先做 P0-1（编排态数据模型 + SSE 协议），这是其余一切的地基 |

**一句话结论**：你不是"缺前端能力"，而是"后端有真编排、前端在演假编排"——把学枢的编排态模型 + SSE 协议搬过来，是投入产出比最高的一步。

---

## 正文（6 个维度对照）

> 每个维度统一按 **「学枢怎么做 → 你项目现状 → 可借鉴点 → 落地成本 → 建议优先级」** 五段展开，末尾附对照表。

---

### 维度 1：多智能体编排可视化

#### 学枢怎么做

学枢的编排可视化分两层，都由**真实 SSE 事件**驱动，无任何前端造假的进度：

**（a）事件归并层 —— `lib/agent-run-store.ts`**
- `AgentRunStore` = `{ runs: Record<runId, AgentRunRecord>, activeRunId }`，纯 reducer（`agentRunStoreReducer`）。
- 每个 `AgentTraceStep`（span）带 `run_id / span_id / parent_span_id / sequence / attempt / event_type / action_type / status / evidence_ids / visibility / tool_policy`。
- `normalizeAgentRunEvent()` **拒绝无 `run_id` 的事件**，避免跨会话串轨迹；`bindNestedRunEventData()` 把工具启动的子 run 因果挂回父 run。
- `buildAgentSpanTree()` 用 `parent_span_id` 组装树，`selectRunSpans/selectRunParticipants` 派生视图。
- 关键语义：`span.status ∈ {pending, running, completed, failed, blocked, cancelled}`，`event_type ∈ {operation, reasoning, tool, delegate, verification, result}`，`action_type` 里明确有 `rework`（返工）、`review`（质量检查）。

**（b）呈现层 —— 两个组件**
- `agent-panel.tsx`：纵向**管线图** `profiler → outliner → supervisor → [并行生成区·LangGraph 扇出 2×N worker 网格] → reviewer → integrator → planner → tutor`，每节点有 `idle/working/done/rework/skipped` 状态 + 进度条 + shimmer；下方是**SSE 事件流终端**（LIVE 呼吸点 + 带 agent 着色 + log level 着色）。扇出区显式标注"并行生成区 · LangGraph 扇出"，并计数 `doneCount/workerCount`。
- `agent-run-inspector.tsx`：**时间线 + 三档密度**（过程/详细/结果），每条 span 带状态 glyph、参与者 chips、耗时、可展开详情；`delegate` 事件画 `from_agent → to_agent` 箭头；`rework`/`attempt>1` 标注"第 N 次"。
- 驳回重做在 UI 上的表达：worker 状态 `rework`（黄色边框）+ reviewer 状态 `rework` + `attempt` 计数 + 详情里的 `improvement_actions`。

#### 你项目现状（study-help-pro）

- `LangGraphFlow.vue`：**纯线性 10 节点**（协调→诊断→规划→检索→生成→评估→审核→证据校验→产物验收→路径规划），由 `currentNode: number` + `completedNodes: number[]` 两个 props 驱动。
- **关键问题：它是"演"出来的，不是"跑"出来的。** `FrugalRAGPanel.vue` 和 `GOMARLPanel.vue` 里都是 `animateFlow(2800)` —— 一个 `setTimeout` 循环按固定节奏点亮 10 个节点，与后端真实执行进度**零绑定**（后端 `/engine/frugal-rag-full`、`/engine/gomarl-consensus` 都是一次性 `api.post` 返回 JSON）。
- 它**漏画了三个关键结构**：①后端实际是 **11 节点**（入口还有 `triage`）；②`generator_cluster` 是 **7 个并行子 Agent**（Teacher/QuizMaster/MindMap/Extension/CodePractice/PPT/VideoScript），前端画成单节点"生成"；③`critic`/`quality_gate` 的**驳回重做回路**（`critic → retriever`、`quality_gate → generator_cluster` FIX/REJECT）在前端完全不可见。
- 没有编排态 store：没有 `run_id`、没有 span 树、没有 reducer，也没有任何"本轮哪个 agent 在干什么"的实时面板。

#### 可借鉴点

| # | 可借鉴点 | 说明 |
|---|---------|------|
| 1.1 | **run-scoped 编排态数据模型** | 直接照搬 `AgentTraceStep` 字段（`run_id/span_id/parent_span_id/sequence/attempt/status/event_type/action_type/evidence_ids`），在 Pinia 里用 `defineStore` + 纯函数 reducer 实现 |
| 1.2 | **扇出可视化** | 把 `LangGraphFlow` 的"生成"节点拆成 `generator_cluster` 的 2×N 网格，显式标注"并行扇出"，参考 `agent-panel` 的 WorkerCell |
| 1.3 | **驳回重做回路可视化** | 增加 `rework` 状态 + `attempt` 计数 + `from_agent → to_agent` 连线，把 `quality_gate FIX → generator_cluster` 画成回路 |
| 1.4 | **三档密度时间线** | 借鉴 `agent-run-inspector` 的"过程/详细/结果"切换，把 FrugalRAG 的 trajectory 升级为可折叠 span 时间线 |
| 1.5 | **事件流终端** | 借鉴 `agent-panel` 的 LogTerminal（LIVE 呼吸点 + agent 着色），你项目后端日志已可透传 |

#### 落地成本：**中**（P0-1 数据模型 + reducer 是纯前端，约 1-2 天；但要让后端真发事件，需同步改 FastAPI，见维度 5）

#### 建议优先级：**P0**（这是你项目与学枢最大的可见差距，也是路演/答辩最能体现"真多智能体"的加分项）

---

### 维度 2：会话态 / 状态管理

#### 学枢怎么做

**单会话全站联动**的核心是三层：

1. **Provider 提升**：`OrchestratorProvider` 挂在根 layout 之上，`useOrchestrator()` 把 `messages / conversationHistory / activeConversationId / resources / path / plans / resourceExecution / agentRunStore / agents / logs / profile / ...` 全部塞进一个 Context，页面切换不卸载，对话/资源/路径状态跨路由常驻。
2. **单一持久化真源 + 防抖落盘**：SQLite（后端 `/api/memory/workspace`）是唯一真源，`version + clientUpdatedAt + expectedVersion` 做乐观并发；前端 400ms 防抖 + `workspaceSaveChainRef` 串行化写入；localStorage 只做旧版本一次性迁移。会话另存一张规范化表（`conversation-store.ts`），500ms 防抖。
3. **90 个 store 的"分层"不是堆文件，而是按职责切 reducer**：`agent-run-store`（编排态）、`conversation-store`（会话）、`learner-state`（工作区快照）、`resource-plan` / `resource-plan-runtime` / `resource-phase-reducer`（资源规划执行）、`learning-path-run-state`（路径运行态）、`resource-plan-recovery`（断线恢复）。每个都是**纯函数 reducer + 选择器（selector）**，不共享可变全局。

#### 你项目现状

- **只有 4 个 store**：`authStore / skillStore / studyStore / achievementStore`。`studyStore` 是一个 ~780 行的"上帝 store"，把认证委派、画像、科目、对话、SSE 流解析、题库、评估、知识图谱**全部塞在一起**。
- 对话态持久化：localStorage 为主（`mars408_conversations_<uid>`，20 条上限 + 4MB 阈值瘦身），`PUT /user/conversations` 做后端兜底。**双写但没有冲突仲裁**（谁先写谁赢，无 version）。
- SSE 解析逻辑**内联在 `sendMessageStream` 里**（`data:` 行切分 + `JSON.parse` + 手写 reasonStart/toolCallStart 计时），无法复用，也无法单元测试。
- 没有"编排态"这一层（编排进度要么是组件局部 `ref`，要么是假动画）。
- 好消息：你项目已有 `@tanstack/vue-virtual`、`api.postStream`、Pinia 组合式 store、`shallowReactive`，地基齐全。

#### 可借鉴点

| # | 可借鉴点 | 说明 |
|---|---------|------|
| 2.1 | **"上帝 store 拆 reducer"** | 把 `studyStore` 里的 SSE 解析抽成纯函数 `normalizeChatEvent()` + `reduceChatEvent()`，与组件解耦，可单测 |
| 2.2 | **编排态独立 store** | 新增 `orchestrationStore`（Pinia），只存 `runs/spans/agents/logs/phase`，与 `studyStore` 的对话态分离 |
| 2.3 | **"单会话全站联动"** | 你项目对话态已在 Pinia 全局，天然跨路由；差距在于资源/路径/编排态没有跟随会话走，可借鉴学枢的"activeConversationId 挂载"模式 |
| 2.4 | **落盘版本仲裁** | 借鉴 `version + expectedVersion`，给 `PUT /user/conversations` 加 version 字段，防多标签页互相覆盖 |
| 2.5 | **防抖串行落盘** | 借鉴 400ms 防抖 + `saveChain` 串行化，替换现在的"每 2s 节流写 localStorage" |

#### 落地成本：**中**（2.1/2.2/2.5 纯前端，1-2 天；2.4 需后端加 version 字段，半天）

#### 建议优先级：**P0**（2.1 + 2.2 是维度 1 的前置）

---

### 维度 3：资源生成物的落地体验（七类资源查看器）

#### 学枢怎么做

`resource-viewer.tsx` 是一个**全屏覆盖层（portal 到 body）**，按 `item.type` 分发到 9 类正文：
- `explainer`（讲义）：左侧章节目录（滚动高亮）+ 正文 + 生活类比 + 要点总结 + **从正文自动抽取可运行 Python 代码块**（`extractPythonCodeExamples`）。
- `mindmap`（导图）：`MindmapWorkspace`，节点可点开 → 找相关讲义 / 生成配套练习。
- `quiz`（题库）：`QuizRunner`（独立组件，逐题作答 + 解析）。
- `solution`（解析）、`reading`（阅读/复盘反思）、`code`（代码 + 变体 + 可"生成演示"轨迹可视化）、`interactive`（HTML 沙箱）、`video`（视频任务：渲染进度条 + 断点恢复）、`courseware`（课件 → 全屏 `SlideDeck` + 导出 PPTX）。

三个"体验级"亮点：
1. **选中即问**：划选正文 → 浮层三个按钮「解释选中内容 / 就此询问 / 写笔记」，把选中文本带上下文压给智能教师开独立问答会话。
2. **整份资源一键讲解**：顶部「智能教师讲解」按钮，`explainPromptForResource()` 把该类型正文压成提示语（讲义→overview+explanation、导图→flattenNodes、课件→逐页标题）。
3. **学习行为埋点**：`useResourceLearningActivity` 用 visibilitychange/focus/blur + 5s 心跳记录阅读时长、滚动、选中、答题提交，滚到底即记"读完"。

#### 你项目现状

- 已有分散的查看器：`MindMapViewer.vue`、`PdfReader.vue`、`VideoPlayer.vue`、`StepQuiz.vue`、`SourceLabPane.vue`（注意：**这是 Linux 0.11 源码实验台，不是溯源面板**——任务描述里的"溯源面板"实为 `EvidenceCheckPanel.vue`）。
- **没有统一的全屏资源查看器**：各查看器各自为政，没有"划选即问""整份讲解""读完打点"这类联动体验。
- 题库交互（`StepQuiz`）相对简单，没有学枢 `QuizRunner` 的"成组呈现 + 逐题解析 + 提交反馈"闭环。
- 课件（PPT）没有放映器，视频已有 `VideoPlayer`（但你项目视频走 `/multimodal/generate-teaching-video` 一次性返回 HTML，无任务流）。

#### 可借鉴点

| # | 可借鉴点 | 说明 |
|---|---------|------|
| 3.1 | **统一全屏资源查看器外壳** | 新建一个 `ResourceViewer.vue`（全屏 overlay + 顶栏 + 类型分发），复用你现有 `MindMapViewer/PdfReader/VideoPlayer` 作为子类型 |
| 3.2 | **"划选即问 / 整份讲解"** | 借鉴 `explainPromptForResource` + 选中浮层，落到你项目的"多模态导师答疑"链路（`askTutor` / `/tutor/enhanced-answer`） |
| 3.3 | **题库闭环** | 借鉴 `QuizRunner` 的逐题作答 + 即时解析 + 提交统计 |
| 3.4 | **阅读完成打点** | 借鉴 `useResourceLearningActivity` 的滚到底记完成 + 时长/交互埋点，喂给你项目的 achievementStore |
| 3.5 | **讲义章节目录** | 借鉴 `lectureSections` 的滚动高亮目录 |

#### 落地成本：**中**（3.1/3.2 是外壳 + 提示语工程，1-2 天；3.3/3.4 各 0.5-1 天）

#### 建议优先级：**P1**（体验提升明显，但优先级低于"编排态"这条主命脉）

---

### 维度 4：防幻觉溯源的可视化表达

#### 学枢怎么做

学枢的防幻觉表达分三处，层层递进：
1. **`ResourceItem.sources` 角标**：每个资源卡片右上角一个 `[来源 n]` 数字角标，n 来自生成器引用的 `source_ids` 数量——这是"一句话可信度"。
2. **span 级 `evidence_ids`**：编排时间线里每条 span 携带 `evidence_ids`，详情展开时以 `<code>` 标签列出证据 id。
3. **`rework` / `review` 驳回态**：reviewer 驳回 + `improvement_actions` + `acceptance_check` + `tool_policy`（只读/会写入/可能破坏/执行前确认）标签，把"哪些是机器校验过、哪些被驳回过"透明呈现。

#### 你项目现状（这里其实你项目并不弱）

- **`EvidenceCheckPanel.vue` 已经相当强**：一致性得分、冲突卡片（severity/evidence 数/disposition）、**修正前后 diff**、**半圆置信度仪表盘**、**引用章节 + 相关度 `(score.toFixed(2))`**、证据原文 + **相似度 `(e.score.toFixed(2))`**。嵌入相似度溯源**已经画出来了**。
- `FrugalRAGPanel.vue` 有 trajectory 时间线（`search_query/observation/rewrite/stop_decision/kg_expansion/...`），检索轨迹也可见。
- 缺口在于**"回答正文里的逐句角标"**：你项目的溯源集中在"侧栏报告"和"引擎页"，但**对话主界面（ChatView）里 assistant 的正文没有 `[来源n]` 角标**，学生读答案时不知道哪句来自哪条证据。
- 另外 `SourceLabPane.vue` 实为源码实验台，任务描述里"溯源面板"的定位有误（见 ⚠️ 待完善）。

#### 可借鉴点

| # | 可借鉴点 | 说明 |
|---|---------|------|
| 4.1 | **正文 `[来源 n]` 角标** | 借鉴 `ResourceItem.sources` 的思路，把 FrugalRAG 返回的 citation 映射到 assistant 正文句级角标（点击浮出"相关度 + 证据原文"） |
| 4.2 | **驳回态可视化** | 借鉴 `rework`/`attempt`/`acceptance_check` 表达，把 `quality_gate` 的 FIX/REJECT 在正文旁显示为"本段经 N 轮校验" |
| 4.3 | **复用而非重造** | 你已有 `EvidenceCheckPanel` 的 diff/gauge/citation 组件，学枢可借鉴的是"把这些表达**前移到对话正文**，而不是只放在引擎页" |

#### 落地成本：**低-中**（4.1 需后端 chat/stream 返回 citation 对齐，半天；4.2 依赖维度 1 的编排态；4.3 是布局/复用调整）

#### 建议优先级：**P1**（4.1 直接提升"防幻觉"的可感知度，答辩有说服力）

---

### 维度 5：SSE 实时通信模式

#### 学枢怎么做

`core/sse.py` 定义了**命名事件协议**：`sse_format(event, data)` 产出 `event: {name}\ndata: {json}\n\n`。事件族：
- `plan`（{topic, modules}）→ `progress`（{agent, status, detail}）→ `content`（{agent, type, data}）→ `review`（{task_id, approved, issues}）→ `done`（{completed, status}）
- 另有 `trace`（编排 span）、`stage`、`exam`、`graded`、`report`、`error`。
- 关键工程细节：`astream_via_thread` 用线程桥接兼容 py3.10（你项目后端同样是 py3.10，可直接参考其 `Queue` 桥接 + 背压 + 取消语义）；前端 `streamSSE` 按 `event` 分发到 `useOrchestrator` 的 `executePlan`，`resourcePresentation`（`reasoning-presentation`）用队列做"思考事件先入队、结果 delta 限速回放"。
- **事件可回放**：`fetchAgentRunEvents(runId)` 让刷新后能重放历史 run 的 span（消息只存 `runId`，轨迹不进消息）。

#### 你项目现状

- 后端 `api/chat.py` 的 `/chat/stream` 已经用 `StreamingResponse + text/event-stream`，但事件只有 `reasoning / tool_call / tool_result / content / error / safety_alert`，**没有编排事件**；且是"LLM 工具调用循环"，不是 LangGraph 编排流。
- 后端**有完整的 LangGraph 11 节点图**（`agents/graph.py`），含 `generator_cluster` 7 路并行扇出 + `critic`/`quality_gate` 驳回回路——但**没有通过 SSE 把这些节点进度吐给前端**，`/engine/*` 全是 `api.post` 一次性 JSON。
- 前端 `api.postStream` 已支持 `AbortController`，但 `studyStore.sendMessageStream` 是手写 `data:` 行解析，没有 event 名分发、没有重连、没有回放。

#### 可借鉴点（这是"能否映射"的正面回答）

**能映射，且你项目后端已经具备全部原料。** 映射关系：

| 学枢事件 | 你项目 LangGraph 节点 | 触发点 |
|---------|---------------------|--------|
| `plan` | `planner` 产出 task 列表 | 任务规划完成时 |
| `progress` | `triage/coordinator/diagnostician/retriever/assessor/critic/evidence_check/quality_gate/path_planner` 各节点 | 每节点进入/完成时 |
| `content` | `generator_cluster` 7 个子 Agent 产出 | 每个资源产物生成时 |
| `review` | `critic` + `quality_gate`（FIX/REJECT） | 驳回/通过时 |
| `done` | `path_planner → END` | 图结束时 |

| # | 可借鉴点 | 说明 |
|---|---------|------|
| 5.1 | **后端加命名事件流** | 在 LangGraph 节点间发 `progress`/`review`/`done`（LangGraph 有 `stream_mode`/`get_stream_writer`，py3.10 受限可参考学枢的线程桥接 `astream_via_thread`） |
| 5.2 | **前端 event 分发器** | 用 `streamSSE` 风格按 `event` 名分发到编排态 reducer，替换手写 `data:` 解析 |
| 5.3 | **run_id 绑定 + 回放** | 消息只存 `runId`，`fetchAgentRunEvents(runId)` 回放历史 run 的 span（你项目目前对话刷新后轨迹全丢） |
| 5.4 | **断开重连 / 终态兜底** | 借鉴学枢"SSE 掉线后用持久化快照兜底、不把 UI 卡在处理中"的语义 |

#### 落地成本：**高**（这是唯一需要后端 + 前端协同的维度；后端 LangGraph 事件插桩约 2-3 天，前端分发器 + 回放约 1-2 天）

#### 建议优先级：**P0**（它是维度 1 的"燃料"，没有事件流，编排可视化仍是空壳）

---

### 维度 6：架构可复用度总结

#### 框架无关、可直接照搬的范式（✅ 照搬）

| 范式 | 学枢载体 | 你项目落点 |
|------|---------|-----------|
| run-scoped 编排态数据模型 | `agent-run-store.ts`（纯 TS） | Pinia `orchestrationStore` + 纯函数 reducer |
| SSE 命名事件协议 | `core/sse.py` + `streamSSE` | FastAPI `StreamingResponse` + `api.postStream` 分发器 |
| 事件归一化 + 防串轨迹 | `normalizeAgentRunEvent` / `acceptsBoundRun` | 同名纯函数 |
| 状态机分层（conversation/plan/phase） | 90 个 reducer store | 拆分 `studyStore` 上帝 store |
| 乐观并发落盘（version） | `learner-state.ts` | `PUT /user/conversations` 加 version |
| 防抖串行落盘 | `workspaceSaveChainRef` | Pinia 内 Promise chain |
| 编排态派生选择器 | `selectRunSpans/buildAgentSpanTree` | 同名 computed/getter |
| 消息 kind 分发渲染 | `chat.tsx` 的 `MessageKind` | `ChatView` 的 segments 已部分具备 |

#### React 特有、不可移植的实现载体（❌ 需重新实现，但决策可迁移）

| 载体 | 说明 | Vue3 等价物 |
|------|------|------------|
| React Server Components / Next.js | 服务端渲染 | 你项目是纯 SPA，无需 SSR，直接忽略 |
| Tailwind v4 原子类 | 样式载体 | 你项目的 `--design-token` CSS 变量体系（已在用） |
| `framer-motion` | 动画 | CSS transition + `<Transition>`（你项目已用） |
| `lucide-react` | 图标 | 你项目 `icons.ts`（已具备） |
| React Context Provider | 全局态提升 | Pinia store（天然全局，无需 Provider 那一层） |
| `createPortal` 全屏查看器 | overlay | Vue 的 `<Teleport to="body">` |

**净结论**：学枢的"骨架"（数据模型、事件协议、状态机、持久化策略）100% 可移植；"皮肤"（组件写法、样式、动画库）需按 Vue3 重写，但**决策本身已经替你踩过坑**，你不需要重新设计，只需翻译。

---

## ✅ 行动清单

> 按 P0 / P1 / P2 排序，每条含负责角色。共 9 条。

| 优先级 | 编号 | 行动 | 负责角色 |
|-------|------|------|---------|
| **P0** | A1 | 定义 run-scoped 编排态 TS 类型 + 纯函数 reducer（`run_id/span_id/parent_span_id/sequence/attempt/status/event_type/action_type/evidence_ids`），新建 Pinia `orchestrationStore` | 架构师 + 前端 |
| **P0** | A2 | 后端 LangGraph 11 节点插桩，按 `plan/progress/content/review/done` 发命名 SSE 事件（含 `generator_cluster` 扇出 + `critic`/`quality_gate` 驳回态），py3.10 参考学枢线程桥接 | 后端 + 架构师 |
| **P0** | A3 | 前端把 `studyStore.sendMessageStream` 的手写 `data:` 解析抽成纯函数 `normalizeChatEvent` + event 分发器；消息只存 `runId`，支持 `fetchAgentRunEvents` 回放 | 前端 |
| **P0** | A4 | 升级 `LangGraphFlow.vue`：11 节点 + `generator_cluster` 2×N 扇出网格 + 驳回回路 + 事件流终端，接入 `orchestrationStore`（废除 `animateFlow` 假动画） | 前端 |
| **P1** | B1 | 新建统一全屏 `ResourceViewer.vue`（`<Teleport to="body">` + 类型分发），接入"划选即问 / 整份讲解"到 `/tutor/enhanced-answer` | 前端 |
| **P1** | B2 | 对话正文句级 `[来源 n]` 角标：把 FrugalRAG citation 映射到 assistant 正文，点击浮出"相关度 + 证据原文"（复用 EvidenceCheckPanel 的表达） | 前端 + 后端 |
| **P1** | B3 | 题库交互升级为"逐题作答 + 即时解析 + 提交统计"闭环，喂给 achievementStore | 前端 |
| **P2** | C1 | `PUT /user/conversations` 增加 `version` 字段做乐观并发 + 400ms 防抖串行落盘，替换 2s 节流写 localStorage | 后端 + 前端 |
| **P2** | C2 | 视频资源从"一次性返回 HTML"升级为任务流（渲染进度 + 断点恢复 + 失败重试），参考学枢 `VideoBody` | 后端 + 前端 |

---

## ⚠️ 待完善 / 已知局限

1. **未实际运行两项目**：本次为静态只读代码评估，未启动 study-help-pro 后端（8002）或学枢后端（8000）做端到端验证。SSE 事件时序、LangGraph `stream_mode` 在 py3.10 下的实际行为需以运行验证为准。
2. **SSE 协议需后端确认**：A2 中"11 节点插桩发事件"是架构建议，是否已存在部分插桩（`shared/sse_guard.py` 存在但 `/chat/stream` 未用编排事件）需后端 owner 确认，避免重复造轮子。
3. **`SourceLabPane.vue` 定位偏差**：任务描述称其为"溯源面板"，实际它是 **Linux 0.11 源码实验台**（`data/sourceLabExercises.ts` + WASM 编译）。真正的防幻觉溯源在 `EvidenceCheckPanel.vue`（+ `utils/evidence.ts`）。本报告维度 4 已按正确对应关系评估。
4. **store 计数口径**：任务描述"学枢 90 个 store"实为 `frontend/lib/` 下约 90 个模块文件（含 store/reducer/工具），并非 90 个独立全局 store；其本质是"纯函数 reducer + 选择器"的分层，本报告已按此语义表述。
5. **多标签页并发**：你项目当前 localStorage 双写无 version 仲裁，C1 建议的乐观并发仅在"改后端字段"后生效，未评估 Electron 桌面端（你项目当前非 Electron）的多进程场景。
6. **成本为相对估算**：各落地成本的"天"数基于单前端 + 单后端人力，未纳入测试、回归与评审时间；P0 的 A2（后端插桩）是最大不确定项。

---

## 📚 数据来源 & 成员产出索引

### 参考项目「学枢」关键文件（已读）
| 文件 | 用途 |
|------|------|
| `frontend/components/orchestrator-provider.tsx` | 全局 Provider 提升 + 会话态挂载 |
| `frontend/hooks/use-orchestrator.ts` | 编排引擎：SSE 消费 + 落盘 + 回放 + 消息生命周期 |
| `frontend/components/agent-run-inspector.tsx` | 三档密度 span 时间线 |
| `frontend/components/agent-panel.tsx` | 管线图 + 扇出区 + 事件流终端 |
| `frontend/lib/agent-run-store.ts` | run-scoped 编排态 reducer + 事件归一化 + span 树 |
| `frontend/lib/types.ts` | 领域类型（AgentTraceStep / ResourceData / SSE 协议对齐） |
| `frontend/components/chat.tsx` | 消息 kind 分发 + 内联 trace + 附件上传 |
| `frontend/components/resource-viewer.tsx` | 9 类资源查看器 + 划选即问 + 阅读埋点 |
| `frontend/lib/learner-state.ts` | SQLite 工作区 + 乐观并发落盘 |
| `backend/app/core/sse.py` | SSE 命名事件协议 + py3.10 线程桥接 |

### 目标项目「study-help-pro」关键文件（已读）
| 文件 | 用途 |
|------|------|
| `src/views/ChatView.vue` | 对话主界面 + segments 渲染 |
| `src/components/LangGraphFlow.vue` | 线性 10 节点进度（假动画） |
| `src/components/FrugalRAGPanel.vue` / `GOMARLPanel.vue` | 引擎页（`animateFlow` 假动画 + 一次性 JSON） |
| `src/components/EvidenceCheckPanel.vue` | 防幻觉溯源可视化（diff/gauge/citation/相似度） |
| `src/components/SourceLabPane.vue` | Linux 0.11 源码实验台（非溯源面板） |
| `src/stores/studyStore.ts` | 上帝 store（含内联 SSE 解析） |
| `src/utils/api.ts` | API 客户端（`postStream` + 401 拦截 + 重试） |
| `py-server/agents/graph.py` | LangGraph 11 节点 + 扇出 + 驳回回路 |
| `py-server/api/chat.py` | `/chat/stream` SSE（仅 LLM 工具循环事件） |

### 成员产出索引（本团队）
- 本报告：`deliverables/engineering-assurance/frontend-borrow-assessment-2026-10-01.md`（architect-4）
- 关联产出：架构债扫描（architect-2）、文档债基线（tech-writer 系列）——见 `deliverables/engineering-assurance/` 与 `deliverables/OVERVIEW-现状盘点-2026-09-15.md`

---

*（完）* 阿奇 · 系统架构师 · 2026-10-01
