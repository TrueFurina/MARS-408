<script setup lang="ts">
import { ref, watch } from 'vue'

const weakTopics = defineModel<string>('weakTopics', { default: 'TCP, 运输层' })
const masteredTopics = defineModel<string>('masteredTopics', { default: '以太网, 数据链路层' })
const reviewStage = defineModel<string>('reviewStage', { default: 'strengthen' })
const targetScore = defineModel<number>('targetScore', { default: 120 })
const show = defineModel<boolean>('show', { default: false })

const reviewStageOptions = [
  { value: 'basic', label: '基础阶段' },
  { value: 'strengthen', label: '强化阶段' },
  { value: 'comprehensive', label: '综合阶段' },
  { value: 'mock', label: '模考阶段' },
]

function buildProfile() {
  return {
    weak_topics: weakTopics.value.split(',').map(s => s.trim()).filter(Boolean),
    mastered_topics: masteredTopics.value.split(',').map(s => s.trim()).filter(Boolean),
    review_stage: reviewStage.value,
    target_score: Number(targetScore.value) || 100,
  }
}

defineExpose({ buildProfile })
</script>

<template>
  <div class="profile-toggle-row">
    <button class="profile-toggle-btn" @click="show = !show">
      {{ show ? '▼ 收起画像参数' : '▶ 展开画像参数（个性化排序）' }}
    </button>
    <span v-if="show" class="profile-badge active">个性化排序已启用</span>
    <span v-else class="profile-badge">默认排序（无画像）</span>
  </div>

  <div v-if="show" class="profile-input-panel glass-card">
    <div class="profile-field">
      <label class="profile-label">薄弱知识点 (加分↑)</label>
      <input v-model="weakTopics" class="engine-input" placeholder="TCP, 运输层" />
    </div>
    <div class="profile-field">
      <label class="profile-label">已掌握知识点 (减分↓)</label>
      <input v-model="masteredTopics" class="engine-input" placeholder="以太网, 数据链路层" />
    </div>
    <div class="profile-field">
      <label class="profile-label">复习阶段</label>
      <select v-model="reviewStage" class="engine-select">
        <option v-for="s in reviewStageOptions" :key="s.value" :value="s.value">{{ s.label }}</option>
      </select>
    </div>
    <div class="profile-field">
      <label class="profile-label">目标分数</label>
      <input v-model="targetScore" class="engine-input" type="number" placeholder="120" />
    </div>
  </div>
</template>

<style scoped>
.profile-toggle-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
.profile-toggle-btn { font-size: 0.75rem; color: var(--accent-primary); cursor: pointer; background: none; border: none; padding: 0.25rem 0; }
.profile-badge { font-size: 0.6875rem; padding: 0.1875rem 0.625rem; border-radius: var(--radius-full); background: var(--bg-tertiary); color: var(--text-muted); }
.profile-badge.active { background: var(--accent-primary-10); color: var(--accent-primary); }
.profile-input-panel { padding: 1rem; margin-bottom: 1rem; background: var(--bg-card); border: 1px solid var(--border-color); border-radius: var(--radius-md); display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
.profile-field { display: flex; flex-direction: column; gap: 0.25rem; }
.profile-label { font-size: 0.75rem; color: var(--text-muted); font-weight: 500; }
.engine-select { padding: 0.5rem 0.75rem; border-radius: var(--radius-sm); background: var(--bg-input); border: 1px solid var(--border-color); color: var(--text-primary); font-size: 0.8125rem; outline: none; }
.engine-input { padding: 0.5rem 0.75rem; border-radius: var(--radius-sm); background: var(--bg-input); border: 1px solid var(--border-color); color: var(--text-primary); font-size: 0.8125rem; outline: none; transition: var(--transition); }
.engine-input:focus { border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--accent-primary-10); }
.glass-card { background: var(--glass-bg); backdrop-filter: blur(12px); border: 1px solid var(--border-color); border-radius: var(--radius-md); }
</style>