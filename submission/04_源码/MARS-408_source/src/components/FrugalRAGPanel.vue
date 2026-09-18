<script setup lang="ts">
import { ref } from 'vue'
import { renderMarkdownSafe } from '@/utils/markdown'
import { api } from '@/utils/api'
import LangGraphFlow from '@/components/LangGraphFlow.vue'
import ProfileInputPanel from '@/components/ProfileInputPanel.vue'
import { icons } from '@/components/icons'

// ── 配置 ──
const question = ref('')
const course = ref('computer_network')
const loading = ref(false)
const result = ref<any>(null)
const startTime = ref(0)
const elapsedMs = ref(0)

const courseOptions = [
  { value: 'computer_network', label: '计算机网络' },
  { value: 'data_structures', label: '数据结构' },
  { value: 'operating_system', label: '操作系统' },
  { value: 'computer_organization', label: '计算机组成原理' },
]

const reviewStageOptions = [
  { value: 'basic', label: '基础阶段' },
  { value: 'strengthen', label: '强化阶段' },
  { value: 'comprehensive', label: '综合阶段' },
  { value: 'mock', label: '模考阶段' },
]

// ── 画像参数 ──
const profileInputRef = ref<InstanceType<typeof ProfileInputPanel> | null>(null)

// ── LangGraph 10 节点进度 ──
const flowActive = ref(false)
const flowCurrentNode = ref(-1)
const flowCompleted = ref<number[]>([])
const flowStepDetails = [
  '分析学习目标与画像', '诊断知识薄弱点', '制定检索策略与路径',
  '执行FrugalRAG多轮检索', '多Agent协同生成内容', 'GoMARL共识评估质量',
  '审核冲突消解与一致性', '证据校验与防幻觉 grounding', '产物验收闸门质量把关',
  '输出最终个性化路径',
]
const flowNodeLabels = [
  '协调', '诊断', '规划', '检索', '生成', '评估', '审核', '证据校验', '产物验收', '路径规划',
]

async function animateFlow(durationMs = 2800) {
  flowActive.value = true
  flowCurrentNode.value = -1
  flowCompleted.value = []
  const totalNodes = 10
  const stepDelay = durationMs / totalNodes
  for (let i = 0; i < totalNodes; i++) {
    if (!flowActive.value) break
    flowCurrentNode.value = i
    await new Promise(r => setTimeout(r, stepDelay * 0.5))
    flowCompleted.value = [...flowCompleted.value, i]
    if (i < totalNodes - 1) {
      await new Promise(r => setTimeout(r, stepDelay * 0.5))
    }
  }
  await new Promise(r => setTimeout(r, 200))
}

const trajectoryTypeIcon: Record<string, string> = {
  search_query: icons.search,
  observation: icons.eye,
  observation_rewrite: icons.refresh,
  stop_decision: icons.xCircle,
  query_rewrite: icons.pen,
  thought: icons.thought,
  finish: icons.check,
  kg_expansion: icons.link,
  cross_subject_search: icons.compass,
}

async function runSearch() {
  if (!question.value.trim() || loading.value) return
  loading.value = true
  result.value = null
  startTime.value = Date.now()
  elapsedMs.value = 0

  animateFlow(3000)

  try {
    result.value = await api.post<any>('/engine/frugal-rag-full', {
      question: question.value,
      course: course.value,
      top_k: 5,
      student_profile: profileInputRef.value?.buildProfile?.() || {},
    })
    elapsedMs.value = Date.now() - startTime.value
  } catch (e) {
    result.value = { status: 'error', message: String(e) }
    elapsedMs.value = Date.now() - startTime.value
  } finally {
    loading.value = false
    flowActive.value = false
  }
}
</script>

<template>
  <div class="engine-section glass-card">
    <div class="engine-section-title">
      <span class="engine-icon" v-html="icons.bookOpen"></span>
      FrugalRAG 节俭检索引擎
      <span class="engine-tag">LLM查询优化 + 启发式停止 + 个性化排序</span>
    </div>
    <div class="engine-desc">
      查询预处理 → SFT检索策略 → KG跨科目扩展 → E5向量检索 → 个性化重排 → RL停止决策 → 查询重写 → 融合排序
    </div>

    <div class="engine-input-row">
      <select v-model="course" class="engine-select">
        <option v-for="c in courseOptions" :key="c.value" :value="c.value">{{ c.label }}</option>
      </select>
      <input v-model="question" class="engine-input" placeholder="输入问题，如：TCP三次握手的过程是什么？"
        @keyup.enter="runSearch" />
      <button class="engine-btn glow-primary" @click="runSearch" :disabled="loading">
        {{ loading ? '检索中...' : '检索' }}
      </button>
    </div>

    <!-- 画像参数 -->
    <ProfileInputPanel ref="profileInputRef" />

    <!-- LangGraph 10 节点流式进度可视化 -->
    <LangGraphFlow
      v-if="loading || result?.status === 'ok'"
      :current-node="flowCurrentNode"
      :completed-nodes="flowCompleted"
      :step-details="flowStepDetails"
      :node-labels="flowNodeLabels"
      :loading="loading"
    />

    <!-- 检索结果 -->
    <div v-if="result?.status === 'ok'" class="engine-result">
      <div class="engine-result-meta">
        <span class="meta-pill accent">耗时: {{ elapsedMs }}ms</span>
        <span class="meta-pill">复杂度: {{ result.complexity }}</span>
        <span class="meta-pill">检索次数: {{ result.total_searches }}</span>
        <span class="meta-pill">查询重写: {{ result.rewrites }}</span>
        <span class="meta-pill">覆盖率: {{ ((result.coverage ?? 0) * 100).toFixed(0) }}%</span>
        <span class="meta-pill">检索片段: {{ result.chunks_count }}</span>
      </div>

      <div v-if="result.personalized_rerank?.applied" class="rerank-stats glass-card">
        <div class="rerank-header">
          <span class="rerank-icon" v-html="icons.target"></span>
          个性化检索排序
          <span class="rerank-badge">{{ result.personalized_rerank.affected_chunks }} 片段受画像影响</span>
        </div>
        <div v-if="result.personalized_rerank.profile_summary" class="rerank-profile-summary">
          <span class="rerank-ps-item weak">薄弱: {{ result.personalized_rerank.profile_summary.weak_topics?.join(', ') }}</span>
          <span class="rerank-ps-item mastered">已掌握: {{ result.personalized_rerank.profile_summary.mastered_topics?.join(', ') }}</span>
          <span class="rerank-ps-item">阶段: {{ result.personalized_rerank.profile_summary.review_stage }}</span>
          <span class="rerank-ps-item">目标: {{ result.personalized_rerank.profile_summary.target_score }}分</span>
        </div>
        <div v-if="result.personalized_rerank.adjustments?.length" class="rerank-adjustments">
          <div v-for="adj in result.personalized_rerank.adjustments.slice(0, 3)" :key="adj.chunk_id" class="rerank-adjust-item">
            <span class="adj-score">{{ Number(adj.adjustment) > 0 ? '+' : '' }}{{ Number(adj.adjustment).toFixed(3) }}</span>
            <span class="adj-reasons">{{ adj.reasons.join(', ') }}</span>
          </div>
        </div>
      </div>

      <div class="trajectory-timeline">
        <div v-for="(step, i) in result.trajectory" :key="i"
          class="trajectory-step" :class="'step-' + step.type">
          <span class="trajectory-icon" v-html="trajectoryTypeIcon[step.type] || '·'"></span>
          <div class="trajectory-content">
            <span class="trajectory-type">{{ step.type }}</span>
            <span v-if="step.query" class="trajectory-query">查询: "{{ step.query }}"</span>
            <span v-if="step.new_chunks !== undefined" class="trajectory-info">新增 {{ step.new_chunks }} 片段</span>
            <span v-if="step.chunks_found !== undefined" class="trajectory-info">找到 {{ step.chunks_found }} 片段</span>
            <span v-if="step.should_stop !== undefined" class="trajectory-info">
              <template v-if="step.should_stop"><span class="traj-mini" v-html="icons.check"></span> 停止</template><template v-else><span class="traj-mini" v-html="icons.play"></span> 继续</template> — {{ step.reason }}
            </span>
            <span v-if="step.thought" class="trajectory-thought">{{ step.thought }}</span>
            <span v-if="step.answer_length" class="trajectory-info">
              生成答案 {{ step.answer_length }} 字，覆盖率 {{ ((step.final_coverage ?? 0) * 100).toFixed(0) }}%
            </span>
          </div>
        </div>
      </div>

      <div class="engine-answer glass-card">
        <div class="engine-answer-title">最终答案</div>
        <div class="markdown-body" v-html="renderMarkdownSafe(result.answer || '')"></div>
      </div>
    </div>

    <div v-else-if="result?.status === 'error'" class="engine-error">
      {{ result.message }}
    </div>
  </div>
</template>

<style scoped>
.engine-section {
  margin-bottom:2rem;
  padding:1.5rem;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius:var(--radius-lg);
  backdrop-filter: blur(12px);
}

.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-color);
  border-radius:var(--radius-md);
}

.engine-section-title {
  display: flex;
  align-items: center;
  gap:0.5rem;
  font-size:1.125rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom:0.25rem;
}

.engine-icon { font-size:1.375rem; display:inline-flex; align-items:center; color:var(--accent-primary); }
.engine-icon svg { width:1.375rem; height:1.375rem; }

.engine-tag {
  margin-left:auto;
  font-size:0.6875rem;
  padding:0.1875rem 0.75rem;
  border-radius:var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-weight: 500;
}

.engine-desc {
  font-size:0.8125rem;
  color: var(--text-secondary);
  margin-bottom:1rem;
}

.engine-input-row {
  display: flex;
  gap:0.5rem;
  margin-bottom:1rem;
}

.engine-select {
  padding:0.625rem 0.875rem;
  border-radius:var(--radius-sm);
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size:0.875rem;
  outline: none;
}

.engine-input {
  flex: 1;
  padding:0.625rem 1rem;
  border-radius:var(--radius-sm);
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size:0.875rem;
  outline: none;
  transition: var(--transition);
}

.engine-input:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px var(--accent-primary-10);
}

.engine-btn {
  padding:0.625rem 1.5rem;
  border-radius:var(--radius-full);
  border: none;
  background: var(--gradient-primary);
  color: #fff;
  font-size:0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition-bounce);
  white-space: nowrap;
}

.engine-btn:hover {
  transform: translateY(-1px) scale(1.02);
  box-shadow: var(--glow-primary);
}

.engine-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.glow-primary { box-shadow: var(--glow-primary); }

.profile-toggle-row {
  display: flex;
  align-items: center;
  gap:0.5rem;
  margin-bottom:0.5rem;
}

.profile-toggle-btn {
  font-size:0.75rem;
  color: var(--accent-primary);
  cursor: pointer;
  background: none;
  border: none;
  padding:0.25rem 0;
}

.profile-badge {
  font-size:0.6875rem;
  padding:0.125rem 0.625rem;
  border-radius:var(--radius-full);
  background: var(--bg-tertiary);
  color: var(--text-muted);
}

.profile-badge.active {
  background: var(--accent-primary-10);
  color: var(--accent-primary);
}

.profile-input-panel {
  padding:1rem;
  margin-bottom:1rem;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap:0.75rem;
}

.profile-field { display: flex; flex-direction: column; gap:0.25rem; }
.profile-label { font-size:0.75rem; color: var(--text-secondary); font-weight: 600; }

.engine-result { margin-top:1rem; }

.engine-result-meta {
  display: flex;
  flex-wrap: wrap;
  gap:0.5rem;
  margin-bottom:1rem;
}

.meta-pill {
  font-size:0.75rem;
  padding:0.25rem 0.75rem;
  border-radius:var(--radius-full);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-weight: 500;
}

.meta-pill.accent {
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-weight: 600;
}

.rerank-stats {
  padding:1rem;
  margin-bottom:1rem;
}

.rerank-header {
  display: flex;
  align-items: center;
  gap:0.5rem;
  margin-bottom:0.5rem;
}

.rerank-icon { font-size:1rem; display:inline-flex; align-items:center; color:var(--accent-primary); }
.rerank-icon svg { width:1rem; height:1rem; }

.rerank-badge {
  margin-left:auto;
  font-size:0.6875rem;
  padding:0.125rem 0.625rem;
  border-radius:var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-weight: 500;
}

.rerank-profile-summary {
  display: flex;
  flex-wrap: wrap;
  gap:0.5rem;
  margin-bottom:0.5rem;
}

.rerank-ps-item {
  font-size:0.6875rem;
  padding:0.125rem 0.5rem;
  border-radius:var(--radius-xs);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.rerank-ps-item.weak { color: var(--accent-danger); background: var(--accent-danger-10); }
.rerank-ps-item.mastered { color: var(--accent-success); background: var(--accent-success-10); }

.rerank-adjustments { display: flex; flex-direction: column; gap:0.25rem; }

.rerank-adjust-item {
  display: flex;
  align-items: center;
  gap:0.5rem;
  font-size:0.75rem;
  padding:0.25rem 0.5rem;
  background: var(--bg-tertiary);
  border-radius:var(--radius-xs);
}

.adj-score { font-weight: 700; color: var(--accent-primary); min-width:3.125rem; }
.adj-reasons { color: var(--text-secondary); }

.trajectory-timeline {
  display: flex;
  flex-direction: column;
  gap:0.25rem;
  padding:1rem;
  background: var(--bg-secondary);
  border-radius:var(--radius-md);
  margin-bottom:1rem;
}

.trajectory-step {
  display: flex;
  align-items: flex-start;
  gap:0.625rem;
  padding:0.375rem 0;
  border-bottom: 1px solid var(--border-light);
}

.trajectory-step:last-child { border-bottom: none; }

.trajectory-step.step-kg_expansion,
.trajectory-step.step-cross_subject_search {
  background: color-mix(in srgb, var(--subject-ds) 6%, transparent);
  border-radius:var(--radius-xs);
  padding:0.375rem 0.5rem;
}

.trajectory-icon { font-size:1rem; flex-shrink: 0; margin-top:0.125rem; display:inline-flex; align-items:center; }
.trajectory-icon svg { width:1rem; height:1rem; }
.traj-mini { display:inline-flex; vertical-align:middle; margin-right:0.25rem; }
.traj-mini svg { width:0.875rem; height:0.875rem; }
.trajectory-content { display: flex; flex-direction: column; gap:0.125rem; font-size:0.8125rem; }

.trajectory-type {
  font-weight: 600;
  color: var(--accent-primary);
  font-size:0.6875rem;
  text-transform: uppercase;
}

.trajectory-query {
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size:0.75rem;
}

.trajectory-info { color: var(--text-secondary); font-size:0.75rem; }
.trajectory-thought { color: var(--text-muted); font-size:0.75rem; font-style: italic; }

.engine-answer {
  padding:1.25rem;
  background: var(--bg-secondary);
  border-radius:var(--radius-md);
  border: 1px solid var(--border-color);
}

.engine-answer-title {
  font-size:0.875rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom:0.75rem;
}

.engine-error {
  padding:0.75rem 1rem;
  background: var(--accent-danger-10);
  border-radius:var(--radius-sm);
  color: var(--accent-danger);
  font-size:0.8125rem;
}

@media (max-width: 768px) {
  .profile-input-panel { grid-template-columns: 1fr; }
}
</style>
