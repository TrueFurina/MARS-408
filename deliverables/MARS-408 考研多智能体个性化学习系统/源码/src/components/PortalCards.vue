<script setup lang="ts">
import { icons } from '@/components/icons'

interface PortalItem {
  key: string
  icon: string
  title: string
  subtitle: string
  tags: string[]
  route: string
  color: string
  accent: string
  completed: boolean
}

defineProps<{
  portals: PortalItem[]
}>()

const emit = defineEmits<{
  navigate: [route: string]
}>()
</script>

<template>
  <section class="portals-section">
    <div class="section-label">核心功能入口</div>
    <div class="portals-grid stagger-children">
      <div v-for="p in portals" :key="p.key" class="portal-card" role="button" tabindex="0"
        @click="emit('navigate', p.route)"
        @keydown.enter="emit('navigate', p.route)"
        @keydown.space.prevent="emit('navigate', p.route)">
        <div class="portal-icon-wrap" :style="{ background: p.color }">
          <span :style="{ color: p.accent }" v-html="p.icon"></span>
        </div>
        <div class="portal-body">
          <div class="portal-title">{{ p.title }}</div>
          <div class="portal-subtitle">{{ p.subtitle }}</div>
          <div class="portal-tags">
            <span v-for="tag in p.tags" :key="tag" class="portal-tag" :style="{ color: p.accent, background: p.color }">{{ tag }}</span>
          </div>
        </div>
        <div class="portal-enter" :style="{ color: p.accent }">
          进入系统
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.portals-section {
  padding: 0 2rem 2rem;
  max-width: 75rem;
  margin: 0 auto;
}
.section-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-weight: 600;
  margin-bottom: 0.75rem;
  letter-spacing: 0.0312rem;
}
.portals-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}
.portal-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  padding: 1.5rem 1.25rem;
  cursor: pointer;
  transition: var(--transition-slow);
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  position: relative;
}
.portal-card:hover {
  border-color: var(--color-glass-border);
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg);
}
.portal-icon-wrap {
  width: 3rem;
  height: 3rem;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.portal-icon-wrap svg { width: 1.5rem; height: 1.5rem; }
.portal-title {
  font-size: 1.0625rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.0187rem;
}
.portal-subtitle {
  font-size: 0.8125rem;
  color: var(--text-secondary);
  line-height: 1.5;
  margin-top: 0.25rem;
}
.portal-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
  margin-top: 0.25rem;
}
.portal-tag {
  font-size: 0.6875rem;
  padding: 0.1875rem 0.625rem;
  border-radius: var(--radius-full);
  font-weight: 600;
}
.portal-enter {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  margin-top: auto;
  transition: var(--transition);
}
.portal-enter svg { width: 0.875rem; height: 0.875rem; }
.portal-card:hover .portal-enter { opacity: 1; }

@media (max-width: 1024px) {
  .portals-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 768px) {
  .portals-section { padding: 0 1.25rem 1.25rem; }
  .portals-grid { grid-template-columns: 1fr; }
  .portal-card { padding: 1.25rem 1rem; }
}
</style>