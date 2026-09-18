<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { icons } from '@/components/icons'

// ── Benchmark 数据：唯一来源是后端 /api/benchmark/results（真产物）──
//
// 【2026-09-15 修正】此处原为四组硬编码常量，注释却写
// "来自 scripts/benchmark.py --demo 的真实输出" —— 自相矛盾：
// scripts/benchmark.py 的 --demo 是**合成数据**模式。
// 现改为消费 py-server/experiments/results/benchmark_YYYY-MM-DD.json 真产物：
//   · experiment1：28 条真实查询，FrugalRAG vs 全量检索
//   · experiment2：30 题 × 3 次，NeuralMixer vs 加权投票
// 无真数据时不填充任何 fallback，一律渲染空态。
import { useBenchmark } from '@/composables/useBenchmark'

const { loading, error, provenance, rows, questions, summary, load } = useBenchmark()

/** 图表消费的逐查询数据（真数据；为空时图表渲染空态） */
const chartRows = computed(() => rows.value)

/** 数值格式化：null（无数据）一律渲染 "—"，不用 0 冒充 */
function pct(v: number | null, digits = 1): string {
  return v === null ? '—' : (v * 100).toFixed(digits)
}
/** 带符号的百分点增量 */
function ppDelta(v: number | null, digits = 1): string {
  if (v === null) return '—'
  const s = (v * 100).toFixed(digits)
  return v > 0 ? `+${s}` : s
}
function ms(v: number | null, digits = 1): string {
  return v === null ? '—' : v.toFixed(digits)
}
function fixed(v: number | null, digits = 2): string {
  return v === null ? '—' : v.toFixed(digits)
}

// ── 召回率对比柱状图（SVG）──
const recallChartRef = ref<SVGSVGElement | null>(null)
const chartWidth = ref(680)
const chartHeight = 320

function updateChartWidth() {
  if (recallChartRef.value) {
    const w = recallChartRef.value.parentElement?.clientWidth ?? 680
    chartWidth.value = Math.min(Math.max(w, 320), 720)
  }
}

// 柱状图布局参数
const chartPadding = { top: 30, right: 20, bottom: 70, left: 50 }
const innerWidth = computed(() => chartWidth.value - chartPadding.left - chartPadding.right)
const innerHeight = chartHeight - chartPadding.top - chartPadding.bottom
const groupCount = computed(() => Math.max(chartRows.value.length, 1))
const groupWidth = computed(() => innerWidth.value / groupCount.value)
const barWidth = computed(() => Math.min(groupWidth.value * 0.32, 22))
const barGap = 4

const yMax = 1.0
const yTicks = [0, 0.2, 0.4, 0.6, 0.8, 1.0]

function yToPx(val: number): number {
  return chartPadding.top + innerHeight * (1 - val / yMax)
}

function barX(index: number, isFrugal: boolean): number {
  const groupStart = chartPadding.left + index * groupWidth.value + groupWidth.value / 2
  const offset = isFrugal ? -(barWidth.value / 2 + barGap / 2) : (barWidth.value / 2 + barGap / 2)
  return groupStart + offset - barWidth.value / 2
}

function barY(val: number): number {
  return yToPx(val)
}

function barHeight(val: number): number {
  return innerHeight * (val / yMax)
}

// ── 矛盾检测对比图（SVG 水平条形图）──
const contradictionBarHeight = 44
const contradictionBarGap = 16

// ── 动画进度 ──
const animProgress = ref(0)
let animFrame: number | null = null

function startAnimation() {
  animProgress.value = 0
  const start = performance.now()
  const duration = 1200
  function tick(now: number) {
    const elapsed = now - start
    const t = Math.min(elapsed / duration, 1)
    // easeOutCubic
    animProgress.value = 1 - Math.pow(1 - t, 3)
    if (t < 1) {
      animFrame = requestAnimationFrame(tick)
    }
  }
  animFrame = requestAnimationFrame(tick)
}

let resizeHandler: (() => void) | null = null
onMounted(() => {
  updateChartWidth()
  resizeHandler = () => updateChartWidth()
  window.addEventListener('resize', resizeHandler)
  void load().then(() => nextTick(() => startAnimation()))
})
onUnmounted(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  if (animFrame) cancelAnimationFrame(animFrame)
})

watch(chartWidth, () => { /* trigger re-render via computed */ })
</script>

<template>
  <div class="page-section benchmark-page">
    <!-- 标题 -->
    <div class="section-title">
      <span v-html="icons.barChart" class="section-title-icon"></span>
      创新量化基准
    </div>
    <div class="section-desc">
      FrugalRAG 检索引擎与 GOMARL 共识机制的量化对比实验 — 数据直读自后端真产物，缺失即留空
    </div>

    <!-- 数据溯源（provenance）：每个数字都可追溯到文件与时间戳 -->
    <div v-if="provenance" class="provenance-bar glass-card">
      <span class="prov-badge">真产物</span>
      <span class="prov-item"><b>来源</b><code>{{ provenance.source_file }}</code></span>
      <span class="prov-item"><b>产出时间</b>{{ provenance.file_mtime }}</span>
      <span class="prov-item" v-if="provenance.n_queries"><b>样本</b>{{ provenance.n_queries }} 查询 · {{ provenance.n_questions }} 题 × {{ provenance.n_trials_per_question }} 次</span>
      <span class="prov-item" v-if="provenance.random_seed !== null"><b>随机种子</b>{{ provenance.random_seed }}</span>
      <span class="prov-item" v-if="provenance.env?.python"><b>环境</b>Python {{ provenance.env.python }} · torch {{ provenance.env.torch ?? '—' }}</span>
    </div>
    <div v-else-if="loading" class="prov-skeleton">正在加载真实基准数据…</div>

    <!-- 接口异常 / 无真产物：渲染空态，绝不回退到示例数据 -->
    <div v-if="error" class="no-data glass-card">
      <div class="no-data-title">暂无真实基准数据</div>
      <div class="no-data-desc">{{ error }}</div>
      <div class="no-data-desc">真产物路径：<code>py-server/experiments/results/benchmark_*.json</code>。本页不会用合成数据填充。</div>
      <button class="no-data-btn" @click="load()">重新加载</button>
    </div>

    <template v-if="!error">
    <!-- 核心指标卡片 -->
    <div class="metric-cards">
      <div class="metric-card glass-card metric-recall">
        <div class="metric-icon-wrap"><span v-html="icons.chartUp" class="metric-icon"></span></div>
        <div class="metric-value">{{ ppDelta(summary?.recallDelta ?? null) }}<span class="metric-unit">pp</span></div>
        <div class="metric-label">Top-5 召回率提升</div>
        <div class="metric-sub">FrugalRAG {{ pct(summary?.frugal.mean_recall_5 ?? null) }}% vs 全量 {{ pct(summary?.full.mean_recall_5 ?? null) }}%</div>
      </div>
      <div class="metric-card glass-card metric-precision">
        <div class="metric-icon-wrap"><span v-html="icons.shield" class="metric-icon"></span></div>
        <div class="metric-value">{{ ppDelta(summary?.precisionDelta ?? null) }}<span class="metric-unit">pp</span></div>
        <div class="metric-label">Top-5 精确率提升</div>
        <div class="metric-sub">MRR {{ fixed(summary?.frugal.mean_mrr ?? null) }} vs {{ fixed(summary?.full.mean_mrr ?? null) }}</div>
      </div>
      <div class="metric-card glass-card metric-accuracy">
        <div class="metric-icon-wrap"><span v-html="icons.target" class="metric-icon"></span></div>
        <div class="metric-value">{{ ppDelta(summary?.accuracyDelta ?? null) }}<span class="metric-unit">pp</span></div>
        <div class="metric-label">共识准确率提升</div>
        <div class="metric-sub">NeuralMixer {{ pct(summary?.neuralAccuracy ?? null) }}% vs 加权投票 {{ pct(summary?.votingAccuracy ?? null) }}%</div>
      </div>
    </div>

    <!-- 实验1：FrugalRAG vs 全量检索 召回率对比 -->
    <div class="chart-section glass-card">
      <div class="chart-header">
        <div class="chart-title">
          <span v-html="icons.chart" class="card-title-icon"></span>
          实验1 · FrugalRAG vs 全量检索 — Top-5 召回率对比
        </div>
        <div class="chart-legend">
          <span class="legend-item"><span class="legend-dot legend-frugal"></span>FrugalRAG</span>
          <span class="legend-item"><span class="legend-dot legend-full"></span>全量检索</span>
        </div>
      </div>
      <div class="chart-container" ref="recallChartRef">
        <svg :width="chartWidth" :height="chartHeight" :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="recall-chart">
          <defs>
            <linearGradient id="frugalGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#7c6af2" stop-opacity="0.9"/>
              <stop offset="100%" stop-color="#6b5cdb" stop-opacity="0.6"/>
            </linearGradient>
            <linearGradient id="fullGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#5b8bd8" stop-opacity="0.7"/>
              <stop offset="100%" stop-color="#3b82f6" stop-opacity="0.4"/>
            </linearGradient>
            <filter id="barGlow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="2" result="blur"/>
              <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
          </defs>

          <!-- Y 轴网格线 + 刻度 -->
          <g class="y-axis">
            <line
              v-for="tick in yTicks"
              :key="'grid-' + tick"
              :x1="chartPadding.left"
              :y1="yToPx(tick)"
              :x2="chartWidth - chartPadding.right"
              :y2="yToPx(tick)"
              stroke="rgba(255,255,255,0.05)"
              stroke-width="1"
            />
            <text
              v-for="tick in yTicks"
              :key="'label-' + tick"
              :x="chartPadding.left - 8"
              :y="yToPx(tick) + 4"
              text-anchor="end"
              fill="rgba(148,163,184,0.6)"
              font-size="10"
            >{{ (tick * 100).toFixed(0) }}%</text>
          </g>

          <!-- 柱状图（28 条真实查询；无数据时 chartRows 为空 → 不渲染柱体） -->
          <g class="bars">
            <template v-for="(item, i) in chartRows" :key="'bar-' + item.id + '-' + i">
              <!-- FrugalRAG 柱 -->
              <rect
                :x="barX(i, true)"
                :y="barY(item.frugalRecall * animProgress)"
                :width="barWidth"
                :height="barHeight(item.frugalRecall * animProgress)"
                fill="url(#frugalGrad)"
                rx="3"
                filter="url(#barGlow)"
                class="bar-frugal"
              >
                <title>{{ item.query }}（{{ item.course }}）· FrugalRAG recall@5={{ (item.frugalRecall * 100).toFixed(1) }}% · {{ item.frugalLatency.toFixed(1) }}ms</title>
              </rect>
              <!-- 全量检索柱 -->
              <rect
                :x="barX(i, false)"
                :y="barY(item.fullRecall * animProgress)"
                :width="barWidth"
                :height="barHeight(item.fullRecall * animProgress)"
                fill="url(#fullGrad)"
                rx="3"
                class="bar-full"
              >
                <title>{{ item.query }}（{{ item.course }}）· 全量检索 recall@5={{ (item.fullRecall * 100).toFixed(1) }}% · {{ item.fullLatency.toFixed(1) }}ms</title>
              </rect>
              <!-- X 轴标签：28 组密集，显示序号，完整查询见悬浮提示 -->
              <text
                :x="chartPadding.left + i * groupWidth + groupWidth / 2"
                :y="chartHeight - chartPadding.bottom + 16"
                text-anchor="middle"
                fill="rgba(148,163,184,0.7)"
                font-size="9"
                class="x-label"
              >{{ i + 1 }}</text>
            </template>
          </g>
          <text
            v-if="!chartRows.length"
            :x="chartWidth / 2"
            :y="chartHeight / 2"
            text-anchor="middle"
            fill="rgba(148,163,184,0.6)"
            font-size="12"
          >无真实查询级数据</text>

          <!-- X 轴线 -->
          <line
            :x1="chartPadding.left"
            :y1="chartHeight - chartPadding.bottom"
            :x2="chartWidth - chartPadding.right"
            :y2="chartHeight - chartPadding.bottom"
            stroke="rgba(255,255,255,0.1)"
            stroke-width="1"
          />
        </svg>
      </div>
      <!-- 实验1 数据摘要（均为真产物汇总值；null → "—"） -->
      <div class="chart-summary">
        <div class="summary-item">
          <span class="summary-label">平均召回率@5</span>
          <span class="summary-val frugal-val">{{ pct(summary?.frugal.mean_recall_5 ?? null) }}%</span>
          <span class="summary-divider">vs</span>
          <span class="summary-val full-val">{{ pct(summary?.full.mean_recall_5 ?? null) }}%</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">平均延迟</span>
          <span class="summary-val">{{ ms(summary?.frugal.mean_latency_ms ?? null) }}ms</span>
          <span class="summary-divider">vs</span>
          <span class="summary-val">{{ ms(summary?.full.mean_latency_ms ?? null) }}ms</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">平均召回块数</span>
          <span class="summary-val">{{ fixed(summary?.frugal.mean_chunks ?? null) }}</span>
          <span class="summary-divider">vs</span>
          <span class="summary-val">{{ fixed(summary?.full.mean_chunks ?? null) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Token 变化</span>
          <span class="summary-val" :class="(summary?.tokenReductionPct ?? 0) >= 0 ? 'good-val' : 'warn-val'">{{ ppDelta(summary?.tokenReductionPct ?? null) }}%</span>
          <span class="summary-note">负号表示 FrugalRAG 反而多耗 token</span>
        </div>
      </div>
      <div class="honest-note">
        <b>如实说明：</b>本组真实数据显示 FrugalRAG 以显著更高的延迟（约
        {{ ms(summary?.frugal.mean_latency_ms ?? null, 0) }}ms vs {{ ms(summary?.full.mean_latency_ms ?? null, 0) }}ms）
        换取召回率 {{ ppDelta(summary?.recallDelta ?? null) }}pp 的提升，且 token 消耗并未下降（{{ ppDelta(summary?.tokenReductionPct ?? null) }}%）。
        该结果是本机 CPU 环境下的实测值，不代表生产环境表现。
      </div>
    </div>

    <!-- 实验2：NeuralMixer vs 加权投票 准确率对比 -->
    <div class="chart-section glass-card">
      <div class="chart-header">
        <div class="chart-title">
          <span v-html="icons.shield" class="card-title-icon"></span>
          实验2 · NeuralMixer vs 加权投票 — 共识准确率对比
        </div>
        <div class="chart-legend">
          <span class="legend-item"><span class="legend-dot legend-consensus"></span>NeuralMixer</span>
          <span class="legend-item"><span class="legend-dot legend-voting"></span>加权投票</span>
        </div>
      </div>
      <div class="method-change-note">
        注：原页面展示的"矛盾检出数"在真产物中不存在（来自 --demo 合成数据），已移除，改为真产物中确实存在的准确率与一致性指标。
      </div>

      <!-- 准确率对比（数值全部来自 /api/benchmark/results 真产物，随最新产物自动更新） -->
      <div class="contradiction-compare">
        <div class="contra-row">
          <div class="contra-label">
            <span class="contra-dot consensus-dot"></span>
            NeuralMixer
          </div>
          <div class="contra-bar-wrap">
            <div class="contra-bar consensus-bar" :style="{ width: ((summary?.neuralAccuracy ?? 0) * 100 * animProgress) + '%' }">
              <span class="contra-bar-text">{{ pct(summary?.neuralAccuracy ?? null) }}%</span>
            </div>
          </div>
          <div class="contra-count consensus-count">{{ pct(summary?.neuralAccuracy ?? null) }}%</div>
        </div>
        <div class="contra-row">
          <div class="contra-label">
            <span class="contra-dot voting-dot"></span>
            加权投票
          </div>
          <div class="contra-bar-wrap">
            <div class="contra-bar voting-bar" :style="{ width: ((summary?.votingAccuracy ?? 0) * 100 * animProgress) + '%' }">
              <span class="contra-bar-text">{{ pct(summary?.votingAccuracy ?? null) }}%</span>
            </div>
          </div>
          <div class="contra-count voting-count">{{ pct(summary?.votingAccuracy ?? null) }}%</div>
        </div>
      </div>

      <!-- 与标准答案的一致性（Cohen's κ）+ 延迟开销 -->
      <div class="consensus-detail">
        <div class="detail-stat">
          <div class="detail-label">准确率优势</div>
          <div class="detail-val advantage-val">{{ ppDelta(summary?.accuracyDelta ?? null) }}pp</div>
          <div class="detail-note">{{ summary?.nQuestions ?? '—' }} 题 × {{ summary?.nTrials ?? '—' }} 次观测</div>
        </div>
        <div class="detail-stat">
          <div class="detail-label">κ（vs 标准答案）</div>
          <div class="detail-val">{{ fixed(summary?.kappaNeuralVsTruth ?? null) }}</div>
          <div class="detail-note">NeuralMixer 与标准答案一致性</div>
        </div>
        <div class="detail-stat">
          <div class="detail-label">κ（vs 标准答案）</div>
          <div class="detail-val blind-pass">{{ fixed(summary?.kappaVotingVsTruth ?? null) }}</div>
          <div class="detail-note">加权投票与标准答案一致性</div>
        </div>
      </div>

      <!-- 逐题答对情况点阵（30 题 × 3 次观测；实心=本次答对，空心=答错） -->
      <div class="round-chart">
        <div class="round-chart-title">逐题答对情况（{{ questions.length }} 题 × 3 次观测）</div>
        <svg :width="chartWidth" :height="132" :viewBox="`0 0 ${chartWidth} 132`" class="round-svg" v-if="questions.length">
          <!-- NeuralMixer -->
          <g v-for="(q, i) in questions" :key="'nn-' + q.id">
            <circle
              v-for="n in 3"
              :key="'nn-dot-' + q.id + '-' + n"
              :cx="chartPadding.left + 18 + i * (innerWidth - 36) / Math.max(questions.length - 1, 1)"
              :cy="26 + (n - 1) * 12"
              r="4"
              :fill="n <= q.neuralCorrect ? '#7c6af2' : 'transparent'"
              :stroke="n <= q.neuralCorrect ? 'none' : 'rgba(148,163,184,0.45)'"
              stroke-width="1"
              :opacity="animProgress"
              class="consensus-dot-svg"
            >
              <title>{{ q.id }} {{ q.stem }} · NeuralMixer {{ q.neuralCorrect }}/{{ q.nTrials }} 次答对</title>
            </circle>
          </g>
          <!-- 加权投票 -->
          <g v-for="(q, i) in questions" :key="'vv-' + q.id">
            <circle
              v-for="n in 3"
              :key="'vv-dot-' + q.id + '-' + n"
              :cx="chartPadding.left + 18 + i * (innerWidth - 36) / Math.max(questions.length - 1, 1)"
              :cy="76 + (n - 1) * 12"
              r="4"
              :fill="n <= q.votingCorrect ? '#5b8bd8' : 'transparent'"
              :stroke="n <= q.votingCorrect ? 'none' : 'rgba(148,163,184,0.45)'"
              stroke-width="1"
              :opacity="animProgress"
            >
              <title>{{ q.id }} {{ q.stem }} · 加权投票 {{ q.votingCorrect }}/{{ q.nTrials }} 次答对</title>
            </circle>
          </g>
          <text :x="chartPadding.left" y="18" font-size="10" font-weight="600" fill="rgba(226,232,240,0.85)">NeuralMixer</text>
          <text :x="chartPadding.left" y="120" font-size="10" fill="rgba(148,163,184,0.7)">加权投票</text>
        </svg>
        <div v-else class="round-empty">无逐题明细数据</div>
      </div>
    </div>

    <!-- 方法论说明 -->
    <div class="methodology glass-card">
      <div class="methodology-title"><span v-html="icons.sparkle" class="card-title-icon"></span> 实验方法</div>
      <div class="methodology-grid">
        <div class="method-item">
          <div class="method-label">实验1 · 检索引擎对比</div>
          <div class="method-desc">{{ summary?.nQueries ?? '—' }} 条 408 真题查询（top_k=5），对比 FrugalRAG（BM25+向量融合+阈值过滤+重排）与全量向量检索的 Top-5 召回率与精确率</div>
        </div>
        <div class="method-item">
          <div class="method-label">实验2 · 共识机制对比</div>
          <div class="method-desc">{{ summary?.nQuestions ?? '—' }} 道选择题 × {{ summary?.nTrials ?? '—' }} 次独立观测，对比 NeuralMixer（注意力加权）与加权投票的答题准确率，并以 Cohen's κ 度量其与标准答案的一致性</div>
        </div>
      </div>
      <div class="methodology-footer">
        数据来源：<code>{{ provenance?.source_file ?? 'py-server/experiments/results/benchmark_*.json' }}</code>
        （产出时间 {{ provenance?.file_mtime ?? '—' }}，随机种子 {{ provenance?.random_seed ?? '—' }}）。
        本页数值全部由后端 <code>GET /api/benchmark/results</code> 直读该产物渲染，<b>无任何合成或示例兜底</b>。
      </div>
    </div>
    </template>
  </div>
</template>

<style scoped>
.section-title-icon { display: inline-flex; vertical-align: middle; margin-right: 0.375rem; }
.section-title-icon svg { width: 1.25rem; height: 1.25rem; }
.card-title-icon { display: inline-flex; vertical-align: middle; margin-right: 0.375rem; }
.card-title-icon svg { width: 1.125rem; height: 1.125rem; }

.benchmark-page { display: flex; flex-direction: column; gap: var(--space-5); }

/* ── 数据溯源条（provenance）── */
.provenance-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2) var(--space-4);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-2xs); color: var(--text-muted);
  border: 1px solid var(--accent-primary-20);
}
.prov-badge {
  padding: 2px var(--space-2); border-radius: 999px;
  background: rgba(var(--success-rgb), 0.15); color: var(--color-success);
  font-weight: var(--weight-bold); font-size: var(--text-2xs);
}
.prov-item b { color: var(--text-secondary); font-weight: var(--weight-semibold); margin-right: var(--space-1); }
.prov-item code { font-size: var(--text-2xs); color: var(--text-secondary); }
.prov-skeleton { font-size: var(--text-xs); color: var(--text-muted); padding: var(--space-3); }

/* ── 无真数据空态 ── */
.no-data {
  padding: var(--space-8) var(--space-5); text-align: center;
  border: 1px dashed var(--color-border-strong);
}
.no-data-title { font-size: var(--text-base); font-weight: var(--weight-bold); color: var(--text-primary, var(--text-secondary)); margin-bottom: var(--space-2); }
.no-data-desc { font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--space-2); }
.no-data-desc code { font-size: var(--text-2xs); }
.no-data-btn {
  margin-top: var(--space-2); padding: 6px var(--space-4); border-radius: var(--radius-md);
  background: var(--accent-primary-10); color: var(--accent-primary);
  border: 1px solid var(--accent-primary-20); cursor: pointer; font-size: var(--text-xs);
}

/* ── 如实说明 / 口径变更说明 ── */
.honest-note, .method-change-note {
  margin-top: var(--space-3); padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md); font-size: var(--text-xs); line-height: var(--leading-relaxed);
  background: rgba(var(--warning-rgb), 0.08);
  border-left: 3px solid var(--color-warning);
  color: var(--text-secondary);
}
.honest-note b, .method-change-note b { color: var(--color-warning); }
.summary-val.good-val { color: var(--color-success); }
.round-empty { padding: var(--space-5); text-align: center; font-size: var(--text-xs); color: var(--text-muted); }

/* ── 核心指标卡片 ── */
.metric-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-4); }
.metric-card {
  padding: var(--space-6) var(--space-5);
  text-align: center;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--accent-primary-20);
}
.metric-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 2px;
  background: var(--gradient-primary);
  opacity: 0.6;
}
.metric-recall::before { background: linear-gradient(90deg, var(--accent-primary), var(--flow-control)); }
.metric-precision::before { background: linear-gradient(90deg, var(--subject-co), var(--color-success)); }
.metric-accuracy::before { background: linear-gradient(90deg, var(--color-warning), var(--accent-primary)); }
.metric-unit { font-size: var(--text-lg); font-weight: var(--weight-bold); margin-left: 2px; -webkit-text-fill-color: var(--text-muted); }

.metric-icon-wrap {
  width: 40px; height: 40px;
  margin: 0 auto var(--space-2);
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius-md);
  background: var(--accent-primary-10);
}
.metric-icon svg { width: 1.25rem; height: 1.25rem; color: var(--accent-primary); }
.metric-recall .metric-icon { color: var(--accent-primary); }
.metric-precision .metric-icon { color: var(--color-success); }
.metric-accuracy .metric-icon { color: var(--color-warning); }

.metric-value {
  font-size: 2rem; font-weight: 800;
  background: var(--gradient-text);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: var(--leading-tight);
}
.metric-vs { font-size: var(--text-lg); font-weight: var(--weight-semibold); opacity: 0.5; -webkit-text-fill-color: var(--text-muted); }
.metric-label { font-size: var(--text-sm); font-weight: var(--weight-semibold); color: var(--text-secondary); margin-top: var(--space-1); }
.metric-sub { font-size: var(--text-2xs); color: var(--text-muted); margin-top: 0.375rem; }

/* ── 图表区域 ── */
.chart-section { padding: var(--space-5); }
.chart-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-4); flex-wrap: wrap; gap: var(--space-2); }
.chart-title { font-size: var(--text-md); font-weight: var(--weight-semibold); color: var(--text-primary); display: flex; align-items: center; }
.chart-legend { display: flex; gap: var(--space-4); }
.legend-item { display: flex; align-items: center; gap: 0.375rem; font-size: var(--text-xs); color: var(--text-secondary); }
.legend-dot { width: 10px; height: 10px; border-radius: 3px; }
.legend-frugal { background: linear-gradient(180deg, var(--color-accent), var(--color-accent-active)); }
.legend-full { background: linear-gradient(180deg, var(--color-info), var(--subject-cn)); opacity: 0.7; }
.legend-consensus { background: var(--color-accent); }
.legend-voting { background: var(--color-info); opacity: 0.5; }

.chart-container { width: 100%; overflow-x: auto; }
.recall-chart { display: block; margin: 0 auto; }
/* SVG 文本令牌化：避免浅色主题下出现浅蓝/白底白字 */
.bar-label { fill: var(--accent-primary); }
.consensus-gate-label { fill: var(--accent-primary); }
.bar-frugal { transition: opacity 0.2s; }
.bar-full { transition: opacity 0.2s; }
.bar-frugal:hover { opacity: 0.85; }
.bar-full:hover { opacity: 0.85; }

/* ── 图表摘要 ── */
.chart-summary { display: flex; gap: var(--space-6); margin-top: var(--space-4); flex-wrap: wrap; padding-top: 0.875rem; border-top: 1px solid var(--color-border); }
.summary-item { display: flex; align-items: baseline; gap: 0.375rem; }
.summary-label { font-size: var(--text-xs); color: var(--text-muted); }
.summary-val { font-size: var(--text-base); font-weight: var(--weight-bold); color: var(--text-primary); }
.frugal-val { color: var(--accent-primary); }
.full-val { color: var(--color-info); }
.warn-val { color: var(--accent-warm); }
.summary-divider { font-size: var(--text-2xs); color: var(--text-muted); padding: 0 0.125rem; }
.summary-note { font-size: var(--text-2xs); color: var(--text-muted); margin-left: var(--space-1); }

/* ── 矛盾检测对比 ── */
.contradiction-compare { display: flex; flex-direction: column; gap: var(--space-4); margin-bottom: var(--space-5); }
.contra-row { display: flex; align-items: center; gap: var(--space-3); }
.contra-label { width: 80px; font-size: var(--text-sm); font-weight: var(--weight-semibold); color: var(--text-secondary); display: flex; align-items: center; gap: 0.375rem; flex-shrink: 0; }
.contra-dot { width: 10px; height: 10px; border-radius: 50%; }
.consensus-dot { background: var(--color-accent); box-shadow: 0 0 8px rgba(var(--accent-rgb),0.4); }
.voting-dot { background: var(--color-info); opacity: 0.5; }
.contra-bar-wrap { flex: 1; height: 36px; background: rgba(255,255,255,0.03); border-radius: var(--radius-sm); overflow: hidden; position: relative; }
.contra-bar { height: 100%; border-radius: var(--radius-sm); display: flex; align-items: center; padding: 0 var(--space-3); transition: width 0.1s linear; min-width: 60px; }
.consensus-bar { background: linear-gradient(90deg, rgba(var(--accent-rgb),0.8), rgba(var(--accent-rgb),0.5)); box-shadow: 0 0 12px rgba(var(--accent-rgb),0.2); }
.voting-bar { background: linear-gradient(90deg, rgba(var(--info-rgb),0.4), rgba(var(--info-rgb),0.2)); }
.contra-bar-text { font-size: var(--text-xs); font-weight: var(--weight-semibold); color: var(--text-inverse); white-space: nowrap; }
.contra-bar-text-zero { font-size: var(--text-xs); color: var(--text-muted); }
.contra-count { font-size: var(--text-3xl); font-weight: 800; width: 48px; text-align: right; }
.consensus-count { color: var(--accent-primary); }
.voting-count { color: var(--text-muted); }

/* ── 共识详情 ── */
.consensus-detail { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-3); margin-bottom: var(--space-5); }
.detail-stat { padding: 0.875rem; background: rgba(255,255,255,0.02); border-radius: var(--radius-sm); border: 1px solid rgba(255,255,255,0.04); }
.detail-label { font-size: var(--text-2xs); color: var(--text-muted); margin-bottom: var(--space-1); }
.detail-val { font-size: var(--text-2xl); font-weight: 800; }
.low-consistency { color: var(--accent-warm); }
.blind-pass { color: var(--text-muted); }
.advantage-val { color: var(--color-success); }
.detail-note { font-size: 0.625rem; color: var(--text-muted); margin-top: var(--space-1); }

/* ── 逐轮散点图 ── */
.round-chart { margin-top: var(--space-2); }
.round-chart-title { font-size: var(--text-xs); font-weight: var(--weight-semibold); color: var(--text-secondary); margin-bottom: var(--space-2); }
.round-svg { display: block; width: 100%; max-width: 680px; }
.consensus-dot-svg { filter: drop-shadow(0 0 3px rgba(var(--accent-rgb),0.4)); }

/* ── 方法论 ── */
.methodology { padding: var(--space-5); }
.methodology-title { font-size: var(--text-md); font-weight: var(--weight-semibold); color: var(--text-primary); margin-bottom: 0.875rem; display: flex; align-items: center; }
.methodology-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-4); margin-bottom: 0.875rem; }
.method-item { padding: var(--space-3); background: rgba(255,255,255,0.02); border-radius: var(--radius-sm); border-left: 3px solid var(--accent-primary); }
.method-label { font-size: var(--text-xs); font-weight: var(--weight-bold); color: var(--accent-primary); margin-bottom: var(--space-1); }
.method-desc { font-size: var(--text-xs); line-height: 1.5; color: var(--text-secondary); }
.methodology-footer { font-size: var(--text-2xs); color: var(--text-muted); padding-top: 0.625rem; border-top: 1px solid rgba(255,255,255,0.04); }
.methodology-footer code { background: rgba(var(--accent-rgb),0.1); padding: 0.125rem 0.375rem; border-radius: 4px; font-size: var(--text-2xs); color: var(--accent-primary); }

/* ── 响应式 ── */
@media (max-width: 640px) {
  .metric-cards { grid-template-columns: 1fr; }
  .consensus-detail { grid-template-columns: 1fr; }
  .methodology-grid { grid-template-columns: 1fr; }
  .chart-summary { flex-direction: column; gap: var(--space-2); }
  .contra-label { width: 64px; font-size: var(--text-xs); }
}
</style>
