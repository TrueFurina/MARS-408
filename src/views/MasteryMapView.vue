<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useStudyStore, type MasteryItem, type WeakPoint, type KnowledgePoint } from '@/stores/studyStore'
import { resolveToken } from '@/utils/themeTokens'
import { icons } from '@/components/icons'
import RingProgress from '@/components/RingProgress.vue'

const store = useStudyStore()

const masteryData = ref<MasteryItem[]>([])
const loading = ref(true)
const error = ref('')

/**
 * 四档掌握度映射（与 KnowledgeGraph 的 high/mid/low/none 语义一致）：
 *   pct === 0      → none（未学/无数据）
 *   pct >= 75      → high
 *   pct >= 50      → mid
 *   其余（< 50）   → low
 */
type MasteryTier = 'high' | 'mid' | 'low' | 'none'

function tierOf(pct: number): MasteryTier {
  if (!pct || pct <= 0) return 'none'
  if (pct >= 75) return 'high'
  if (pct >= 50) return 'mid'
  return 'low'
}

const TIER_TOKEN: Record<MasteryTier, string> = {
  high: 'var(--mastery-high)',
  mid: 'var(--mastery-mid)',
  low: 'var(--mastery-low)',
  none: 'var(--mastery-none)',
}

const TIER_LABEL: Record<MasteryTier, string> = {
  high: '扎实',
  mid: '一般',
  low: '薄弱',
  none: '未测',
}

function tierToken(pct: number): string {
  return TIER_TOKEN[tierOf(pct)]
}
function tierLabel(pct: number): string {
  return TIER_LABEL[tierOf(pct)]
}
function tierColorResolved(pct: number): string {
  // canvas 上下文无法解析 CSS 变量，需经 getComputedStyle 取实际值
  return resolveToken(TIER_TOKEN[tierOf(pct)], '#7c6af2')
}

/** 是否全为 0（无真实掌握度数据）——展示占位引导 */
const allZero = computed(() => {
  if (masteryData.value.length === 0) return false
  return masteryData.value.every((m) => !m.pct || m.pct <= 0)
})

/** 薄弱点热力等级：按错误次数映射到 --seq-1..6（连续色阶） */
function heatLevel(count: number): number {
  if (!count || count <= 0) return 1
  if (count >= 20) return 6
  if (count >= 14) return 5
  if (count >= 9) return 4
  if (count >= 5) return 3
  if (count >= 2) return 2
  return 1
}
function heatToken(count: number): string {
  return `var(--seq-${heatLevel(count)})`
}
function heatColorResolved(count: number): string {
  return resolveToken(`--seq-${heatLevel(count)}`, 'rgba(124,106,242,0.3)')
}

/** 当前选中的科目筛选（点击科目卡片可联动薄弱点列表） */
const selectedSubject = ref<string>('')
const filteredWeakPoints = computed<WeakPoint[]>(() => {
  if (!selectedSubject.value) return store.weakPoints
  return store.weakPoints.filter((w) => w.subject === selectedSubject.value)
})

const weakTotal = computed(() => store.weakPointsTotal)

// ── 知识点级（章节级）掌握度下钻 ──
const knowledgePoints = ref<KnowledgePoint[]>([])
const displayKnowledgePoints = computed<KnowledgePoint[]>(() => {
  if (!selectedSubject.value) return knowledgePoints.value
  return knowledgePoints.value.filter((k) => k.subject === selectedSubject.value)
})

// 章节英文 key → 中文展示名（仅已知 STEP_QUESTIONS 章节的静态标签映射，非编造数据）
const CHAPTER_LABELS: Record<string, string> = {
  tcp_congestion: 'TCP拥塞控制',
  tree: '树与二叉树',
  cache: '高速缓存',
  page_replacement: '页面置换',
  ip: 'IP与子网',
  hash: '哈希表',
  data: '数据与编码',
  process: '进程调度',
  sorting: '排序',
}
function chapterLabel(ch: string): string {
  return CHAPTER_LABELS[ch] || ch
}
// 知识点掌握度 pct（mastery 0-1 → 0-100；null 视为未练习）
function kpPct(kp: KnowledgePoint): number {
  return kp.mastery == null ? 0 : Math.round(kp.mastery * 100)
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [mastery] = await Promise.all([
      store.fetchMasteryData(),
      store.fetchWeakPoints(),
      store.fetchKnowledgeMastery(),
    ])
    masteryData.value = mastery ?? []
    knowledgePoints.value = store.knowledgePoints ?? []
  } catch (e: any) {
    error.value = e?.message || '加载掌握度数据失败'
  } finally {
    loading.value = false
  }
}

function selectSubject(subject: string) {
  selectedSubject.value = selectedSubject.value === subject ? '' : subject
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="page-section">
    <div class="section-title">
      <span v-html="icons.mapPin" class="section-title-icon"></span>
      掌握度地图
    </div>
    <div class="section-desc">
      科目级掌握度与薄弱点可视化 —— 一眼看清四科强弱，优先突破高频错题
    </div>

    <!-- 加载态 -->
    <div v-if="loading" class="empty-state">
      <div v-for="i in 4" :key="i" class="skeleton"
        style="width:100%;height:120px;margin-bottom:var(--space-4);"></div>
    </div>

    <!-- 错误态 -->
    <div v-else-if="error" class="empty-state">
      <div class="empty-title">
        <span v-html="icons.warning" class="inline-icon"></span> {{ error }}
      </div>
      <div class="empty-desc">完成练习后，掌握度地图会自动更新</div>
      <button class="engine-btn" style="margin-top:var(--space-3);" @click="loadData">
        <span v-html="icons.refresh" class="inline-icon"></span> 重新加载
      </button>
    </div>

    <template v-else>
      <!-- 科目掌握度 -->
      <div class="map-card glass-card">
        <div class="card-title">
          <span v-html="icons.barChart" class="card-title-icon"></span>
          科目掌握度
          <span v-if="allZero" class="map-hint">（暂无数据，完成练习后自动点亮）</span>
        </div>

        <!-- 全零占位 -->
        <div v-if="allZero" class="map-placeholder">
          <div class="placeholder-icon" v-html="icons.mapPin"></div>
          <div class="placeholder-text">还没有掌握度数据</div>
          <div class="placeholder-desc">去做几道练习题，系统会统计你四科的掌握情况</div>
        </div>

        <!-- 科目卡片网格 -->
        <div v-else class="subject-grid">
          <button
            v-for="m in masteryData"
            :key="m.subject"
            class="subject-tile"
            :class="{ active: selectedSubject === m.subject }"
            :style="{ borderColor: selectedSubject === m.subject ? tierToken(m.pct) : 'var(--color-border)' }"
            @click="selectSubject(m.subject)"
          >
            <RingProgress
              :value="m.pct"
              :size="84"
              :stroke="8"
              :label="m.label"
              :color="tierToken(m.pct)"
            />
            <!-- 掌握度进度条：scaleX 填充（遵循 SSOT 动效约束，禁止 width 过渡） -->
            <div class="tile-bar-bg">
              <div
                class="tile-bar-fill"
                :style="{ width: '100%', transform: `scaleX(${Math.max(0, Math.min(100, m.pct)) / 100})`, background: tierToken(m.pct) }"
              ></div>
            </div>
            <div class="tile-meta">
              <span class="tile-label">{{ m.label }}</span>
              <span class="tile-tier" :style="{ color: tierToken(m.pct) }">{{ tierLabel(m.pct) }}</span>
            </div>
          </button>
        </div>

        <!-- 梯度图例 -->
        <div v-if="!allZero" class="tier-legend">
          <span class="legend-item"><span class="legend-dot" :style="{ background: 'var(--mastery-high)' }"></span>扎实 (≥75%)</span>
          <span class="legend-item"><span class="legend-dot" :style="{ background: 'var(--mastery-mid)' }"></span>一般 (50–74%)</span>
          <span class="legend-item"><span class="legend-dot" :style="{ background: 'var(--mastery-low)' }"></span>薄弱 (&lt;50%)</span>
          <span class="legend-item"><span class="legend-dot" :style="{ background: 'var(--mastery-none)' }"></span>未测 (0%)</span>
        </div>
      </div>

      <!-- 薄弱点 -->
      <div class="map-card glass-card">
        <div class="card-title">
          <span v-html="icons.target" class="card-title-icon"></span>
          薄弱知识点
          <span class="map-count" v-if="weakTotal > 0">{{ weakTotal }} 个</span>
          <span v-if="selectedSubject" class="map-filter" @click="selectedSubject = ''">
            已筛选：{{ masteryData.find((m) => m.subject === selectedSubject)?.label || selectedSubject }} ✕
          </span>
        </div>

        <div v-if="filteredWeakPoints.length === 0" class="weak-empty">
          <span v-html="icons.sparkle" class="inline-icon"></span>
          {{ selectedSubject ? '该科目暂无薄弱点记录' : '暂无薄弱点数据，保持节奏继续练习' }}
        </div>

        <div v-else class="weak-list">
          <div
            v-for="(w, i) in filteredWeakPoints"
            :key="i"
            class="weak-item"
            :style="{ borderLeftColor: w.mastered ? 'var(--mastery-high)' : 'var(--state-weak)' }"
          >
            <!-- 热力指示：连续色阶 --seq-N，错误次数越高越深 -->
            <span class="weak-heat" :style="{ background: heatToken(w.count) }" :title="`错误 ${w.count} 次`"></span>
            <div class="weak-main">
              <div class="weak-top">
                <span class="weak-concept">{{ w.concept }}</span>
                <span
                  class="weak-badge"
                  :class="w.mastered ? 'badge-mastered' : 'badge-open'"
                >{{ w.mastered ? '已掌握' : '待加强' }}</span>
              </div>
              <div class="weak-sub">
                <span class="weak-tag">{{ w.subject }}</span>
                <span class="weak-tag">· {{ w.chapter }}</span>
                <span class="weak-tag weak-error" :style="{ color: 'var(--mastery-low)' }">{{ w.error_type }}</span>
              </div>
            </div>
            <div class="weak-count" :style="{ color: tierColorResolved(0) }">
              <span class="weak-count-num" :style="{ color: 'var(--mastery-low)' }">{{ w.count }}</span>
              <span class="weak-count-unit">次错</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 知识点级（章节级）掌握度下钻 -->
      <div class="map-card glass-card">
        <div class="card-title">
          <span v-html="icons.barChart" class="card-title-icon"></span>
          知识点掌握度
          <span v-if="selectedSubject" class="map-filter" @click="selectedSubject = ''">
            已筛选：{{ masteryData.find((m) => m.subject === selectedSubject)?.label || selectedSubject }} ✕
          </span>
          <span v-else class="map-hint">（点击上方科目可下钻单个科目）</span>
        </div>

        <div v-if="displayKnowledgePoints.length === 0" class="weak-empty">
          <span v-html="icons.sparkle" class="inline-icon"></span>
          暂无知识点掌握度数据，完成步骤化练习后自动点亮
        </div>

        <div v-else class="kp-list">
          <div
            v-for="(kp, i) in displayKnowledgePoints"
            :key="i"
            class="kp-item"
            :style="{ borderLeftColor: kp.mastery == null ? 'var(--mastery-none)' : tierToken(kpPct(kp)) }"
          >
            <div class="kp-main">
              <div class="kp-top">
                <span class="kp-chapter">{{ chapterLabel(kp.chapter) }}</span>
                <span class="kp-tag">{{ kp.chapter }}</span>
              </div>
              <div class="kp-sub">
                <span class="kp-subject">{{ kp.subject }}</span>
                <span v-if="kp.mastery == null" class="kp-badge badge-none">未练习</span>
                <span
                  v-else
                  class="kp-badge"
                  :class="tierOf(kpPct(kp)) === 'high' ? 'badge-mastered' : 'badge-open'"
                >{{ tierLabel(kpPct(kp)) }}</span>
              </div>
            </div>
            <!-- 进度条：scaleX 填充（遵循 SSOT 动效约束，禁止 width 过渡） -->
            <div class="kp-bar-bg">
              <div
                class="kp-bar-fill"
                :style="{ width: '100%', transform: `scaleX(${kpPct(kp) / 100})`, background: kp.mastery == null ? 'var(--mastery-none)' : tierToken(kpPct(kp)) }"
              ></div>
            </div>
            <div class="kp-count">
              <span class="kp-count-num">{{ kp.mastery == null ? '—' : kpPct(kp) }}<span class="kp-count-unit" v-if="kp.mastery != null">%</span></span>
              <span class="kp-count-sub">{{ kp.total }} 次练</span>
            </div>
          </div>
        </div>
      </div>

      <!--
        数据层现状（P4，已闭环）：
        后端新增 GET /quiz/knowledge-mastery?subject=... 返回章节级真实掌握度
        （mastery = 正确/(正确+错误)，未练习为 null 不插值）。
        前端据此绘制知识点下钻，与科目级 / 薄弱点两层并列，无编造数字。
      -->
    </template>
  </div>
</template>

<style scoped>
.inline-icon { display: inline-flex; vertical-align: middle; margin-right: var(--space-1); }
.inline-icon svg { width: 1rem; height: 1rem; }
.section-title-icon { display: inline-flex; vertical-align: middle; margin-right: 0.375rem; }
.section-title-icon svg { width: 1.25rem; height: 1.25rem; }
.card-title-icon { display: inline-flex; vertical-align: middle; margin-right: 0.375rem; }
.card-title-icon svg { width: 1.125rem; height: 1.125rem; }

.map-card { padding: var(--space-5); margin-bottom: var(--space-4); }
.card-title {
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
  color: var(--text-primary);
  margin-bottom: var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.map-hint { font-size: var(--text-xs); color: var(--text-muted); font-weight: var(--weight-regular); }
.map-count {
  margin-left: auto;
  font-size: var(--text-xs);
  padding: 0.125rem var(--space-2);
  border-radius: var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-weight: var(--weight-bold);
}
.map-filter {
  margin-left: auto;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0.125rem var(--space-2);
  border-radius: var(--radius-full);
  background: var(--bg-tertiary);
}
.map-filter:hover { color: var(--accent-primary); }

/* ── 全零占位 ── */
.map-placeholder { text-align: center; padding: var(--space-10) var(--space-6); }
.placeholder-icon { margin-bottom: var(--space-3); opacity: 0.35; }
.placeholder-icon :deep(svg) { width: 2.75rem; height: 2.75rem; }
.placeholder-text { font-size: var(--text-lg); font-weight: var(--weight-bold); color: var(--text-primary); margin-bottom: var(--space-1); }
.placeholder-desc { font-size: var(--text-sm); color: var(--text-muted); }

/* ── 科目网格 ── */
.subject-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--space-4);
}
.subject-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--motion-transition);
}
.subject-tile:hover { transform: translateY(-2px); box-shadow: var(--shadow-card-hover); }
.subject-tile.active { box-shadow: var(--shadow-glow); }
.tile-bar-bg {
  width: 100%;
  height: 0.5rem;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}
.tile-bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  width: 100%;
  transform-origin: left;
  transition: transform var(--duration-slow) var(--ease-standard);
}
.tile-meta { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.tile-label { font-size: var(--text-sm); font-weight: var(--weight-semibold); color: var(--text-primary); }
.tile-tier { font-size: var(--text-2xs); font-weight: var(--weight-bold); }

/* ── 梯度图例 ── */
.tier-legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
  margin-top: var(--space-4);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border);
  font-size: var(--text-2xs);
  color: var(--text-secondary);
}
.legend-item { display: inline-flex; align-items: center; gap: var(--space-1); }
.legend-dot { width: 0.625rem; height: 0.625rem; border-radius: 50%; display: inline-block; }

/* ── 薄弱点 ── */
.weak-empty { font-size: var(--text-sm); color: var(--text-muted); padding: var(--space-3) 0; }
.weak-list { display: flex; flex-direction: column; gap: var(--space-2); }
.weak-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface-2);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--state-weak);
  transition: var(--motion-transition);
}
.weak-item:hover { background: var(--color-surface-hover); transform: translateX(2px); }
.weak-heat {
  width: 0.5rem;
  align-self: stretch;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}
.weak-main { flex: 1; min-width: 0; }
.weak-top { display: flex; align-items: center; gap: var(--space-2); }
.weak-concept { font-size: var(--text-sm); font-weight: var(--weight-semibold); color: var(--text-primary); }
.weak-badge {
  font-size: var(--text-2xs);
  padding: 0.0625rem var(--space-2);
  border-radius: var(--radius-full);
  font-weight: var(--weight-bold);
}
.badge-open { background: var(--accent-danger-10); color: var(--accent-danger); }
.badge-mastered { background: var(--accent-success-10); color: var(--accent-success); }
.weak-sub { display: flex; flex-wrap: wrap; gap: var(--space-1); margin-top: var(--space-1); }
.weak-tag { font-size: var(--text-xs); color: var(--text-muted); }
.weak-error { font-weight: var(--weight-medium); }
.weak-count { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; }
.weak-count-num { font-size: var(--text-lg); font-weight: var(--weight-bold); font-variant-numeric: tabular-nums; }
.weak-count-unit { font-size: var(--text-2xs); color: var(--text-muted); }

/* ── 知识点掌握度 ── */
.kp-list { display: flex; flex-direction: column; gap: var(--space-2); }
.kp-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface-2);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--mastery-none);
  transition: var(--motion-transition);
}
.kp-item:hover { background: var(--color-surface-hover); transform: translateX(2px); }
.kp-main { flex: 1; min-width: 0; }
.kp-top { display: flex; align-items: center; gap: var(--space-2); }
.kp-chapter { font-size: var(--text-sm); font-weight: var(--weight-semibold); color: var(--text-primary); }
.kp-tag { font-size: var(--text-2xs); color: var(--text-muted); font-family: var(--font-mono, monospace); }
.kp-sub { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); margin-top: var(--space-1); }
.kp-subject { font-size: var(--text-xs); color: var(--text-muted); }
.kp-badge {
  font-size: var(--text-2xs);
  padding: 0.0625rem var(--space-2);
  border-radius: var(--radius-full);
  font-weight: var(--weight-bold);
}
.badge-none { background: var(--bg-tertiary); color: var(--text-muted); }
.badge-open { background: var(--accent-danger-10); color: var(--accent-danger); }
.badge-mastered { background: var(--accent-success-10); color: var(--accent-success); }
.kp-bar-bg {
  width: 7rem;
  height: 0.5rem;
  background: var(--bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
  flex-shrink: 0;
}
.kp-bar-fill {
  height: 100%;
  border-radius: var(--radius-full);
  width: 100%;
  transform-origin: left;
  transition: transform var(--duration-slow) var(--ease-standard);
}
.kp-count { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; min-width: 3.5rem; }
.kp-count-num { font-size: var(--text-lg); font-weight: var(--weight-bold); font-variant-numeric: tabular-nums; color: var(--text-primary); }
.kp-count-sub { font-size: var(--text-2xs); color: var(--text-muted); }

@media (max-width: 768px) {
  .map-card { padding: var(--space-4); }
  .subject-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
