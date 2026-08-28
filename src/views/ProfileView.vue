<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { useAchievementStore } from '@/stores/achievementStore'
import { api } from '@/utils/api'

const store = useStudyStore()
const achStore = useAchievementStore()
const router = useRouter()
const loading = ref(true)
const quizHistory = ref<{ subject: string; correct: boolean }[]>([])
const LOAD_TIMEOUT = 8000

// ── 编辑目标 ──
const showEdit = ref(false)
const editTarget = ref(120)
const editSchool = ref('')
const editStudyTime = ref('2-4h')
const editSubjectCount = ref(4)
const saving = ref(false)
const saveMsg = ref('')
const saveOk = ref(false)

async function saveProfile() {
  saving.value = true
  saveMsg.value = ''
  try {
    await api.post('/profile/update', {
      target_score: editTarget.value,
      target_school: editSchool.value,
      study_time: editStudyTime.value,
      subject_count: editSubjectCount.value,
    })
    saveOk.value = true
    saveMsg.value = '✅ 保存成功'
    setTimeout(() => { showEdit.value = false; saveMsg.value = '' }, 2000)
  } catch (e: any) {
    saveOk.value = false
    saveMsg.value = '❌ ' + (e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const TRAIT_COLORS = [
  '#8B5CF6', '#7c6af2', '#3B82F6', '#06B6D4',
  '#EC4899', '#F472B6', '#818CF8', '#4F46E5',
]

// 8 维画像计算
const traits = computed(() => {
  const p = store.studentProfile
  if (!p) return store.data?.profileTraits ?? []
  return [
    { id: 'knowledge', label: '知识基础', value: baseToPercent(p.knowledge_base), icon: '🧠', desc: '当前知识掌握水平' },
    { id: 'style', label: '学习风格', value: styleToPercent(p.learning_style), icon: getStyleIcon(p.learning_style), desc: '最佳学习方式' },
    { id: 'goal', label: '学习目标', value: goalToPercent(p.goal), icon: '🎯', desc: '目标明确程度' },
    { id: 'progress', label: '学习进度', value: Math.min(100, (p.progress ?? 0) * 14), icon: '📈', desc: '整体学习完成度' },
    { id: 'weakness', label: '薄弱攻克', value: weaknessToPercent(p.weak_points), icon: '💪', desc: '薄弱点覆盖进度' },
    { id: 'accuracy', label: '答题准确率', value: calculateAccuracy(), icon: '🎯', desc: '近7天答题正确率' },
    { id: 'activeness', label: '学习活跃度', value: calculateActiveness(), icon: '🔥', desc: '日均学习时长' },
    { id: 'discipline', label: '自律性', value: calculateDiscipline(), icon: '⏰', desc: '学习计划完成率' },
  ]
})

// 画像摘要
const profileSummary = computed(() => {
  const p = store.studentProfile
  if (!p) return { level: '未知', style: '未知', weakCount: 0, strength: '待评估' }
  const level = p.knowledge_base || 'beginner'
  const levelLabel = { none: '零基础', beginner: '入门', intermediate: '进阶', advanced: '精通' }[level] || level
  const style = p.learning_style || 'reading'
  const styleLabel = { visual: '视觉型', reading: '阅读型', 'hands-on': '实操型', auditory: '听觉型' }[style] || style
  const weakCount = (p.weak_points || '').split(/[,，、]/).filter(Boolean).length
  const avgScore = traits.value.reduce((s, t) => s + t.value, 0) / traits.value.length
  const strength = avgScore >= 70 ? '优势明显' : avgScore >= 50 ? '稳步提升' : '需要加强'
  return { level: levelLabel, style: styleLabel, weakCount, strength }
})

// 推荐建议
const recommendations = computed(() => {
  const p = store.studentProfile
  if (!p) return []
  const items: { icon: string; text: string; action: string; route: string }[] = []
  if (baseToPercent(p.knowledge_base) < 50) {
    items.push({ icon: '📚', text: '基础薄弱，建议从基础概念开始系统学习', action: '去学习', route: '/knowledge' })
  }
  if (p.weak_points) {
    const weaks = p.weak_points.split(/[,，、]/).filter(Boolean)
    weaks.slice(0, 3).forEach(w => {
      items.push({ icon: '🎯', text: `薄弱点「${w}」需要重点突破`, action: '生成练习', route: `/practice?focus=${w}` })
    })
  }
  if ((p.progress ?? 0) < 3) {
    items.push({ icon: '🗺️', text: '学习进度较慢，建议制定每日学习计划', action: '规划路径', route: '/learning-path' })
  }
  if (calculateAccuracy() < 50) {
    items.push({ icon: '📝', text: '答题准确率偏低，建议先复习再做题', action: '复习知识点', route: '/knowledge' })
  }
  return items
})

// 转化函数
function baseToPercent(base: string | undefined): number {
  const map: Record<string, number> = { none: 20, beginner: 40, intermediate: 65, advanced: 85 }
  return map[base ?? ''] || 50
}
function styleToPercent(style: string | undefined): number {
  const map: Record<string, number> = { visual: 80, reading: 60, 'hands-on': 70, auditory: 50 }
  return map[style ?? ''] || 65
}
function goalToPercent(goal: string | undefined): number {
  if (!goal) return 30
  if (goal.includes('120') || goal.includes('高分')) return 90
  if (goal.includes('90') || goal.includes('过线')) return 60
  return 50
}
function weaknessToPercent(weak: string | undefined): number {
  if (!weak) return 0
  const count = weak.split(/[,，、]/).filter(Boolean).length
  return Math.min(100, count * 12)
}
function getStyleIcon(style: string | undefined): string {
  const map: Record<string, string> = { visual: '👁️', reading: '📖', 'hands-on': '🛠️', auditory: '👂' }
  return map[style ?? ''] || '📖'
}
function calculateAccuracy(): number {
  const history = quizHistory.value
  if (history.length === 0) return 50
  const recent = history.slice(-20)
  const correct = recent.filter((q: any) => q.correct).length
  return Math.round(correct / recent.length * 100)
}
function calculateActiveness(): number {
  const sessions = store.conversations || []
  if (sessions.length === 0) return 30
  return Math.min(100, sessions.length * 8)
}
function calculateDiscipline(): number {
  const p = store.studentProfile
  if (!p?.progress) return 40
  return Math.min(100, (p.progress ?? 0) * 10 + 30)
}

// Radar chart
function drawRadar() {
  const canvas = document.getElementById('profileRadar') as HTMLCanvasElement
  if (!canvas || traits.value.length < 3) return
  const wrapper = canvas.parentElement
  const dpr = window.devicePixelRatio || 1
  const size = wrapper?.clientWidth || 320
  canvas.width = size * dpr
  canvas.height = size * dpr
  canvas.style.width = size + 'px'
  canvas.style.height = size + 'px'
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.scale(dpr, dpr)
  const cx = size / 2, cy = size / 2
  const radius = Math.min(cx, cy) * 0.65
  const n = traits.value.length
  const angleStep = (Math.PI * 2) / n
  const values = traits.value.map(t => t.value / 100)

  // 同心网格
  for (const level of [0.2, 0.4, 0.6, 0.8, 1.0]) {
    const r = radius * level
    ctx.beginPath()
    for (let i = 0; i <= n; i++) {
      const angle = -Math.PI / 2 + i * angleStep
      const x = cx + r * Math.cos(angle), y = cy + r * Math.sin(angle)
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
    }
    ctx.closePath()
    ctx.strokeStyle = `rgba(124, 106, 242, ${0.08 + level * 0.10})`
    ctx.stroke()
  }
  // 轴线
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + i * angleStep
    ctx.beginPath(); ctx.moveTo(cx, cy)
    ctx.lineTo(cx + radius * Math.cos(angle), cy + radius * Math.sin(angle))
    ctx.strokeStyle = 'rgba(124, 106, 242, 0.18)'; ctx.stroke()
  }
  // 数据区域
  ctx.beginPath()
  for (let i = 0; i <= n; i++) {
    const idx = i % n, angle = -Math.PI / 2 + i * angleStep
    const r = radius * (values[idx] ?? 0)
    const x = cx + r * Math.cos(angle), y = cy + r * Math.sin(angle)
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
  }
  ctx.closePath()
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius)
  grad.addColorStop(0, 'rgba(124, 106, 242, 0.35)')
  grad.addColorStop(0.5, 'rgba(124, 106, 242, 0.25)')
  grad.addColorStop(1, 'rgba(59, 130, 246, 0.10)')
  ctx.fillStyle = grad; ctx.fill()
  ctx.strokeStyle = 'rgba(124, 106, 242, 0.7)'
  ctx.lineWidth = 2; ctx.stroke()
  // 标签
  for (let i = 0; i < n; i++) {
    const angle = -Math.PI / 2 + i * angleStep, item = traits.value[i]
    if (!item) continue
    const r = radius * (values[i] ?? 0), x = cx + r * Math.cos(angle), y = cy + r * Math.sin(angle)
    const color = TRAIT_COLORS[i % TRAIT_COLORS.length] ?? '#8B5CF6'
    ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI * 2)
    ctx.fillStyle = color; ctx.fill(); ctx.strokeStyle = '#8B5CF6'; ctx.lineWidth = 2; ctx.stroke()
    ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2); ctx.fillStyle = color + '20'; ctx.fill()
    const labelR = radius + 24, lx = cx + labelR * Math.cos(angle), ly = cy + labelR * Math.sin(angle)
    ctx.fillStyle = '#94a3b8'
    ctx.font = '600 12px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText(item.icon + ' ' + item.label, lx, ly)
    const valR = r + (labelR - r) * 0.35
    ctx.fillStyle = color
    ctx.font = '700 14px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.fillText(item.value + '%', cx + valR * Math.cos(angle), cy + valR * Math.sin(angle))
  }
}

let resizeHandler: (() => void) | null = null
let themeObserver: MutationObserver | null = null

// L1/L2/L3 三层学情记忆（低侵入联动：画像页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞画像页 */ }
}

onMounted(() => {
  loadMemoryOverview()
  // 拉取真实答题历史（替代已移除的 store.quizHistory），供准确率计算
  api.get<any>('/quiz/history').then((r: any) => {
    if (r?.records?.length) {
      quizHistory.value = r.records.map((x: any) => ({ subject: x.subject || 'unknown', correct: !!x.correct }))
    }
  }).catch(() => {}).finally(() => {
    loading.value = false
    // loading 变 false 后 canvas 才会渲染，必须等 DOM 更新再画雷达图
    nextTick(() => setTimeout(drawRadar, 50))
  })
  resizeHandler = () => drawRadar()
  window.addEventListener('resize', resizeHandler)
  // 监听主题切换，重绘雷达图
  themeObserver = new MutationObserver(() => setTimeout(drawRadar, 50))
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
})

// 兜底：loading 从 true→false 时确保雷达图重绘（应对 finally 时序竞争）
watch(loading, (v) => {
  if (!v) nextTick(() => setTimeout(drawRadar, 80))
})

onUnmounted(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  if (themeObserver) themeObserver.disconnect()
})
</script>

<template>
  <div class="page-section active">
    <div v-if="loading" class="profile-skeleton">
      <div class="skeleton" style="width:200px;height:28px;margin-bottom:20px;border-radius:8px;"></div>
      <div class="skeleton" style="width:100%;height:120px;margin-bottom:16px;border-radius:12px;"></div>
      <div class="skeleton-grid"><div v-for="i in 4" :key="i" class="skeleton" style="height:120px;border-radius:12px;"></div></div>
    </div>
    <template v-else>
      <div class="section-header">
        <div class="section-title">🧑‍🎓 学生画像</div>
        <div class="section-desc">基于学习行为数据构建的 8 维个性化能力图谱 | <button class="btn-link" @click="showEdit = !showEdit">{{ showEdit ? '收起编辑' : '编辑目标' }}</button></div>
      </div>

      <!-- L1/L2/L3 三层学情记忆健康度（低侵入联动） -->
      <div v-if="memoryOverview" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
        <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 {{ memoryOverview.memory_level || 'L3' }}</span>
        <span style="padding:3px 10px;border-radius:12px;background:var(--bg-tertiary);color:var(--text-secondary);">掌握度 {{ memoryOverview.mastery_points ?? 0 }} 点</span>
        <span style="padding:3px 10px;border-radius:12px;background:var(--bg-tertiary);color:var(--text-secondary);">情景事件 {{ memoryOverview.episodic_count ?? 0 }}</span>
        <span v-if="memoryOverview.weak_points?.length" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">记忆薄弱: {{ memoryOverview.weak_points.slice(0, 4).join('、') }}</span>
      </div>

      <!-- 编辑目标 -->
      <div v-if="showEdit" class="card" style="margin-bottom:20px;">
        <div class="card-header"><span class="card-title">✏️ 编辑学习目标</span></div>
        <div class="edit-grid">
          <div class="edit-field">
            <label class="edit-label">目标分数</label>
            <input type="number" v-model.number="editTarget" min="0" max="150" class="edit-input" />
            <span class="edit-hint">408 考研总分 150 分</span>
          </div>
          <div class="edit-field">
            <label class="edit-label">目标院校</label>
            <input type="text" v-model="editSchool" placeholder="如：北京大学" class="edit-input" />
          </div>
          <div class="edit-field">
            <label class="edit-label">每日学习时长</label>
            <select v-model="editStudyTime" class="edit-input">
              <option value="<1h">&lt; 1小时</option>
              <option value="1-2h">1-2小时</option>
              <option value="2-4h">2-4小时</option>
              <option value="4-6h">4-6小时</option>
              <option value=">6h">&gt; 6小时</option>
            </select>
          </div>
          <div class="edit-field">
            <label class="edit-label">报考科目数</label>
            <select v-model="editSubjectCount" class="edit-input">
              <option :value="1">1 科</option>
              <option :value="2">2 科</option>
              <option :value="3">3 科</option>
              <option :value="4">4 科（全科）</option>
            </select>
          </div>
        </div>
        <div class="edit-actions">
          <button class="btn btn-primary" @click="saveProfile" :disabled="saving">{{ saving ? '保存中...' : '💾 保存' }}</button>
          <span v-if="saveMsg" class="save-msg" :class="{ success: saveOk, error: !saveOk }">{{ saveMsg }}</span>
        </div>
      </div>

      <!-- 画像摘要卡片 -->
      <div class="profile-hero">
        <div class="profile-avatar-large">408</div>
        <div class="profile-hero-body">
          <div class="profile-hero-top">
            <div class="profile-name">408考研人</div>
            <div class="profile-strength" :class="profileSummary.strength === '优势明显' ? 'strong' : profileSummary.strength === '稳步提升' ? 'stable' : 'weak'">{{ profileSummary.strength }}</div>
          </div>
          <div class="profile-meta-row">
            <span class="profile-meta-tag">📊 {{ profileSummary.level }}</span>
            <span class="profile-meta-tag">{{ getStyleIcon(store.studentProfile?.learning_style) }} {{ profileSummary.style }}</span>
            <span class="profile-meta-tag">💪 {{ profileSummary.weakCount }} 个薄弱点</span>
          </div>
          <div class="profile-hero-actions">
            <button class="btn btn-sm btn-soft" @click="router.push('/practice')">📝 针对性练习</button>
            <button class="btn btn-sm btn-ghost" @click="router.push('/skills')">🤖 推荐AI技能</button>
          </div>
        </div>
      </div>

      <!-- 8 维画像卡片 -->
      <div class="profile-dim-grid">
        <div v-for="trait in traits" :key="trait.id" class="profile-dim-card">
          <div class="dim-header">
            <span class="dim-icon">{{ trait.icon }}</span>
            <span class="dim-label">{{ trait.label }}</span>
            <span class="dim-value">{{ trait.value }}%</span>
          </div>
          <div class="dim-bar-bg">
            <div class="dim-bar-fill" :style="{ width: trait.value + '%', background: `linear-gradient(90deg, ${TRAIT_COLORS[traits.indexOf(trait) % TRAIT_COLORS.length]}, ${TRAIT_COLORS[(traits.indexOf(trait) + 1) % TRAIT_COLORS.length]})` }"></div>
          </div>
          <div class="dim-desc">{{ trait.desc }}</div>
        </div>
      </div>

      <!-- 雷达图 + 学习风格 -->
      <div class="grid-2" style="margin-top: 20px;">
        <div class="card">
          <div class="card-header"><span class="card-title">🕸️ 8 维能力雷达图</span></div>
          <div v-if="traits.length < 3" class="radar-placeholder">
            <div style="font-size:40px;margin-bottom:8px;">📊</div>
            <div style="font-size:14px;color:var(--text-muted);">完成入学测评后自动生成雷达图</div>
            <button class="engine-btn" style="margin-top:12px;" @click="router.push('/diagnostic/start')">去测评</button>
          </div>
          <div v-else class="radar-wrapper"><canvas id="profileRadar" class="radar-canvas"></canvas></div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">💡 个性化建议</span></div>
          <div class="recommend-list">
            <div v-for="(rec, i) in recommendations" :key="i" class="recommend-item">
              <span class="recommend-icon">{{ rec.icon }}</span>
              <div class="recommend-body">
                <div class="recommend-text">{{ rec.text }}</div>
                <button class="btn btn-sm btn-ghost" @click="router.push(rec.route)">{{ rec.action }} →</button>
              </div>
            </div>
            <div v-if="recommendations.length === 0" class="recommend-empty">
              <div style="font-size:32px;margin-bottom:8px;">🎉</div>
              <div style="color:var(--text-muted);font-size:14px;">所有维度表现良好，继续保持！</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 科目掌握度 -->
      <div class="card" style="margin-top: 20px;">
        <div class="card-header">
          <span class="card-title">📊 科目掌握度</span>
          <button class="btn btn-sm btn-ghost" @click="router.push('/learning-path')">查看完整路径 →</button>
        </div>
        <div class="mastery-grid">
          <div v-for="m in (store.data?.masteryData ?? [])" :key="m.subject" class="mastery-card">
            <div class="mastery-label">{{ m.label || m.subject }}</div>
            <div class="mastery-bar-bg"><div class="mastery-bar-fill" :style="{ width: (m.pct ?? 0) + '%' }"></div></div>
            <div class="mastery-pct">{{ m.pct ?? 0 }}%</div>
          </div>
          <div v-if="(store.data?.masteryData ?? []).length === 0" class="mastery-empty">
            <div style="font-size:14px;color:var(--text-muted);">暂无数据，开始学习后自动生成</div>
          </div>
        </div>
      </div>

      <!-- 薄弱点 + 评价 -->
      <div class="grid-2" style="margin-top: 20px;">
        <div class="card">
          <div class="card-header"><span class="card-title">⚠️ 待加强知识点</span></div>
          <div>
            <div v-for="w in (store.studentProfile?.weak_points || '').split(/[,，、]/).filter(Boolean).slice(0, 5)" :key="w" class="weakness-item">
              <span class="weakness-bullet"></span>
              <span class="weakness-name">{{ w }}</span>
              <span class="weakness-tag">待加强</span>
            </div>
            <div v-if="!store.studentProfile?.weak_points" style="font-size:14px;color:var(--text-muted);padding:20px;text-align:center;">暂无薄弱点数据</div>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">📋 学习评估</span></div>
          <div class="assessment-stats">
            <div class="assessment-stat">
              <span class="stat-value" style="color:var(--accent-primary)">{{ calculateAccuracy() }}%</span>
              <span class="stat-label">答题准确率</span>
            </div>
            <div class="assessment-stat">
              <span class="stat-value" style="color:var(--accent-cyan)">{{ calculateActiveness() }}%</span>
              <span class="stat-label">学习活跃度</span>
            </div>
            <div class="assessment-stat">
              <span class="stat-value" style="color:var(--accent-success)">{{ calculateDiscipline() }}%</span>
              <span class="stat-label">自律性</span>
            </div>
            <div class="assessment-stat">
              <span class="stat-value" style="color:var(--accent-warm)">{{ (store.studentProfile?.progress ?? 0) * 14 }}%</span>
              <span class="stat-label">学习进度</span>
            </div>
          </div>
</div>
      </div>

      <!-- 成就系统预览 -->
      <div class="card" style="margin-top: 20px;">
        <div class="card-header">
          <span class="card-title">🏆 成就徽章</span>
          <button class="btn btn-sm btn-ghost" @click="router.push('/achievements')">查看全部 →</button>
        </div>
        <div class="achievement-preview">
          <div class="achievement-summary">
            <div class="ach-summary-stat">
              <span class="ach-summary-value">{{ achStore.unlockedCount }}</span>
              <span class="ach-summary-label">已解锁</span>
            </div>
            <div class="ach-summary-divider"></div>
            <div class="ach-summary-stat">
              <span class="ach-summary-value">{{ achStore.totalCount }}</span>
              <span class="ach-summary-label">总成就</span>
            </div>
            <div class="ach-summary-divider"></div>
            <div class="ach-summary-stat">
              <span class="ach-summary-value">{{ achStore.progressPercent }}%</span>
              <span class="ach-summary-label">完成率</span>
            </div>
          </div>
          <div class="ach-preview-badges">
            <div v-for="ach in achStore.recentAchievements.slice(0, 4)" :key="ach.id" class="ach-preview-badge" :style="{ borderColor: ach.color + '40', background: ach.color + '08' }">
              <span class="ach-preview-icon">{{ ach.icon }}</span>
              <span class="ach-preview-name">{{ ach.name }}</span>
            </div>
            <div v-if="achStore.recentAchievements.length === 0" class="ach-preview-empty">
              <div style="font-size: 2rem; margin-bottom: 4px;">🏆</div>
              <div style="font-size: 13px; color: var(--text-muted);">开始学习，解锁你的第一个成就！</div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.profile-hero { display:flex; gap:20px; padding:24px; background:var(--color-surface); border:1px solid var(--color-border); border-radius:14px; margin-bottom:20px; }
.profile-avatar-large { width:72px; height:72px; border-radius:16px; background:var(--gradient-primary); display:flex; align-items:center; justify-content:center; font-size:28px; color:#fff; font-weight:700; flex-shrink:0; }
.profile-hero-body { flex:1; min-width:0; }
.profile-hero-top { display:flex; align-items:center; gap:12px; margin-bottom:8px; }
.profile-name { font-size:22px; font-weight:700; color:var(--color-text); }
.profile-strength { font-size:12px; padding:2px 10px; border-radius:20px; font-weight:600; }
.profile-strength.strong { background:rgba(34,197,94,0.12); color:var(--accent-success); }
.profile-strength.stable { background:rgba(6,182,212,0.12); color:var(--accent-cyan); }
.profile-strength.weak { background:rgba(245,158,11,0.12); color:var(--accent-warm); }
.profile-meta-row { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
.profile-meta-tag { font-size:12px; padding:3px 10px; border-radius:6px; background:var(--color-surface-2); color:var(--color-text-2); }
.profile-hero-actions { display:flex; gap:8px; }
.profile-dim-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:10px; margin-bottom:20px; }
.profile-dim-card { padding:14px; background:var(--color-surface); border:1px solid var(--color-border); border-radius:10px; }
.dim-header { display:flex; align-items:center; gap:8px; margin-bottom:8px; }
.dim-icon { font-size:20px; }
.dim-label { flex:1; font-size:14px; font-weight:600; color:var(--color-text); }
.dim-value { font-size:16px; font-weight:700; color:var(--color-text); }
.dim-bar-bg { height:6px; background:var(--color-surface-2); border-radius:3px; overflow:hidden; margin-bottom:6px; }
.dim-bar-fill { height:100%; border-radius:3px; transition:width 0.8s ease; }
.dim-desc { font-size:11px; color:var(--color-text-3); }
.grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media(max-width:800px){ .grid-2{grid-template-columns:1fr} }
.card { padding:20px; background:var(--color-surface); border:1px solid var(--color-border); border-radius:12px; }
.card-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; }
.card-title { font-size:16px; font-weight:600; color:var(--color-text); }
.radar-wrapper { width:100%; max-width:500px; margin:0 auto; }
.radar-canvas { width:100%; height:auto; display:block; }
.recommend-list { display:flex; flex-direction:column; gap:10px; }
.recommend-item { display:flex; gap:10px; padding:12px; background:var(--color-surface-2); border-radius:8px; }
.recommend-icon { font-size:20px; line-height:1.4; }
.recommend-body { flex:1; }
.recommend-text { font-size:13px; color:var(--color-text-2); margin-bottom:6px; line-height:1.5; }
.recommend-empty { text-align:center; padding:30px; }
.mastery-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:10px; }
.mastery-card { padding:14px; background:var(--color-surface-2); border-radius:8px; }
.mastery-label { font-size:13px; font-weight:600; color:var(--color-text); margin-bottom:8px; }
.mastery-bar-bg { height:6px; background:var(--color-surface); border-radius:3px; overflow:hidden; }
.mastery-bar-fill { height:100%; background:var(--gradient-primary); border-radius:3px; transition:width 0.8s ease; }
.mastery-pct { font-size:12px; font-weight:600; color:var(--color-text-2); margin-top:4px; text-align:right; }
.mastery-empty { grid-column:1/-1; text-align:center; padding:30px; }
.weakness-item { display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:6px; margin-bottom:4px; }
.weakness-item:hover { background:var(--color-surface-hover); }
.weakness-bullet { width:6px; height:6px; border-radius:50%; background:var(--accent-warm); flex-shrink:0; }
.weakness-name { flex:1; font-size:14px; color:var(--color-text); }
.weakness-tag { font-size:11px; padding:2px 8px; border-radius:4px; background:rgba(245,158,11,0.12); color:var(--accent-warm); }
.assessment-stats { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.assessment-stat { text-align:center; padding:14px; background:var(--color-surface-2); border-radius:8px; }
.assessment-stat .stat-value { display:block; font-size:24px; font-weight:700; }
.assessment-stat .stat-label { display:block; font-size:12px; color:var(--color-text-3); margin-top:2px; }
.skeleton-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:10px; }
/* ── 编辑目标 ── */
.edit-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; padding:12px 0; }
.edit-field { display:flex; flex-direction:column; gap:4px; }
.edit-label { font-size:13px; font-weight:600; color:var(--color-text-2); }
.edit-input { padding:8px 12px; border-radius:8px; border:1px solid var(--color-border); background:var(--color-surface); color:var(--color-text); font-size:14px; outline:none; }
.edit-input:focus { border-color:var(--accent-primary); }
.edit-hint { font-size:11px; color:var(--color-text-3); }
.edit-actions { display:flex; align-items:center; gap:12px; padding:8px 0; }
.save-msg { font-size:13px; }
.save-msg.success { color:var(--accent-success); }
.save-msg.error { color:var(--accent-danger); }
.btn-link { background:none; border:none; color:var(--accent-primary); cursor:pointer; font-size:13px; padding:0; text-decoration:underline; }
.btn-link:hover { color:var(--accent-primary-hover); }

/* ── 成就预览 ── */
.achievement-preview { }
.achievement-summary { display: flex; align-items: center; gap: 1rem; padding: 0.75rem 1rem; background: var(--color-surface-2); border-radius: 10px; margin-bottom: 0.75rem; }
.ach-summary-stat { text-align: center; flex: 1; }
.ach-summary-value { display: block; font-size: 1.25rem; font-weight: 800; color: var(--accent-primary); }
.ach-summary-label { display: block; font-size: 0.6875rem; color: var(--text-muted); margin-top: 0.125rem; }
.ach-summary-divider { width: 1px; height: 2rem; background: var(--color-border); }
.ach-preview-badges { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.ach-preview-badge { display: flex; align-items: center; gap: 0.375rem; padding: 0.5rem 0.75rem; border-radius: 8px; border: 1px solid; }
.ach-preview-icon { font-size: 1.125rem; }
.ach-preview-name { font-size: 0.75rem; font-weight: 600; color: var(--text-primary); }
.ach-preview-empty { text-align: center; padding: 1.25rem; }
</style>