<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/utils/api'
import { getAuthHeaders } from '@/utils/api'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'

const API_BASE = ''

const teachingRulesData = ref<any>(null)
const selectedTopicId = ref('transport')
const topicPrerequisites = ref<any>(null)

async function loadTeachingRules() {
  try {
    const resp = await fetch(`${API_BASE}/api/engine/teaching-rules`, { headers: getAuthHeaders() })
    teachingRulesData.value = await resp.json()
  } catch { /* ignore */ }
}
onMounted(loadTeachingRules)

async function loadTopicPrerequisites() {
  if (!selectedTopicId.value) return
  try {
    const resp = await fetch(`${API_BASE}/api/engine/teaching-rules/prerequisites/${selectedTopicId.value}`, { headers: getAuthHeaders() })
    topicPrerequisites.value = await resp.json()
  } catch { /* ignore */ }
}
onMounted(loadTopicPrerequisites)

const topicOptions = [
  { value: 'transport', label: '运输层', weight: '0.20' },
  { value: 'tcp', label: 'TCP协议', weight: '0.18' },
  { value: 'memory_management', label: '内存管理', weight: '0.20' },
  { value: 'cpu', label: 'CPU寻址', weight: '0.20' },
  { value: 'sorting', label: '排序算法', weight: '0.20' },
  { value: 'process', label: '进程管理', weight: '0.20' },
  { value: 'virtual_memory', label: '虚拟内存' },
  { value: 'datalink', label: '数据链路层' },
  { value: 'network', label: '网络层' },
]
</script>

<template>
  <div class="engine-section glass-card">
    <div class="engine-section-title">
      <span class="engine-icon">📚</span>
      408教学规则引擎
      <span class="engine-tag">知识点依赖+考查权重</span>
    </div>
    <div class="engine-desc">
      86个知识点，4课程，跨科目依赖关系（如：CPU寻址→内存管理→虚拟内存），考查权重驱动复习优先级
    </div>

    <div v-if="teachingRulesData === null" class="teaching-rules-stats">
      <Skeleton v-for="n in 4" :key="n" variant="title" width="100%" height="2.25rem" radius="var(--radius-sm)" />
    </div>
    <EmptyState v-else-if="teachingRulesData?.status !== 'ok'" title="教学规则暂不可用"
      description="后端 /api/engine/teaching-rules 未返回数据，请确认服务已启动。" />
    <div v-else class="teaching-rules-stats">
      <div class="stat-row">
        <span class="stat-label">知识点总数</span>
        <span class="stat-value highlight">{{ teachingRulesData.stats.total_topics }}</span>
      </div>
      <div class="stat-row" v-for="(count, course) in teachingRulesData.stats.course_distribution" :key="course">
        <span class="stat-label">{{ course }}</span>
        <span class="stat-value">{{ count }} 知识点</span>
      </div>
    </div>

    <div class="topic-prereq-viewer">
      <div class="prereq-input-row">
        <select v-model="selectedTopicId" @change="loadTopicPrerequisites" class="engine-select">
          <option v-for="opt in topicOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}<template v-if="opt.weight"> (exam_weight={{ opt.weight }})</template>
          </option>
        </select>
      </div>

      <div v-if="topicPrerequisites?.status === 'ok'" class="topic-prereq-display">
        <div class="prereq-main">
          <span class="prereq-topic-name">{{ topicPrerequisites.topic_name }}</span>
          <span class="prereq-course">{{ topicPrerequisites.course }}</span>
          <span class="prereq-weight">考查权重: {{ (topicPrerequisites.exam_weight * 100).toFixed(0) }}%</span>
          <span class="prereq-diff">难度: {{ topicPrerequisites.difficulty }}</span>
        </div>
        <div v-if="topicPrerequisites.prerequisites?.length" class="prereq-list">
          <div class="prereq-label">前置依赖:</div>
          <span v-for="p in topicPrerequisites.prerequisites" :key="p" class="prereq-tag same-course">{{ p }}</span>
        </div>
        <div v-if="topicPrerequisites.cross_subject_prerequisites?.length" class="prereq-list cross">
          <div class="prereq-label">跨科目依赖:</div>
          <span v-for="p in topicPrerequisites.cross_subject_prerequisites" :key="p" class="prereq-tag cross-course">{{ p }}</span>
        </div>
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

.engine-select {
  padding:0.625rem 0.875rem;
  border-radius:var(--radius-sm);
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size:0.875rem;
  outline: none;
}

.teaching-rules-stats {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap:0.5rem;
  margin-bottom:1rem;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  padding:0.5rem 0.75rem;
  background: var(--bg-secondary);
  border-radius:var(--radius-sm);
}

.stat-label { font-size:0.75rem; color: var(--text-secondary); }
.stat-value { font-size:0.75rem; color: var(--text-primary); font-weight: 600; }
.stat-value.highlight { color: var(--accent-primary); }

.topic-prereq-viewer { margin-top:0.75rem; }
.prereq-input-row { margin-bottom:0.75rem; }

.topic-prereq-display {
  padding:1rem;
  background: var(--bg-secondary);
  border-radius:var(--radius-md);
  border: 1px solid var(--border-color);
}

.prereq-main {
  display: flex;
  align-items: center;
  gap:0.75rem;
  margin-bottom:0.75rem;
}

.prereq-topic-name { font-size:1rem; font-weight: 700; color: var(--accent-primary); }
.prereq-course { font-size:0.75rem; color: var(--text-muted); }

.prereq-weight {
  font-size:0.75rem;
  padding:0.125rem 0.625rem;
  border-radius:var(--radius-full);
  background: var(--accent-danger-20);
  color: var(--accent-danger);
  font-weight: 600;
}

.prereq-diff {
  font-size:0.75rem;
  padding:0.125rem 0.625rem;
  border-radius:var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
}

.prereq-list { margin-bottom:0.5rem; }
.prereq-label { font-size:0.75rem; color: var(--text-secondary); font-weight: 600; margin-bottom:0.25rem; }

.prereq-tag {
  font-size:0.6875rem;
  padding:0.125rem 0.5rem;
  border-radius:var(--radius-xs);
  margin-right:0.25rem;
  display: inline-block;
}

.prereq-tag.same-course { background: var(--accent-primary-10); color: var(--accent-primary); }
.prereq-tag.cross-course { background: color-mix(in srgb, var(--subject-ds) 15%, transparent); color: var(--subject-ds); }
</style>
