<script setup lang="ts">
/* ===================== F4 个人成长页（2026-10-15）=====================
 * 数据源：GET /career/my-growth（career_store.growth_profile）。
 * 诚信口径：只呈现真实落库数据；未完成/无评分会话不进趋势与前后测对比；
 * 前后测差值仅当 pre/post 两侧都有已评分会话时才出现（不插值、不作显著性宣称）。 */
import { ref, computed, onMounted } from 'vue'
import { api, friendlyError } from '@/utils/api'
import { CAREER_DIM_LABEL as DIM_LABEL, CAREER_DIM_ORDER as DIM_ORDER } from '@/data/careerDimensions'

interface TrendPoint { date: string; score: number; phase: string | null }
interface GrowthSession {
  session_id: string; title: string; scenario_id: string; status: string
  phase: string | null; turn_count: number; started_at: string; finished_at: string | null
  dimension_scores: Record<string, number>; overall: number | null
}
interface Growth {
  user_id: string; session_count: number; finished_count: number
  sessions: GrowthSession[]
  dimension_trend: Record<string, TrendPoint[]>
  dimension_avg: Record<string, number>
  phase_compare: {
    pre: Record<string, number>; post: Record<string, number>; delta: Record<string, number>
    note: string
  } | null
  quotes: { dimension: string; score: number | null; quote: string; turn: number | null; polarity: string; session_id: string; started_at: string }[]
}

const growth = ref<Growth | null>(null)
const loading = ref(true)
const errorMsg = ref('')

const PHASE_LABEL: Record<string, string> = { pre: '前测', post: '后测' }
const STATUS_LABEL: Record<string, string> = { ongoing: '进行中', finished: '已完成', abandoned: '已放弃' }

async function loadGrowth() {
  loading.value = true
  try {
    growth.value = await api.get<Growth>('/career/my-growth')
  } catch (e) {
    errorMsg.value = friendlyError(e, '成长数据加载失败')
  } finally {
    loading.value = false
  }
}
onMounted(loadGrowth)

const overallBest = computed(() => {
  const vals = (growth.value?.sessions || []).map(s => s.overall).filter((v): v is number => v != null)
  return vals.length ? Math.max(...vals) : null
})

/* 前后测对比行：仅两侧都有差值的维度才出一行（不插值） */
const phaseRows = computed(() => {
  const pc = growth.value?.phase_compare
  if (!pc) return []
  return DIM_ORDER
    .filter(d => (pc.delta[d] ?? null) != null)
    .map(d => ({ key: d, label: DIM_LABEL[d] || d,
                 pre: pc.pre[d], post: pc.post[d], delta: pc.delta[d] as number }))
})

/* 单维趋势 sparkline：x 按会话序，y 为 0-5 分 */
function sparkPoints(pts: TrendPoint[]): { line: string; dot: string | null } {
  if (!pts.length) return { line: '', dot: null }
  const W = 120, H = 36, PAD = 3
  const xy = pts.map((p, i) => {
    const x = pts.length === 1 ? W / 2 : PAD + (i * (W - PAD * 2)) / (pts.length - 1)
    const y = H - PAD - (Math.max(0, Math.min(5, p.score)) / 5) * (H - PAD * 2)
    return [x, y] as const
  })
  const last = xy[xy.length - 1]
  return { line: xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' '),
           dot: last ? last.map(v => v.toFixed(1)).join(',') : null }
}

function dimTrend(d: string): TrendPoint[] { return growth.value?.dimension_trend?.[d] || [] }
function dimAvg(d: string): number | null {
  const v = growth.value?.dimension_avg?.[d]
  return v == null ? null : v
}
function fmtDate(iso: string): string { return (iso || '').slice(0, 10) }
</script>

<template>
  <div class="growth-page">
    <div class="g-header">
      <div class="c-title"> 我的成长</div>
      <div class="c-desc">跨会话六维趋势、前后测对比与证据金句——全部来自你的真实实训记录</div>
    </div>

    <div v-if="loading" class="c-loading">正在加载成长数据…</div>
    <div v-else-if="errorMsg" class="c-error">{{ errorMsg }}</div>
    <template v-else-if="growth">
      <div class="g-stats">
        <div class="g-stat"><div class="gs-h">实训场次</div><div class="gs-v">{{ growth.session_count }}</div></div>
        <div class="g-stat"><div class="gs-h">已完成</div><div class="gs-v">{{ growth.finished_count }}</div></div>
        <div class="g-stat"><div class="gs-h">最高综合分</div><div class="gs-v">{{ overallBest ?? '—' }}</div></div>
      </div>

      <!-- 前后测对比（仅两侧齐备时出现；探索性口径） -->
      <section v-if="growth.phase_compare" class="g-section">
        <h2>前后测对比</h2>
        <table class="g-table">
          <thead><tr><th>维度</th><th>前测均分</th><th>后测均分</th><th>差值</th></tr></thead>
          <tbody>
            <tr v-for="r in phaseRows" :key="r.key">
              <td>{{ r.label }}</td>
              <td>{{ r.pre ?? '缺失' }}</td>
              <td>{{ r.post ?? '缺失' }}</td>
              <td :class="r.delta > 0 ? 'up' : (r.delta < 0 ? 'down' : '')">
                {{ r.delta > 0 ? '+' : '' }}{{ r.delta }}
              </td>
            </tr>
          </tbody>
        </table>
        <p class="g-note">⚠️ {{ growth.phase_compare.note }}</p>
      </section>

      <!-- 六维趋势 -->
      <section class="g-section">
        <h2>六维趋势</h2>
        <div class="g-dim-grid">
          <div v-for="d in DIM_ORDER" :key="d" class="g-dim-card">
            <div class="gd-head">
              <span class="gd-name">{{ DIM_LABEL[d] }}</span>
              <span class="gd-avg">{{ dimAvg(d) ?? '—' }}</span>
            </div>
            <svg v-if="dimTrend(d).length" viewBox="0 0 120 36" class="gd-spark" preserveAspectRatio="none">
              <polyline :points="sparkPoints(dimTrend(d)).line" fill="none" stroke="var(--accent-primary)" stroke-width="1.6" />
              <circle v-if="sparkPoints(dimTrend(d)).dot" :cx="sparkPoints(dimTrend(d)).dot!.split(',')[0]"
                      :cy="sparkPoints(dimTrend(d)).dot!.split(',')[1]" r="2.4" fill="var(--accent-primary)" />
            </svg>
            <div v-else class="gd-empty">暂无已完成评分</div>
            <div class="gd-meta">{{ dimTrend(d).length }} 个评分点</div>
          </div>
        </div>
      </section>

      <!-- 证据金句 -->
      <section class="g-section">
        <h2>证据金句</h2>
        <p class="g-sub">评估真实引用过的你的原话（按场次倒序）</p>
        <div v-if="growth.quotes.length" class="g-quotes">
          <div v-for="(q, i) in growth.quotes" :key="i" class="g-quote">
            <div class="gq-text">「{{ q.quote }}」</div>
            <div class="gq-meta">
              <span class="gq-dim">{{ DIM_LABEL[q.dimension] || q.dimension }}</span>
              <span v-if="q.turn != null">第 {{ q.turn }} 轮</span>
              <span v-if="q.polarity">{{ q.polarity }}</span>
              <span>{{ fmtDate(q.started_at) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="g-empty">还没有金句——完成一场实训后，评估引用过的原话会出现在这里。</div>
      </section>

      <!-- 场次明细 -->
      <section class="g-section">
        <h2>场次明细</h2>
        <div class="g-sessions">
          <div v-for="s in growth.sessions" :key="s.session_id" class="g-sess">
            <div class="gs-line1">
              <span class="gs-title">{{ s.title || s.scenario_id }}</span>
              <span v-if="s.phase" class="gs-phase" :class="'ph-' + s.phase">{{ PHASE_LABEL[s.phase] }}</span>
              <span class="gs-status" :class="'st-' + s.status">{{ STATUS_LABEL[s.status] || s.status }}</span>
            </div>
            <div class="gs-line2">
              <span>{{ fmtDate(s.started_at) }}</span>
              <span>{{ s.turn_count }} 轮</span>
              <span>综合 {{ s.overall ?? '—' }}</span>
              <span v-if="Object.keys(s.dimension_scores).length">
                六维：{{ Object.entries(s.dimension_scores).map(([d, v]) => `${DIM_LABEL[d] || d} ${v}`).join(' · ') }}
              </span>
              <span v-else class="dim">无评分</span>
            </div>
          </div>
        </div>
      </section>
    </template>
    <div v-else class="g-empty">还没有实训记录——去完成一场对抗实训，这里就会出现你的成长轨迹。</div>
  </div>
</template>

<style scoped>
.growth-page { max-width: 960px; margin: 0 auto; padding: 18px var(--space-4) 60px; color: var(--text-primary); }
.g-header { margin-bottom: var(--space-4); }
.c-title { font-size: 22px; font-weight: var(--weight-bold); }
.c-desc { font-size: var(--text-sm); color: var(--text-secondary); margin-top: 6px; line-height: 1.6; }
.c-loading, .c-error { padding: 14px; border-radius: 10px; font-size: var(--text-sm); margin: var(--space-3) 0; }
.c-loading { background: var(--bg-secondary); }
.c-error { background: var(--accent-danger-10); color: var(--accent-danger); }
.g-stats { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: var(--space-4); }
.g-stat { flex: 1; min-width: 120px; background: var(--bg-card); border: 1px solid var(--border-color);
  border-radius: 12px; padding: var(--space-3) 14px; }
.gs-h { font-size: var(--text-2xs); color: var(--text-secondary); }
.gs-v { font-size: 24px; font-weight: var(--weight-bold); color: var(--accent-primary); }
.g-section { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 14px;
  padding: var(--space-4); margin-bottom: 14px; }
.g-section h2 { font-size: var(--text-md); margin: 0 0 var(--space-3); }
.g-sub { font-size: var(--text-sm); color: var(--text-secondary); margin: -6px 0 var(--space-3); }
.g-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
.g-table th, .g-table td { border: 1px solid var(--border-color); padding: 6px 10px; text-align: left; }
.g-table th { background: var(--bg-secondary); }
.g-table .up { color: var(--kpi-trend-up); font-weight: var(--weight-semibold); }
.g-table .down { color: var(--kpi-trend-down); }
.g-note { font-size: var(--text-2xs); color: var(--text-secondary); margin: var(--space-2) 0 0; line-height: 1.6; }
.g-dim-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
.g-dim-card { border: 1px solid var(--border-color); border-radius: 10px; padding: 10px 12px; }
.gd-head { display: flex; justify-content: space-between; align-items: baseline; }
.gd-name { font-size: var(--text-sm); font-weight: var(--weight-semibold); }
.gd-avg { font-size: 18px; font-weight: var(--weight-bold); color: var(--accent-primary); }
.gd-spark { width: 100%; height: 36px; margin-top: 6px; }
.gd-empty { font-size: var(--text-2xs); color: var(--text-secondary); margin-top: 6px; }
.gd-meta { font-size: var(--text-2xs); color: var(--text-secondary); margin-top: 4px; }
.g-quotes { display: grid; gap: 8px; }
.g-quote { border-left: 3px solid var(--accent-primary); background: var(--bg-secondary);
  border-radius: 0 8px 8px 0; padding: 8px 12px; }
.gq-text { font-size: var(--text-sm); line-height: 1.6; }
.gq-meta { display: flex; gap: 10px; flex-wrap: wrap; font-size: var(--text-2xs); color: var(--text-secondary); margin-top: 4px; }
.gq-dim { color: var(--accent-primary); font-weight: var(--weight-semibold); }
.g-sessions { display: grid; gap: 8px; }
.g-sess { border: 1px solid var(--border-color); border-radius: 10px; padding: 8px 12px; }
.gs-line1 { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.gs-title { font-size: var(--text-sm); font-weight: var(--weight-semibold); }
.gs-phase { font-size: var(--text-2xs); padding: 1px 8px; border-radius: 8px; }
.gs-phase.ph-pre { background: var(--accent-primary-10); color: var(--accent-primary); }
.gs-phase.ph-post { background: var(--color-success-bg); color: var(--color-success); }
.gs-status { font-size: var(--text-2xs); color: var(--text-secondary); }
.gs-status.st-finished { color: #389e0d; }
.gs-line2 { display: flex; gap: 12px; flex-wrap: wrap; font-size: var(--text-2xs); color: var(--text-secondary); margin-top: 4px; }
.g-empty { font-size: var(--text-sm); color: var(--text-secondary); padding: var(--space-4); text-align: center; }
.dim { color: var(--text-secondary); }
</style>
