<script setup lang="ts">
import { ref, computed } from 'vue'
import { useAchievementStore } from '@/stores/achievementStore'

const achStore = useAchievementStore()

const CATEGORY_LABELS: Record<string, string> = {
  milestone: '里程碑',
  practice: '练习达人',
  knowledge: '知识探索',
  streak: '坚持学习',
  master: '成就大师',
}

const CATEGORY_ICONS: Record<string, string> = {
  milestone: '🏁',
  practice: '📝',
  knowledge: '📚',
  streak: '🔥',
  master: '👑',
}

const activeCategory = ref('all')

const filteredAchievements = computed(() => {
  if (activeCategory.value === 'all') return achStore.achievements
  return achStore.achievements.filter(a => a.category === activeCategory.value)
})

const sortedAchievements = computed(() => {
  return [...filteredAchievements.value].sort((a, b) => {
    if (a.unlocked && !b.unlocked) return -1
    if (!a.unlocked && b.unlocked) return 1
    if (a.unlocked && b.unlocked) {
      return new Date(b.unlockedAt || '').getTime() - new Date(a.unlockedAt || '').getTime()
    }
    return b.progress - a.progress
  })
})
</script>

<template>
  <div class="achievement-panel">
    <!-- 头部 -->
    <div class="ach-header">
      <div class="ach-header-left">
        <div class="ach-title">🏆 成就系统</div>
        <div class="ach-subtitle">解锁成就，记录你的学习旅程</div>
      </div>
      <div class="ach-overall">
        <div class="ach-overall-circle">
          <svg viewBox="0 0 36 36" class="ach-circular">
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none" stroke="var(--bg-tertiary)" stroke-width="3" />
            <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none" stroke="var(--accent-primary)" stroke-width="3"
              :stroke-dasharray="`${achStore.progressPercent}, 100`" stroke-linecap="round" />
          </svg>
          <div class="ach-overall-text">{{ achStore.progressPercent }}%</div>
        </div>
        <div class="ach-overall-count">{{ achStore.unlockedCount }}/{{ achStore.totalCount }}</div>
      </div>
    </div>

    <!-- 分类筛选 -->
    <div class="ach-filters">
      <button
        v-for="cat in ['all', 'milestone', 'practice', 'knowledge', 'streak', 'master']"
        :key="cat"
        class="ach-filter-btn"
        :class="{ active: activeCategory === cat }"
        @click="activeCategory = cat"
      >
        {{ cat === 'all' ? '全部' : CATEGORY_ICONS[cat] + ' ' + CATEGORY_LABELS[cat] }}
      </button>
    </div>

    <!-- 最近解锁 -->
    <div v-if="achStore.recentAchievements.length > 0" class="ach-recent">
      <div class="ach-recent-title">最近解锁</div>
      <div class="ach-recent-list">
        <div v-for="ach in achStore.recentAchievements" :key="ach.id" class="ach-recent-item" :style="{ borderColor: ach.color + '40' }">
          <span class="ach-recent-icon">{{ ach.icon }}</span>
          <div class="ach-recent-info">
            <div class="ach-recent-name">{{ ach.name }}</div>
            <div class="ach-recent-desc">{{ ach.description }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 成就网格 -->
    <div class="ach-grid">
      <div v-for="ach in sortedAchievements" :key="ach.id" class="ach-card"
        :class="{ unlocked: ach.unlocked, locked: !ach.unlocked }"
        :style="ach.unlocked ? { borderColor: ach.color + '40' } : {}">
        <!-- 图标 -->
        <div class="ach-card-icon" :style="ach.unlocked ? { background: ach.color + '20', color: ach.color } : {}">
          {{ ach.icon }}
        </div>
        <!-- 信息 -->
        <div class="ach-card-body">
          <div class="ach-card-name">{{ ach.name }}</div>
          <div class="ach-card-desc">{{ ach.description }}</div>
          <!-- 进度条 -->
          <div v-if="!ach.unlocked" class="ach-card-progress">
            <div class="ach-progress-bar-bg">
              <div class="ach-progress-bar-fill" :style="{ width: ach.progress + '%', background: ach.color }"></div>
            </div>
            <span class="ach-progress-label">{{ ach.progressLabel }}</span>
          </div>
          <div v-else class="ach-card-unlocked">
            <span class="ach-unlocked-dot" :style="{ background: ach.color }"></span>
            已解锁
          </div>
        </div>
        <!-- 分类标签 -->
        <span class="ach-card-category" :style="ach.unlocked ? { background: ach.color + '15', color: ach.color } : {}">
          {{ CATEGORY_ICONS[ach.category] }} {{ CATEGORY_LABELS[ach.category] || ach.category }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.achievement-panel {
  padding: 0;
}

.ach-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.25rem;
  padding: 0 0 1rem;
  border-bottom: 1px solid var(--border-color);
}

.ach-title {
  font-size: 1.125rem;
  font-weight: 700;
  color: var(--text-primary);
}

.ach-subtitle {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.125rem;
}

.ach-overall {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
}

.ach-overall-circle {
  position: relative;
  width: 3rem;
  height: 3rem;
}

.ach-circular {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}

.ach-overall-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6875rem;
  font-weight: 700;
  color: var(--accent-primary);
}

.ach-overall-count {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
}

/* 最近解锁 */
.ach-recent {
  margin-bottom: 1.25rem;
}

.ach-recent-title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.ach-recent-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.ach-recent-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-md);
  border: 1px solid;
  background: var(--bg-tertiary);
}

.ach-recent-icon {
  font-size: 1.25rem;
}

.ach-recent-name {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.ach-recent-desc {
  font-size: 0.6875rem;
  color: var(--text-muted);
  margin-top: 0.0625rem;
}

/* 成就网格 */
.ach-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 0.625rem;
}

.ach-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.875rem;
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  position: relative;
  transition: all 0.2s;
}

.ach-card:hover {
  background: var(--bg-card-hover);
}

.ach-card.locked {
  opacity: 0.55;
}

.ach-card-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-md);
  background: var(--color-surface);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  flex-shrink: 0;
}

.ach-card.locked .ach-card-icon {
  background: var(--color-surface);
  filter: grayscale(0.8);
}

.ach-card-body {
  flex: 1;
  min-width: 0;
}

.ach-card-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-primary);
}

.ach-card-desc {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.125rem;
}

.ach-card-progress {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.ach-progress-bar-bg {
  flex: 1;
  height: 0.375rem;
  background: var(--color-surface);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.ach-progress-bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  transition: width 0.4s ease;
}

.ach-progress-label {
  font-size: 0.6875rem;
  color: var(--text-muted);
  white-space: nowrap;
}

.ach-card-unlocked {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 0.5rem;
  font-size: 0.6875rem;
  color: var(--accent-success);
  font-weight: 600;
}

.ach-unlocked-dot {
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 50%;
}

.ach-card-category {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  font-size: 0.625rem;
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-full);
  background: var(--color-surface);
  color: var(--text-muted);
}

/* 分类筛选 */
.ach-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-bottom: 1rem;
}
.ach-filter-btn {
  padding: 0.3125rem 0.75rem;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}
.ach-filter-btn:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.ach-filter-btn.active {
  background: var(--accent-primary-15);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: 600;
}
</style>