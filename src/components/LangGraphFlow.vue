<script setup lang="ts">
/**
 * LangGraphFlow — 10 节点 LangGraph StateGraph 进度可视化
 *
 * 节点流转：协调(coordinator) → 诊断(diagnostician) → 规划(planner)
 *          → 检索(retriever) → 生成(generator) → 评估(assessor)
 *          → 审核(reviewer) → 路径规划(path_planner)
 *
 * 每节点有 4 种状态：
 *   pending   — 灰色圆圈，等待中
 *   active    — 发光脉冲 + Lottie-like spinner，正在执行
 *   completed — 绿色发光 ✓ checkmark，已完成
 *   skipped   — （保留，暂未使用）
 *
 * Props:
 *   currentNode: number — 当前活跃节点索引 (-1 表示全部 pending, 0-9 表示第几个活跃)
 *   completedNodes: number[] — 已完成节点索引数组
 *   stepDetails: string[] — 每步详细说明（可选）
 *   loading: boolean — 是否正在加载中
 */
import { computed, ref, watch } from 'vue'
import { icons } from '@/components/icons'

const props = withDefaults(defineProps<{
  currentNode: number
  completedNodes?: number[]
  stepDetails?: string[]
  loading?: boolean
  nodeLabels?: string[]
}>(), {
  currentNode: -1,
  completedNodes: () => [],
  stepDetails: () => [],
  loading: false,
  nodeLabels: () => [
    '协调', '诊断', '规划', '检索',
    '生成', '评估', '审核', '证据校验', '产物验收', '路径规划',
  ],
})

const nodeColors = [
  'var(--agent-coord)',    // 协调
  'var(--agent-diag)',     // 诊断
  'var(--agent-plan)',     // 规划
  'var(--agent-retrieve)', // 检索
  'var(--agent-gen)',      // 生成
  'var(--agent-eval)',     // 评估
  'var(--agent-quality)',  // 审核
  'var(--agent-evidence)', // 证据校验
  'var(--agent-gate)',     // 产物验收
  'var(--agent-path)',     // 路径规划
]

const nodeIcons: (keyof typeof icons)[] = [
  'target', 'search', 'mapPin', 'book',
  'robot', 'checkCircle', 'eye', 'scale', 'shield', 'path',
]

const nodeDescriptions = computed(() => {
  const defaults = [
    '分析学习目标与画像',
    '诊断知识薄弱点',
    '制定检索策略',
    '执行FrugalRAG检索',
    '多Agent协同生成',
    'GoMARL共识评估',
    '审核质量与冲突',
    '证据校验与防幻觉 grounding',
    '产物验收闸门质量把关',
    '输出最终学习路径',
  ]
  return props.stepDetails.length > 0 ? props.stepDetails : defaults
})

function nodeState(index: number): 'pending' | 'active' | 'completed' {
  if (props.completedNodes.includes(index)) return 'completed'
  if (props.currentNode === index && props.loading) return 'active'
  return 'pending'
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
      <span class="flow-title">LangGraph 10 节点协同流程</span>
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
        :style="{ width: `${(completedNodes.length / nodeLabels.length) * 100}%` }"
      ></div>
    </div>
  </div>
</template>

<style scoped>
.langgraph-flow {
  padding:1.25rem 1.5rem;
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-color);
  border-radius:1rem;
  margin-bottom:1.25rem;
  transition: all 0.3s ease;
}

.langgraph-flow.is-loading {
  border-color: var(--accent-primary);
  box-shadow: 0 0 20px var(--accent-primary-10);
}

.flow-header {
  display: flex;
  align-items: center;
  gap:0.75rem;
  margin-bottom:1.25rem;
}

.flow-badge {
  font-size:0.6875rem;
  font-weight: 700;
  padding:0.1875rem 0.75rem;
  border-radius:1.25rem;
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  text-transform: uppercase;
  letter-spacing:0.0312rem;
}

.flow-title {
  font-size:0.875rem;
  font-weight: 700;
  color: var(--text-primary);
}

.flow-subtitle {
  margin-left:auto;
  font-size:0.6875rem;
  color: var(--text-muted);
  font-weight: 500;
}

.flow-track {
  display: flex;
  align-items: flex-start;
  gap:0;
  padding:0.5rem 0;
  justify-content: center;
  flex-wrap: wrap;
}

/* ── 节点 ── */
.flow-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap:0.375rem;
  padding:0.5rem 0.375rem;
  min-width:5rem;
  transition: all 0.3s ease;
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
  transition: all 0.4s cubic-bezier(0.16, 1, 0.3, 1);
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

.circle-num {
  font-size:1rem;
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
  color: #fff;
}

.circle-check {
  font-size:1.25rem;
  font-weight: 900;
  color: #fff;
  animation: check-pop 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.node-label {
  font-size:0.75rem;
  font-weight: 700;
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
  font-size:0.875rem;
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
  margin-top:1rem;
  padding:0 0.125rem;
  color: var(--color-text-3);
  transition: all 0.4s ease;
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
  margin-top:1rem;
  overflow: hidden;
}

.flow-progress-fill {
  height:100%;
  background: var(--gradient-progress, linear-gradient(135deg, var(--accent-primary), var(--subject-ds)));
  border-radius:0.125rem;
  transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
  min-width:0;
}

/* ── 动画 ── */
@keyframes node-pulse {
  0%, 100% { box-shadow: 0 0 12px var(--node-color); }
  50% { box-shadow: 0 0 28px var(--node-color), 0 0 40px color-mix(in srgb, var(--node-color) 40%, transparent); }
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
    padding:0.25rem 0;
  }
  .flow-node {
    min-width:auto;
  }
}
</style>
