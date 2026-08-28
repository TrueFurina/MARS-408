<script setup lang="ts">
import { ref, computed } from 'vue'
import LangGraphFlow from '@/components/LangGraphFlow.vue'
import { icons } from '@/components/icons'
import { useStudyStore } from '@/stores/studyStore'
import { api } from '@/utils/api'

const store = useStudyStore()

// ── 共识状态 ──
const topic = ref('TCP三次握手')
const loading = ref(false)
const result = ref<any>(null)

// ── LangGraph 流状态 ──
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

async function animateFlow(durationMs = 2400) {
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

// ── Agent 样本数据 ──
const sampleAgentResults = computed(() => [
  {
    agent_name: 'teacher',
    content: `TCP建立连接使用三次握手：1) 客户端发送SYN 2) 服务端回复SYN+ACK 3) 客户端发送ACK。三次握手确保双方都准备好通信。`,
    score: 8.5,
  },
  {
    agent_name: 'quizmaster',
    content: `题目：TCP三次握手中，第二步发送的报文标志位是什么？答案：SYN=1, ACK=1。因为服务端既要表示同意建立连接(SYN)，又要确认收到客户端的SYN(ACK)。`,
    score: 8.0,
  },
  {
    agent_name: 'media_designer',
    content: `可视化方案：用动画展示三次握手过程，客户端→SYN→服务端，服务端→SYN+ACK→客户端，客户端→ACK→服务端。每一步用不同颜色箭头标注。`,
    score: 7.5,
  },
])

async function runConsensus() {
  if (loading.value) return
  loading.value = true
  result.value = null

  animateFlow(2400)

  try {
    result.value = await api.post<any>('/engine/gomarl-consensus', {
      agent_results: sampleAgentResults.value,
      student_profile: store.studentProfile || {},
      topic: topic.value,
      course: 'computer_network',
    })
  } catch (e) {
    result.value = { status: 'error', message: String(e) }
  } finally {
    loading.value = false
    flowActive.value = false
  }
}
</script>

<template>
  <div class="engine-section glass-card">
    <div class="engine-section-title">
      <span class="engine-icon" v-html="icons.robot"></span>
      GoMARL 多智能体共识引擎
      <span class="engine-tag">NeuralMixer + 冲突消解 + 动态权重</span>
    </div>
    <div class="engine-desc">
      E5编码 → 知识一致性校验 → 证据冲突消解 → 动态权重(画像+教学规则) → NeuralMixer共识 → 历史记录
    </div>

    <div class="engine-input-row">
      <input v-model="topic" class="engine-input" placeholder="学习主题" />
      <button class="engine-btn glow-primary" @click="runConsensus" :disabled="loading">
        {{ loading ? '评估中...' : '共识评估' }}
      </button>
    </div>

    <!-- LangGraph 流式进度可视化 -->
    <LangGraphFlow
      v-if="loading || result?.status === 'ok'"
      :current-node="flowCurrentNode"
      :completed-nodes="flowCompleted"
      :step-details="flowStepDetails"
      :node-labels="flowNodeLabels"
      :loading="loading"
    />

    <div class="gomarl-agents-preview">
      <div v-for="agent in sampleAgentResults" :key="agent.agent_name" class="gomarl-agent-preview-card glass-card">
        <div class="gomarl-agent-name">{{ agent.agent_name }}</div>
        <div class="gomarl-agent-score">评分: {{ agent.score }}</div>
        <div class="gomarl-agent-content">{{ agent.content.substring(0, 80) }}...</div>
      </div>
    </div>

    <!-- 共识结果 -->
    <div v-if="result?.status === 'ok'" class="engine-result">
      <div class="gomarl-consensus-score glass-card">
        <span class="score-label">共识质量分数</span>
        <span class="score-value gradient-text">{{ (result?.consensus_score ?? 0).toFixed(2) }}</span>
        <span class="score-neural" v-if="result.neural_used"><span class="mini-icon" v-html="icons.brain"></span> 神经网络混合</span>
        <span class="score-neural" v-else><span class="mini-icon" v-html="icons.barChart"></span> 加权平均</span>
      </div>

      <!-- 动态权重 -->
      <div v-if="result.dynamic_weights" class="gomarl-weights">
        <div class="gomarl-weights-title">动态权重（EWMA + 学生画像 + 教学规则）</div>
        <div class="gomarl-weights-grid">
          <div v-for="(weight, name) in result.dynamic_weights" :key="name" class="gomarl-weight-item">
            <span class="weight-name">{{ name }}</span>
            <div class="weight-bar">
              <div class="weight-fill gradient-bar" :style="{ width: Math.min(weight * 50, 100) + '%' }"></div>
            </div>
            <span class="weight-value">{{ (weight ?? 0).toFixed(2) }}</span>
          </div>
        </div>
      </div>

      <!-- 冲突检测 -->
      <div v-if="result.conflicts" class="gomarl-conflicts">
        <div class="gomarl-conflicts-title">
          冲突检测与消解
          <span class="consistency-badge" :class="{ high: result.conflicts.overall_consistency > 0.8 }">
            一致性: {{ ((result.conflicts?.overall_consistency ?? 0) * 100).toFixed(0) }}%
          </span>
        </div>
        <div class="gomarl-conflict-stats">
          <span class="conflict-stat">总冲突: {{ result.conflicts.total }}</span>
          <span class="conflict-stat resolved">已消解: {{ result.conflicts.resolved }}</span>
          <span class="conflict-stat unresolved">未消解: {{ result.conflicts.unresolved }}</span>
        </div>
        <div v-for="(c, i) in result.conflicts.details" :key="i" class="gomarl-conflict-detail">
          <span class="conflict-type">{{ c.type }}</span>
          <span class="conflict-desc">{{ c.agent_a }} vs {{ c.agent_b }}: {{ c.description }}</span>
          <span class="conflict-resolution">→ {{ c.resolution }} ({{ ((c.confidence ?? 0) * 100).toFixed(0) }}%)</span>
        </div>
      </div>

      <!-- 分组信息 -->
      <div v-if="result.groups?.length" class="gomarl-groups">
        <div class="gomarl-groups-title">动态分组（GoMARL GroupMixer）</div>
        <div class="gomarl-groups-list">
          <span v-for="(group, i) in result.groups" :key="i" class="gomarl-group-tag">
            组{{ Number(i) + 1 }}: {{ Array.isArray(group) ? group.join(', ') : group }}
          </span>
        </div>
        <div v-if="result.sd_loss > 0" class="gomarl-sd-loss">
          相似度-多样性损失: {{ result.sd_loss.toFixed(4) }}
        </div>
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
.mini-icon { display:inline-flex; vertical-align:middle; margin-right:0.25rem; }
.mini-icon svg { width:0.875rem; height:0.875rem; }

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

.gradient-text {
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.gradient-bar {
  background: linear-gradient(90deg, var(--nm-mix-from), var(--nm-mix-to));
  border-radius:var(--radius-full);
  transition: width 0.3s ease;
}

.engine-result { margin-top:1rem; }

.engine-error {
  padding:0.75rem 1rem;
  background: var(--accent-danger-10);
  border-radius:var(--radius-sm);
  color: var(--accent-danger);
  font-size:0.8125rem;
}

.gomarl-agents-preview {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap:0.75rem;
  margin-bottom:1rem;
}

.gomarl-agent-preview-card { padding:0.75rem; }
.gomarl-agent-name { font-size:0.8125rem; font-weight: 700; color: var(--accent-primary); margin-bottom:0.25rem; }
.gomarl-agent-score { font-size:0.6875rem; color: var(--text-muted); margin-bottom:0.25rem; }
.gomarl-agent-content { font-size:0.6875rem; color: var(--text-secondary); line-height:1.4; }

.gomarl-consensus-score {
  display: flex;
  align-items: center;
  gap:0.75rem;
  padding:1.25rem;
  margin-bottom:1rem;
}

.score-label { font-size:0.875rem; color: var(--text-secondary); }

.score-value {
  font-size:2.25rem;
  font-weight: 800;
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.score-neural {
  margin-left:auto;
  font-size:0.75rem;
  padding:0.25rem 0.75rem;
  border-radius:var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
}

.gomarl-weights { margin-bottom:1rem; }
.gomarl-weights-title { font-size:0.8125rem; font-weight: 700; color: var(--text-primary); margin-bottom:0.5rem; }
.gomarl-weights-grid { display: flex; flex-direction: column; gap:0.375rem; }
.gomarl-weight-item { display: flex; align-items: center; gap:0.5rem; }
.weight-name { font-size:0.75rem; color: var(--text-secondary); min-width:6.25rem; }
.weight-bar { flex: 1; height:0.375rem; background: var(--bg-tertiary); border-radius:var(--radius-full); overflow: hidden; }
.weight-value { font-size:0.75rem; color: var(--text-primary); font-weight: 600; min-width:2.5rem; text-align: right; }

.gomarl-conflicts { margin-bottom:1rem; }
.gomarl-conflicts-title { display: flex; align-items: center; gap:0.5rem; font-size:0.8125rem; font-weight: 700; color: var(--text-primary); margin-bottom:0.5rem; }

.consistency-badge {
  font-size:0.6875rem;
  padding:0.125rem 0.625rem;
  border-radius:var(--radius-full);
  background: color-mix(in srgb, var(--conflict-detected) 20%, transparent);
  color: var(--conflict-detected);
}

.consistency-badge.high { background: color-mix(in srgb, var(--conflict-resolved) 20%, transparent); color: var(--conflict-resolved); }

.gomarl-conflict-stats { display: flex; gap:0.75rem; margin-bottom:0.5rem; }
.conflict-stat { font-size:0.75rem; color: var(--text-secondary); }
.conflict-stat.resolved { color: var(--conflict-resolved); }
.conflict-stat.unresolved { color: var(--conflict-detected); }

.gomarl-conflict-detail {
  display: flex;
  align-items: center;
  gap:0.5rem;
  padding:0.375rem 0.625rem;
  background: var(--bg-tertiary);
  border-radius:var(--radius-sm);
  margin-bottom:0.25rem;
  font-size:0.75rem;
}

.conflict-type { font-size:0.625rem; padding:0.125rem 0.375rem; border-radius:var(--radius-xs); background: var(--accent-primary-10); color: var(--accent-primary); font-weight: 600; }
.conflict-desc { color: var(--text-secondary); flex: 1; }
.conflict-resolution { color: var(--conflict-resolved); font-weight: 500; }

.gomarl-groups { margin-bottom:1rem; }
.gomarl-groups-title { font-size:0.8125rem; font-weight: 700; color: var(--text-primary); margin-bottom:0.5rem; }
.gomarl-groups-list { display: flex; flex-wrap: wrap; gap:0.375rem; }
.gomarl-group-tag { font-size:0.6875rem; padding:0.1875rem 0.625rem; border-radius:var(--radius-full); background: var(--bg-tertiary); color: var(--text-secondary); }
.gomarl-sd-loss { font-size:0.6875rem; color: var(--text-muted); margin-top:0.25rem; }

@keyframes pulse-glow {
  0%, 100% { opacity: 1; box-shadow: 0 0 4px var(--accent-primary); }
  50% { opacity: 0.6; box-shadow: 0 0 8px var(--accent-primary); }
}

@media (max-width: 768px) {
  .gomarl-agents-preview { grid-template-columns: 1fr; }
}
</style>
