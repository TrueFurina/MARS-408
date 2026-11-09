<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAchievementStore } from '@/stores/achievementStore'
import { api } from '@/utils/api'
import { toast } from '@/utils/toast'

const achStore = useAchievementStore()
const loading = ref(true)

// L1/L2/L3 三层学情记忆（低侵入联动：成就页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)

// 达成通知：记录上次已解锁数，检测新增解锁弹 Toast
const _PREV_KEY = 'mangdehenzhi_ach_prev_unlocked'
const newlyUnlocked = ref<string[]>([])

function notifyNewAchievements() {
  const prev = parseInt(localStorage.getItem(_PREV_KEY) || '0', 10) || 0
  const now = achStore.unlockedCount
  if (now > prev) {
    // 找出新增解锁的成就
    const newly = achStore.achievements
      .filter(a => a.unlocked && a.unlockedAt)
      .sort((a, b) => new Date(b.unlockedAt!).getTime() - new Date(a.unlockedAt!).getTime())
      .slice(0, now - prev)
      .map(a => a.name)
    if (newly.length) {
      newlyUnlocked.value = newly
      toast('success', ` 成就解锁: ${newly.join('、')}`)
    }
  }
  localStorage.setItem(_PREV_KEY, String(now))
}

// 分享成就
function shareAchievement(ach: any) {
  const text = ` 我在 芒得很职 解锁了成就「${ach.name}」！${ach.description}`
  try {
    if (navigator.share) {
      navigator.share({ title: '芒得很职 成就', text }).catch(() => {})
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(() => {
        const t = (window as any).__toast
        if (t?.info) t.info('成就已复制到剪贴板，快去分享吧！')
      }).catch(() => {})
    }
  } catch { /* 分享失败忽略 */ }
}

onMounted(async () => {
  try {
    await achStore.fetchFromBackend()
  } catch (e) {
    console.error('获取成就失败:', e)
  } finally {
    loading.value = false
  }
  notifyNewAchievements()
  loadMemoryOverview()
})

async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞成就页 */ }
}
</script>

<template>
  <div class="page-section">
    <div class="ac-eyebrow">ACHIEVEMENTS</div>
    <div class="section-title"> 成就系统</div>
    <div class="section-desc">完成学习任务，解锁成就徽章</div>

    <!-- 薄弱点原来一排红底红字，与全站已统一的中性胶囊不一致；统一成标签 + 词条两层 -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip">
      <span class="mem-label">记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" class="mem-chip">{{ w }}</span>
    </div>

    <div v-if="loading" class="empty-state"><div class="empty-title">加载中...</div></div>
    <div v-else>
      <div class="achievement-stats">
        <span class="ach-stat">已解锁 <strong>{{ achStore.unlockedCount }}</strong> / {{ achStore.totalCount }}</span>
        <div class="ach-progress" aria-hidden="true">
          <div class="ach-progress-fill" :style="{ transform: `scaleX(${achStore.totalCount ? achStore.unlockedCount / achStore.totalCount : 0})` }"></div>
        </div>
      </div>
      <div class="achievement-grid">
        <div v-for="ach in achStore.achievements" :key="ach.id" class="achievement-card" :class="{ unlocked: ach.unlocked }">
          <!-- 未解锁也显示图标（灰化）：全空会让用户以为"成就没有图标"（实测反馈） -->
          <div class="ach-icon" :class="{ 'is-locked': !ach.unlocked }">{{ ach.icon }}</div>
          <div class="ach-info">
            <div class="ach-title">{{ ach.name }}</div>
            <div class="ach-desc">{{ ach.description }}</div>
          </div>
          <div class="ach-badge" v-if="ach.unlocked"></div>
          <button v-if="ach.unlocked" class="ach-share" title="分享成就" @click="shareAchievement(ach)"></button>
        </div>
      </div>

      <!-- 新解锁成就提示条 -->
      <div v-if="newlyUnlocked.length" class="newly-unlocked-strip">
         恭喜解锁新成就：{{ newlyUnlocked.join('、') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 原来是一条居中大字横条：60px 高只放一句「已解锁 3 / 27」，上下都是空。
   改为左对齐一句话 + 一条细进度，信息密度和版式都跟其他页一致。 */
/* 用 grid 而不是 flex 排这一行：flex-basis 的简写会被 cssMinify 压成 `flex:8rem`，
   压缩后的语义与原文不一致，进度条轨道只拿到 60px 左右。
   grid 的 `auto 1fr` 不依赖简写展开，轨道稳定铺满右侧剩余宽度。 */
.achievement-stats { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: var(--space-4); font-size: var(--text-base); margin-bottom: var(--space-5); padding: var(--space-4) var(--space-5); background: var(--color-card); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
/* 轨道用 border 色而不是 surface-2：surface-2 与卡片底色只差几个灰阶，暗色下整条看不见，
   看起来就像"只有一小截紫色" */
.ach-progress { display: block; width: 100%; max-width: 22rem; height: 6px; border-radius: 3px; background: var(--color-border); overflow: hidden; }
.ach-progress-fill { display: block; height: 100%; transform-origin: left center; background: var(--color-accent-solid); border-radius: 2px; }
.mem-label { font-size: var(--text-xs); font-weight: var(--weight-semibold); color: var(--accent-primary); background: var(--accent-primary-10); padding: 3px 10px; border-radius: 12px; }
.mem-chip { font-size: var(--text-xs); color: var(--color-text-2); background: var(--color-surface-2); border: 1px solid var(--color-border); padding: 3px 10px; border-radius: 12px; }
.my-mini-strip, .memory-mini-strip { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 12px; }
.ac-eyebrow { font-size: 11px; line-height: 1; letter-spacing: 0.16em; text-transform: uppercase; color: var(--accent-primary); font-weight: 600; margin-bottom: 10px; }
.achievement-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-3); }
.achievement-card { display: flex; align-items: center; gap: var(--space-3); padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--glass-border); background: var(--glass-bg); transition: var(--transition); }
.achievement-card.unlocked { border-color: var(--accent-primary); background: var(--accent-primary-05); }
.ach-icon { font-size: 32px; width: 48px; text-align: center; }
/* 未解锁：图标灰化但仍可见（否则整格空白，用户会以为图标缺失） */
.ach-icon.is-locked { filter: grayscale(1); opacity: 0.35; }
.ach-info { flex: 1; }
.ach-title { font-size: var(--text-base); font-weight: var(--weight-semibold); margin-bottom: 2px; }
.ach-desc { font-size: var(--text-xs); color: var(--text-muted); }
.ach-badge { font-size: var(--text-xl); }
.ach-share { width: 32px; height: 32px; border-radius: var(--radius-sm); border: 1px solid var(--glass-border); background: transparent; cursor: pointer; font-size: var(--text-md); flex-shrink: 0; transition: var(--transition); opacity: 0; }
.achievement-card:hover .ach-share { opacity: 1; }
.ach-share:hover { background: var(--accent-primary-10); border-color: var(--accent-primary); }
.newly-unlocked-strip { margin-top: var(--space-4); padding: var(--space-3) var(--space-4); border-radius: var(--radius-md); background: linear-gradient(135deg, rgba(var(--warning-rgb),0.15), rgba(var(--warning-rgb),0.1)); border: 1px solid rgba(var(--warning-rgb),0.3); color: var(--text-primary); font-size: var(--text-base); font-weight: var(--weight-medium); animation: ach-pop 0.4s ease; }
@keyframes ach-pop { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
</style>