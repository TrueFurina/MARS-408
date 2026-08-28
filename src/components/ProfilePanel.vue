<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useStudyStore } from '@/stores/studyStore'
import { icons } from '@/components/icons'

const store = useStudyStore()

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
}>()

const TRAIT_COLORS = ['var(--subject-ds)', 'var(--subject-cn)', 'var(--subject-co)', 'var(--subject-os)', 'var(--accent-primary)', 'var(--accent-warm)', 'var(--accent-success)', 'var(--accent-pink)']

const subjectColors: Record<string, string> = {
  ds: 'var(--subject-ds)',
  cn: 'var(--subject-cn)',
  co: 'var(--subject-co)',
  os: 'var(--subject-os)',
}

// 从后端实时拉取掌握度数据
const masteryDataFromApi = ref<{ subject: string; label: string; pct: number }[]>([])
const masteryLoading = ref(false)

onMounted(() => {
  if (props.open) {
    loadMasteryData()
  }
})

// 当面板打开时自动拉取数据
watch(() => props.open, (isOpen) => {
  if (isOpen) {
    loadMasteryData()
  }
})

async function loadMasteryData() {
  masteryLoading.value = true
  try {
    const data = await store.fetchMasteryData()
    if (data && data.length > 0) {
      masteryDataFromApi.value = data
      store.data.masteryData = data
    }
  } catch { /* 静默降级 */ }
  finally { masteryLoading.value = false }
}

// 从 Store 读取真实画像
const profile = computed(() => {
  const p = store.studentProfile
  if (!p) return null
  return {
    name: '408考研人',
    target: '408计算机核心知识体系',
    tags: getTags(p),
    avatar: 'Net',
  }
})

const traits = computed(() => {
  if (!store.studentProfile) return []
  const p = store.studentProfile
  return [
    { id: 'knowledge', label: '知识基础', value: baseToPercent(p.knowledge_base), iconKey: 'brain' },
    { id: 'style', label: '学习风格', value: styleToPercent(p.learning_style), iconKey: getStyleIconKey(p.learning_style) },
    { id: 'goal', label: '学习目标', value: goalToPercent(p.goal), iconKey: 'target' },
    { id: 'progress', label: '学习进度', value: Math.min(100, (p.progress ?? 0) * 14), iconKey: 'chartUp' },
    { id: 'interest', label: '专注方向', value: areaToPercent(p.interest_area), iconKey: 'fire' },
    { id: 'study_time', label: '每日时长', value: timeToPercent(p.study_time || '1-2h'), iconKey: 'clock' },
    { id: 'difficulty', label: '难度偏好', value: diffToPercent(p.preferred_difficulty || 'medium'), iconKey: 'mountain' },
    { id: 'weakness', label: '知识扎实度', value: weakToPercent(p.weak_points), iconKey: 'shield' },
  ]
})

const mastery = computed(() => {
  const apiData = masteryDataFromApi.value
  if (apiData.length > 0) return apiData
  return store.data?.masteryData ?? []
})

const weaknesses = computed(() => {
  if (!store.studentProfile) return store.data?.weaknesses ?? []
  const wp = store.studentProfile.weak_points
  if (!wp) return store.data?.weaknesses ?? []
  return [
    ...wp.split(/[,，、]/).filter(Boolean).map((name: string) => ({
      name: name.trim(),
      desc: '基于对话分析得出的薄弱点',
      priority: 'high' as const,
      score: '40%',
    })),
    ...(store.data?.weaknesses ?? []).slice(0, 2),
  ].slice(0, 5)
})

function baseToPercent(base: string | undefined): number {
  const map: Record<string, number> = { none: 20, beginner: 40, intermediate: 65, advanced: 85 }
  return map[base ?? ''] || 50
}

function styleToPercent(style: string | undefined): number {
  const map: Record<string, number> = { visual: 80, reading: 60, 'hands-on': 70, auditory: 50 }
  return map[style ?? ''] || 65
}

function getStyleIconKey(style: string | undefined): string {
  const map: Record<string, string> = { visual: 'eye', reading: 'bookOpen', 'hands-on': 'wrench', auditory: 'ear' }
  return map[style ?? ''] || 'bookOpen'
}

function timeToPercent(time: string | undefined): number {
  const map: Record<string, number> = { '<1h': 20, '1-2h': 50, '2-3h': 70, '3-4h': 85, '>4h': 95 }
  return map[time ?? ''] || 50
}

function diffToPercent(diff: string | undefined): number {
  const map: Record<string, number> = { easy: 30, medium: 55, hard: 80, mixed: 65 }
  return map[diff ?? ''] || 55
}

function goalToPercent(goal: string | undefined): number {
  const map: Record<string, number> = { exam: 90, practical: 70, theory: 60, general: 50 }
  return map[goal ?? ''] || 65
}

function areaToPercent(area: string | undefined): number {
  const map: Record<string, number> = { networking: 80, security: 70, protocol: 60, programming: 75, general: 50 }
  return map[area ?? ''] || 50
}

function weakToPercent(weak_points: string | undefined): number {
  const count = weak_points ? weak_points.split(/[,，、]/).filter(Boolean).length : 0
  const map: Record<string, number> = { '0': 95, '1': 80, '2': 65, '3': 50, '4': 40 }
  return map[String(Math.min(count, 4))] || 40
}

function getTags(p: any): string[] {
  const tags = ['计算机']
  if (p.goal === 'exam') tags.push('应试')
  else if (p.goal === 'practical') tags.push('实践')
  else if (p.goal === 'theory') tags.push('理论')
  if (p.interest_area === 'security') tags.push('安全方向')
  else if (p.interest_area === 'protocol') tags.push('协议方向')
  else if (p.interest_area === 'programming') tags.push('编程方向')
  return tags
}

function priorityClass(p: string): string {
  return `weakness-priority-${p}`
}

function daysText(): string {
  return '408考研 · 四科知识体系'
}

// 计算综合评分
const overallScore = computed(() => {
  if (traits.value.length === 0) return 0
  const sum = traits.value.reduce((s, t) => s + t.value, 0)
  return Math.round(sum / traits.value.length)
})

// 学习阶段
const learningPhase = computed(() => {
  const s = overallScore.value
  if (s >= 80) return { label: '冲刺阶段', color: 'var(--accent-success)', desc: '基础扎实，保持节奏' }
  if (s >= 60) return { label: '强化阶段', color: 'var(--accent-warm)', desc: '稳步提升，重点突破薄弱' }
  if (s >= 40) return { label: '基础阶段', color: 'var(--accent-cyan)', desc: '打好基础，系统学习' }
  return { label: '起步阶段', color: 'var(--accent-primary)', desc: '建立知识框架' }
})
</script>

<template>
  <div v-if="open" class="panel-overlay open" @click.self="emit('close')"></div>
  <div class="profile-panel" :class="{ open }">
    <div class="profile-panel-header">
      <h2>学生画像</h2>
      <button class="profile-panel-close" @click="emit('close')" aria-label="关闭画像面板" v-html="icons.close"></button>
    </div>

    <div class="profile-panel-body">
      <!-- 基本信息 -->
      <div class="profile-compact-header">
        <div class="profile-avatar" v-html="icons.user"></div>
        <div class="profile-meta">
          <h3>{{ profile?.name || '408考研人' }}</h3>
          <p>{{ profile?.target || '408计算机核心知识体系' }}</p>
          <div class="profile-tags">
            <span v-for="tag in profile?.tags || []" :key="tag" class="profile-tag">{{ tag }}</span>
          </div>
        </div>
        <div class="profile-score-badge" :style="{ background: learningPhase.color }">
          <div class="score-badge-value">{{ overallScore }}分</div>
          <div class="score-badge-label">{{ learningPhase.label }}</div>
        </div>
      </div>

      <!-- 学习阶段提示 -->
      <div class="phase-banner" :style="{ borderColor: learningPhase.color, background: learningPhase.color + '10' }">
        <div class="phase-banner-icon" :style="{ color: learningPhase.color }">{{ learningPhase.label === '冲刺阶段' ? '🏆' : learningPhase.label === '强化阶段' ? '🔥' : learningPhase.label === '基础阶段' ? '📚' : '🌱' }}</div>
        <div class="phase-banner-text">
          <div class="phase-banner-title" :style="{ color: learningPhase.color }">{{ learningPhase.label }}</div>
          <div class="phase-banner-desc">{{ learningPhase.desc }}</div>
        </div>
      </div>

      <!-- 关键统计 -->
      <div class="profile-stats-grid">
        <div class="profile-stat-card">
          <div class="stat-value">{{ store.daysToExam }}</div>
          <div class="stat-label">距考研</div>
        </div>
        <div class="profile-stat-card">
          <div class="stat-value">{{ store.studentProfile?.target_score || 120 }}</div>
          <div class="stat-label">目标分数</div>
        </div>
        <div class="profile-stat-card">
          <div class="stat-value">{{ store.studentProfile?.subject_count || 4 }}</div>
          <div class="stat-label">报考科目</div>
        </div>
        <div class="profile-stat-card">
          <div class="stat-value">{{ store.studentProfile?.study_time || '2-4h' }}</div>
          <div class="stat-label">每日学习</div>
        </div>
      </div>

      <!-- 能力特质 -->
      <div class="traits-section">
        <div class="traits-title">学习能力特质</div>
        <div v-for="(trait, idx) in traits" :key="trait.id" class="trait-row">
          <span class="trait-icon" v-html="icons[trait.iconKey as keyof typeof icons]"></span>
          <span class="trait-label">{{ trait.label }}</span>
          <div class="trait-bar-bg">
            <div
              class="trait-bar-fill"
              :style="{
                width: trait.value + '%',
                background: TRAIT_COLORS[idx % TRAIT_COLORS.length],
              }"
            ></div>
          </div>
          <span class="trait-value">{{ trait.value }}%</span>
        </div>
      </div>

      <!-- 科目掌握 -->
      <div class="traits-section">
        <div class="traits-title">科目掌握度</div>
        <div v-for="m in mastery" :key="m.subject" class="trait-row">
          <span class="trait-label">{{ m.label }}</span>
          <div class="trait-bar-bg">
            <div
              class="trait-bar-fill"
              :style="{
                width: m.pct + '%',
                background: subjectColors[m.subject] || 'var(--accent-primary)',
              }"
            ></div>
          </div>
          <span class="trait-value">{{ m.pct }}%</span>
        </div>
      </div>

      <!-- 薄弱点 -->
      <div class="traits-section">
        <div class="traits-title">待加强知识点</div>
        <div v-for="w in weaknesses" :key="w.name" class="weakness-item">
          <div class="weakness-name">
            <span>{{ w.name }}</span>
            <span class="weakness-score" :class="priorityClass(w.priority)">{{ w.score }}</span>
          </div>
          <div class="weakness-desc">{{ w.desc }}</div>
        </div>
      </div>

      <div style="text-align:center;padding:16px 0 8px;font-size:12px;color:var(--text-muted);">
        {{ daysText() }} · 坚持就是胜利
      </div>
    </div>
  </div>
</template>
