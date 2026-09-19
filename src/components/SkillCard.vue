<script setup lang="ts">
import type { SkillItem } from '@/stores/skillStore'
import { icons } from '@/components/icons'

const props = defineProps<{
  skill: SkillItem
  compact?: boolean
}>()

const emit = defineEmits<{
  click: [id: string]
}>()

function stars(count: number): string {
  const full = Math.round(count)
  return ''.repeat(full) + ''.repeat(5 - full)
}

function statusLabel(s: string): string {
  return { draft: '草稿', published: '已发布', archived: '已归档' }[s] || s
}

function statusClass(s: string): string {
  return { draft: 'badge-draft', published: 'badge-published', archived: 'badge-archived' }[s] || ''
}
</script>

<template>
  <div class="skill-card" :class="{ compact }" role="button" tabindex="0" :aria-label="'技能: ' + skill.name" @click="emit('click', skill.id)" @keydown.enter="emit('click', skill.id)" @keydown.space.prevent="emit('click', skill.id)">
    <div class="skill-card-header">
      <span class="skill-icon" role="img" :aria-label="skill.icon + ' 图标'">{{ skill.icon }}</span>
      <div class="skill-meta">
        <span class="skill-name">{{ skill.name }}</span>
        <span class="skill-creator">{{ skill.is_official ? '官方' : skill.creator_name }}</span>
      </div>
      <span v-if="!compact" class="skill-status" :class="statusClass(skill.status)" :aria-label="'状态: ' + statusLabel(skill.status)">{{ statusLabel(skill.status) }}</span>
    </div>

    <p v-if="!compact" class="skill-desc">{{ skill.description }}</p>

    <div class="skill-footer">
      <span class="skill-rating" v-html="icons.star" aria-hidden="true"></span>
      <span class="skill-rating-val" :aria-label="skill.avg_rating.toFixed(1) + ' 星'">{{ skill.avg_rating.toFixed(1) }}</span>
      <span class="skill-usage">· {{ skill.usage_count }} 次使用</span>
      <span v-if="skill.tags.length" class="skill-tags">
        <span v-for="tag in skill.tags.slice(0, 3)" :key="tag" class="skill-tag" :aria-label="'标签: ' + tag">{{ tag }}</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
.skill-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius:var(--radius-md);
  padding:var(--space-4);
  cursor: pointer;
  transition: var(--transition);
  display: flex;
  flex-direction: column;
  gap:var(--space-2);
}
.skill-card:hover {
  border-color: var(--color-border-focus);
  background: var(--color-surface-hover);
  transform: translateY(-2px);
}
.skill-card.compact { padding:var(--space-3); gap:var(--space-1); }

.skill-card-header {
  display: flex;
  align-items: center;
  gap:0.625rem;
}
.skill-icon { font-size:1.75rem; line-height:var(--leading-none); }
.skill-meta { flex: 1; min-width:0; }
.skill-name { display: block; font-size:var(--text-lg); font-weight: var(--weight-semibold); color: var(--color-text); }
.skill-creator { display: block; font-size:var(--text-xs); color: var(--color-text-3); }
.skill-status { font-size:var(--text-2xs); padding:0.125rem var(--space-2); border-radius:var(--radius-full); font-weight: var(--weight-medium); white-space: nowrap; }
.badge-draft { background: color-mix(in srgb, var(--accent-warm) 12%, transparent); color: var(--accent-warm); }
.badge-published { background: color-mix(in srgb, var(--accent-success) 12%, transparent); color: var(--accent-success); }
.badge-archived { background: color-mix(in srgb, var(--color-text-2) 12%, transparent); color: var(--color-text-2); }

.skill-desc { font-size:var(--text-sm); color: var(--color-text-2); line-height:1.5; margin:0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.skill-footer { display: flex; align-items: center; gap:var(--space-1); font-size:var(--text-xs); color: var(--color-text-3); flex-wrap: wrap; }
.skill-rating { width:0.875rem; height:0.875rem; color: var(--accent-warm); }
.skill-rating-val { font-weight: var(--weight-semibold); color: var(--accent-warm); }
.skill-usage { color: var(--color-text-3); }
.skill-tags { margin-left:auto; display: flex; gap:var(--space-1); }
.skill-tag { font-size:var(--text-2xs); padding:0.0625rem 0.375rem; border-radius:var(--radius-xs); background: var(--color-surface-2); color: var(--color-text-2); }
</style>