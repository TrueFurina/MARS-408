import { reactive, ref } from 'vue'
import { icons } from '@/components/icons'

/**
 * 编排流单一真源 —— 后端 LangGraph SSE `node_done` 事件 → 前端节点流转状态。
 *
 * 后端（py-server）已通过 `agent_graph.astream` 发送真实 `node_done`（field=节点名），
 * 本 composable 是「SSE 事件 → currentNode / completedNodes / 回路重试态」的唯一真源，
 * 供 ResourceView（真实流）与 EngineView（演示态）共用，避免状态逻辑各写一份漂移。
 *
 * 关键设计：
 * - `completedNodes` 保持单调只增（进度条不回退），回环用 `nodeStates`/`retryCount` 分层表达。
 * - 「相邻去重」兜底：后端 retriever / evidence_check 各连发两次 node_done（正常执行），
 *   与真实回环（中间必隔其他节点）区分，避免误判重入。
 */

export type NodeVisualState =
  | 'pending'
  | 'active'
  | 'completed'
  | 'retrying'
  | 'rejected'

export interface SseEvent {
  type: string
  field?: string
  content?: unknown
}

export interface LoopEvent {
  from: string
  to: string
  n: number
}

export interface OrchestrationNode {
  name: string
  index: number
  label: string
  icon: keyof typeof icons
  color: string
  description: string
}

/** 图序真源：后端 LangGraph 11 节点（py-server/agents/graph.py，set_entry_point("triage")） */
export const NODE_ORDER: string[] = [
  'triage', 'coordinator', 'diagnostician', 'planner', 'retriever',
  'generator_cluster', 'assessor', 'critic', 'evidence_check', 'quality_gate', 'path_planner',
]

export const NODE_INDEX: Record<string, number> = NODE_ORDER.reduce(
  (acc, name, idx) => {
    acc[name] = idx
    return acc
  },
  {} as Record<string, number>,
)

/**
 * 节点元数据单一真源（label/icon/color/description）。
 * LangGraphFlow 默认值、EngineView 的 flowNodeLabels/flowStepDetails 均从这里派生。
 * 注：`triage` 颜色暂用 `var(--accent-primary)` 兜底（--agent-triage 属 P1，见规格 §1.4）。
 */
export const ORCHESTRATION_NODES: OrchestrationNode[] = [
  { name: 'triage',            index: 0,  label: '分级路由', icon: 'compass',     color: 'var(--accent-primary)',  description: 'Triage 分级路由，低风险短路快路径' },
  { name: 'coordinator',       index: 1,  label: '协调',     icon: 'target',      color: 'var(--agent-coord)',    description: '全局协调、解析请求与画像' },
  { name: 'diagnostician',     index: 2,  label: '诊断',     icon: 'search',      color: 'var(--agent-diag)',     description: '学情诊断知识薄弱点' },
  { name: 'planner',           index: 3,  label: '规划',     icon: 'mapPin',      color: 'var(--agent-plan)',     description: '制定任务规划与检索策略' },
  { name: 'retriever',         index: 4,  label: '检索',     icon: 'book',        color: 'var(--agent-retrieve)', description: 'FrugalRAG 多轮检索' },
  { name: 'generator_cluster', index: 5,  label: '生成',     icon: 'robot',       color: 'var(--agent-gen)',      description: '7 类资源并行生成' },
  { name: 'assessor',          index: 6,  label: '评估反馈', icon: 'checkCircle', color: 'var(--agent-eval)',     description: '评估生成资源质量并反馈' },
  { name: 'critic',            index: 7,  label: '质量校验', icon: 'eye',         color: 'var(--agent-quality)',  description: '三元评审共识与一致性校验' },
  { name: 'evidence_check',    index: 8,  label: '证据校验', icon: 'scale',       color: 'var(--agent-evidence)', description: '证据校验与防幻觉 grounding' },
  { name: 'quality_gate',      index: 9,  label: '产物验收', icon: 'shield',      color: 'var(--agent-gate)',     description: '产物验收闸门（PASS/FIX/REJECT）' },
  { name: 'path_planner',      index: 10, label: '路径规划', icon: 'path',        color: 'var(--agent-path)',     description: '输出最终个性化学习路径' },
]

export function useOrchestrationFlow() {
  const currentNode = ref(-1)                                  // 活跃索引
  const completedNodes = ref<number[]>([])                     // 已完成索引（单调只增）
  const nodeStates = ref<Record<number, NodeVisualState>>({})  // 逐节点视觉态（含 retrying/rejected）
  const retryCount = ref<Record<number, number>>({})           // 回环重入计数（按节点，从 1 起）
  const gateVerdict = ref<'pass' | 'fix' | 'reject' | null>(null)
  const fastPath = ref(false)                                  // triage_skip 快路径
  const flowLoading = ref(false)
  const loopLog = ref<LoopEvent[]>([])                         // 回环时间线

  let lastNodeDoneField: string | null = null  // 相邻去重：同字段连续第二个 node_done 忽略
  let prevNodeField: string | null = null      // 上一个非重复 node_done，用于 loopLog.from

  /** 幂等消费一条 SSE 事件（仅 node_done、gate_pass/gate_fix/gate_rejected、status 生效；content/data/evidence 由调用方另行处理） */
  function handleEvent(evt: SseEvent): void {
    if (!evt || !evt.type) return

    if (evt.type === 'node_done') {
      const field = (evt.field || '') as string
      const idx = NODE_INDEX[field]
      if (idx == null) return  // 未知字段忽略

      // (a) 相邻去重：后端 retriever / evidence_check 各连发两次 node_done（正常执行）
      if (field === lastNodeDoneField) return
      lastNodeDoneField = field

      // 快路径回退：quick_answer 失败后走完整流水线，收到首个非 triage node_done 时清回
      if (fastPath.value && field !== 'triage') fastPath.value = false

      // (b) 回环检测：前进游标 —— 新节点索引 < 上一个节点索引 才判回环重入。
      // completedNodes 单调只增不删，不能用 includes 判回环：回环后下游节点索引仍留在其中，
      // 它们的"二次完成"会被误判为 retrying。例：quality_gate(FIX)→generator_cluster 二次时
      // idx=5 < 9 判回环；generator_cluster 二次后 assessor 二次 idx=6 > 5 → 正常完成。
      const prevIdx = prevNodeField != null ? (NODE_INDEX[prevNodeField] ?? -1) : -1
      if (idx < prevIdx) {
        // 回环重入（统一覆盖三条回边：retriever→planner / critic→retriever / quality_gate→generator_cluster）
        retryCount.value[idx] = (retryCount.value[idx] || 0) + 1
        nodeStates.value[idx] = 'retrying'
        // 视觉回退：图序 >= idx 的下游回到 pending/retrying，但 completedNodes 不删（保持单调）
        for (let j = idx; j < NODE_ORDER.length; j++) {
          nodeStates.value[j] = j === idx ? 'retrying' : 'pending'
        }
        loopLog.value.push({ from: prevNodeField ?? 'start', to: field, n: retryCount.value[idx] })
      } else {
        // 正常推进（含回环后下游节点的"二次完成"）；防御性去重避免 completedNodes 出现重复项
        if (!completedNodes.value.includes(idx)) completedNodes.value.push(idx)
        nodeStates.value[idx] = 'completed'
      }

      prevNodeField = field
      currentNode.value = idx
      flowLoading.value = true
      return
    }

    if (evt.type === 'gate_fix') {
      gateVerdict.value = 'fix'
      const qg = NODE_INDEX['quality_gate']
      if (qg != null) {
        nodeStates.value[qg] = 'completed'
        // 防御性：确保 quality_gate 已在 completedNodes（正常情况下其 node_done 已先到，
        // 此处兜底，避免闸门节点在进度条中缺失）
        if (!completedNodes.value.includes(qg)) completedNodes.value.push(qg)
      }
      return
    }
    if (evt.type === 'gate_pass') {
      gateVerdict.value = 'pass'
      return
    }
    if (evt.type === 'gate_rejected') {
      gateVerdict.value = 'reject'
      const qg = NODE_INDEX['quality_gate']
      if (qg != null) nodeStates.value[qg] = 'rejected'
      flowLoading.value = false
      return
    }
    if (evt.type === 'status' && evt.field === 'triage_skip') {
      fastPath.value = true
      completedNodes.value = [0]
      nodeStates.value = { 0: 'completed' }  // 清空其他键，只保留 triage
      flowLoading.value = false
      return
    }
    if (evt.type === 'status' && evt.field === 'done') {
      flowLoading.value = false
      return
    }
  }

  function reset(): void {
    currentNode.value = -1
    completedNodes.value = []
    nodeStates.value = {}
    retryCount.value = {}
    gateVerdict.value = null
    fastPath.value = false
    flowLoading.value = false
    loopLog.value = []
    lastNodeDoneField = null
    prevNodeField = null
  }

  // 用 reactive 包装：模板里 flow.currentNode 等自动解包（嵌套在普通对象中的 ref 不会自动解包）
  return reactive({
    currentNode,
    completedNodes,
    nodeStates,
    retryCount,
    gateVerdict,
    fastPath,
    flowLoading,
    loopLog,
    handleEvent,
    reset,
  })
}
