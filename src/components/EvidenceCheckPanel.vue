<script setup lang="ts">
// ============================================================
// 证据校验可视化面板（INC-02 · 玻璃态发光）
// 复用 DESIGN_TOKENS 的 --color-glass / --glow-primary / 学科色 / 状态色，
// 不引入新视觉语言。消费后端 evidence_check 节点推送的 EvidenceReport。
// ============================================================
import { ref, computed } from 'vue'
import { icons } from '@/components/icons'
import EmptyState from '@/components/EmptyState.vue'
import { api } from '@/utils/api'
import {
  TYPE_LABEL,
  SEVERITY_COLOR,
  SEVERITY_LABEL,
  DISPOSITION_LABEL,
  DISPOSITION_COLOR,
  AGENT_LABEL,
  type EvidenceReport,
  type ConflictDTO,
  type CorrectionDTO,
} from '@/utils/evidence'

const props = defineProps<{
  report: EvidenceReport | null
}>()

// 现场演示（多角色/答辩）：构造矛盾输入 → /api/engine/conflict-check → 展示检测过程
const demoLoading = ref(false)
const demoError = ref('')
const demoReport = ref<EvidenceReport | null>(null)

// 预置演示案例：匹配后端预定义矛盾对（408 高频，确保检出冲突）
const DEMO_CASES = [
  {
    name: 'TCP 握手次数矛盾',
    course: 'computer_network',
    agentResults: [
      { agent_name: 'teacher', content: 'TCP 通过三次握手建立可靠连接（SYN → SYN+ACK → ACK）。' },
      { agent_name: 'quizmaster', content: 'TCP 通过四次握手建立连接（SYN → ACK → SYN+ACK → ACK）。' },
    ],
  },
  {
    name: 'TCP 挥手次数矛盾',
    course: 'computer_network',
    agentResults: [
      { agent_name: 'teacher', content: 'TCP 四次挥手释放连接（FIN → ACK → FIN → ACK）。' },
      { agent_name: 'quizmaster', content: 'TCP 三次挥手断开连接（FIN → ACK → FIN）。' },
    ],
  },
]

const activeDemo = computed(() => demoReport.value || props.report)

function normalizeDemoResult(raw: any): EvidenceReport | null {
  // 将 conflict-check 响应统一为 EvidenceReport 结构
  const conflicts = Array.isArray(raw?.conflicts) ? raw.conflicts : []
  return {
    status: conflicts.length ? 'flagged' : 'ok',
    overall_consistency: raw?.overall_consistency ?? 1,
    consistency_score: Math.round((raw?.overall_consistency ?? 1) * 100),
    confidence_score: raw?.confidence ?? 1,
    total_conflicts: conflicts.length,
    resolved: conflicts.filter((c: any) => c.disposition === 'adopt').length,
    unresolved: conflicts.filter((c: any) => c.disposition !== 'adopt').length,
    conflicts: conflicts.map((c: any, i: number) => ({
      id: `demo-${i}`,
      type: c.type || 'factual',
      agent_a: c.agent_a || c.agents?.[0] || 'teacher',
      agent_b: c.agent_b || c.agents?.[1] || 'quizmaster',
      description: c.description || c.issue || '检测到矛盾内容',
      severity: c.severity || 'medium',
      evidence: c.evidence || [],
      resolution: c.resolution || '',
      confidence: c.confidence ?? 0.9,
      disposition: c.disposition || 'human_review',
    })),
    citations: raw?.citations || [],
    corrections: raw?.corrections || [],
    grounding_score: raw?.grounding_score ?? null,
    grounding_flagged: !!raw?.grounding_flagged,
    checked_agents: raw?.checked_agents || ['teacher', 'quizmaster'],
    course: raw?.course || 'computer_network',
    elapsed_ms: raw?.elapsed_ms ?? 0,
  }
}

async function runDemo(idx: number) {
  const demo = DEMO_CASES[idx]
  if (!demo) return
  demoLoading.value = true
  demoError.value = ''
  try {
    const res = await api.post('/engine/conflict-check', {
      agent_results: demo.agentResults,
      course: demo.course,
    })
    demoReport.value = normalizeDemoResult((res as any)?.result || res || {})
  } catch (e: any) {
    demoError.value = e?.message || '演示失败，请检查后端服务'
  } finally {
    demoLoading.value = false
  }
}

function clearDemo() {
  demoReport.value = null
  demoError.value = ''
}

// 详情抽屉
const drawerOpen = ref(false)
const activeConflict = ref<ConflictDTO | null>(null)
// 修正 diff 展开切换
const showCorrections = ref(true)

function openDrawer(c: ConflictDTO) {
  activeConflict.value = c
  drawerOpen.value = true
}

function closeDrawer() {
  drawerOpen.value = false
}

// 防幻觉置信度仪表盘角度（0-100 → 0-180deg 半圆）
const gaugeAngle = computed(() => {
  const score = props.report?.confidence_score ?? 1
  return Math.round(Math.max(0, Math.min(1, score)) * 180)
})
const gaugeColor = computed(() => {
  const score = props.report?.confidence_score ?? 1
  if (score >= 0.8) return 'var(--accent-success)'
  if (score >= 0.5) return 'var(--accent-warm)'
  return 'var(--accent-danger)'
})
const confidencePercent = computed(() => Math.round((props.report?.confidence_score ?? 1) * 100))

const hasCorrections = computed(() => (props.report?.corrections || []).length > 0)
const hasCitations = computed(() => (props.report?.citations || []).length > 0)

const statusInfo = computed(() => {
  const r = props.report
  if (!r) return { text: '暂无', color: 'var(--color-text-2)', glow: 'none' }
  if (r.status === 'error' || r.status === 'degraded') {
    return { text: '校验暂不可用', color: 'var(--accent-warm)', glow: 'var(--glow-primary)' }
  }
  if ((r.total_conflicts ?? 0) === 0) {
    return { text: '一致性通过', color: 'var(--accent-success)', glow: 'var(--glow-success)' }
  }
  // 有高危事实冲突 → 危险红；否则警示橙
  const hasHigh = (r.conflicts ?? []).some((c) => c.severity === 'high')
  return {
    text: hasHigh ? '存在高危冲突' : '存在冲突',
    color: hasHigh ? 'var(--accent-danger)' : 'var(--accent-warm)',
    glow: hasHigh ? '0 0 20px var(--accent-danger-20)' : 'var(--glow-primary)',
  }
})

function agentName(a: string) {
  return AGENT_LABEL[a] ?? a
}
</script>

<template>
  <!-- 现场演示区（幻觉防控答辩演示：构造矛盾输入 → 检测 → 展示） -->
  <div class="ev-demo-bar">
    <span class="ev-demo-title">🧪 现场演示（构造矛盾输入）</span>
    <button v-for="(d, i) in DEMO_CASES" :key="i" class="ev-demo-btn" :disabled="demoLoading" @click="runDemo(i)">
      {{ demoLoading ? '检测中...' : d.name }}
    </button>
    <button v-if="demoReport" class="ev-demo-btn ghost" :disabled="demoLoading" @click="clearDemo">清空演示</button>
    <span v-if="demoError" class="ev-demo-error">{{ demoError }}</span>
  </div>

  <div v-if="activeDemo" class="evidence-panel">
    <!-- 头部状态徽标 -->
    <div class="ev-header" :style="{ boxShadow: statusInfo.glow }">
      <div class="ev-status-dot" :style="{ background: statusInfo.color }"></div>
      <div class="ev-title"><span class="ev-inline-icon" v-html="icons.microscope"></span> 证据校验报告</div>
      <div class="ev-status-badge" :style="{ color: statusInfo.color, borderColor: statusInfo.color }">
        {{ statusInfo.text }}
      </div>
      <div class="ev-score">
        <span class="ev-score-num" :style="{ color: statusInfo.color }">{{ activeDemo.consistency_score }}</span>
        <span class="ev-score-unit">/100 一致性</span>
      </div>
    </div>

    <!-- 概要统计 -->
    <div class="ev-stats">
      <div class="ev-stat">
        <div class="ev-stat-num">{{ activeDemo.total_conflicts }}</div>
        <div class="ev-stat-label">检出冲突</div>
      </div>
      <div class="ev-stat" style="color: var(--accent-success)">
        <div class="ev-stat-num">{{ activeDemo.resolved }}</div>
        <div class="ev-stat-label">已消解</div>
      </div>
      <div class="ev-stat" style="color: var(--accent-warm)">
        <div class="ev-stat-num">{{ activeDemo.unresolved }}</div>
        <div class="ev-stat-label">待处理</div>
      </div>
      <div class="ev-stat">
        <div class="ev-stat-num">{{ (activeDemo.checked_agents || []).length }}</div>
        <div class="ev-stat-label">已检 Agent</div>
      </div>
    </div>

    <!-- 防幻觉置信度仪表盘（半圆 SVG） -->
    <div class="ev-gauge-section">
      <div class="ev-gauge-label"><span class="ev-inline-icon" v-html="icons.shield"></span> 防幻觉置信度</div>
      <div class="ev-gauge-wrap">
        <svg class="ev-gauge" viewBox="0 0 120 70" width="120" height="70">
          <!-- 背景弧 -->
          <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke-width="8" stroke-linecap="round"
            :style="{ stroke: 'var(--color-glass-border)' }"/>
          <!-- 数值弧（旋转角度由 gaugeAngle 控制） -->
          <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke-width="8" stroke-linecap="round"
            :stroke-dasharray="157" :stroke-dashoffset="157 - (157 * gaugeAngle / 180)"
            :style="{ stroke: gaugeColor, transition: 'stroke-dashoffset 0.8s ease' }"/>
        </svg>
        <div class="ev-gauge-num" :style="{ color: gaugeColor }">{{ confidencePercent }}<span class="ev-gauge-pct">%</span></div>
      </div>
      <div class="ev-gauge-hint" v-if="activeDemo.grounding_flagged">
        <span class="ev-inline-icon-sm" v-html="icons.warning"></span> 知识支撑度 {{ activeDemo.grounding_score }}，检出疑似幻觉
      </div>
      <div class="ev-gauge-hint" v-else-if="activeDemo.grounding_score !== null && activeDemo.grounding_score !== undefined">
        知识支撑度 {{ activeDemo.grounding_score }}，内容有据可循
      </div>
    </div>

    <!-- 防幻觉可演示：冲突修正 diff（修正前→修正后高亮） -->
    <div v-if="hasCorrections" class="ev-corrections-section">
      <div class="ev-section-head" role="button" tabindex="0" :aria-expanded="showCorrections" @click="showCorrections = !showCorrections" @keydown.enter="showCorrections = !showCorrections" @keydown.space.prevent="showCorrections = !showCorrections">
        <span class="ev-section-icon" v-html="icons.wrench"></span>
        <span class="ev-section-title-text">冲突修正回写（系统已自动校错）</span>
        <span class="ev-toggle">{{ showCorrections ? '▾' : '▸' }}</span>
        <span class="ev-correction-count">{{ (activeDemo.corrections || []).length }} 处</span>
      </div>
      <transition name="collapse">
        <div v-show="showCorrections" class="ev-corrections-list">
          <div v-for="(cor, i) in (activeDemo.corrections || [])" :key="i" class="ev-correction-card">
            <div class="ev-correction-desc">{{ cor.description }}</div>
            <div class="ev-diff">
              <div class="ev-diff-before">
                <div class="ev-diff-label">修正前</div>
                <div class="ev-diff-text">{{ cor.before }}</div>
              </div>
              <div class="ev-diff-arrow">→</div>
              <div class="ev-diff-after">
                <div class="ev-diff-label">修正后 <span class="ev-inline-icon-sm" v-html="icons.check"></span></div>
                <div class="ev-diff-text">{{ cor.after }}</div>
              </div>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- 防幻觉可演示：引用章节（知识库来源溯源） -->
    <div v-if="hasCitations" class="ev-citations-section">
      <div class="ev-section-head">
        <span class="ev-section-icon" v-html="icons.attach"></span>
        <span class="ev-section-title-text">引用章节（知识库溯源）</span>
        <span class="ev-correction-count">{{ (activeDemo.citations || []).length }} 条</span>
      </div>
      <div class="ev-citations-list">
        <div v-for="(cit, i) in (activeDemo.citations || [])" :key="i" class="ev-citation">
          <div class="ev-citation-text">{{ cit.text }}</div>
          <div class="ev-citation-meta">
            <span class="ev-citation-source"><span class="ev-inline-icon-sm" v-html="icons.book"></span> {{ cit.source || '知识库' }}</span>
            <span class="ev-citation-score" :style="{ color: cit.score >= 0.5 ? 'var(--accent-success)' : 'var(--accent-warm)' }">
              相关度 {{ (cit.score ?? 0).toFixed(2) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 冲突卡片列表 -->
    <div v-if="(activeDemo.conflicts || []).length === 0" class="ev-empty">
      未检出 Agent 间知识冲突，资源一致性良好 <span class="ev-inline-icon-sm" v-html="icons.check"></span>
    </div>

    <div v-else class="ev-card-list">
      <div
        v-for="c in activeDemo.conflicts"
        :key="c.id"
        class="ev-card"
        @click="openDrawer(c)"
      >
        <!-- 类型 pill -->
        <span class="ev-pill" :style="{ background: 'color-mix(in srgb, ' + (SEVERITY_COLOR[c.severity] || 'var(--accent-primary)') + ' 16%, transparent)', color: SEVERITY_COLOR[c.severity] || 'var(--accent-primary)' }">
          {{ TYPE_LABEL[c.type] || c.type }}
        </span>

        <!-- 涉及 Agent 对 -->
        <div class="ev-agents">
          {{ agentName(c.agent_a) }} <span class="ev-vs">vs</span> {{ agentName(c.agent_b) }}
        </div>

        <!-- 严重度 + 证据数 -->
        <div class="ev-meta">
          <span class="ev-sev" :style="{ color: SEVERITY_COLOR[c.severity] || 'var(--accent-primary)' }">
            ● {{ SEVERITY_LABEL[c.severity] || c.severity }}
          </span>
          <span class="ev-evcount" style="color: var(--accent-cyan)">
            <span class="ev-inline-icon-sm" v-html="icons.attach"></span> {{ (c.evidence || []).length }} 证据
          </span>
          <span class="ev-disp" :style="{ color: DISPOSITION_COLOR[c.disposition] || 'var(--accent-warm)' }">
            {{ DISPOSITION_LABEL[c.disposition] || c.disposition }}
          </span>
        </div>

        <!-- 冲突描述 -->
        <div class="ev-desc">{{ c.description }}</div>
      </div>
    </div>

    <!-- 详情抽屉（右滑） -->
    <transition name="drawer">
      <div v-if="drawerOpen" class="ev-drawer-mask" @click.self="closeDrawer">
        <aside class="ev-drawer" v-if="activeConflict">
          <div class="ev-drawer-head">
            <span class="ev-pill" :style="{ background: 'color-mix(in srgb, ' + (SEVERITY_COLOR[activeConflict.severity] || 'var(--accent-primary)') + ' 16%, transparent)', color: SEVERITY_COLOR[activeConflict.severity] || 'var(--accent-primary)' }">
              {{ TYPE_LABEL[activeConflict.type] || activeConflict.type }}
            </span>
            <span class="ev-drawer-title">{{ agentName(activeConflict.agent_a) }} vs {{ agentName(activeConflict.agent_b) }}</span>
            <button class="ev-close" @click="closeDrawer">✕</button>
          </div>

          <div class="ev-drawer-desc">{{ activeConflict.description }}</div>

          <!-- 证据原文 -->
          <div class="ev-section-title"><span class="ev-inline-icon-sm" v-html="icons.attach"></span> 证据来源（FrugalRAG 检索）</div>
          <div v-if="(activeConflict.evidence || []).length === 0" class="ev-empty-sm">无附证据</div>
          <div v-for="(e, i) in (activeConflict.evidence || [])" :key="i" class="ev-evidence">
            <div class="ev-evidence-text">{{ e.text }}</div>
            <div class="ev-evidence-meta">
              <span class="ev-sim">相似度 {{ (e.score ?? 0).toFixed(2) }}</span>
              <span class="ev-src">{{ e.source || '教材库' }}</span>
            </div>
          </div>

          <!-- 消解结论 -->
          <div class="ev-section-title"><span class="ev-inline-icon-sm" v-html="icons.scale"></span> 消解结论</div>
          <div class="ev-resolution" :style="{ borderColor: DISPOSITION_COLOR[activeConflict.disposition] || 'var(--accent-warm)' }">
            <span class="ev-disp-badge" :style="{ background: DISPOSITION_COLOR[activeConflict.disposition] || 'var(--accent-warm)' }">
              {{ DISPOSITION_LABEL[activeConflict.disposition] || activeConflict.disposition }}
            </span>
            <span class="ev-confidence">置信度 {{ (activeConflict.confidence ?? 0).toFixed(2) }}</span>
            <div class="ev-resolution-text">{{ activeConflict.resolution || '（无）' }}</div>
          </div>
        </aside>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.evidence-panel {
  display: flex;
  flex-direction: column;
  gap:1rem;
}

/* ── 头部玻璃态发光条 ── */
.ev-header {
  display: flex;
  align-items: center;
  gap:0.75rem;
  padding:0.875rem 1.125rem;
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  border-radius:var(--radius-md);
  transition: var(--transition);
}
.ev-status-dot {
  width:0.625rem;
  height:0.625rem;
  border-radius:50%;
  box-shadow: 0 0 10px currentColor;
}
.ev-title {
  font-size:0.9375rem;
  font-weight: 700;
  color: var(--color-text);
}
.ev-status-badge {
  font-size:0.75rem;
  font-weight: 600;
  padding:0.1875rem 0.75rem;
  border: 1px solid;
  border-radius:var(--radius-full);
}
.ev-score {
  margin-left:auto;
  display: flex;
  align-items: baseline;
  gap:0.25rem;
}
.ev-score-num { font-size:1.375rem; font-weight: 800; }
.ev-score-unit { font-size:0.75rem; color: var(--color-text-3); }

/* ── 概要统计 ── */
.ev-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap:0.625rem;
}
.ev-stat {
  text-align: center;
  padding:0.75rem 0.5rem;
  background: var(--color-glass);
  border: 1px solid var(--color-glass-border);
  border-radius:var(--radius-sm);
}
.ev-stat-num { font-size:1.25rem; font-weight: 800; color: var(--color-text); }
.ev-stat-label { font-size:0.6875rem; color: var(--color-text-3); margin-top:0.125rem; }

/* ── 冲突卡片 ── */
.ev-card-list {
  display: flex;
  flex-direction: column;
  gap:0.75rem;
}
.ev-card {
  padding:0.875rem 1rem;
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  border-radius:var(--radius-md);
  cursor: pointer;
  transition: var(--transition);
}
.ev-card:hover {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px var(--accent-primary-10), var(--glow-primary);
  transform: translateY(-1px);
}
.ev-pill {
  display: inline-block;
  font-size:0.6875rem;
  font-weight: 700;
  padding:0.125rem 0.625rem;
  border-radius:var(--radius-full);
}
.ev-agents {
  margin-top:0.5rem;
  font-size:0.875rem;
  font-weight: 600;
  color: var(--color-text);
}
.ev-vs { color: var(--color-text-3); font-weight: 400; font-size:0.75rem; margin:0 0.25rem; }
.ev-meta {
  display: flex;
  align-items: center;
  gap:0.875rem;
  margin-top:0.375rem;
  font-size:0.75rem;
  font-weight: 600;
}
.ev-desc {
  margin-top:0.5rem;
  font-size:0.8125rem;
  color: var(--color-text-2);
  line-height:1.5;
}

.ev-empty {
  text-align: center;
  padding:1.75rem;
  font-size:0.875rem;
  color: var(--accent-success);
  background: var(--accent-success-10);
  border-radius:var(--radius-md);
}

/* ── 抽屉 ── */
.ev-drawer-mask {
  position: fixed;
  inset:0;
  background: var(--color-overlay);
  backdrop-filter: blur(2px);
  z-index: var(--z-modal);
  display: flex;
  justify-content: flex-end;
}
.ev-drawer {
  width:min(30rem, 92vw);
  height:100%;
  overflow-y: auto;
  padding:1.5rem;
  background: var(--color-surface-2);
  border-left: 1px solid var(--color-border-glow);
  box-shadow: var(--shadow-xl);
  animation: drawer-in 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
@keyframes drawer-in {
  from { transform: translateX(100%); opacity: 0.4; }
  to { transform: translateX(0); opacity: 1; }
}
.ev-drawer-head {
  display: flex;
  align-items: center;
  gap:0.625rem;
  margin-bottom:0.875rem;
}
.ev-drawer-title { font-size:0.9375rem; font-weight: 700; color: var(--color-text); flex: 1; }
.ev-close {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-2);
  border-radius:var(--radius-sm);
  width:1.75rem; height:1.75rem;
  cursor: pointer;
  transition: var(--transition);
}
.ev-close:hover { color: var(--accent-danger); border-color: var(--accent-danger); }
.ev-drawer-desc {
  font-size:0.8125rem;
  color: var(--color-text-2);
  line-height:1.6;
  padding:0.75rem;
  background: var(--color-glass);
  border-radius:var(--radius-sm);
  margin-bottom:1rem;
}
.ev-section-title {
  font-size:0.8125rem;
  font-weight: 700;
  color: var(--color-text);
  margin:1.125rem 0 0.625rem;
}
.ev-evidence {
  padding:0.625rem 0.75rem;
  background: var(--color-glass);
  border: 1px solid var(--color-glass-border);
  border-radius:var(--radius-sm);
  margin-bottom:0.5rem;
}
.ev-evidence-text { font-size:0.8125rem; color: var(--color-text-2); line-height:1.6; }
.ev-evidence-meta {
  display: flex;
  justify-content: space-between;
  margin-top:0.375rem;
  font-size:0.6875rem;
  color: var(--color-text-3);
}
.ev-sim { color: var(--accent-cyan); font-weight: 600; }
.ev-empty-sm { font-size:0.75rem; color: var(--color-text-3); padding:0.5rem 0; }
.ev-resolution {
  padding:0.75rem;
  background: var(--color-glass);
  border-left: 3px solid;
  border-radius:var(--radius-sm);
}
.ev-disp-badge {
  display: inline-block;
  font-size:0.6875rem;
  font-weight: 700;
  color: #fff;
  padding:0.125rem 0.625rem;
  border-radius:var(--radius-full);
}
.ev-confidence { font-size:0.6875rem; color: var(--color-text-3); margin-left:0.625rem; }
.ev-resolution-text { margin-top:0.5rem; font-size:0.8125rem; color: var(--color-text-2); line-height:1.6; }

.drawer-enter-active, .drawer-leave-active { transition: opacity 0.25s ease; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }

/* ── 防幻觉置信度仪表盘 ── */
.ev-gauge-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.375rem;
  padding: 1rem;
  background: var(--color-glass);
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-md);
}
.ev-gauge-label {
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--color-text);
}
.ev-gauge-wrap {
  position: relative;
  width: 120px;
  height: 70px;
}
.ev-gauge {
  display: block;
}
.ev-gauge-num {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  font-size: 1.5rem;
  font-weight: 800;
  line-height: 1;
}
.ev-gauge-pct { font-size: 0.75rem; font-weight: 600; }
.ev-gauge-hint {
  font-size: 0.6875rem;
  color: var(--color-text-3);
  text-align: center;
}

/* ── 修正 diff 区域 ── */
.ev-corrections-section, .ev-citations-section {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
.ev-section-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;
}
.ev-section-icon { font-size: 0.875rem; }

/* ── 内联 SVG 图标（v-html 注入，需显式尺寸/配色） ── */
.ev-inline-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: middle;
  width: 1.125rem;
  height: 1.125rem;
  margin-right: 0.375rem;
  color: var(--accent-primary);
}
.ev-inline-icon svg, .ev-inline-icon-sm svg {
  width: 100%;
  height: 100%;
  flex-shrink: 0;
}
.ev-inline-icon-sm {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  vertical-align: middle;
  width: 0.9375rem;
  height: 0.9375rem;
  margin-right: 0.25rem;
  color: currentColor;
}
.ev-section-title-text {
  font-size: 0.875rem;
  font-weight: 700;
  color: var(--color-text);
  flex: 1;
}
.ev-toggle {
  font-size: 0.75rem;
  color: var(--color-text-3);
}
.ev-correction-count {
  font-size: 0.6875rem;
  font-weight: 700;
  color: var(--accent-primary);
  background: var(--accent-primary-10);
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-full);
}
.ev-corrections-list {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
.ev-correction-card {
  padding: 0.75rem;
  background: var(--color-glass);
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--accent-success);
}
.ev-correction-desc {
  font-size: 0.75rem;
  color: var(--color-text-2);
  margin-bottom: 0.5rem;
}
.ev-diff {
  display: flex;
  gap: 0.5rem;
  align-items: stretch;
}
.ev-diff-before, .ev-diff-after {
  flex: 1;
  padding: 0.5rem 0.625rem;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  line-height: 1.5;
}
.ev-diff-before {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
}
.ev-diff-after {
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
}
.ev-diff-label {
  font-size: 0.625rem;
  font-weight: 700;
  text-transform: uppercase;
  margin-bottom: 0.25rem;
}
.ev-diff-before .ev-diff-label { color: var(--accent-danger); }
.ev-diff-after .ev-diff-label { color: var(--accent-success); }
.ev-diff-text {
  color: var(--color-text-2);
  word-break: break-word;
}
.ev-diff-arrow {
  display: flex;
  align-items: center;
  font-size: 1rem;
  color: var(--accent-primary);
  font-weight: 700;
}
.collapse-enter-active, .collapse-leave-active { transition: all 0.25s ease; overflow: hidden; }
.collapse-enter-from, .collapse-leave-to { opacity: 0; max-height: 0; }
.collapse-enter-to, .collapse-leave-from { opacity: 1; max-height: 600px; }

/* ── 引用章节 ── */
.ev-citations-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.ev-citation {
  padding: 0.5rem 0.625rem;
  background: var(--color-glass);
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--accent-cyan);
}
.ev-citation-text {
  font-size: 0.75rem;
  color: var(--color-text-2);
  line-height: 1.5;
  margin-bottom: 0.25rem;
}
.ev-citation-meta {
  display: flex;
  justify-content: space-between;
  font-size: 0.625rem;
}
.ev-citation-source { color: var(--accent-cyan); font-weight: 600; }
.ev-citation-score { font-weight: 600; }

/* ── 现场演示区（幻觉防控答辩演示） ── */
.ev-demo-bar {
  display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;
  padding: 0.625rem 0.875rem; margin-bottom: 0.875rem;
  background: var(--color-glass); border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-sm); border-left: 3px solid var(--accent-amber);
}
.ev-demo-title { font-size: 0.8125rem; font-weight: 600; color: var(--color-text); margin-right: 0.25rem; }
.ev-demo-btn {
  padding: 0.375rem 0.75rem; border-radius: var(--radius-sm);
  border: 1px solid var(--color-glass-border); background: var(--color-glass);
  color: var(--accent-primary); font-size: 0.75rem; cursor: pointer; transition: var(--transition);
}
.ev-demo-btn:hover:not(:disabled) { border-color: var(--accent-primary); background: var(--accent-primary-10); }
.ev-demo-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.ev-demo-btn.ghost { color: var(--color-text-2); }
.ev-demo-error { font-size: 0.75rem; color: var(--accent-danger); }
@media (max-width: 480px) { .ev-demo-bar { flex-direction: column; align-items: flex-start; } }
</style>
