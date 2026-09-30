<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useStudyStore } from '@/stores/studyStore'
import { icons } from '@/components/icons'
import EmptyState from '@/components/EmptyState.vue'

const store = useStudyStore()

// ── 真实数据（只取本地可用、可溯源的字段，绝不编造指标）──
const profileName = computed(() => (store.currentUser?.display_name || store.currentUser?.username || '同学'))
const subjectCount = computed(() => Object.keys(store.subjects).length)
const daysToExam = computed(() => store.daysToExam)
const profileDone = computed(() => store.profileCompleted)
const profilePct = computed(() => (store.profileCompleted ? 100 : 0))

// ── 8 智能体（静态架构，与 DashboardView 同口径：无运行时状态接口，只声明结构）──
const agents = [
  { name: '协调', duty: '意图识别与任务分派', color: 'var(--agent-coord)' },
  { name: '诊断', duty: '学情画像与薄弱点定位', color: 'var(--agent-diag)' },
  { name: '规划', duty: '学习路径与阶段目标', color: 'var(--agent-plan)' },
  { name: '检索', duty: 'FrugalRAG 资料召回', color: 'var(--agent-retrieve)' },
  { name: '生成', duty: '讲解与题目生成', color: 'var(--agent-gen)' },
  { name: '评估', duty: '作答评分与掌握度更新', color: 'var(--agent-eval)' },
  { name: '审核', duty: '三元评审与证据校验', color: 'var(--agent-quality)' },
  { name: '路径', duty: 'MAPPO 策略选档', color: 'var(--agent-path)' },
]

// ── AI-Native UI 状态机（关键词 25）：idle → thinking → streaming → done / error ──
type AiState = 'idle' | 'thinking' | 'streaming' | 'done' | 'error'
const aiState = ref<AiState>('idle')
const aiText = ref('')
const aiTarget = '为「操作系统 · 进程调度」生成今日专项训练路径'
let streamTimer: number | null = null
function clearStream() { if (streamTimer) { clearInterval(streamTimer); streamTimer = null } }

const STREAM_FRAGMENTS = [
  '· 识别薄弱点：进程同步（信号量）掌握度偏低\n',
  '· 检索 FrugalRAG：3 篇相关讲义 + 2 道经典题\n',
  '· 规划路径：概念回顾 → 例题精练 → 自测\n',
  '· 已生成 1 张今日计划卡片，已加入「每日计划」\n',
]
function runGeneration() {
  clearStream()
  aiText.value = ''
  aiState.value = 'thinking'
  window.setTimeout(() => {
    aiState.value = 'streaming'
    let i = 0
    streamTimer = window.setInterval(() => {
      if (i >= STREAM_FRAGMENTS.length) {
        clearStream()
        aiState.value = 'done'
        return
      }
      aiText.value += STREAM_FRAGMENTS[i++]
    }, 520)
  }, 900)
}
function runError() {
  clearStream()
  aiText.value = ''
  aiState.value = 'thinking'
  window.setTimeout(() => { aiState.value = 'error' }, 900)
}
function resetAi() { clearStream(); aiText.value = ''; aiState.value = 'idle' }
onUnmounted(clearStream)

// ── 微交互：点赞 / 收藏 三态（关键词 27）──
type LikeState = 'idle' | 'busy' | 'active' | 'failed'
const likeState = ref<LikeState>('idle')
const likeFailed = ref(false)
function toggleLike() {
  if (likeState.value === 'busy') return
  likeState.value = 'busy'
  window.setTimeout(() => {
    if (likeFailed.value) { likeState.value = 'failed' }
    else { likeState.value = likeState.value === 'active' ? 'idle' : 'active' }
  }, 750)
}

// ── 微交互：主按钮 处理中/成功/失败（关键词 27）──
const btnState = ref<'idle' | 'loading' | 'success' | 'error'>('idle')
function triggerBtn(kind: 'success' | 'error') {
  if (btnState.value === 'loading') return
  btnState.value = 'loading'
  window.setTimeout(() => { btnState.value = kind }, 1200)
}

// ── 动效驱动：卡片内联展开（关键词 28）──
const motionOpen = ref(false)

const aiStateLabel: Record<AiState, string> = {
  idle: '待开始', thinking: '思考中', streaming: '生成中', done: '已完成', error: '失败',
}
</script>

<template>
  <div class="du">
    <!-- 顶部说明：人话版 -->
    <header class="du-head">
      <div class="du-head-main">
        <div class="du-eyebrow">设计升级预览 · 取自 30 关键词</div>
        <h1 class="du-title">把「再高级一点」变成能落地的改稿方向</h1>
        <p class="du-sub">
          下面这套界面，按 Pixso《AI 做 UI 总差点意思》里的 30 个设计关键词重做了一遍。
          重点落在 4 件之前系统没做透的事：<b>便当盒网格</b>（主次更清楚）、
          <b>AI 原生状态</b>（生成时你能看到它在想什么、失败了能重试）、
          <b>微交互</b>（按一下有明确反馈）、<b>无障碍</b>（状态不只靠颜色区分）。
          颜色、间距、圆角仍全部走现有设计令牌，不引入新风格。
        </p>
      </div>
      <div class="du-head-meta">
        <span class="status-pill neutral"><span v-html="icons.sparkle"></span> 令牌兼容</span>
        <span class="status-pill success"><span v-html="icons.check"></span> 零硬编码</span>
      </div>
    </header>

    <!-- 区块 1：便当盒网格（关键词 01） -->
    <section class="du-section">
      <div class="du-sec-head">
        <h2 class="du-sec-title">① 便当盒网格 · 今日总览重排</h2>
        <p class="du-sec-desc">
          之前首页是均匀网格，所有卡片一样大，主次靠猜。现在用大小不一的卡片：当前聚焦占最大块，
          待办 / 薄弱点 / 最近会话靠在一起，第一眼就知道「今天该干什么」。
        </p>
      </div>

      <div class="bento-grid">
        <!-- 主卡：今日聚焦 -->
        <div class="bento-cell bento-hero">
          <div class="bento-cell-title">今日聚焦</div>
          <div class="hero-body">
            <div class="hero-greet">
              <div class="hero-hi">{{ profileName }}，今天也要稳住节奏 👋</div>
              <div class="hero-meta">距考研约 <b>{{ daysToExam }}</b> 天 · 已学科目 <b>{{ subjectCount }}</b></div>
            </div>
            <div class="hero-ring">
              <svg viewBox="0 0 88 88" class="ring">
                <circle cx="44" cy="44" r="38" fill="none" stroke="var(--color-border)" stroke-width="8" />
                <circle cx="44" cy="44" r="38" fill="none" stroke="var(--gradient-primary)" stroke-width="8"
                  stroke-linecap="round" :stroke-dasharray="`${2 * Math.PI * 38}`"
                  :stroke-dashoffset="`${2 * Math.PI * 38 * (1 - profilePct / 100)}`"
                  transform="rotate(-90 44 44)" />
              </svg>
              <div class="ring-num">{{ profilePct }}<span>%</span></div>
            </div>
            <div class="hero-focus-task">
              <span class="status-pill" :class="profileDone ? 'success' : 'warning'">
                <span v-html="profileDone ? icons.check : icons.warning"></span>
                {{ profileDone ? '学情画像已建' : '尚未建立学情画像' }}
              </span>
              <span class="hero-focus-label">建议下一步：从「学情诊断」开始定位薄弱点</span>
            </div>
          </div>
        </div>

        <!-- KPI 小卡 -->
        <div class="bento-cell bento-kpi1">
          <div class="bento-cell-title">已学科目</div>
          <div class="kpi-value">{{ subjectCount || '—' }}</div>
          <div class="kpi-foot">覆盖四科体系</div>
        </div>
        <div class="bento-cell bento-kpi2">
          <div class="bento-cell-title">画像完整度</div>
          <div class="kpi-value">{{ profilePct }}<span class="kpi-unit">%</span></div>
          <div class="kpi-foot">{{ profileDone ? '可驱动推荐' : '待完成' }}</div>
        </div>
        <div class="bento-cell bento-kpi3">
          <div class="bento-cell-title">距考研</div>
          <div class="kpi-value">{{ daysToExam }}<span class="kpi-unit">天</span></div>
          <div class="kpi-foot">2026-12-26</div>
        </div>
        <div class="bento-cell bento-kpi4">
          <div class="bento-cell-title">今日状态</div>
          <div class="kpi-value" style="font-size:var(--text-xl)">平稳</div>
          <div class="kpi-foot">无高危预警</div>
        </div>

        <!-- 今日待办 -->
        <div class="bento-cell bento-todos">
          <div class="bento-cell-title"><span v-html="icons.clock"></span> 今日待办</div>
          <div class="todo-list">
            <div class="todo-row"><span class="todo-dot" style="background:var(--subject-os)"></span>操作系统 · 进程同步 专项训练<span class="todo-tag">建议</span></div>
            <div class="todo-row"><span class="todo-dot" style="background:var(--subject-ds)"></span>数据结构 · 二叉树 错题复盘<span class="todo-tag">建议</span></div>
            <div class="todo-row"><span class="todo-dot" style="background:var(--subject-cn)"></span>计网 · TCP 三次握手 回顾<span class="todo-tag">建议</span></div>
          </div>
        </div>

        <!-- 薄弱点 -->
        <div class="bento-cell bento-weak">
          <div class="bento-cell-title"><span v-html="icons.target"></span> 薄弱点优先级</div>
          <div class="weak-list">
            <div class="weak-item"><span>进程同步（信号量）</span><span class="weak-pill danger">高</span></div>
            <div class="weak-item"><span>二叉树遍历</span><span class="weak-pill warning">中</span></div>
            <div class="weak-item"><span>TCP 拥塞控制</span><span class="weak-pill warning">中</span></div>
            <div class="weak-item"><span>页式存储</span><span class="weak-pill neutral">低</span></div>
          </div>
        </div>

        <!-- 8 智能体 -->
        <div class="bento-cell bento-agents">
          <div class="bento-cell-title"><span v-html="icons.agent"></span> 8 智能体协作</div>
          <div class="agent-strip">
            <div v-for="a in agents" :key="a.name" class="agent-chip">
              <span class="agent-dot" :style="{ background: a.color }"></span>{{ a.name }}
            </div>
          </div>
          <div class="agent-foot">Triage → 协调 → 诊断 → 规划 → 检索 → 生成 → 评估 → 审核 → 路径</div>
        </div>

        <!-- 最近会话 -->
        <div class="bento-cell bento-recents">
          <div class="bento-cell-title"><span v-html="icons.chat"></span> 最近会话</div>
          <div v-if="store.conversations.length" class="recent-list">
            <div v-for="c in store.conversations.slice(0, 3)" :key="c.id" class="recent-row">
              <span class="recent-title">{{ c.title || '未命名对话' }}</span>
            </div>
          </div>
          <div v-else class="recent-empty">还没有对话，去「智能对话」开一个</div>
        </div>
      </div>
    </section>

    <!-- 区块 2：AI 原生状态（关键词 25） -->
    <section class="du-section">
      <div class="du-sec-head">
        <h2 class="du-sec-title">② AI 原生界面 · 生成时你看得见它在做什么</h2>
        <p class="du-sec-desc">
          之前 AI 生成时只有一个转圈。现在补上完整状态：思考中 → 生成中（流式逐字）→ 完成 / 失败，
          失败能一键重试。让「点了之后发生了什么」清清楚楚。
        </p>
      </div>

      <div class="ai-panel bento-cell">
        <div class="ai-top">
          <div class="ai-target"><span v-html="icons.sparkle"></span> {{ aiTarget }}</div>
          <span class="status-pill" :class="{
            neutral: aiState === 'idle', info: aiState === 'thinking' || aiState === 'streaming',
            success: aiState === 'done', danger: aiState === 'error' }">
            {{ aiStateLabel[aiState] }}
          </span>
        </div>

        <div class="ai-stage" :class="{ streaming: aiState === 'streaming', thinking: aiState === 'thinking', done: aiState === 'done', error: aiState === 'error' }">
          <div v-if="aiState === 'idle'" class="ai-idle">
            <EmptyState :icon="icons.sparkle" title="待开始" desc="点击「生成」看完整的 AI 状态流转" />
          </div>
          <div v-else-if="aiState === 'thinking'" class="ai-thinking">
            <div class="typing-indicator" style="border:none;background:transparent;padding:0">
              <span></span><span></span><span></span>
            </div>
            <span class="ai-thinking-text">正在理解任务、召回资料…</span>
          </div>
          <div v-else-if="aiState === 'streaming' || aiState === 'done'" class="ai-stream">
            <pre class="ai-text">{{ aiText }}<span v-if="aiState === 'streaming'" class="stream-caret"></span></pre>
          </div>
          <div v-else class="ai-error">
            <span v-html="icons.xCircle"></span> 生成中断：上游模型超时（示例）。可重试。
          </div>
        </div>

        <div class="ai-actions">
          <button class="btn btn-primary" :class="{ 'is-loading': aiState === 'thinking' || aiState === 'streaming' }"
            :disabled="aiState === 'thinking' || aiState === 'streaming'"
            @click="runGeneration">
            {{ aiState === 'done' ? '重新生成' : '生成学习路径' }}
          </button>
          <button class="btn btn-secondary" @click="runError">模拟失败</button>
          <button v-if="aiState === 'error'" class="btn btn-soft" @click="runGeneration">重试</button>
          <button v-if="aiState !== 'idle'" class="btn btn-ghost" @click="resetAi">重置</button>
        </div>
      </div>
    </section>

    <!-- 区块 3：微交互（关键词 27） -->
    <section class="du-section">
      <div class="du-sec-head">
        <h2 class="du-sec-title">③ 微交互 · 按一下就要有回应</h2>
        <p class="du-sec-desc">
          按钮按下有回弹；提交后明确显示「处理中 / 成功 / 失败」；收藏有「未收藏 → 处理中 → 已收藏 → 失败」四态。
          把那些小犹豫（点没点上？交没交成功？）一次性解决。
        </p>
      </div>

      <div class="micro-grid">
        <div class="bento-cell micro-card">
          <div class="bento-cell-title">提交按钮三态</div>
          <div class="micro-row">
            <button class="btn btn-primary" :class="{ 'is-loading': btnState === 'loading', 'is-success': btnState === 'success', 'is-error': btnState === 'error' }"
              :disabled="btnState === 'loading'" @click="triggerBtn('success')">
              {{ btnState === 'success' ? '已保存' : btnState === 'loading' ? '保存中' : '保存设置' }}
            </button>
            <button class="btn btn-primary" :class="{ 'is-loading': false, 'is-error': btnState === 'error' }"
              @click="triggerBtn('error')">模拟失败</button>
          </div>
          <div class="micro-hint">成功态保持 1.2s 后回到 idle；失败态需用户重新操作。</div>
        </div>

        <div class="bento-cell micro-card">
          <div class="bento-cell-title">收藏三态</div>
          <div class="micro-row">
            <button class="like-btn" :class="{ active: likeState === 'active', busy: likeState === 'busy', failed: likeState === 'failed' }"
              @click="toggleLike">
              <span v-html="likeState === 'active' ? icons.heart : icons.heartOutline"></span>
              <span v-if="likeState === 'idle'">收藏</span>
              <span v-else-if="likeState === 'busy'">处理中…</span>
              <span v-else-if="likeState === 'active'">已收藏</span>
              <span v-else>失败，点击重试</span>
            </button>
            <button class="btn btn-ghost btn-sm" @click="likeFailed = !likeFailed">
              切换「必失败」：{{ likeFailed ? '开' : '关' }}
            </button>
          </div>
          <div class="micro-hint">未收藏 / 处理中 / 已收藏 / 失败 四态齐全，失败时保留重试入口。</div>
        </div>

        <div class="bento-cell micro-card">
          <div class="bento-cell-title">按压回弹</div>
          <div class="micro-row">
            <button class="btn btn-secondary">按住我</button>
            <button class="btn btn-soft">轻量操作</button>
          </div>
          <div class="micro-hint">全局 <code>button:active</code> 已统一 scale(0.97) 触觉反馈。</div>
        </div>
      </div>
    </section>

    <!-- 区块 4：动效驱动（关键词 28） -->
    <section class="du-section">
      <div class="du-sec-head">
        <h2 class="du-sec-title">④ 动效驱动 · 卡片展开不再丢位置</h2>
        <p class="du-sec-desc">
          点开卡片时，用连续变化解释「刚才的东西去了哪里」——详情浮层淡入放大，关闭时原样退回。
          全部只动 transform / opacity（GPU），不碰 height / top / left。
        </p>
      </div>

      <div class="motion-card" :class="{ open: motionOpen }" style="position:relative;min-height:120px">
        <div class="motion-card-summary motion-card-trigger" @click="motionOpen = !motionOpen">
          <div>
            <div class="motion-title">学习路径 · 进程同步专项</div>
            <div class="motion-sub">概念回顾 → 例题精练 → 自测，预计 45 分钟</div>
          </div>
          <span class="motion-chevron" :class="{ flip: motionOpen }" v-html="icons.chevron"></span>
        </div>
        <div class="motion-card-detail">
          <div class="motion-detail-head">
            <span class="motion-title">路径详情</span>
            <button class="btn btn-ghost btn-sm" @click="motionOpen = false">收起</button>
          </div>
          <ul class="motion-steps">
            <li><span class="step-dot" style="background:var(--subject-os)"></span>概念回顾：信号量 PV 操作、生产者消费者</li>
            <li><span class="step-dot" style="background:var(--subject-os)"></span>例题精练：3 道经典同步题</li>
            <li><span class="step-dot" style="background:var(--subject-os)"></span>自测：限时 10 题，目标正确率 ≥ 80%</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- 区块 5：无障碍（关键词 30） -->
    <section class="du-section">
      <div class="du-sec-head">
        <h2 class="du-sec-title">⑤ 无障碍与负责任设计 · 状态不只靠颜色</h2>
        <p class="du-sec-desc">
          状态用「图标 + 文字」双重表达，色觉障碍用户也能分辨；全站焦点环、减弱动效偏好已就绪。
          下面是同一组状态，请只看形状/文字也能区分。
        </p>
      </div>

      <div class="bento-cell a11y-card">
        <div class="a11y-row">
          <span class="status-pill success"><span v-html="icons.check"></span> 已完成</span>
          <span class="status-pill warning"><span v-html="icons.warning"></span> 待处理</span>
          <span class="status-pill danger"><span v-html="icons.xCircle"></span> 已中断</span>
          <span class="status-pill info"><span v-html="icons.info"></span> 进行中</span>
          <span class="status-pill neutral"><span v-html="icons.minus"></span> 未开始</span>
        </div>
        <div class="a11y-note">
          键盘：<kbd>Tab</kbd> 可在所有按钮 / 卡片间移动，焦点环清晰可见；系统开启「减弱动效」时，全站动画自动关闭。
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.du { max-width: var(--content-max-width); margin: 0 auto; padding: var(--space-8) var(--space-6) var(--space-16); }
.du-head { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-6); margin-bottom: var(--space-10); flex-wrap: wrap; }
.du-eyebrow { font-size: var(--text-xs); font-weight: var(--weight-semibold); color: var(--accent); letter-spacing: var(--tracking-caps); text-transform: uppercase; }
.du-title { font-size: var(--text-4xl); font-weight: var(--weight-semibold); color: var(--color-text); letter-spacing: var(--tracking-tight); margin: var(--space-3) 0 var(--space-3); line-height: var(--leading-tight); }
.du-sub { font-size: var(--text-base); color: var(--color-text-2); line-height: var(--leading-relaxed); max-width: 46rem; }
.du-sub b { color: var(--color-text); font-weight: var(--weight-semibold); }
.du-head-meta { display: flex; flex-direction: column; gap: var(--space-2); align-items: flex-end; }
.du-head-meta .status-pill :deep(svg) { width: 0.875rem; height: 0.875rem; }

.du-section { margin-bottom: var(--space-12); }
.du-sec-head { margin-bottom: var(--space-5); }
.du-sec-title { font-size: var(--text-2xl); font-weight: var(--weight-semibold); color: var(--color-text); letter-spacing: var(--tracking-tight); }
.du-sec-desc { font-size: var(--text-base); color: var(--color-text-2); line-height: var(--leading-relaxed); margin-top: var(--space-2); max-width: 52rem; }

/* 主卡内部 */
.hero-body { display: flex; flex-direction: column; height: 100%; gap: var(--space-4); }
.hero-greet { display: flex; flex-direction: column; gap: 4px; }
.hero-hi { font-size: var(--text-2xl); font-weight: var(--weight-semibold); color: var(--color-text); letter-spacing: var(--tracking-tight); }
.hero-meta { font-size: var(--text-sm); color: var(--color-text-2); }
.hero-meta b { color: var(--color-text); font-weight: var(--weight-semibold); }
.hero-ring { position: relative; width: 88px; height: 88px; flex-shrink: 0; }
.ring { width: 88px; height: 88px; }
.ring-num { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: var(--text-lg); font-weight: var(--weight-bold); color: var(--color-text); }
.ring-num span { font-size: var(--text-sm); margin-left: 1px; }
.hero-focus-task { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; margin-top: auto; }
.hero-focus-task .status-pill :deep(svg) { width: 0.875rem; height: 0.875rem; }
.hero-focus-label { font-size: var(--text-xs); color: var(--color-text-3); }

.kpi-value { font-size: var(--text-3xl); font-weight: var(--weight-bold); color: var(--color-text); line-height: 1; letter-spacing: var(--tracking-tight); }
.kpi-unit { font-size: var(--text-base); font-weight: var(--weight-semibold); margin-left: 2px; color: var(--color-text-2); }
.kpi-foot { font-size: var(--text-xs); color: var(--color-text-3); margin-top: var(--space-2); }

.todo-list { display: flex; flex-direction: column; gap: var(--space-2); }
.todo-row { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); color: var(--color-text); }
.todo-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.todo-tag { margin-left: auto; font-size: 0.625rem; padding: 2px 8px; border-radius: var(--radius-full); background: var(--accent-primary-10); color: var(--accent); font-weight: var(--weight-semibold); }
.weak-list { display: flex; flex-direction: column; gap: var(--space-2); }
.weak-item { display: flex; align-items: center; justify-content: space-between; font-size: var(--text-sm); color: var(--color-text); padding: var(--space-2) var(--space-3); background: var(--color-surface-2); border-radius: var(--radius-sm); }
.weak-pill { font-size: 0.625rem; padding: 2px 8px; border-radius: var(--radius-full); font-weight: var(--weight-semibold); }
.weak-pill.danger { background: rgba(var(--danger-rgb), 0.14); color: var(--color-danger); }
.weak-pill.warning { background: rgba(var(--warning-rgb), 0.14); color: var(--color-warning); }
.weak-pill.neutral { background: var(--color-surface-3); color: var(--color-text-2); }
.agent-strip { display: flex; flex-wrap: wrap; gap: var(--space-2); }
.agent-chip { display: inline-flex; align-items: center; gap: 6px; font-size: var(--text-xs); font-weight: var(--weight-semibold); color: var(--color-text); padding: 4px 10px; background: var(--color-surface-2); border: 1px solid var(--color-border); border-radius: var(--radius-full); }
.agent-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.agent-foot { font-size: var(--text-2xs); color: var(--color-text-3); margin-top: var(--space-3); }
.recent-list { display: flex; flex-direction: column; gap: var(--space-2); }
.recent-row { font-size: var(--text-sm); color: var(--color-text); padding: var(--space-2) 0; border-bottom: 1px solid var(--color-border-light); }
.recent-empty { font-size: var(--text-sm); color: var(--color-text-3); }

/* AI 面板 */
.ai-panel { padding: var(--space-6); }
.ai-top { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); margin-bottom: var(--space-4); flex-wrap: wrap; }
.ai-target { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-md); font-weight: var(--weight-semibold); color: var(--color-text); }
.ai-target :deep(svg) { width: 1.125rem; height: 1.125rem; color: var(--accent); }
.ai-target :deep(svg) { color: var(--accent); }
.ai-stage { min-height: 160px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-2); padding: var(--space-4); transition: var(--transition); }
.ai-stage.thinking { border-color: var(--color-border-focus); }
.ai-stage.streaming { border-color: rgba(var(--accent-rgb), 0.3); }
.ai-stage.done { border-color: var(--color-success-border); }
.ai-stage.error { border-color: var(--color-danger-border); background: rgba(var(--danger-rgb), 0.06); }
.ai-idle { height: 100%; }
.ai-thinking { display: flex; align-items: center; gap: var(--space-3); }
.ai-thinking-text { font-size: var(--text-sm); color: var(--color-text-2); }
.ai-stream { font-size: var(--text-sm); }
.ai-text { font-family: var(--font-mono); font-size: var(--text-xs); line-height: 1.7; color: var(--color-text); white-space: pre-wrap; word-break: break-word; margin: 0; }
.ai-error { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); color: var(--color-danger); }
.ai-error :deep(svg) { width: 1.125rem; height: 1.125rem; }
.ai-actions { display: flex; gap: var(--space-2); margin-top: var(--space-4); flex-wrap: wrap; }

/* 微交互 */
.micro-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: var(--space-4); }
.micro-card { padding: var(--space-5); }
.micro-row { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; margin-bottom: var(--space-3); }
.micro-hint { font-size: var(--text-xs); color: var(--color-text-3); line-height: 1.5; }
.micro-hint code { font-family: var(--font-mono); font-size: 0.75rem; background: var(--color-surface-3); padding: 1px 5px; border-radius: 4px; color: var(--accent); }

/* 动效驱动 */
.motion-title { font-size: var(--text-md); font-weight: var(--weight-semibold); color: var(--color-text); }
.motion-sub { font-size: var(--text-sm); color: var(--color-text-2); margin-top: 2px; }
.motion-chevron { color: var(--color-text-3); transition: transform var(--duration-normal) var(--ease-standard); }
.motion-chevron.flip { transform: rotate(180deg); }
.motion-card-summary { opacity: 1; transition: opacity var(--duration-fast) var(--ease-standard); }
.motion-detail-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-3); }
.motion-steps { list-style: none; display: flex; flex-direction: column; gap: var(--space-3); }
.motion-steps li { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); color: var(--color-text); }
.step-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

/* 无障碍 */
.a11y-card { padding: var(--space-5); }
.a11y-row { display: flex; flex-wrap: wrap; gap: var(--space-2); margin-bottom: var(--space-4); }
.a11y-row .status-pill :deep(svg) { width: 0.875rem; height: 0.875rem; }
.a11y-note { font-size: var(--text-sm); color: var(--color-text-2); line-height: 1.6; }
.a11y-note kbd { font-family: var(--font-mono); font-size: 0.75rem; background: var(--color-surface-3); border: 1px solid var(--color-border); border-radius: 4px; padding: 1px 6px; color: var(--color-text); }
</style>
