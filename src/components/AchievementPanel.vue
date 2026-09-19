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
  milestone: '',
  practice: '',
  knowledge: '',
  streak: '',
  master: '',
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
        <div class="ach-title"> 成就系统</div>
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
              <div class="ach-progress-bar-fill" :style="{ width: '100%', transform: 'scaleX(' + (ach.progress / 100) + ')', transformOrigin: 'left', background: ach.color }"></div>
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
  margin-bottom: var(--space-5);
  padding: 0 0 var(--space-4);
  border-bottom: 1px solid var(--border-color);
}

.ach-title {
  font-size: var(--text-xl);
  font-weight: var(--weight-bold);
  color: var(--text-primary);
}

.ach-subtitle {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: 0.125rem;
}

.ach-overall {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
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
  font-size: var(--text-2xs);
  font-weight: var(--weight-bold);
  color: var(--accent-primary);
}

.ach-overall-count {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  color: var(--text-secondary);
}

/* 最近解锁 */
.ach-recent {
  margin-bottom: var(--space-5);
}

.ach-recent-title {
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  color: var(--text-secondary);
  margin-bottom: var(--space-2);
}

.ach-recent-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.ach-recent-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid;
  background: var(--bg-tertiary);
}

.ach-recent-icon {
  font-size: var(--text-2xl);
}

.ach-recent-name {
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
}

.ach-recent-desc {
  font-size: var(--text-2xs);
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
  gap: var(--space-3);
  padding: 0.875rem;
  border-radius: var(--radius-md);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  position: relative;
  transition: var(--transition)
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
  font-size: var(--text-2xl);
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
  font-size: var(--text-base);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
}

.ach-card-desc {
  font-size: var(--text-xs);
  color: var(--text-muted);
  margin-top: 0.125rem;
}

.ach-card-progress {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
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
  width: 100%; transform-origin: left; transition: transform var(--duration-slow) var(--ease-standard);
}

.ach-progress-label {
  font-size: var(--text-2xs);
  color: var(--text-muted);
  white-space: nowrap;
}

.ach-card-unlocked {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: var(--space-2);
  font-size: var(--text-2xs);
  color: var(--accent-success);
  font-weight: var(--weight-semibold);
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
  padding: 0.125rem var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-surface);
  color: var(--text-muted);
}

/* 分类筛选 */
.ach-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-bottom: var(--space-4);
}
.ach-filter-btn {
  padding: 0.3125rem var(--space-3);
  border-radius: var(--radius-full);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: var(--transition)
}
.ach-filter-btn:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.ach-filter-btn.active {
  background: var(--accent-primary-15);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  font-weight: var(--weight-semibold);
}
</style>