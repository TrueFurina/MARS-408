<script setup lang="ts">
/**
 * LangGraphFlow — 11 节点 LangGraph StateGraph 进度可视化
 *
 * 节点流转（与后端 py-server/agents/graph.py 对齐）：
 *   triage(分级路由) → coordinator(协调) → diagnostician(诊断) → planner(规划)
 *   → retriever(检索) → generator_cluster(生成) → assessor(评估反馈)
 *   → critic(质量校验) → evidence_check(证据校验) → quality_gate(产物验收)
 *   → path_planner(路径规划)
 *
 * 每节点状态：
 *   pending   — 灰色圆圈，等待中
 *   active    — 发光脉冲 + spinner，正在执行
 *   completed — 发光 checkmark，已完成
 *   retrying  — 琥珀呼吸环 + 重入角标（回环重试，加法扩展）
 *   rejected  — 红色（产物验收拒绝）
 *   skipped   — （保留，暂未使用）
 *
 * Props:
 *   currentNode: number — 当前活跃节点索引 (-1 表示全部 pending)
 *   completedNodes: number[] — 已完成节点索引数组
 *   stepDetails: string[] — 每步详细说明（可选，覆盖默认描述）
 *   loading: boolean — 是否正在加载中（决定 active 态）
 *   nodeLabels: string[] — 节点标签（可选，覆盖默认）
 *   nodeStates: Record<number,string> — 逐节点视觉态（retrying/rejected 由此外部注入，向后兼容）
 *   retryCount: Record<number,number> — 回环重入计数（用于 ×N 角标）
 *
 * 节点元数据（label/icon/color/description）默认值来自 ORCHESTRATION_NODES 单一真源，
 * 不再与 EngineView 等调用点各写一份，避免漂移。
 */
import { computed } from 'vue'
import { icons } from '@/components/icons'
import { ORCHESTRATION_NODES } from '@/composables/useOrchestrationFlow'

type VisualState = 'pending' | 'active' | 'completed' | 'retrying' | 'rejected'

const props = withDefaults(defineProps<{
  currentNode: number
  completedNodes?: number[]
  stepDetails?: string[]
  loading?: boolean
  nodeLabels?: string[]
  nodeStates?: Record<number, string>
  retryCount?: Record<number, number>
}>(), {
  currentNode: -1,
  completedNodes: () => [],
  stepDetails: () => [],
  loading: false,
  nodeLabels: () => ORCHESTRATION_NODES.map(n => n.label),
  nodeStates: () => ({}),
  retryCount: () => ({}),
})

const nodeColors = ORCHESTRATION_NODES.map(n => n.color)
const nodeIcons = ORCHESTRATION_NODES.map(n => n.icon)

const defaultDescriptions = ORCHESTRATION_NODES.map(n => n.description)
const nodeDescriptions = computed(() =>
  props.stepDetails.length > 0 ? props.stepDetails : defaultDescriptions
)

function nodeState(index: number): VisualState {
  // 外部注入的显式视觉态优先于 completedNodes 推导：回环回退时 composable 把下游节点置
  // 'pending'，此处必须尊重，否则又落回 completedNodes.includes → 显示 completed，视觉回退失效。
  // retrying 时该节点仍在 completedNodes 中，同样必须被外部态覆盖。
  const ext = props.nodeStates?.[index]
  if (ext && ['retrying', 'rejected', 'pending', 'active'].includes(ext)) {
    return ext as VisualState
  }
  if (props.completedNodes.includes(index)) return 'completed'
  if (props.currentNode === index && props.loading) return 'active'
  return 'pending'
}

/** 回环重入次数（0 = 未重入） */
function retryTimes(index: number): number {
  return props.retryCount?.[index] ?? 0
}

// ── 各状态的样式类 ──

function circleClass(index: number): string {
  const state = nodeState(index)
  const base = 'flow-circle'
  return `${base} ${base}--${state}`
}

function arrowClass(index: number): string {
  // 箭头连接第 index 到 index+1
  if (props.completedNodes.includes(index)) return 'flow-arrow flow-arrow--done'
  if (props.currentNode === index) return 'flow-arrow flow-arrow--active'
  return 'flow-arrow'
}
</script>

<template>
  <div class="langgraph-flow" :class="{ 'is-loading': loading }">
    <div class="flow-header">
      <span class="flow-badge">
        <span v-if="loading" v-html="icons.hourglass" class="badge-icon"></span>
        <span v-else v-html="icons.check" class="badge-icon"></span>
        {{ loading ? '执行中' : '就绪' }}
      </span>
      <span class="flow-title">LangGraph 11 节点协同流程</span>
      <span class="flow-subtitle">
        {{ loading
          ? `当前: ${nodeLabels[currentNode] || '初始化'}`
          : `${completedNodes.length}/${nodeLabels.length} 节点已完成`
        }}
      </span>
    </div>

    <div class="flow-track">
      <template v-for="(label, i) in nodeLabels" :key="i">
        <!-- 节点 -->
        <div class="flow-node" :class="`flow-node--${nodeState(i)}`">
          <div
            class="flow-circle"
            :class="circleClass(i)"
            :style="{ '--node-color': nodeColors[i] }"
          >
            <!-- pending: 数字 -->
            <span v-if="nodeState(i) === 'pending'" class="circle-num">{{ i + 1 }}</span>
            <!-- active: spinner -->
            <span v-else-if="nodeState(i) === 'active'" class="circle-spinner">
              <svg viewBox="0 0 24 24" class="spinner-icon">
                <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor"
                  stroke-width="2.5" stroke-dasharray="45" stroke-linecap="round">
                  <animateTransform attributeName="transform" type="rotate"
                    from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite" />
                </circle>
              </svg>
            </span>
            <!-- retrying: 回环重入（琥珀呼吸 + 重入角标） -->
            <span v-else-if="nodeState(i) === 'retrying'" class="circle-retry">
              <span class="retry-icon" v-html="icons.refresh"></span>
              <span v-if="retryTimes(i) > 0" class="retry-count">×{{ retryTimes(i) + 1 }}</span>
            </span>
            <!-- rejected: 产物验收拒绝 -->
            <span v-else-if="nodeState(i) === 'rejected'" class="circle-reject" v-html="icons.xCircle"></span>
            <!-- completed: checkmark -->
            <span v-else class="circle-check" v-html="icons.check"></span>
          </div>
          <div class="node-label">{{ label }}</div>
          <div class="node-desc">{{ nodeDescriptions[i] }}</div>
          <div class="node-icon" v-html="icons[nodeIcons[i]!]"></div>
        </div>

        <!-- 箭头 -->
        <div v-if="i < nodeLabels.length - 1" class="flow-arrow" :class="arrowClass(i)">
          <svg viewBox="0 0 24 20" class="arrow-svg">
            <line x1="2" y1="10" x2="22" y2="10" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
            <polyline points="16,4 22,10 16,16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>
      </template>
    </div>

    <!-- 进度条 -->
    <div class="flow-progress-bar">
      <div
        class="flow-progress-fill"
        :style="{ width: '100%', transform: `scaleX(${completedNodes.length / nodeLabels.length})`, transformOrigin: 'left' }"
      ></div>
    </div>
  </div>
</template>

<style scoped>
.langgraph-flow {
  padding:var(--space-5) var(--space-6);
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-color);
  border-radius:1rem;
  margin-bottom:var(--space-5);
  transition: var(--transition)
}

.langgraph-flow.is-loading {
  border-color: var(--accent-primary);
  box-shadow: 0 0 20px var(--accent-primary-10);
}

.flow-header {
  display: flex;
  align-items: center;
  gap:var(--space-3);
  margin-bottom:var(--space-5);
}

.flow-badge {
  font-size:var(--text-2xs);
  font-weight: var(--weight-bold);
  padding:0.1875rem var(--space-3);
  border-radius:1.25rem;
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  text-transform: uppercase;
  letter-spacing:0.0312rem;
}

.flow-title {
  font-size:var(--text-base);
  font-weight: var(--weight-bold);
  color: var(--text-primary);
}

.flow-subtitle {
  margin-left:auto;
  font-size:var(--text-2xs);
  color: var(--text-muted);
  font-weight: var(--weight-medium);
}

.flow-track {
  display: flex;
  align-items: flex-start;
  gap:0;
  padding:var(--space-2) 0;
  justify-content: center;
  flex-wrap: wrap;
}

/* ── 节点 ── */
.flow-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap:0.375rem;
  padding:var(--space-2) 0.375rem;
  min-width:5rem;
  transition: var(--transition);
  opacity: 0.55;
  position: relative;
}

.flow-node--active {
  opacity: 1;
  transform: scale(1.08);
}

.flow-node--active::after {
  content: '';
  position: absolute;
  inset:-0.25rem;
  border-radius:0.875rem;
  border: 1.5px solid var(--node-color, var(--accent-primary));
  opacity: 0.3;
  animation: node-ring-pulse 1.5s ease-in-out infinite;
}

.flow-node--completed {
  opacity: 1;
}

.flow-node--retrying,
.flow-node--rejected {
  opacity: 1;
}

.flow-node--completed::after {
  content: '';
  position: absolute;
  inset:-0.25rem;
  border-radius:0.875rem;
  border: 1.5px solid var(--accent-success);
  opacity: 0.2;
}

@keyframes node-ring-pulse {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50% { transform: scale(1.05); opacity: 0.1; }
}

.flow-circle {
  width:2.625rem;
  height:2.625rem;
  border-radius:50%;
  background: var(--bg-tertiary);
  border: 2px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
  position: relative;
}

/* pending */
.flow-circle--pending {
  border-color: var(--color-glass-border);
}

/* active */
.flow-circle--active {
  background: var(--node-color);
  border-color: var(--node-color);
  box-shadow: 0 0 16px var(--node-color), 0 0 32px color-mix(in srgb, var(--node-color) 35%, transparent);
  animation: node-pulse 1.5s ease-in-out infinite;
}

/* completed */
.flow-circle--completed {
  background: var(--node-color);
  border-color: var(--node-color);
  box-shadow: 0 0 8px var(--node-color);
}

/* retrying：回环重入，琥珀呼吸环（复用 --accent-warm） */
.flow-circle--retrying {
  background: var(--accent-warm);
  border-color: var(--accent-warm);
  animation: retry-pulse 1.5s ease-in-out infinite;
}

/* rejected：产物验收拒绝，红色 */
.flow-circle--rejected {
  background: var(--accent-danger);
  border-color: var(--accent-danger);
  box-shadow: 0 0 8px var(--accent-danger);
}

.circle-num {
  font-size:var(--text-lg);
  font-weight: 800;
  color: var(--text-muted);
}

.circle-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner-icon {
  width:1.375rem;
  height:1.375rem;
  color: var(--color-text-on-accent);
}

.circle-check {
  font-size:var(--text-2xl);
  font-weight: 900;
  color: var(--color-text-on-accent);
  animation: check-pop 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

/* retrying：刷新图标 + 重入角标 */
.circle-retry {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-on-accent);
}
.retry-icon {
  display: inline-flex;
  animation: retry-spin 1.2s linear infinite;
}
.retry-icon svg {
  width: 1.25rem;
  height: 1.25rem;
}
.retry-count {
  position: absolute;
  top: -0.625rem;
  right: -0.875rem;
  min-width: 1.125rem;
  height: 1.125rem;
  padding: 0 0.25rem;
  border-radius: var(--radius-full);
  background: var(--accent-warm);
  color: var(--color-text-on-accent);
  font-size: 0.625rem;
  font-weight: var(--weight-bold);
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* rejected：红叉 */
.circle-reject {
  display: inline-flex;
  color: var(--color-text-on-accent);
}
.circle-reject svg {
  width: 1.25rem;
  height: 1.25rem;
}

.node-label {
  font-size:var(--text-xs);
  font-weight: var(--weight-bold);
  color: var(--text-primary);
  white-space: nowrap;
}

.node-desc {
  font-size:0.5625rem;
  color: var(--text-muted);
  max-width:5.625rem;
  text-align: center;
  line-height:1.3;
  display: none;
}

.flow-node--active .node-desc {
  display: block;
}

.node-icon {
  font-size:var(--text-base);
  position: absolute;
  top:-0.375rem;
  right:-0.375rem;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.flow-node--active .node-icon {
  opacity: 1;
}

/* ── 箭头 ── */
.flow-arrow {
  display: flex;
  align-items: center;
  align-self: flex-start;
  margin-top:var(--space-4);
  padding:0 0.125rem;
  color: var(--color-text-3);
  transition: var(--transition);
  flex-shrink: 0;
}

.flow-arrow--active {
  color: var(--flow-control);
}

.flow-arrow--done {
  color: var(--flow-data);
}

.arrow-svg {
  width:1.25rem;
  height:1rem;
}

/* ── 进度条 ── */
.flow-progress-bar {
  height:0.25rem;
  background: var(--bg-tertiary);
  border-radius:0.125rem;
  margin-top:var(--space-4);
  overflow: hidden;
}

.flow-progress-fill {
  height:100%;
  background: var(--gradient-progress, linear-gradient(135deg, var(--accent-primary), var(--subject-ds)));
  border-radius:0.125rem;
  width: 100%; transform-origin: left; transition: transform var(--duration-slow) var(--ease-standard);
  min-width:0;
}

/* ── 动画 ── */
@keyframes node-pulse {
  0%, 100% { box-shadow: 0 0 12px var(--node-color); }
  50% { box-shadow: 0 0 28px var(--node-color), 0 0 40px color-mix(in srgb, var(--node-color) 40%, transparent); }
}

@keyframes retry-pulse {
  0%, 100% { box-shadow: 0 0 12px var(--accent-warm); }
  50% { box-shadow: 0 0 28px var(--accent-warm), 0 0 40px color-mix(in srgb, var(--accent-warm) 40%, transparent); }
}

@keyframes retry-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes check-pop {
  0% { transform: scale(0.3); opacity: 0; }
  70% { transform: scale(1.2); }
  100% { transform: scale(1); opacity: 1; }
}

@media (max-width: 768px) {
  .flow-track {
    flex-direction: column;
    align-items: center;
  }
  .flow-arrow {
    transform: rotate(90deg);
    margin:0;
    padding:var(--space-1) 0;
  }
  .flow-node {
    min-width:auto;
  }
}
</style>
