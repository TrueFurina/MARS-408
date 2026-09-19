<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore, type StatData, type Session, type Task } from '@/stores/studyStore'
import { icons } from '@/components/icons'
import RingProgress from '@/components/RingProgress.vue'
import EmptyState from '@/components/EmptyState.vue'
import PortalCards from '@/components/PortalCards.vue'
import { api } from '@/utils/api'

const store = useStudyStore()
const router = useRouter()

const stats = ref<StatData | null>(null)
const sessions = ref<Session[]>([])
const tasks = ref<Task[]>([])
const memoryOverview = ref<any>(null)
const loading = ref(true)
const recommendations = ref<any[]>([])

// ── 仪表盘扩展：8-Agent 协作架构（静态结构声明）──
// 【证据纪律 2026-09-15】此前此处硬编码 status: 'online'/'busy'/'idle' 并注释称"由后端 SSE 驱动"，
// 但 py-server/api/agents.py 只有 generate-* 路由，不存在任何 agent 运行时状态接口 —— 注释与实现不符，
// 属于发生型证据造假。现改为纯静态架构：只声明结构固定、可验证的"角色 + 职责"，
// 不渲染任何运行时状态。待后端提供 /api/agents/runtime 后再接入真实状态。
const agents = [
  { name: '协调', role: 'Coordinator', duty: '意图识别与任务分派', color: 'var(--agent-coord)' },
  { name: '诊断', role: 'Diagnostician', duty: '学情画像与薄弱点定位', color: 'var(--agent-diag)' },
  { name: '规划', role: 'Planner', duty: '学习路径与阶段目标', color: 'var(--agent-plan)' },
  { name: '检索', role: 'Retriever', duty: 'FrugalRAG 资料召回', color: 'var(--agent-retrieve)' },
  { name: '生成', role: 'Generator', duty: '讲解与题目生成', color: 'var(--agent-gen)' },
  { name: '评估', role: 'Assessor', duty: '作答评分与掌握度更新', color: 'var(--agent-eval)' },
  { name: '审核', role: 'Critic', duty: '三元评审与证据校验', color: 'var(--agent-quality)' },
  { name: '路径', role: 'PathPlanner', duty: 'MAPPO 策略选档', color: 'var(--agent-path)' },
]

// ── 科目练习热力图（行 = 科目，列 = 该科目最近 8 次真实练习记录）──
// 【证据纪律 2026-09-15】原实现用 ((i * 37) % 3) - 1 的确定性公式，把 1 个学科掌握度
// 扩散成 8 个"知识点"格（基础概念 / 核心原理 / …），其中 7/8 的数值无任何数据源，
// 属于编造细分数据（原注释称"非编造"不成立）。
// 现改为：每个有色格子 = 一条真实 Session 记录的 score，可追溯到具体那次练习；
// 无记录的格子留空（灰底 + "—"），绝不填充推算值。
const HEATMAP_COLS = 8
const heatmapRows = computed(() => {
  return subjectMastery.value.map((m) => {
    const records = sessions.value
      .filter((s) => s.subject === m.key && typeof s.score === 'number')
      .slice(0, HEATMAP_COLS)
    const cells = Array.from({ length: HEATMAP_COLS }, (_, i) => {
      const rec = records[i]
      if (!rec) return { level: 0, seq: i + 1, label: '暂无练习记录' }
      const score = Math.round(rec.score)
      return {
        level: Math.min(5, Math.max(1, Math.floor(score / 20) + 1)),
        seq: i + 1,
        label: `第 ${i + 1} 次练习 · 得分 ${score}`,
      }
    })
    return { key: m.key, name: m.name, color: m.color, cells, count: records.length }
  })
})

// 预警干预（从 recommendations 中提取高危项；无数据时显示空态）
const alerts = computed(() => {
  if (!recommendations.value.length) return []
  return recommendations.value
    .filter((r: any) => r.priority === 'high' || r.priority === 'medium')
    .slice(0, 4)
    .map((r: any) => ({
      topic: r.title,
      action: r.text,
      level: r.priority === 'high' ? 'danger' : 'weak',
      route: r.route || '/practice',
    }))
})

function subjectLabel(s: string): string {
  return store.subjects[s]?.name || s
}

const userName = computed(() => store.studentProfile ? '同学' : '408考研人')

// 408 考研倒计时（以 2026 年 12 月第三个周六为考研日 ≈ 12/19）
const examDate = new Date('2026-12-19T08:30:00')
const daysToExam = computed(() => {
  const now = new Date()
  const diff = examDate.getTime() - now.getTime()
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)))
})

const subjectEntries = computed(() => {
  return Object.entries(store.subjects).map(([key, val]) => ({ key, name: val.name }))
})

// 学科掌握度：以最近学习记录的得分均值作为真实掌握度代理；无数据时优雅降级
const subjectColorMap: Record<string, string> = {
  data_structures: 'var(--subject-ds)',
  computer_network: 'var(--subject-cn)',
  computer_organization: 'var(--subject-co)',
  operating_system: 'var(--subject-os)',
}
const subjectMastery = computed(() => {
  const entries = subjectEntries.value
  const acc: Record<string, { sum: number; n: number }> = {}
  entries.forEach(({ key }) => { acc[key] = { sum: 0, n: 0 } })
  sessions.value.forEach((s) => {
    const a = acc[s.subject]
    if (a && typeof s.score === 'number') {
      a.sum += s.score
      a.n += 1
    }
  })
  return entries.map(({ key, name }) => {
    const a = acc[key]
    const value = a && a.n > 0 ? Math.round(a.sum / a.n) : null
    return { key, name, value, color: subjectColorMap[key] || 'var(--accent-primary)' }
  })
})

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--text-success)'
  if (score >= 60) return 'var(--accent-warm)'
  return 'var(--text-danger)'
}

function tagClass(subject: string): string {
  const keys = Object.keys(store.subjects)
  const idx = keys.indexOf(subject)
  return idx >= 0 ? `subject-${idx % 8}` : ''
}

// 功能入口卡片——对应赛题5大核心功能
const portals = [
  {
    key: 'profile',
    icon: icons.user,
    title: '对话式学习画像',
    subtitle: '自然语言对话 · 8维度动态画像 · 随学随新',
    tags: ['多维度画像', '对话构建', '动态更新'],
    route: '/profile/build',
    color: 'rgba(124, 106, 242, 0.15)',
    accent: 'var(--accent)',
    completed: false,
  },
  {
    key: 'agent',
    icon: icons.sparkle,
    title: '多智能体资源生成',
    subtitle: '8个AI智能体协作 · 7种个性化资源 · 审核防幻觉',
    tags: ['讲解文档', '练习题库', '思维导图', '拓展阅读', 'PPT大纲', '代码实操', '审核报告'],
    route: '/resource',
    color: 'rgba(59, 130, 246, 0.15)',
    accent: 'var(--accent-blue)',
    completed: false,
  },
  {
    key: 'path',
    icon: icons.path,
    title: '个性化学习路径',
    subtitle: '薄弱点驱动排序 · 动态路径规划 · 资源精准推送',
    tags: ['路径规划', '资源推送', '薄弱点聚焦'],
    route: '/learning-path',
    color: 'rgba(6, 182, 212, 0.15)',
    accent: 'var(--accent-cyan)',
    completed: false,
  },
  {
    key: 'assessment',
    icon: icons.target,
    title: '学习效果评估',
    subtitle: '7章掌握度热力图 · 易错点分析 · LLM智能评估',
    tags: ['热力图', '易错点', '动态调整'],
    route: '/assessment',
    color: 'rgba(244, 114, 182, 0.15)',
    accent: 'var(--accent-pink)',
    completed: false,
  },
]

// 可选加分项入口
const bonusPortals = [
  { key: 'chat', icon: icons.chat, title: '智能辅导答疑', route: '/chat', color: 'var(--accent-success-20)', accent: 'var(--accent-success)' },
  { key: 'knowledge', icon: icons.knowledge, title: '408知识图谱', route: '/knowledge', color: 'rgba(245, 158, 11, 0.15)', accent: 'var(--accent-warm)' },
]

// 评审入口 — 引导评委看技术亮点
const judgePortals = [
  { key: 'engine', icon: icons.engine, title: '算法引擎可视化', desc: 'FrugalRAG节俭检索 + GoMARL共识引擎 + Agent辩论协议 — 核心技术对比表', route: '/engine', color: 'rgba(124, 106, 242, 0.12)', accent: 'var(--accent)', tag: ' 评审推荐' },
  { key: 'resource', icon: icons.agent, title: '多智能体资源生成', desc: '10节点LangGraph StateGraph + SSE实时流 + 7种个性化资源', route: '/resource', color: 'rgba(59, 130, 246, 0.12)', accent: 'var(--accent-blue)', tag: '核心功能' },
  { key: 'knowledge', icon: icons.knowledge, title: '408四科知识图谱', desc: '487知识点节点 + Canvas力导向图 + 四科分组聚合', route: '/knowledge', color: 'rgba(6, 182, 212, 0.12)', accent: 'var(--accent-cyan)', tag: '核心功能' },
]

function go(route: string) { router.push(route) }

onMounted(async () => {
  try {
    const [s, ses, t] = await Promise.all([
      store.fetchStats(),
      store.fetchRecentSessions(),
      store.fetchRecommendedTasks(),
    ])
    stats.value = s
    sessions.value = ses
    tasks.value = t
    // 加载画像驱动推荐
    try {
      const recRes: any = await api.post('/assessment/recommendations', {
        profile: store.studentProfile || {},
        quiz_history: [], // 答题历史由 AssessmentView 统一拉取；此处仅以画像驱动推荐
      })
      recommendations.value = recRes?.recommendations || []
    } catch (e: any) {
      console.warn('获取推荐失败:', e?.message)
    }
    // L1/L2/L3 三层学情记忆健康度（低侵入联动，失败不影响主流程）
    try {
      const memRes: any = await api.get('/memory/overview')
      if (memRes?.status === 'ok') memoryOverview.value = memRes
    } catch { /* 记忆服务不可用时不阻塞 Dashboard */ }
  } catch (e: any) {
    console.warn('Dashboard 数据加载失败:', e?.message)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="landing-page">
    <!-- 加载骨架屏 -->
    <div v-if="loading" class="dashboard-skeleton">
      <div class="skeleton hero-skel"></div>
      <div class="skeleton-grid">
        <div v-for="i in 4" :key="i" class="skeleton skeleton-card"></div>
      </div>
    </div>

    <!-- 空状态：后端未运行 -->
    <EmptyState v-else-if="!stats && !sessions.length && !tasks.length" :icon="icons.dashboard" title="欢迎来到 MARS-408" description="启动后端服务后，这里将展示你的学习数据、最近学习记录和推荐任务。">
      <template #action>
        <button class="hero-cta" @click="go('/profile/build')">开始构建学习画像</button>
        <button class="hero-cta secondary" @click="go('/chat')">进入智能对话</button>
      </template>
    </EmptyState>
    <!-- Hero 区域 -->
    <section class="hero-section">
      <div class="hero-bg-glow"></div>
      <div class="hero-content">
        <div class="hero-top-row">
          <div class="hero-badge">基于大模型的个性化资源生成与学习多智能体系统</div>
          <div class="exam-countdown">
            <span class="countdown-number">{{ daysToExam }}</span>
            <span class="countdown-label">天后考研</span>
          </div>
        </div>
        <h1 class="hero-title">
          408考研<span class="hero-title-accent">智能学习</span>中心
        </h1>
        <p class="hero-tagline">你的专属 408 备考教练 · 八位 AI 助教 · 四科全覆盖</p>
        <div class="hero-stats-row" v-if="stats">
          <div class="hero-stat">
            <span class="hero-stat-value">4</span>
            <span class="hero-stat-label">408科目覆盖</span>
          </div>
          <div class="hero-stat-divider"></div>
          <div class="hero-stat">
            <span class="hero-stat-value">8</span>
            <span class="hero-stat-label">画像维度</span>
          </div>
          <div class="hero-stat-divider"></div>
          <div class="hero-stat">
            <span class="hero-stat-value">6</span>
            <span class="hero-stat-label">协作智能体</span>
          </div>
          <div class="hero-stat-divider"></div>
          <div class="hero-stat">
            <span class="hero-stat-value">7</span>
            <span class="hero-stat-label">资源类型</span>
          </div>
          <div class="hero-stat-divider"></div>
          <div class="hero-stat" v-if="memoryOverview">
            <span class="hero-stat-value">{{ memoryOverview.episodic_count ?? 0 }}</span>
            <span class="hero-stat-label">学情记忆事件</span>
          </div>
        </div>
        <!-- 408 四科标识 -->
        <div class="subject-badges">
          <span class="subject-badge badge-ds">数据结构</span>
          <span class="subject-badge badge-cn">计算机网络</span>
          <span class="subject-badge badge-co">计算机组成原理</span>
          <span class="subject-badge badge-os">操作系统</span>
        </div>
        <!-- 学科快捷入口 -->
        <div v-if="subjectEntries.length" class="subject-quick-grid">
          <div v-for="sub in subjectEntries" :key="sub.key" class="subject-quick-card" :class="'sq-' + sub.key" role="button" tabindex="0" @click="go('/knowledge?subject=' + sub.key)" @keydown.enter="go('/knowledge?subject=' + sub.key)" @keydown.space.prevent="go('/knowledge?subject=' + sub.key)">
            <span class="sq-name">{{ sub.name }}</span>
            <span class="sq-arrow">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            </span>
          </div>
        </div>
        <button v-if="!store.profileCompleted" class="hero-cta" @click="go('/chat')">
          开始构建学习画像
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </button>
      </div>
    </section>

    <!-- 画像驱动推荐 -->
    <section v-if="recommendations.length" class="rec-section">
      <div class="section-label"> 画像驱动推荐</div>
      <div class="rec-grid">
        <div v-for="(rec, i) in recommendations" :key="i" class="rec-card" :class="rec.priority" role="button" tabindex="0" @click="go(rec.route)" @keydown.enter="go(rec.route)" @keydown.space.prevent="go(rec.route)">
          <span class="rec-icon">{{ rec.icon }}</span>
          <div class="rec-body">
            <div class="rec-title">{{ rec.title }}</div>
            <div class="rec-text">{{ rec.text }}</div>
          </div>
          <span class="rec-action">{{ rec.action }} →</span>
        </div>
      </div>
    </section>

    <!--  评审推荐：引导评委看技术亮点 -->
    <section class="judge-section">
      <div class="section-label"> 评审推荐 — 核心技术亮点</div>
      <div class="judge-grid">
        <div v-for="p in judgePortals" :key="p.key" class="judge-card" role="button" tabindex="0" @click="go(p.route)" @keydown.enter="go(p.route)" @keydown.space.prevent="go(p.route)">
          <div class="judge-tag">{{ p.tag }}</div>
          <div class="judge-icon" :style="{ background: p.color, color: p.accent }" v-html="p.icon"></div>
          <div class="judge-title">{{ p.title }}</div>
          <div class="judge-desc">{{ p.desc }}</div>
        </div>
      </div>
    </section>

    <!-- 核心功能入口（4卡片，对应赛题功能1-3+5） -->
    <PortalCards :portals="portals" @navigate="go" />

    <!-- 可选加分功能 -->
    <section class="bonus-section">
      <div class="bonus-label">可选加分功能</div>
      <div class="bonus-row">
        <div v-for="b in bonusPortals" :key="b.key" class="bonus-card" role="button" tabindex="0" @click="go(b.route)" @keydown.enter="go(b.route)" @keydown.space.prevent="go(b.route)">
          <div class="bonus-icon" :style="{ background: b.color, color: b.accent }" v-html="b.icon"></div>
          <span class="bonus-title">{{ b.title }}</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" :style="{ color: b.accent }"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </div>
      </div>
    </section>

    <!-- 学习数据总览 -->
    <section v-if="stats" class="data-section">
      <div class="data-label">学习数据总览</div>
      <div class="data-grid">
        <div class="data-card">
          <div class="data-icon" v-html="icons.book"></div>
          <div class="data-value">{{ stats.studyTime }}h</div>
          <div class="data-label-text">今日学习时长</div>
        </div>
        <div class="data-card">
          <div class="data-icon" v-html="icons.pen"></div>
          <div class="data-value">{{ stats.questionsDone }}</div>
          <div class="data-label-text">今日完成题目</div>
        </div>
        <div class="data-card mastery-card">
          <RingProgress :value="stats.mastery" :size="88" :stroke="8" />
          <div class="data-caption">知识点整体掌握率</div>
        </div>
        <div class="data-card">
          <div class="data-icon" v-html="icons.fire"></div>
          <div class="data-value">{{ stats.streak }}天</div>
          <div class="data-label-text">连续学习</div>
        </div>
      </div>
    </section>

    <!-- 学科掌握度分布 -->
    <section v-if="stats" class="mastery-section">
      <div class="data-label">学科掌握度分布</div>
      <div class="mastery-grid">
        <div v-for="m in subjectMastery" :key="m.key" class="mastery-tile" :class="'sm-' + m.key">
          <RingProgress :value="m.value ?? 0" :size="76" :stroke="7" :color="m.color" />
          <div class="mastery-name">{{ m.name }}</div>
          <div class="mastery-sub">{{ m.value === null ? '数据累积中' : m.value + '%' }}</div>
        </div>
      </div>
    </section>

    <!-- 多智能体协同状态（融合自仪表盘 HTML · 8 Agent 架构可视化） -->
    <section class="agent-status-section">
      <div class="data-label">
        多智能体协作架构
        <span class="tag-demo">静态结构 · 无运行时数据</span>
      </div>
      <div class="agent-grid">
        <div v-for="ag in agents" :key="ag.role" class="agent-card">
          <div class="agent-info">
            <div class="agent-name" :style="{ color: ag.color }">{{ ag.name }} Agent</div>
            <div class="agent-role">{{ ag.role }}</div>
            <div class="agent-duty">{{ ag.duty }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 知识点掌握度热力图（融合自仪表盘 HTML · 紫系连续色阶） -->
    <section v-if="stats" class="heatmap-section">
      <div class="data-label">
        科目练习记录热力图
        <span class="tag-demo">真实练习记录</span>
      </div>
      <div class="heatmap-container">
        <div class="heatmap-row" v-for="row in heatmapRows" :key="row.key">
          <div class="heatmap-subj-label" :style="{ color: row.color }">{{ row.name }}</div>
          <div class="heatmap-cells">
            <div
              v-for="(cell, ci) in row.cells"
              :key="ci"
              class="heatmap-cell"
              :style="{ background: cell.level === 0 ? 'var(--chart-grid)' : `var(--seq-${cell.level})` }"
              :title="cell.label"
            >
              <span class="heatmap-cell-text" :style="{ color: cell.level >= 4 ? 'var(--color-text-invert)' : 'var(--color-text-2)' }">{{ cell.level === 0 ? '—' : cell.seq }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="heatmap-legend">
        <span class="legend-label">得分：</span>
        <span class="legend-item" v-for="(lab, li) in ['0-19', '20-39', '40-59', '60-79', '80-100']" :key="li" :style="{ background: `var(--seq-${li + 1})` }">{{ lab }}</span>
        <span class="legend-item legend-empty">无记录</span>
      </div>
    </section>

    <!-- 预警干预面板（融合自仪表盘 HTML · 薄弱点/危险项驱动行动） -->
    <section v-if="alerts.length" class="alert-section">
      <div class="data-label">
        预警干预
        <span class="tag-demo">画像驱动</span>
      </div>
      <div class="alert-list">
        <div v-for="(al, i) in alerts" :key="i" class="alert-item" :class="'alert-' + al.level" role="button" tabindex="0" @click="go(al.route)" @keydown.enter="go(al.route)" @keydown.space.prevent="go(al.route)">
          <div class="alert-dot" :class="'dot-' + al.level"></div>
          <div class="alert-body">
            <div class="alert-topic">{{ al.topic }}</div>
            <div class="alert-action">{{ al.action }}</div>
          </div>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" class="alert-arrow"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </div>
      </div>
    </section>

    <!-- 最近学习 + 推荐任务 -->
    <section v-if="!loading" class="recent-section">
      <div class="recent-grid">
        <div class="recent-col">
          <div class="recent-header">
            <span>最近学习</span>
            <span class="recent-link" role="button" tabindex="0" @click="go('/chat')" @keydown.enter="go('/chat')" @keydown.space.prevent="go('/chat')">查看全部</span>
          </div>
          <div v-for="s in sessions" :key="s.id" class="recent-session" role="button" tabindex="0" @click="go('/chat')" @keydown.enter="go('/chat')" @keydown.space.prevent="go('/chat')">
            <span class="session-subject-tag" :class="tagClass(s.subject)">{{ subjectLabel(s.subject) || s.subject }}</span>
            <div class="session-info">
              <div class="session-title">{{ s.title }}</div>
              <div class="session-meta">{{ s.date }} · {{ s.duration }}</div>
            </div>
            <div class="session-score" :style="{ color: scoreColor(s.score) }">{{ s.score }}分</div>
          </div>
        </div>
        <div class="recent-col">
          <div class="recent-header">
            <span>推荐任务</span>
            <span class="recent-link" role="button" tabindex="0" @click="go('/practice')" @keydown.enter="go('/practice')" @keydown.space.prevent="go('/practice')">更多</span>
          </div>
          <div v-for="t in tasks" :key="t.id" class="recommend-card" role="button" tabindex="0" @click="go('/practice')" @keydown.enter="go('/practice')" @keydown.space.prevent="go('/practice')">
            <div class="recommend-icon" :style="{ background: 'rgba(124,106,242,0.12)' }">{{ t.icon }}</div>
            <div class="recommend-info">
              <div class="recommend-title">{{ t.title }}</div>
              <div class="recommend-desc">{{ t.desc }}</div>
            </div>
            <div class="recommend-time">{{ t.time }}</div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.landing-page {
  flex: 1;
  overflow-y: auto;
  padding:0;
}

/* ── Hero ── */
.hero-section {
  position: relative;
  padding:3.75rem var(--space-8) var(--space-12);
  overflow: hidden;
}

.hero-bg-glow {
  position: absolute;
  inset:0;
  background:
    radial-gradient(ellipse 600px 400px at 30% 30%, rgba(var(--accent-rgb), 0.08) 0%, transparent 70%),
    radial-gradient(ellipse 500px 300px at 70% 60%, rgba(var(--info-rgb), 0.06) 0%, transparent 70%);
  pointer-events: none;
}

.hero-content {
  max-width:75rem;
  margin:0 auto;
  position: relative;
  z-index: 1;
}

.hero-badge {
  display: inline-block;
  padding:0.375rem var(--space-4);
  border-radius:var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-size:var(--text-xs);
  font-weight: var(--weight-semibold);
  letter-spacing:0.0187rem;
  margin-bottom:var(--space-4);
}

.hero-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap:var(--space-3);
  margin-bottom:var(--space-4);
}

/* 考研倒计时 */
.exam-countdown {
  display: flex;
  align-items: center;
  gap:0.375rem;
  padding:0.375rem var(--space-4) 0.375rem 0.875rem;
  border-radius:var(--radius-full);
  background: rgba(var(--warning-rgb), 0.10);
  border: 1px solid rgba(var(--warning-rgb), 0.20);
}
.countdown-number {
  font-size:var(--text-xl);
  font-weight: 800;
  color: var(--accent-warm);
  line-height:var(--leading-none);
  font-variant-numeric: tabular-nums;
}
.countdown-label {
  font-size:var(--text-xs);
  color: var(--accent-warm);
  font-weight: var(--weight-semibold);
}

/* 学科快捷入口 */
.subject-quick-grid {
  display: flex;
  gap:var(--space-2);
  margin-bottom:var(--space-5);
  flex-wrap: wrap;
}
.subject-quick-card {
  display: flex;
  align-items: center;
  gap:var(--space-2);
  padding:var(--space-2) var(--space-4);
  border-radius:var(--radius-sm);
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: var(--transition);
  background: var(--bg-secondary);
}
.subject-quick-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
}
.sq-name { font-size:var(--text-sm); font-weight: var(--weight-semibold); }
.sq-arrow { opacity: 0; transition: var(--transition); display: flex; }
.subject-quick-card:hover .sq-arrow { opacity: 1; }

.sq-data_structures .sq-name { color: var(--subject-ds); }
.sq-data_structures:hover { border-color: rgba(var(--subject-ds-rgb), 0.30); }
.sq-computer_network .sq-name { color: var(--subject-cn); }
.sq-computer_network:hover { border-color: rgba(var(--subject-cn-rgb), 0.30); }
.sq-computer_organization .sq-name { color: var(--subject-co); }
.sq-computer_organization:hover { border-color: rgba(var(--subject-co-rgb), 0.30); }
.sq-operating_system .sq-name { color: var(--subject-os); }
.sq-operating_system:hover { border-color: rgba(var(--subject-os-rgb), 0.30); }

.hero-title {
  font-size:var(--text-5xl);
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing:-0.0625rem;
  line-height:var(--leading-tight);
  margin-bottom:0.625rem;
}

.hero-title-accent {
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-tagline {
  font-size:var(--text-lg);
  color: var(--text-secondary);
  letter-spacing:0.0625rem;
  margin-bottom:var(--space-7);
}

.hero-stats-row {
  display: flex;
  align-items: center;
  gap:var(--space-6);
  margin-bottom:var(--space-6);
}

.hero-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.hero-stat-value {
  font-size:1.75rem;
  font-weight: 800;
  color: var(--accent-primary);
  letter-spacing:-0.0312rem;
}

.hero-stat-label {
  font-size:var(--text-xs);
  color: var(--text-muted);
  margin-top:0.125rem;
}

.hero-stat-divider {
  width:0.0625rem;
  height:2.25rem;
  background: var(--border-color);
}

.hero-cta {
  display: inline-flex;
  align-items: center;
  gap:var(--space-2);
  padding:0.875rem var(--space-7);
  border-radius:var(--radius-full);
  background: var(--gradient-primary);
  color: var(--color-text-on-accent);
  font-size:var(--text-md);
  font-weight: var(--weight-semibold);
  cursor: pointer;
  transition: var(--transition);
  border: none;
}

.hero-cta:hover {
  opacity: 0.92;
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(var(--accent-rgb), 0.30);
}

.hero-cta svg { width:1rem; height:1rem; }

/* 408 四科标识 */
.subject-badges {
  display: flex;
  gap:var(--space-2);
  margin-bottom:var(--space-6);
  flex-wrap: wrap;
}
.subject-badge {
  font-size:var(--text-xs);
  font-weight: var(--weight-semibold);
  padding:0.3125rem 0.875rem;
  border-radius:var(--radius-full);
  letter-spacing:0.0187rem;
}
.badge-ds { background: rgba(var(--subject-ds-rgb), 0.12); color: var(--subject-ds); border: 1px solid rgba(var(--subject-ds-rgb), 0.20); }
.badge-cn { background: rgba(var(--subject-cn-rgb), 0.12); color: var(--subject-cn); border: 1px solid rgba(var(--subject-cn-rgb), 0.20); }
.badge-co { background: rgba(var(--subject-co-rgb), 0.12); color: var(--subject-co); border: 1px solid rgba(var(--subject-co-rgb), 0.20); }
.badge-os { background: rgba(var(--subject-os-rgb), 0.12); color: var(--subject-os); border: 1px solid rgba(var(--subject-os-rgb), 0.20); }

/*  评审推荐卡片 */
.rec-section { padding:0 var(--space-8) var(--space-6); max-width:75rem; margin:0 auto; }
.rec-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:var(--space-2); }
.rec-card { display:flex; align-items:center; gap:10px; padding:var(--space-3) 14px; border-radius:10px; background:var(--color-surface); border:1px solid var(--color-border); cursor:pointer; transition:var(--transition); }
.rec-card:hover { border-color:var(--color-border-focus); background:var(--color-surface-hover); transform:translateY(-1px); }
.rec-card.high { border-left:3px solid var(--accent-danger); }
.rec-card.medium { border-left:3px solid var(--accent-warm); }
.rec-card.low { border-left:3px solid var(--accent-cyan); }
.rec-icon { font-size:22px; line-height:var(--leading-none); }
.rec-body { flex:1; min-width:0; }
.rec-title { font-size:var(--text-sm); font-weight:var(--weight-semibold); color:var(--color-text); margin-bottom:2px; }
.rec-text { font-size:var(--text-xs); color:var(--color-text-2); line-height:1.4; }
.rec-action { font-size:var(--text-xs); color:var(--accent); font-weight:var(--weight-medium); white-space:nowrap; }

.judge-section {
  padding:0 var(--space-8) var(--space-6);
  max-width:75rem;
  margin:0 auto;
}
.judge-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap:var(--space-3);
}
.judge-card {
  padding:var(--space-5);
  border-radius:var(--radius-md);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1.5px solid var(--glass-border);
  cursor: pointer;
  transition: var(--transition-slow);
  display: flex;
  flex-direction: column;
  gap:0.625rem;
  position: relative;
  overflow: hidden;
}
.judge-card:hover {
  border-color: rgba(var(--accent-rgb), 0.25);
  transform: translateY(-3px);
  box-shadow: var(--shadow-card-hover), var(--glow-primary);
}
.judge-tag {
  position: absolute;
  top:0.625rem;
  right:0.625rem;
  font-size:0.625rem;
  font-weight: var(--weight-bold);
  padding:0.1875rem 0.625rem;
  border-radius:var(--radius-full);
  background: linear-gradient(135deg, var(--accent), var(--accent-warm));
  color: var(--color-text-on-accent);
  letter-spacing:0.0187rem;
}
.judge-icon {
  width:2.75rem;
  height:2.75rem;
  border-radius:var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
}
.judge-icon svg { width:1.5rem; height:1.5rem; }
.judge-title { font-size:var(--text-lg); font-weight: var(--weight-bold); color: var(--text-primary); }
.judge-desc { font-size:var(--text-xs); color: var(--text-secondary); line-height:1.5; }

/*  评审推荐卡片 */
.bonus-section {
  padding:var(--space-4) var(--space-8);
  max-width:75rem;
  margin:0 auto;
}

.bonus-label {
  font-size:var(--text-xs);
  color: var(--text-muted);
  font-weight: var(--weight-semibold);
  margin-bottom:var(--space-3);
  letter-spacing:0.0312rem;
}

.bonus-row {
  display: flex;
  gap:var(--space-3);
}

.bonus-card {
  display: flex;
  align-items: center;
  gap:0.625rem;
  padding:var(--space-3) var(--space-4);
  border-radius:var(--radius-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  cursor: pointer;
  transition: var(--transition);
  flex: 1;
}

.bonus-card:hover {
  border-color: var(--color-glass-border);
  transform: translateY(-1px);
}

.bonus-icon {
  width:2rem;
  height:2rem;
  border-radius:var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
}

.bonus-icon svg { width:1rem; height:1rem; }

.bonus-title {
  font-size:var(--text-base);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  flex: 1;
}

.bonus-card svg:last-child { opacity: 0.5; }
.bonus-card:hover svg:last-child { opacity: 1; }

/* ── Data ── */
.data-section {
  padding:var(--space-6) var(--space-8);
  max-width:75rem;
  margin:0 auto;
}

.data-label {
  font-size:var(--text-xs);
  color: var(--text-muted);
  font-weight: var(--weight-semibold);
  margin-bottom:var(--space-3);
  letter-spacing:0.0312rem;
}

.data-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap:var(--space-3);
}

.data-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius:var(--radius-md);
  padding:var(--space-4);
  text-align: center;
  transition: var(--transition);
}

.data-card:hover {
  border-color: var(--color-glass-border);
}

.data-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom:var(--space-2);
  color: var(--accent-primary);
}

.data-icon svg { width:1.25rem; height:1.25rem; }

.data-value {
  font-size:var(--text-3xl);
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing:-0.0312rem;
}

.data-label-text {
  font-size:var(--text-xs);
  color: var(--text-muted);
  margin-top:var(--space-1);
}

/* ── Mastery rings ── */
.data-card.mastery-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap:var(--space-2);
}
.data-caption {
  font-size:var(--text-xs);
  color: var(--text-muted);
  font-weight: var(--weight-medium);
}
.mastery-section {
  padding:0 var(--space-8) var(--space-6);
  max-width:75rem;
  margin:0 auto;
}
.mastery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap:var(--space-3);
}
.mastery-tile {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius:var(--radius-md);
  padding:var(--space-5) var(--space-4);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap:var(--space-2);
  transition: var(--transition);
}
.mastery-tile:hover {
  border-color: var(--color-glass-border);
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
}
.mastery-name { font-size:var(--text-sm); font-weight: var(--weight-semibold); color: var(--text-primary); }
.mastery-sub { font-size:var(--text-xs); color: var(--text-muted); font-variant-numeric: tabular-nums; }
.sm-data_structures .mastery-name { color: var(--subject-ds); }
.sm-computer_network .mastery-name { color: var(--subject-cn); }
.sm-computer_organization .mastery-name { color: var(--subject-co); }
.sm-operating_system .mastery-name { color: var(--subject-os); }

/* ── Recent ── */
.recent-section {
  padding:var(--space-4) var(--space-8) var(--space-8);
  max-width:75rem;
  margin:0 auto;
}

.recent-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap:var(--space-4);
}

.recent-col {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius:var(--radius-md);
  padding:var(--space-4);
}

.recent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom:var(--space-3);
  font-size:var(--text-md);
  font-weight: var(--weight-bold);
  color: var(--text-primary);
}

.recent-link {
  font-size:var(--text-xs);
  color: var(--text-muted);
  cursor: pointer;
  font-weight: var(--weight-medium);
}

.recent-link:hover { color: var(--accent-primary); }

.recent-session, .recommend-card {
  display: flex;
  align-items: center;
  gap:var(--space-3);
  padding:0.625rem;
  border-radius:var(--radius-sm);
  cursor: pointer;
  transition: var(--transition);
}

.recent-session:hover, .recommend-card:hover { background: var(--bg-card-hover); }

.session-subject-tag {
  font-size:var(--text-2xs);
  padding:0.1875rem 0.5625rem;
  border-radius:var(--radius-full);
  font-weight: var(--weight-semibold);
  flex-shrink: 0;
}

.session-subject-tag.subject-0 { background: rgba(var(--subject-ds-rgb), 0.12); color: var(--subject-ds); }
.session-subject-tag.subject-1 { background: rgba(var(--subject-cn-rgb), 0.12); color: var(--subject-cn); }
.session-subject-tag.subject-2 { background: rgba(var(--subject-co-rgb), 0.12); color: var(--subject-co); }
.session-subject-tag.subject-3 { background: rgba(var(--subject-os-rgb), 0.12); color: var(--subject-os); }

.session-info { flex: 1; min-width:0; }
.session-title { font-size:var(--text-base); font-weight: var(--weight-medium); color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.session-meta { font-size:var(--text-xs); color: var(--text-muted); margin-top:0.125rem; }
.session-score { font-size:var(--text-md); font-weight: var(--weight-bold); flex-shrink: 0; }

.recommend-icon { width:2.25rem; height:2.25rem; border-radius:var(--radius-sm); display: flex; align-items: center; justify-content: center; font-size:var(--text-lg); flex-shrink: 0; }
.recommend-info { flex: 1; min-width:0; }
.recommend-title { font-size:var(--text-base); font-weight: var(--weight-medium); color: var(--text-primary); }
.recommend-desc { font-size:var(--text-xs); color: var(--text-muted); margin-top:0.125rem; }
.recommend-time { font-size:var(--text-xs); color: var(--text-muted); flex-shrink: 0; }

/* ── Agent 状态网格（融合自仪表盘 HTML）── */
.agent-status-section {
  padding:0 var(--space-8) var(--space-6);
  max-width:75rem;
  margin:0 auto;
}
.agent-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap:0.625rem;
}
.agent-card {
  display: flex;
  align-items: center;
  gap:0.625rem;
  padding:var(--space-3) 0.875rem;
  border-radius: var(--radius-md);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  transition: var(--transition);
}
.agent-card:hover {
  border-color: var(--color-border-focus);
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
}
.agent-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  flex-shrink: 0;
  animation: agent-pulse 2s ease-in-out infinite;
}
@keyframes agent-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
.agent-info { flex: 1; min-width: 0; }
.agent-name { font-size: var(--text-sm); font-weight: var(--weight-bold); }
.agent-role { font-size: var(--text-2xs); color: var(--text-muted); margin-top: 0.0625rem; }
.agent-status-tag { font-size: var(--text-2xs); font-weight: var(--weight-semibold); flex-shrink: 0; }
.agent-duty { font-size: var(--text-2xs); color: var(--color-text-2); margin-top: 0.1875rem; line-height: 1.4; }

/* ── 知识点热力图（融合自仪表盘 HTML · 紫系色阶）── */
.heatmap-section {
  padding:0 var(--space-8) var(--space-6);
  max-width:75rem;
  margin:0 auto;
}
.heatmap-container {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding:var(--space-4);
  display: flex;
  flex-direction: column;
  gap:var(--space-2);
}
.heatmap-row {
  display: flex;
  align-items: center;
  gap:0.625rem;
}
.heatmap-subj-label {
  font-size: var(--text-xs);
  font-weight: var(--weight-bold);
  width: 5rem;
  flex-shrink: 0;
  text-align: right;
}
.heatmap-cells {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: var(--space-1);
  flex: 1;
}
.heatmap-cell {
  height: 2rem;
  border-radius: 0.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
  cursor: default;
}
.heatmap-cell:hover {
  transform: scale(1.15);
  z-index: 2;
  box-shadow: 0 0 8px rgba(var(--accent-rgb),0.30);
}
.heatmap-cell-text {
  font-size: 0.625rem;
  font-weight: var(--weight-semibold);
}
.heatmap-legend {
  display: flex;
  align-items: center;
  gap:0.375rem;
  margin-top:0.625rem;
  flex-wrap: wrap;
}
.legend-label { font-size: var(--text-2xs); color: var(--text-muted); margin-right: var(--space-1); }
.legend-item {
  font-size: 0.625rem;
  font-weight: var(--weight-semibold);
  padding: 0.125rem var(--space-2);
  border-radius: 0.25rem;
  color: var(--color-text-invert);
}
.legend-empty {
  background: var(--chart-grid);
  color: var(--color-text-2);
  border: 1px solid var(--color-border);
}

/* ── 预警干预面板（融合自仪表盘 HTML）── */
.alert-section {
  padding:0 var(--space-8) var(--space-6);
  max-width:75rem;
  margin:0 auto;
}
.alert-list {
  display: flex;
  flex-direction: column;
  gap:var(--space-2);
}
.alert-item {
  display: flex;
  align-items: center;
  gap:var(--space-3);
  padding:var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: var(--transition);
}
.alert-item:hover {
  border-color: var(--color-border-focus);
  transform: translateX(4px);
  box-shadow: var(--shadow-card-hover);
}
.alert-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-danger { background: var(--state-danger); box-shadow: 0 0 6px var(--state-danger); }
.dot-weak { background: var(--state-weak); box-shadow: 0 0 6px var(--state-weak); }
.alert-body { flex: 1; min-width: 0; }
.alert-topic { font-size: var(--text-sm); font-weight: var(--weight-semibold); color: var(--text-primary); }
.alert-action { font-size: var(--text-xs); color: var(--text-secondary); margin-top: 0.125rem; }
.alert-arrow { color: var(--text-muted); flex-shrink: 0; }
.alert-item:hover .alert-arrow { color: var(--accent-primary); }

/* ── 示意角标 ── */
.tag-demo {
  display: inline-block;
  font-size: 0.625rem;
  font-weight: var(--weight-semibold);
  padding: 0.125rem var(--space-2);
  border-radius: var(--radius-full);
  background: var(--tag-demo-bg);
  color: var(--tag-demo-color);
  margin-left: var(--space-2);
  vertical-align: middle;
}

/* ── Responsive ── */
@media (max-width: 1024px) {
  .portals-grid { grid-template-columns: repeat(2, 1fr); }
  .data-grid { grid-template-columns: repeat(2, 1fr); }
  .recent-grid { grid-template-columns: 1fr; }
  .agent-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 768px) {
  .hero-section { padding:var(--space-10) var(--space-5) var(--space-8); }
  .hero-title { font-size:1.75rem; }
  .hero-tagline { font-size:var(--text-base); }
  .hero-stats-row { gap:var(--space-4); }
  .hero-stat-value { font-size:1.375rem; }
  .portals-section { padding:0 var(--space-5) var(--space-5); }
  .portals-grid { grid-template-columns: 1fr; }
  .portal-card { padding:var(--space-5) var(--space-4); }
  .bonus-section { padding:var(--space-3) var(--space-5); }
  .bonus-row { flex-direction: column; }
  .data-section { padding:var(--space-4) var(--space-5); }
  .data-grid { grid-template-columns: repeat(2, 1fr); }
  .recent-section { padding:var(--space-3) var(--space-5) var(--space-5); }
}

@media (max-width: 480px) {
  .hero-section { padding:var(--space-8) var(--space-4) var(--space-6); }
  .hero-title { font-size:var(--text-3xl); }
  .hero-stats-row { flex-wrap: wrap; gap:var(--space-3); }
  .hero-stat-divider { display: none; }
  .data-grid { grid-template-columns: 1fr 1fr; }
  .agent-grid { grid-template-columns: 1fr; }
  .heatmap-cells { grid-template-columns: repeat(4, 1fr); }
  .heatmap-subj-label { width: 3.5rem; font-size: var(--text-2xs); }
}
</style>
