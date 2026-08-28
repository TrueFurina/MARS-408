<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAchievementStore } from '@/stores/achievementStore'
import { api } from '@/utils/api'

const achStore = useAchievementStore()
const loading = ref(true)

// L1/L2/L3 三层学情记忆（低侵入联动：成就页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)

// 达成通知：记录上次已解锁数，检测新增解锁弹 Toast
const _PREV_KEY = 'mars408_ach_prev_unlocked'
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
      // 使用全局 Toast（window.__toast 由 ToastNotification 组件挂载）
      const t = (window as any).__toast
      if (t?.success) {
        t.success(`🏆 成就解锁: ${newly.join('、')}`)
      } else {
        window.dispatchEvent(new CustomEvent('netlearn-toast', {
          detail: { type: 'success', message: `🏆 成就解锁: ${newly.join('、')}` },
        }))
      }
    }
  }
  localStorage.setItem(_PREV_KEY, String(now))
}

// 分享成就
function shareAchievement(ach: any) {
  const text = `🏆 我在 NetLearn 解锁了成就「${ach.name}」！${ach.description}`
  try {
    if (navigator.share) {
      navigator.share({ title: 'NetLearn 成就', text }).catch(() => {})
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
    <div class="section-title">🏆 成就系统</div>
    <div class="section-desc">完成学习任务，解锁成就徽章</div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <div v-if="loading" class="empty-state"><div class="empty-title">加载中...</div></div>
    <div v-else>
      <div class="achievement-stats">
        <span class="ach-stat">已解锁 <strong>{{ achStore.unlockedCount }}</strong> / {{ achStore.totalCount }}</span>
      </div>
      <div class="achievement-grid">
        <div v-for="ach in achStore.achievements" :key="ach.id" class="achievement-card" :class="{ unlocked: ach.unlocked }">
          <div class="ach-icon">{{ ach.unlocked ? ach.icon : '🔒' }}</div>
          <div class="ach-info">
            <div class="ach-title">{{ ach.name }}</div>
            <div class="ach-desc">{{ ach.description }}</div>
          </div>
          <div class="ach-badge" v-if="ach.unlocked">✅</div>
          <button v-if="ach.unlocked" class="ach-share" title="分享成就" @click="shareAchievement(ach)">📤</button>
        </div>
      </div>

      <!-- 新解锁成就提示条 -->
      <div v-if="newlyUnlocked.length" class="newly-unlocked-strip">
        🎉 恭喜解锁新成就：{{ newlyUnlocked.join('、') }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.achievement-stats { text-align: center; font-size: 16px; margin-bottom: 20px; padding: 16px; background: var(--glass-bg); border-radius: var(--radius-md); }
.achievement-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.achievement-card { display: flex; align-items: center; gap: 12px; padding: 14px; border-radius: var(--radius-md); border: 1px solid var(--glass-border); background: var(--glass-bg); transition: var(--transition); }
.achievement-card.unlocked { border-color: var(--accent-primary); background: var(--accent-primary-05); }
.ach-icon { font-size: 32px; width: 48px; text-align: center; }
.ach-info { flex: 1; }
.ach-title { font-size: 14px; font-weight: 600; margin-bottom: 2px; }
.ach-desc { font-size: 12px; color: var(--text-muted); }
.ach-badge { font-size: 18px; }
.ach-share { width: 32px; height: 32px; border-radius: var(--radius-sm); border: 1px solid var(--glass-border); background: transparent; cursor: pointer; font-size: 15px; flex-shrink: 0; transition: var(--transition); opacity: 0; }
.achievement-card:hover .ach-share { opacity: 1; }
.ach-share:hover { background: var(--accent-primary-10); border-color: var(--accent-primary); }
.newly-unlocked-strip { margin-top: 16px; padding: 12px 16px; border-radius: var(--radius-md); background: linear-gradient(135deg, rgba(250,204,21,0.15), rgba(245,158,11,0.1)); border: 1px solid rgba(250,204,21,0.3); color: var(--text-primary); font-size: 14px; font-weight: 500; animation: ach-pop 0.4s ease; }
@keyframes ach-pop { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
</style>