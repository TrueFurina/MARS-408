<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { icons } from '@/components/icons'

// ── Benchmark 数据（来自 scripts/benchmark.py --demo 的真实输出）──
// 实验1：FrugalRAG 检索 vs 全量检索（10 组查询）
const frugalragData = ref([
  { query: 'TCP三次握手', recall: 0.977, latency: 85.6, chunks: 3 },
  { query: 'CSMA/CD协议', recall: 0.812, latency: 176.9, chunks: 3 },
  { query: 'HTTP/HTTPS区别', recall: 0.983, latency: 132.4, chunks: 3 },
  { query: '子网掩码', recall: 0.948, latency: 87.6, chunks: 3 },
  { query: '二叉树前序遍历', recall: 0.947, latency: 179.9, chunks: 4 },
  { query: '快速排序原理', recall: 0.939, latency: 148.7, chunks: 3 },
  { query: '虚拟内存', recall: 0.786, latency: 125.1, chunks: 3 },
  { query: '进程线程区别', recall: 0.979, latency: 151.3, chunks: 4 },
  { query: 'Cache缓存', recall: 0.877, latency: 174.7, chunks: 5 },
  { query: '流水线技术', recall: 0.986, latency: 169.1, chunks: 3 },
])

const fullRetrievalData = ref([
  { query: 'TCP三次握手', recall: 0.515, latency: 43.3, chunks: 5 },
  { query: 'CSMA/CD协议', recall: 0.712, latency: 69.3, chunks: 5 },
  { query: 'HTTP/HTTPS区别', recall: 0.512, latency: 62.1, chunks: 5 },
  { query: '子网掩码', recall: 0.545, latency: 65.0, chunks: 5 },
  { query: '二叉树前序遍历', recall: 0.681, latency: 69.8, chunks: 5 },
  { query: '快速排序原理', recall: 0.741, latency: 52.0, chunks: 5 },
  { query: '虚拟内存', recall: 0.739, latency: 36.9, chunks: 5 },
  { query: '进程线程区别', recall: 0.733, latency: 59.7, chunks: 5 },
  { query: 'Cache缓存', recall: 0.586, latency: 69.1, chunks: 5 },
  { query: '流水线技术', recall: 0.629, latency: 61.9, chunks: 5 },
])

// 实验2：共识门 vs 平均投票（10 轮）
const consensusGateData = ref([
  { round: 1, score: 3.927, consistency: 0.4, contradictions: 4 },
  { round: 2, score: 4.068, consistency: 0.4, contradictions: 4 },
  { round: 3, score: 3.953, consistency: 0.4, contradictions: 4 },
  { round: 4, score: 3.767, consistency: 0.4, contradictions: 4 },
  { round: 5, score: 3.899, consistency: 0.4, contradictions: 4 },
  { round: 6, score: 3.987, consistency: 0.4, contradictions: 4 },
  { round: 7, score: 3.877, consistency: 0.4, contradictions: 4 },
  { round: 8, score: 3.637, consistency: 0.4, contradictions: 4 },
  { round: 9, score: 3.518, consistency: 0.4, contradictions: 4 },
  { round: 10, score: 3.633, consistency: 0.4, contradictions: 4 },
])

const averageVotingData = ref([
  { round: 1, score: 3.861, consistency: 1.0, contradictions: 0 },
  { round: 2, score: 4.008, consistency: 1.0, contradictions: 0 },
  { round: 3, score: 3.910, consistency: 1.0, contradictions: 0 },
  { round: 4, score: 3.723, consistency: 1.0, contradictions: 0 },
  { round: 5, score: 3.837, consistency: 1.0, contradictions: 0 },
  { round: 6, score: 3.937, consistency: 1.0, contradictions: 0 },
  { round: 7, score: 3.827, consistency: 1.0, contradictions: 0 },
  { round: 8, score: 3.600, consistency: 1.0, contradictions: 0 },
  { round: 9, score: 3.471, consistency: 1.0, contradictions: 0 },
  { round: 10, score: 3.594, consistency: 1.0, contradictions: 0 },
])

// ── 汇总统计 ──
const summary = computed(() => {
  const frAvgRecall = frugalragData.value.reduce((s, d) => s + d.recall, 0) / frugalragData.value.length
  const fullAvgRecall = fullRetrievalData.value.reduce((s, d) => s + d.recall, 0) / fullRetrievalData.value.length
  const frAvgChunks = frugalragData.value.reduce((s, d) => s + d.chunks, 0) / frugalragData.value.length
  const fullAvgChunks = fullRetrievalData.value.reduce((s, d) => s + d.chunks, 0) / fullRetrievalData.value.length
  const frAvgLatency = frugalragData.value.reduce((s, d) => s + d.latency, 0) / frugalragData.value.length
  const fullAvgLatency = fullRetrievalData.value.reduce((s, d) => s + d.latency, 0) / fullRetrievalData.value.length
  const cgTotalContradictions = consensusGateData.value.reduce((s, d) => s + d.contradictions, 0)
  const avTotalContradictions = averageVotingData.value.reduce((s, d) => s + d.contradictions, 0)
  const cgAvgConsistency = consensusGateData.value.reduce((s, d) => s + d.consistency, 0) / consensusGateData.value.length
  const avAvgConsistency = averageVotingData.value.reduce((s, d) => s + d.consistency, 0) / averageVotingData.value.length

  return {
    recallImprovement: ((frAvgRecall - fullAvgRecall) * 100).toFixed(1),
    frAvgRecall: (frAvgRecall * 100).toFixed(1),
    fullAvgRecall: (fullAvgRecall * 100).toFixed(1),
    noiseReduction: ((1 - frAvgChunks / fullAvgChunks) * 100).toFixed(0),
    frAvgLatency: frAvgLatency.toFixed(0),
    fullAvgLatency: fullAvgLatency.toFixed(0),
    latencyOverhead: (frAvgLatency - fullAvgLatency).toFixed(0),
    cgContradictions: cgTotalContradictions,
    avContradictions: avTotalContradictions,
    cgConsistency: (cgAvgConsistency * 100).toFixed(0),
    avConsistency: (avAvgConsistency * 100).toFixed(0),
  }
})

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
const groupCount = frugalragData.value.length
const groupWidth = computed(() => innerWidth.value / groupCount)
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
  nextTick(() => startAnimation())
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
      FrugalRAG 检索引擎与 GOMARL 共识门机制的量化对比实验 — 创新有数据支撑
    </div>

    <!-- 核心指标卡片 -->
    <div class="metric-cards">
      <div class="metric-card glass-card metric-recall">
        <div class="metric-icon-wrap"><span v-html="icons.chartUp" class="metric-icon"></span></div>
        <div class="metric-value">+{{ summary.recallImprovement }}%</div>
        <div class="metric-label">Top-5 召回率提升</div>
        <div class="metric-sub">FrugalRAG {{ summary.frAvgRecall }}% vs 全量 {{ summary.fullAvgRecall }}%</div>
      </div>
      <div class="metric-card glass-card metric-noise">
        <div class="metric-icon-wrap"><span v-html="icons.shield" class="metric-icon"></span></div>
        <div class="metric-value">{{ summary.noiseReduction }}%</div>
        <div class="metric-label">噪声过滤率</div>
        <div class="metric-sub">阈值过滤 + BM25 精确匹配去噪</div>
      </div>
      <div class="metric-card glass-card metric-contradiction">
        <div class="metric-icon-wrap"><span v-html="icons.target" class="metric-icon"></span></div>
        <div class="metric-value">{{ summary.cgContradictions }}<span class="metric-vs"> vs 0</span></div>
        <div class="metric-label">矛盾检出数</div>
        <div class="metric-sub">共识门 vs 平均投票（10轮×4矛盾）</div>
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

          <!-- 柱状图 -->
          <g class="bars">
            <template v-for="(item, i) in frugalragData" :key="'bar-' + i">
              <!-- FrugalRAG 柱 -->
              <rect
                :x="barX(i, true)"
                :y="barY(item.recall * animProgress)"
                :width="barWidth"
                :height="barHeight(item.recall * animProgress)"
                fill="url(#frugalGrad)"
                rx="3"
                filter="url(#barGlow)"
                class="bar-frugal"
              />
              <!-- 全量检索柱 -->
              <rect
                :x="barX(i, false)"
                :y="barY(fullRetrievalData[i]!.recall * animProgress)"
                :width="barWidth"
                :height="barHeight(fullRetrievalData[i]!.recall * animProgress)"
                fill="url(#fullGrad)"
                rx="3"
                class="bar-full"
              />
              <!-- FrugalRAG 数值标签 -->
              <text
                v-if="animProgress > 0.8"
                :x="barX(i, true) + barWidth / 2"
                :y="barY(item.recall) - 4"
                text-anchor="middle"
                font-size="9"
                font-weight="600"
                class="bar-label"
              >{{ (item.recall * 100).toFixed(0) }}</text>
              <!-- X 轴标签 -->
              <text
                :x="chartPadding.left + i * groupWidth + groupWidth / 2"
                :y="chartHeight - chartPadding.bottom + 16"
                text-anchor="middle"
                fill="rgba(148,163,184,0.7)"
                font-size="9"
                class="x-label"
              >{{ item.query.length > 6 ? item.query.slice(0, 6) + '…' : item.query }}</text>
            </template>
          </g>

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
      <!-- 实验1 数据摘要 -->
      <div class="chart-summary">
        <div class="summary-item">
          <span class="summary-label">平均召回率</span>
          <span class="summary-val frugal-val">{{ summary.frAvgRecall }}%</span>
          <span class="summary-divider">vs</span>
          <span class="summary-val full-val">{{ summary.fullAvgRecall }}%</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">平均延迟</span>
          <span class="summary-val">{{ summary.frAvgLatency }}ms</span>
          <span class="summary-divider">vs</span>
          <span class="summary-val">{{ summary.fullAvgLatency }}ms</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">延迟开销</span>
          <span class="summary-val warn-val">+{{ summary.latencyOverhead }}ms</span>
          <span class="summary-note">换取召回率 +{{ summary.recallImprovement }}%</span>
        </div>
      </div>
    </div>

    <!-- 实验2：共识门 vs 平均投票 矛盾检测对比 -->
    <div class="chart-section glass-card">
      <div class="chart-header">
        <div class="chart-title">
          <span v-html="icons.shield" class="card-title-icon"></span>
          实验2 · 共识门 vs 平均投票 — 矛盾检测能力对比
        </div>
        <div class="chart-legend">
          <span class="legend-item"><span class="legend-dot legend-consensus"></span>共识门</span>
          <span class="legend-item"><span class="legend-dot legend-voting"></span>平均投票</span>
        </div>
      </div>

      <!-- 矛盾检出总数对比（大数字 + 水平条） -->
      <div class="contradiction-compare">
        <div class="contra-row">
          <div class="contra-label">
            <span class="contra-dot consensus-dot"></span>
            共识门
          </div>
          <div class="contra-bar-wrap">
            <div class="contra-bar consensus-bar" :style="{ width: (summary.cgContradictions / 40 * 100 * animProgress) + '%' }">
              <span class="contra-bar-text">{{ Math.round(summary.cgContradictions * animProgress) }} 个矛盾</span>
            </div>
          </div>
          <div class="contra-count consensus-count">{{ summary.cgContradictions }}</div>
        </div>
        <div class="contra-row">
          <div class="contra-label">
            <span class="contra-dot voting-dot"></span>
            平均投票
          </div>
          <div class="contra-bar-wrap">
            <div class="contra-bar voting-bar" :style="{ width: (summary.avContradictions / 40 * 100 * animProgress) + '%' }">
              <span class="contra-bar-text" v-if="summary.avContradictions > 0">{{ summary.avContradictions }} 个矛盾</span>
              <span class="contra-bar-text-zero" v-else>未检出</span>
            </div>
          </div>
          <div class="contra-count voting-count">{{ summary.avContradictions }}</div>
        </div>
      </div>

      <!-- 一致性分数 + 逐轮对比 -->
      <div class="consensus-detail">
        <div class="detail-stat">
          <div class="detail-label">共识门一致性</div>
          <div class="detail-val" :class="{ 'low-consistency': true }">{{ summary.cgConsistency }}%</div>
          <div class="detail-note">检出矛盾后主动降权</div>
        </div>
        <div class="detail-stat">
          <div class="detail-label">平均投票一致性</div>
          <div class="detail-val blind-pass">{{ summary.avConsistency }}%</div>
          <div class="detail-note">盲目通过（无检测能力）</div>
        </div>
        <div class="detail-stat">
          <div class="detail-label">检测优势</div>
          <div class="detail-val advantage-val">+{{ summary.cgContradictions }}</div>
          <div class="detail-note">拦截"四次握手"等知识性错误</div>
        </div>
      </div>

      <!-- 逐轮矛盾检测散点图（SVG） -->
      <div class="round-chart">
        <div class="round-chart-title">逐轮矛盾检出（10轮测试）</div>
        <svg :width="chartWidth" :height="120" :viewBox="`0 0 ${chartWidth} 120`" class="round-svg">
          <!-- 共识门：每轮4个矛盾 -->
          <g v-for="(item, i) in consensusGateData" :key="'cg-' + i">
            <circle
              v-for="n in item.contradictions"
              :key="'cg-dot-' + i + '-' + n"
              :cx="chartPadding.left + 20 + i * (innerWidth - 40) / 9"
              :cy="30 + (n - 1) * 14"
              r="5"
              fill="#7c6af2"
              :opacity="animProgress"
              class="consensus-dot-svg"
            />
          </g>
          <!-- 平均投票：0个矛盾 -->
          <g v-for="(item, i) in averageVotingData" :key="'av-' + i">
            <text
              :x="chartPadding.left + 20 + i * (innerWidth - 40) / 9"
              :y="95"
              text-anchor="middle"
              fill="rgba(148,163,184,0.3)"
              font-size="10"
            >—</text>
          </g>
          <!-- 标签 -->
          <text :x="chartPadding.left" y="20" class="consensus-gate-label" font-size="10" font-weight="600">共识门</text>
          <text :x="chartPadding.left" y="100" fill="rgba(148,163,184,0.4)" font-size="10">平均投票</text>
          <!-- 轮次标签 -->
          <text
            v-for="(item, i) in consensusGateData"
            :key="'round-' + i"
            :x="chartPadding.left + 20 + i * (innerWidth - 40) / 9"
            :y="115"
            text-anchor="middle"
            fill="rgba(148,163,184,0.4)"
            font-size="8"
          >R{{ i + 1 }}</text>
        </svg>
      </div>
    </div>

    <!-- 方法论说明 -->
    <div class="methodology glass-card">
      <div class="methodology-title"><span v-html="icons.sparkle" class="card-title-icon"></span> 实验方法</div>
      <div class="methodology-grid">
        <div class="method-item">
          <div class="method-label">实验1 · 检索引擎对比</div>
          <div class="method-desc">10 组 408 真题查询，对比 FrugalRAG（BM25+向量融合+阈值过滤+重排）与全量向量检索的 Top-5 关键词召回率</div>
        </div>
        <div class="method-item">
          <div class="method-label">实验2 · 共识机制对比</div>
          <div class="method-desc">10 轮多 Agent 输出（含故意矛盾），对比共识门（加权投票+矛盾检测+降权）与简单平均投票的矛盾拦截能力</div>
        </div>
      </div>
      <div class="methodology-footer">
        数据来源：scripts/benchmark.py --demo · 10 组查询 × 10 轮测试 · 真实模式可用 <code>python scripts/benchmark.py</code> 复现
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-title-icon { display: inline-flex; vertical-align: middle; margin-right: 0.375rem; }
.section-title-icon svg { width: 1.25rem; height: 1.25rem; }
.card-title-icon { display: inline-flex; vertical-align: middle; margin-right: 0.375rem; }
.card-title-icon svg { width: 1.125rem; height: 1.125rem; }

.benchmark-page { display: flex; flex-direction: column; gap: 1.25rem; }

/* ── 核心指标卡片 ── */
.metric-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
.metric-card {
  padding: 1.5rem 1.25rem;
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
.metric-noise::before { background: linear-gradient(90deg, #06b6d4, #22c55e); }
.metric-contradiction::before { background: linear-gradient(90deg, #f59e0b, #ef4444); }

.metric-icon-wrap {
  width: 40px; height: 40px;
  margin: 0 auto 0.5rem;
  display: flex; align-items: center; justify-content: center;
  border-radius: var(--radius-md);
  background: var(--accent-primary-10);
}
.metric-icon svg { width: 1.25rem; height: 1.25rem; color: var(--accent-primary); }
.metric-recall .metric-icon { color: var(--accent-primary); }
.metric-noise .metric-icon { color: #22c55e; }
.metric-contradiction .metric-icon { color: #f59e0b; }

.metric-value {
  font-size: 2rem; font-weight: 800;
  background: var(--gradient-text);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  line-height: 1.2;
}
.metric-vs { font-size: 1rem; font-weight: 600; opacity: 0.5; -webkit-text-fill-color: var(--text-muted); }
.metric-label { font-size: 0.8125rem; font-weight: 600; color: var(--text-secondary); margin-top: 0.25rem; }
.metric-sub { font-size: 0.6875rem; color: var(--text-muted); margin-top: 0.375rem; }

/* ── 图表区域 ── */
.chart-section { padding: 1.25rem; }
.chart-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem; }
.chart-title { font-size: 0.9375rem; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; }
.chart-legend { display: flex; gap: 1rem; }
.legend-item { display: flex; align-items: center; gap: 0.375rem; font-size: 0.75rem; color: var(--text-secondary); }
.legend-dot { width: 10px; height: 10px; border-radius: 3px; }
.legend-frugal { background: linear-gradient(180deg, #7c6af2, #6b5cdb); }
.legend-full { background: linear-gradient(180deg, #5b8bd8, #3b82f6); opacity: 0.7; }
.legend-consensus { background: #7c6af2; }
.legend-voting { background: #5b8bd8; opacity: 0.5; }

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
.chart-summary { display: flex; gap: 1.5rem; margin-top: 1rem; flex-wrap: wrap; padding-top: 0.875rem; border-top: 1px solid var(--color-border, rgba(255,255,255,0.06)); }
.summary-item { display: flex; align-items: baseline; gap: 0.375rem; }
.summary-label { font-size: 0.75rem; color: var(--text-muted); }
.summary-val { font-size: 0.875rem; font-weight: 700; color: var(--text-primary); }
.frugal-val { color: var(--accent-primary); }
.full-val { color: #5b8bd8; }
.warn-val { color: var(--accent-warm, #f59e0b); }
.summary-divider { font-size: 0.6875rem; color: var(--text-muted); padding: 0 0.125rem; }
.summary-note { font-size: 0.6875rem; color: var(--text-muted); margin-left: 0.25rem; }

/* ── 矛盾检测对比 ── */
.contradiction-compare { display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.25rem; }
.contra-row { display: flex; align-items: center; gap: 0.75rem; }
.contra-label { width: 80px; font-size: 0.8125rem; font-weight: 600; color: var(--text-secondary); display: flex; align-items: center; gap: 0.375rem; flex-shrink: 0; }
.contra-dot { width: 10px; height: 10px; border-radius: 50%; }
.consensus-dot { background: #7c6af2; box-shadow: 0 0 8px rgba(124,106,242,0.4); }
.voting-dot { background: #5b8bd8; opacity: 0.5; }
.contra-bar-wrap { flex: 1; height: 36px; background: rgba(255,255,255,0.03); border-radius: var(--radius-sm); overflow: hidden; position: relative; }
.contra-bar { height: 100%; border-radius: var(--radius-sm); display: flex; align-items: center; padding: 0 0.75rem; transition: width 0.1s linear; min-width: 60px; }
.consensus-bar { background: linear-gradient(90deg, rgba(124,106,242,0.8), rgba(124,106,242,0.5)); box-shadow: 0 0 12px rgba(124,106,242,0.2); }
.voting-bar { background: linear-gradient(90deg, rgba(91,139,216,0.4), rgba(91,139,216,0.2)); }
.contra-bar-text { font-size: 0.75rem; font-weight: 600; color: var(--text-inverse); white-space: nowrap; }
.contra-bar-text-zero { font-size: 0.75rem; color: var(--text-muted); }
.contra-count { font-size: 1.5rem; font-weight: 800; width: 48px; text-align: right; }
.consensus-count { color: var(--accent-primary); }
.voting-count { color: var(--text-muted); }

/* ── 共识详情 ── */
.consensus-detail { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin-bottom: 1.25rem; }
.detail-stat { padding: 0.875rem; background: rgba(255,255,255,0.02); border-radius: var(--radius-sm); border: 1px solid rgba(255,255,255,0.04); }
.detail-label { font-size: 0.6875rem; color: var(--text-muted); margin-bottom: 0.25rem; }
.detail-val { font-size: 1.25rem; font-weight: 800; }
.low-consistency { color: var(--accent-warm, #f59e0b); }
.blind-pass { color: var(--text-muted); }
.advantage-val { color: #22c55e; }
.detail-note { font-size: 0.625rem; color: var(--text-muted); margin-top: 0.25rem; }

/* ── 逐轮散点图 ── */
.round-chart { margin-top: 0.5rem; }
.round-chart-title { font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.5rem; }
.round-svg { display: block; width: 100%; max-width: 680px; }
.consensus-dot-svg { filter: drop-shadow(0 0 3px rgba(124,106,242,0.4)); }

/* ── 方法论 ── */
.methodology { padding: 1.25rem; }
.methodology-title { font-size: 0.9375rem; font-weight: 600; color: var(--text-primary); margin-bottom: 0.875rem; display: flex; align-items: center; }
.methodology-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; margin-bottom: 0.875rem; }
.method-item { padding: 0.75rem; background: rgba(255,255,255,0.02); border-radius: var(--radius-sm); border-left: 3px solid var(--accent-primary, #7c6af2); }
.method-label { font-size: 0.75rem; font-weight: 700; color: var(--accent-primary, #7c6af2); margin-bottom: 0.25rem; }
.method-desc { font-size: 0.75rem; line-height: 1.5; color: var(--text-secondary); }
.methodology-footer { font-size: 0.6875rem; color: var(--text-muted); padding-top: 0.625rem; border-top: 1px solid rgba(255,255,255,0.04); }
.methodology-footer code { background: rgba(124,106,242,0.1); padding: 0.125rem 0.375rem; border-radius: 4px; font-size: 0.6875rem; color: var(--accent-primary); }

/* ── 响应式 ── */
@media (max-width: 640px) {
  .metric-cards { grid-template-columns: 1fr; }
  .consensus-detail { grid-template-columns: 1fr; }
  .methodology-grid { grid-template-columns: 1fr; }
  .chart-summary { flex-direction: column; gap: 0.5rem; }
  .contra-label { width: 64px; font-size: 0.75rem; }
}
</style>
