<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSkillStore, type CreatorStats } from '@/stores/skillStore'
import Skeleton from '@/components/Skeleton.vue'
import { icons } from '@/components/icons'
import { api } from '@/utils/api'

const router = useRouter()
const store = useSkillStore()

const stats = ref<CreatorStats | null>(null)
const loading = ref(true)

// 简单柱状图 — 纯 CSS 实现，无外部依赖
function barWidth(value: number, max: number): string {
  if (max === 0) return '0%'
  return Math.max(5, (value / max) * 100) + '%'
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([
      store.fetchCreatorStats(),
      store.fetchMySkills(),
    ])
    stats.value = store.creatorStats
    // 趋势图补零：确保近 7 天都有数据
    if (stats.value?.usage_trend) {
      const filled: { day: string; count: number }[] = []
      const now = new Date()
      for (let i = 6; i >= 0; i--) {
        const d = new Date(now)
        d.setDate(d.getDate() - i)
        const key = d.toISOString().slice(0, 10)
        const found = stats.value.usage_trend.find((t: any) => t.day === key)
        filled.push({ day: key.slice(5), count: found?.count || 0 })
      }
      stats.value.usage_trend = filled
    }
  } catch (e) {
    console.error('CreatorDashboard load error:', e)
    stats.value = null
  } finally {
    loading.value = false
  }
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：创作者看板展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞创作者看板 */ }
}
</script>

<template>
  <div class="page-section">
    <div class="section-header">
      <div class="section-title-group">
        <div>
          <div class="section-title"><span v-html="icons.dashboard" class="section-title-icon"></span>创作者看板</div>
          <div class="section-desc">你的 AI 技能创作数据总览</div>
        </div>
      </div>
      <div class="section-actions">
        <button class="btn btn-primary" @click="router.push('/studio')">+ 创建新技能</button>
        <button class="btn btn-ghost" @click="router.push('/skills')">← 返回市场</button>
      </div>
    </div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <div v-if="loading" class="skeleton-grid-2">
      <Skeleton variant="card" />
      <Skeleton variant="card" />
      <Skeleton variant="card" class="skeleton-span-2" />
    </div>

    <div v-else-if="!stats && store.mySkills.length === 0" class="empty-state">
      <div class="empty-title">暂无创作数据</div>
      <div class="empty-desc">你还没有创建过 AI 技能，去工坊创建第一个吧</div>
      <div class="empty-actions"><button class="btn btn-primary" @click="router.push('/studio')">+ 创建新技能</button></div>
    </div>

    <div v-else class="dashboard-grid">
      <!-- 概览卡片 -->
      <div class="dash-card">
        <div class="dash-card-title"><span v-html="icons.skill" class="card-title-icon"></span>技能概览</div>
        <div class="dash-stats">
          <div class="dash-stat">
            <span class="dash-value">{{ stats?.total_skills || 0 }}</span>
            <span class="dash-label">总技能</span>
          </div>
          <div class="dash-stat">
            <span class="dash-value success">{{ stats?.published_skills || 0 }}</span>
            <span class="dash-label">已发布</span>
          </div>
          <div class="dash-stat">
            <span class="dash-value warm">{{ (stats?.total_skills || 0) - (stats?.published_skills || 0) }}</span>
            <span class="dash-label">草稿</span>
          </div>
          <div class="dash-stat">
            <span class="dash-value accent">{{ stats?.total_usage || 0 }}</span>
            <span class="dash-label">总调用</span>
          </div>
        </div>
      </div>

      <!-- 使用趋势 -->
      <div class="dash-card">
        <div class="dash-card-title"><span v-html="icons.chartUp" class="card-title-icon"></span>近 7 天调用趋势</div>
        <div v-if="stats?.usage_trend?.length" class="trend-chart">
          <div class="trend-bar-wrapper">
            <div
              v-for="(item, i) in stats.usage_trend"
              :key="i"
              class="trend-bar-item"
            >
              <div class="trend-bar-value">{{ item.count }}</div>
              <div
                class="trend-bar"
                :style="{ height: barWidth(item.count, Math.max(...stats.usage_trend.map((d: any) => d.count))) }"
              ></div>
              <div class="trend-bar-label">{{ item.day?.slice(5) || '?' }}</div>
            </div>
          </div>
        </div>
        <div v-else class="no-data"><span v-html="icons.chart" class="inline-icon"></span>暂无使用数据</div>
      </div>

      <!-- 我的技能列表 -->
      <div class="dash-card wide-card">
        <div class="dash-card-title"><span v-html="icons.skill" class="card-title-icon"></span>我的技能</div>
        <div v-if="store.mySkills.length === 0" class="no-data"><span v-html="icons.skill" class="inline-icon"></span>还没有创建技能，去工坊创建第一个吧</div>
        <div v-else class="skill-list">
          <div
            v-for="skill in store.mySkills.slice(0, 10)"
            :key="skill.id"
            class="skill-row"
            @click="router.push(`/skills/${skill.id}`)"
          >
            <span class="skill-row-icon">{{ skill.icon }}</span>
            <span class="skill-row-name">{{ skill.name }}</span>
            <span class="skill-row-status" :class="`badge-${skill.status}`">
              {{ { draft: '草稿', published: '已发布', archived: '已归档' }[skill.status] || skill.status }}
            </span>
            <span class="skill-row-usage">{{ skill.usage_count }} 次</span>
            <span class="skill-row-rating">★ {{ skill.avg_rating.toFixed(1) }}</span>
          </div>
        </div>
        <div v-if="store.mySkills.length > 10" class="view-all" @click="router.push('/skills')">
          查看全部 {{ store.mySkills.length }} 个技能 →
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-header { display: flex; justify-content: space-between; align-items: flex-start; gap:1rem; flex-wrap: wrap; margin-bottom:1.25rem; }
.section-title-group { display: flex; align-items: center; gap:0.75rem; }
.section-actions { display: flex; gap:0.5rem; }

.dashboard-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 800px) { .dashboard-grid { grid-template-columns: 1fr; } }
.wide-card { grid-column: 1 / -1; }

.dash-card { padding:1.25rem; background: var(--color-surface); border: 1px solid var(--color-border); border-radius:0.75rem; }
.dash-card-title { font-size:0.9375rem; font-weight: 600; margin-bottom:1rem; color: var(--color-text); }

.dash-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.dash-stat { text-align: center; padding:0.75rem; background: var(--color-surface-2); border-radius:0.5rem; }
.dash-value { display: block; font-size:1.75rem; font-weight: 700; color: var(--color-text); }
.dash-value.success { color: var(--accent-success); }
.dash-value.warm { color: var(--accent-warm); }
.dash-value.accent { color: var(--accent); }
.dash-label { display: block; font-size:0.75rem; color: var(--color-text-3); margin-top:0.125rem; }

/* 趋势图 */
.trend-chart { padding:0.5rem 0; }
.trend-bar-wrapper { display: flex; align-items: flex-end; gap:0.5rem; height:7.5rem; }
.trend-bar-item { flex: 1; display: flex; flex-direction: column; align-items: center; gap:0.25rem; }
.trend-bar-value { font-size:0.6875rem; font-weight: 600; color: var(--color-text-2); }
.trend-bar { width:100%; max-width:2.5rem; background: linear-gradient(to top, var(--accent), var(--accent-cyan)); border-radius:0.25rem 0.25rem 0 0; min-height:0.25rem; transition: height 0.3s ease; }
.trend-bar-label { font-size:0.625rem; color: var(--color-text-3); }

.no-data { text-align: center; padding:2.5rem 1.25rem; color: var(--color-text-3); font-size:0.875rem; }

/* 技能列表 */
.skill-list { display: flex; flex-direction: column; gap:0.375rem; }
.skill-row { display: flex; align-items: center; gap:0.625rem; padding:0.625rem 0.75rem; border-radius:0.5rem; cursor: pointer; transition: background 0.15s; }
.skill-row:hover { background: var(--color-surface-hover); }
.skill-row-icon { font-size:1.25rem; }
.skill-row-name { flex: 1; font-size:0.875rem; font-weight: 500; color: var(--color-text); }
.skill-row-status { font-size:0.6875rem; padding:0.125rem 0.5rem; border-radius:1.25rem; font-weight: 500; }
.badge-draft { background: rgba(245,158,11,0.12); color: var(--accent-warm); }
.badge-published { background: rgba(34,197,94,0.12); color: var(--accent-success); }
.badge-archived { background: rgba(148,163,184,0.12); color: var(--color-text-2); }
.skill-row-usage { font-size:0.75rem; color: var(--color-text-3); }
.skill-row-rating { font-size:0.75rem; color: var(--accent-warm); font-weight: 600; }

.view-all { text-align: center; padding:0.5rem; margin-top:0.5rem; color: var(--accent); font-size:0.8125rem; cursor: pointer; }
.view-all:hover { text-decoration: underline; }
</style>