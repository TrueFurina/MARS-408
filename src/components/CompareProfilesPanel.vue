<script setup lang="ts">
import { ref, computed } from 'vue'
import { getAuthHeaders } from '@/utils/api'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'

const API_BASE = ''

const loading = ref(false)
const ran = ref(false)
const resultA = ref<any>(null)
const resultB = ref<any>(null)
const question = ref('TCP三次握手的过程是什么？')
const course = ref('computer_network')

const courseOptions = [
  { value: 'computer_network', label: '计算机网络' },
  { value: 'data_structures', label: '数据结构' },
  { value: 'operating_system', label: '操作系统' },
  { value: 'computer_organization', label: '计算机组成原理' },
]

const profileA = computed(() => ({
  weak_topics: ['TCP', '运输层', '拥塞控制'],
  mastered_topics: ['以太网', '数据链路层'],
  review_stage: 'strengthen',
  target_score: 110,
}))

const profileB = computed(() => ({
  weak_topics: ['DNS', '网络安全'],
  mastered_topics: ['TCP', '运输层', 'IP协议'],
  review_stage: 'mock',
  target_score: 130,
}))

async function runCompare() {
  if (loading.value) return
  loading.value = true
  ran.value = true
  resultA.value = null
  resultB.value = null
  try {
    const [respA, respB] = await Promise.all([
      fetch(`${API_BASE}/api/engine/frugal-rag-full`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.value, course: course.value, top_k: 5, student_profile: profileA.value }),
      }),
      fetch(`${API_BASE}/api/engine/frugal-rag-full`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.value, course: course.value, top_k: 5, student_profile: profileB.value }),
      }),
    ])
    resultA.value = await respA.json()
    resultB.value = await respB.json()
  } catch (e) {
    resultA.value = { status: 'error', message: String(e) }
    resultB.value = { status: 'error', message: String(e) }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="engine-section glass-card">
    <div class="engine-section-title">
      <span class="engine-icon">🎯</span>
      个性化对比演示
      <span class="engine-tag">不同画像 → 不同检索结果</span>
    </div>
    <div class="engine-desc">
      同一问题，两个不同画像的学生得到不同的检索排序结果，直观展示个性化排序的效果
    </div>

    <div class="engine-input-row">
      <select v-model="course" class="engine-select">
        <option v-for="c in courseOptions" :key="c.value" :value="c.value">{{ c.label }}</option>
      </select>
      <input v-model="question" class="engine-input" placeholder="输入对比问题" />
      <button class="engine-btn glow-secondary" @click="runCompare" :disabled="loading">
        {{ loading ? '对比中...' : '开始对比' }}
      </button>
    </div>

    <div class="compare-profiles-display">
      <div class="compare-profile-card glass-card profile-a">
        <div class="compare-profile-header">画像A — 薄弱TCP的强化阶段学生</div>
        <div class="compare-profile-details">
          <div>薄弱: {{ profileA.weak_topics.join(', ') }}</div>
          <div>已掌握: {{ profileA.mastered_topics.join(', ') }}</div>
          <div>阶段: 强化 | 目标: {{ profileA.target_score }}分</div>
        </div>
      </div>
      <div class="compare-profile-card glass-card profile-b">
        <div class="compare-profile-header">画像B — 已掌握TCP的模考阶段高分学生</div>
        <div class="compare-profile-details">
          <div>薄弱: {{ profileB.weak_topics.join(', ') }}</div>
          <div>已掌握: {{ profileB.mastered_topics.join(', ') }}</div>
          <div>阶段: 模考 | 目标: {{ profileB.target_score }}分</div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="compare-results">
      <Skeleton variant="block" height="6rem" radius="var(--radius-md)" />
      <Skeleton variant="block" height="6rem" radius="var(--radius-md)" />
    </div>
    <EmptyState
      v-else-if="!ran"
      title="尚未运行对比"
      description="点击「开始对比」，查看同一问题在不同学生画像下的个性化检索排序结果"
    />
    <div v-else class="compare-results">
      <div class="compare-column">
        <div class="compare-col-header">画像A 结果</div>
        <div v-if="resultA?.status === 'ok'" class="compare-col-content">
          <div class="compare-stats">
            <span class="meta-pill accent">覆盖率: {{ (resultA.coverage * 100).toFixed(0) }}%</span>
            <span class="meta-pill">检索: {{ resultA.total_searches }}次</span>
          </div>
          <div v-if="resultA.personalized_rerank?.applied" class="compare-rerank-mini">
            <span class="rerank-mini-badge">{{ resultA.personalized_rerank.affected_chunks }} 片段调整</span>
            <div v-for="adj in resultA.personalized_rerank.adjustments?.slice(0,3)" :key="adj.chunk_id" class="compare-adjust">
              {{ Number(adj.adjustment) > 0 ? '↑' : '↓' }} {{ adj.reasons.join(', ') }}
            </div>
          </div>
        </div>
        <div v-else class="compare-col-error">请求失败</div>
      </div>
      <div class="compare-column">
        <div class="compare-col-header">画像B 结果</div>
        <div v-if="resultB?.status === 'ok'" class="compare-col-content">
          <div class="compare-stats">
            <span class="meta-pill accent">覆盖率: {{ (resultB.coverage * 100).toFixed(0) }}%</span>
            <span class="meta-pill">检索: {{ resultB.total_searches }}次</span>
          </div>
          <div v-if="resultB.personalized_rerank?.applied" class="compare-rerank-mini">
            <span class="rerank-mini-badge">{{ resultB.personalized_rerank.affected_chunks }} 片段调整</span>
            <div v-for="adj in resultB.personalized_rerank.adjustments?.slice(0,3)" :key="adj.chunk_id" class="compare-adjust">
              {{ Number(adj.adjustment) > 0 ? '↑' : '↓' }} {{ adj.reasons.join(', ') }}
            </div>
          </div>
        </div>
        <div v-else class="compare-col-error">请求失败</div>
      </div>
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
  backdrop-filter: blur(var(--glass-blur));
}

.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
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

.engine-icon { font-size:1.375rem; }

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

.glow-secondary { box-shadow: var(--glow-secondary); }

.compare-profiles-display {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap:1rem;
  margin-bottom:1rem;
}

.compare-profile-card { padding:1rem; }
.profile-a .compare-profile-header { color: var(--accent-primary); }
.profile-b .compare-profile-header { color: var(--accent-warm); }
.compare-profile-header { font-size:0.875rem; font-weight: 700; margin-bottom:0.5rem; }
.compare-profile-details { font-size:0.75rem; color: var(--text-secondary); }

.compare-results {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap:1rem;
}

.compare-column { padding:1rem; background: var(--bg-secondary); border-radius:var(--radius-md); }
.compare-col-header { font-size:0.875rem; font-weight: 700; color: var(--accent-primary); margin-bottom:0.5rem; }
.compare-col-content { font-size:0.8125rem; color: var(--text-secondary); }
.compare-col-error { font-size:0.8125rem; color: var(--accent-danger); }
.compare-stats { display: flex; gap:0.5rem; margin-bottom:0.5rem; }

.compare-rerank-mini { margin-top:0.5rem; }
.rerank-mini-badge {
  font-size:0.6875rem;
  padding:0.125rem 0.5rem;
  border-radius:var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-weight: 500;
  display: inline-block;
  margin-bottom:0.25rem;
}

.compare-adjust {
  font-size:0.6875rem;
  padding:0.125rem 0.375rem;
  color: var(--text-secondary);
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

@media (max-width: 768px) {
  .compare-profiles-display { grid-template-columns: 1fr; }
  .compare-results { grid-template-columns: 1fr; }
}
</style>
