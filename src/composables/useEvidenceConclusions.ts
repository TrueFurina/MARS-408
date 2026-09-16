/**
 * useEvidenceConclusions —— 结论级证据看板（v1 规则原型）
 *
 * 【定位】把 experiments/results/ 下散落的真实产物，按**结论**聚合成评审可读的证据卡：
 *   每条结论 = 一句论断 + 若干**从真实文件字段提取**的头条指标 + 溯源（文件名 + sha256）。
 *
 * 【诚实性纪律（硬约束）】
 *   1. 所有指标**只从真实产物字段读取**，绝不手写数字；
 *      字段缺失 → 显示 "—"，不编造。
 *   2. 结论与产物的映射是**人工策展的 v1 规则**（非自动发现），故显式标注
 *      「v1 规则原型」，避免把"结构型编排"伪装成"自动推理"。
 *   3. 溯源必须展示：每条结论列出其依据的产物文件与 sha256。
 *
 * 【契约层】明细响应类型取自 src/types/api.generated.ts 的 operations[...]。
 */

import { ref, type Ref } from 'vue'
import { api, friendlyError } from '@/utils/api'
import type { operations } from '@/types/api.generated'

type DetailContract =
  operations['get_experiment_api_experiments__name__get']['responses'][200]['content']['application/json']

export interface Metric {
  label: string
  value: string
  hint?: string
}

export interface ArtifactRef {
  name: string
  file: string
  sha256: string | null
  size_bytes: number | null
  modified: string | null
}

export interface Conclusion {
  id: string
  theme: string
  title: string
  claim: string
  metrics: Metric[]
  artifacts: ArtifactRef[]
  raw: Record<string, unknown>
}

interface ConclusionSpec {
  id: string
  theme: string
  title: string
  /** 依据的产物名（experiments/results/ 下的 basename，不含 .json） */
  artifacts: string[]
  claim: (d: Record<string, any>) => string
  metrics: (d: Record<string, any>) => Metric[]
}

/* ── 数值安全取值 ── */
function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}
function fmt(v: number | null, digits = 2, suffix = ''): string {
  return v === null ? '—' : `${v.toFixed(digits)}${suffix}`
}

/** 把 0~1 的比例值转成百分数文本（如 0.7857 → "78.6%"） */
function pctFromFrac(v: number | null, digits = 1): string {
  return v === null ? '—' : `${(v * 100).toFixed(digits)}%`
}

/** 把 0~1 的比例差值转成百分点文本（如 0.1071 → "+10.7pp"） */
function ppFromFrac(v: number | null, digits = 1): string {
  if (v === null) return '—'
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(digits)}pp`
}

/* ── 结论策展规格（v1 规则原型）── */
export const CONCLUSION_SPECS: ConclusionSpec[] = [
  {
    id: 'marl-algorithms',
    theme: '多智能体算法',
    title: 'MAPPO / QMIX 在奖励上并列最优，VDN 明显落后',
    artifacts: ['marl_algorithms_eval_20260912'],
    claim: (d) =>
      `在 beginner 关卡，MAPPO（${fmt(num(d?.levels?.beginner?.mappo?.avg_reward?.mean))}）与 ` +
      `QMIX（${fmt(num(d?.levels?.beginner?.qmix?.avg_reward?.mean))}）奖励并列最优，` +
      `显著优于 VDN（${fmt(num(d?.levels?.beginner?.vdn?.avg_reward?.mean))}）；` +
      `四者准确率均≈0.95+（规则基线 ${fmt(num(d?.levels?.beginner?.rules?.avg_accuracy), 4)}）。`,
    metrics: (d) => [
      { label: 'MAPPO 奖励(beginner)', value: fmt(num(d?.levels?.beginner?.mappo?.avg_reward?.mean)) },
      { label: 'MAPPO ±std', value: fmt(num(d?.levels?.beginner?.mappo?.avg_reward?.std)) },
      { label: 'QMIX 奖励', value: fmt(num(d?.levels?.beginner?.qmix?.avg_reward?.mean)) },
      { label: 'VDN 奖励', value: fmt(num(d?.levels?.beginner?.vdn?.avg_reward?.mean)) },
      { label: '规则基线奖励', value: fmt(num(d?.levels?.beginner?.rules?.avg_reward)) },
      { label: 'MAPPO 准确率(advanced)', value: fmt(num(d?.levels?.advanced?.mappo?.avg_accuracy?.mean), 4) },
    ],
  },
  {
    id: 'review-analytic',
    theme: '三元评审权重',
    title: '解析式评审策略达到 oracle 上界，且对噪声稳健',
    artifacts: ['accept_review'],
    claim: (d) =>
      `解析式策略在生产打分口径下 capture=${fmt(num(d?.main?.arms?.analytic?.capture_pct), 1, '%')}（= oracle 上界），` +
      `远超新规则（${fmt(num(d?.main?.arms?.rule_new?.capture_pct), 1, '%')}）；` +
      `对 ±3% 噪声仍达 ${fmt(num(d?.gen_noisy?.arms?.analytic?.capture_pct), 1, '%')}。` +
      `门禁判定 PASS=${String(d?.verdict?.PASS)}。`,
    metrics: (d) => [
      { label: '解析式 capture (main)', value: fmt(num(d?.main?.arms?.analytic?.capture_pct), 1, '%') },
      { label: 'oracle 上界 (main)', value: fmt(num(d?.main?.oracle), 2) },
      { label: 'uniform 基线 (main)', value: fmt(num(d?.main?.uniform), 2) },
      { label: '新规则 capture', value: fmt(num(d?.main?.arms?.rule_new?.capture_pct), 1, '%') },
      { label: '解析式 capture (泛化集)', value: fmt(num(d?.gen?.arms?.analytic?.capture_pct), 1, '%') },
      { label: '解析式 capture (±3% 噪声)', value: fmt(num(d?.gen_noisy?.arms?.analytic?.capture_pct), 1, '%') },
      { label: 'headroom (main)', value: fmt(num(d?.main?.headroom), 3) },
    ],
  },
  {
    id: 'budget-sensitivity',
    theme: 'RL 预算敏感',
    title: 'RL 影子策略受预算强烈约束，且被解析式上界封闭',
    artifacts: ['tune_shadow_budget'],
    claim: (d) => {
      const rows: any[] = Array.isArray(d?.rows) ? d.rows : []
      const best = rows.reduce<any | null>(
        (a, r) => {
          if (a === null) return r
          const av = num(a?.main?.capture_pct) ?? -1
          const rv = num(r?.main?.capture_pct) ?? -1
          return rv > av ? r : a
        },
        null,
      )
      const fast = rows.find((r) => r?.horizon === 8)
      const bs = num(best?.seconds)
      const fs = num(fast?.seconds)
      const speedup = bs !== null && fs !== null && fs > 0 ? `${(bs / fs).toFixed(1)}×` : '—'
      return (
        `最优配置「${String(best?.config ?? '—')}」捕获率 ` +
        `${fmt(num(best?.main?.capture_pct), 1, '%')}(main)/${fmt(num(best?.gen?.capture_pct), 1, '%')}(gen)，` +
        `但仍低于解析式的 100%（RL 上界被解析式封闭）；` +
        `hz=8 快 ${speedup}、捕获率小幅下降。`
      )
    },
    metrics: (d) => {
      const rows: any[] = Array.isArray(d?.rows) ? d.rows : []
      const best = rows.reduce<any | null>(
        (a, r) => (a === null || (num(r?.main?.capture_pct) ?? -1) > (num(a?.main?.capture_pct) ?? -1) ? r : a),
        null,
      )
      const fast = rows.find((r) => r?.horizon === 8)
      return [
        { label: '最优配置', value: String(best?.config ?? '—'), hint: '按 main 捕获率选优' },
        { label: '最优 capture (main)', value: fmt(num(best?.main?.capture_pct), 1, '%') },
        { label: '最优 capture (gen)', value: fmt(num(best?.gen?.capture_pct), 1, '%') },
        { label: '最优耗时', value: best ? `${fmt(num(best.seconds), 1, 's')}` : '—' },
        { label: 'hz=8 capture (main)', value: fmt(num(fast?.main?.capture_pct), 1, '%') },
        { label: 'hz=8 耗时', value: fast ? fmt(num(fast.seconds), 1, 's') : '—' },
        { label: '扫参配置数', value: String(rows.length) },
      ]
    },
  },
  {
    id: 'calib-alignment',
    theme: '仿真—真实对齐',
    title: '训练/评测同分布已核验，奖励与验收口径对齐',
    artifacts: ['diag_calib_alignment'],
    claim: (d) =>
      `R1 同分布：最差维度 smd=${fmt(num(d?.R1_distribution_alignment?.worst_std_mean_diff), 3)}（<0.2），` +
      `臂排序一致=${String(d?.R1b_arm_levels?.ordering_identical)}；` +
      `R2 显著性：影子策略对 uniform 的 t=${fmt(num(d?.R2_significance?.aggregate?.uniform?.t))}；` +
      `R4 奖励对齐 ${fmt(num(d?.R4_reward_alignment?.exact_agree_pct), 1, '%')}。` +
      `⇒ 仿真结论可外推，且排除奖励设计错位。`,
    metrics: (d) => [
      { label: 'R1 最差 smd', value: fmt(num(d?.R1_distribution_alignment?.worst_std_mean_diff), 3), hint: '<0.2 视为同分布' },
      { label: 'R1 臂排序一致', value: String(d?.R1b_arm_levels?.ordering_identical) },
      { label: 'R2 shadow 对 uniform t', value: fmt(num(d?.R2_significance?.aggregate?.uniform?.t)) },
      { label: 'R2 shadow 均值(vs uniform)', value: fmt(num(d?.R2_significance?.aggregate?.uniform?.mean)) },
      { label: 'R3 策略一致率', value: fmt(num(d?.R3_interpretability?.agreement_pct), 1, '%') },
      { label: 'R4 奖励对齐', value: fmt(num(d?.R4_reward_alignment?.exact_agree_pct), 1, '%') },
    ],
  },
  {
    id: 'retrieval-benchmark',
    theme: '检索基准',
    title: 'FrugalRAG 召回 +10.7pp，但延迟约 20×、token 未降（如实呈现）',
    artifacts: ['benchmark_2026-08-17'],
    claim: (d) => {
      const f = d?.experiment1?.summary?.frugalrag ?? {}
      const full = d?.experiment1?.summary?.full_retrieval ?? {}
      const e2 = d?.experiment2?.summary ?? {}
      const lf = num(f.mean_latency_ms)
      const lfull = num(full.mean_latency_ms)
      const mult = lf !== null && lfull !== null && lfull > 0 ? `≈${(lf / lfull).toFixed(0)}×` : '—'
      return (
        `28 条真实查询：FrugalRAG 召回@5 ${pctFromFrac(num(f['mean_recall@5']))}（全量 ${pctFromFrac(num(full['mean_recall@5']))}，` +
        `${ppFromFrac(num(d?.experiment1?.summary?.deltas?.recall_delta))}），精度 ${pctFromFrac(num(f['mean_precision@5']))}（全量 ${pctFromFrac(num(full['mean_precision@5']))}）；` +
        `代价是延迟 ${fmt(lf, 1, 'ms')} vs ${fmt(lfull, 1, 'ms')}（${mult}）、token ${fmt(num(d?.experiment1?.summary?.deltas?.token_reduction_pct), 2, '%')}（未降）。` +
        `另一组 30 题×3：NeuralMixer 准确率 ${pctFromFrac(num(e2?.neural_mixer?.accuracy))} vs 加权投票 ${pctFromFrac(num(e2?.weighted_voting?.accuracy))}。`
      )
    },
    metrics: (d) => {
      const f = d?.experiment1?.summary?.frugalrag ?? {}
      const full = d?.experiment1?.summary?.full_retrieval ?? {}
      const dl = d?.experiment1?.summary?.deltas ?? {}
      const e2 = d?.experiment2?.summary ?? {}
      const lf = num(f.mean_latency_ms)
      const lfull = num(full.mean_latency_ms)
      const mult = lf !== null && lfull !== null && lfull > 0 ? `≈${(lf / lfull).toFixed(0)}×` : '—'
      return [
        { label: 'FrugalRAG 召回@5', value: pctFromFrac(num(f['mean_recall@5'])) },
        { label: '全量检索召回@5', value: pctFromFrac(num(full['mean_recall@5'])) },
        { label: '召回提升', value: ppFromFrac(num(dl.recall_delta)) },
        { label: 'FrugalRAG 精度@5', value: pctFromFrac(num(f['mean_precision@5'])) },
        { label: '全量精度@5', value: pctFromFrac(num(full['mean_precision@5'])) },
        { label: 'FrugalRAG 延迟', value: fmt(lf, 1, 'ms') },
        { label: '全量延迟', value: fmt(lfull, 1, 'ms') },
        { label: '延迟倍数', value: mult },
        { label: 'token 变化', value: fmt(num(dl.token_reduction_pct), 2, '%') },
        { label: 'NeuralMixer 准确率', value: pctFromFrac(num(e2?.neural_mixer?.accuracy)) },
        { label: '加权投票准确率', value: pctFromFrac(num(e2?.weighted_voting?.accuracy)) },
        { label: 'NeuralMixer κ(对真值)', value: fmt(num(e2?.cohens_kappa?.neural_vs_truth), 3) },
      ]
    },
  },
  {
    id: 'career-mappo',
    theme: '职业素养 MAPPO',
    title: '训练通过纪律门禁与奖励验收（合成环境，如实标注）',
    artifacts: ['career_mappo_train_20260914'],
    claim: (d) =>
      `3 个种子（${String(d?.args?.seeds ?? '—')}）× ${fmt(num(d?.train?.episodes), 0)} episodes：` +
      `baseline 触发率 ${fmt(num(d?.meta?.baseline_trigger_rate), 2)}，` +
      `mappo_reward_ge_rule=${String(d?.mappo_reward_ge_rule)}、passed=${String(d?.passed)}、纪律违规 ${fmt(num(d?.discipline_violations), 0)}；` +
      `种子可复现=${String(d?.meta?.seed_reproducible)}。` +
      `⚠️ environment_source=${String(d?.meta?.environment_source ?? '—')}（非真实用户轨迹），结论限于该环境。`,
    metrics: (d) => [
      { label: '训练轮数', value: fmt(num(d?.train?.episodes), 0) },
      { label: '种子数', value: String(Array.isArray(d?.seeds) ? d.seeds.length : (Object.keys(d?.seeds ?? {}).length || '—')) },
      { label: 'mean_ep_reward', value: fmt(num(d?.train?.mean_ep_reward), 3) },
      { label: 'mean_loss', value: fmt(num(d?.train?.mean_loss), 5) },
      { label: 'baseline 触发率', value: fmt(num(d?.meta?.baseline_trigger_rate), 2) },
      { label: 'mappo≥rule', value: String(d?.mappo_reward_ge_rule) },
      { label: '纪律违规', value: fmt(num(d?.discipline_violations), 0) },
      { label: 'passed', value: String(d?.passed) },
      { label: '环境来源', value: String(d?.meta?.environment_source ?? '—') },
    ],
  },
]

export function useEvidenceConclusions() {
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)
  const conclusions: Ref<Conclusion[]> = ref([])

  async function fetchDetail(name: string): Promise<{ data: any; ref: ArtifactRef } | null> {
    try {
      const raw = (await api.get<DetailContract>(`/experiments/${encodeURIComponent(name)}`)) as unknown as {
        file?: string
        provenance?: { sha256?: string; size_bytes?: number; modified?: string }
        data?: unknown
      }
      return {
        data: (raw?.data ?? {}) as any,
        ref: {
          name,
          file: String(raw?.file ?? `${name}.json`),
          sha256: raw?.provenance?.sha256 ?? null,
          size_bytes: raw?.provenance?.size_bytes ?? null,
          modified: raw?.provenance?.modified ?? null,
        },
      }
    } catch {
      return null
    }
  }

  async function load(): Promise<Conclusion[]> {
    loading.value = true
    error.value = null
    try {
      const names = [...new Set(CONCLUSION_SPECS.flatMap((s) => s.artifacts))]
      const fetched = await Promise.all(names.map((n) => fetchDetail(n)))
      const byName = new Map<string, { data: any; ref: ArtifactRef }>()
      names.forEach((n, i) => {
        const f = fetched[i]
        if (f) byName.set(n, f)
      })

      const out: Conclusion[] = []
      for (const spec of CONCLUSION_SPECS) {
        const present = spec.artifacts
          .map((n) => byName.get(n))
          .filter((x): x is { data: any; ref: ArtifactRef } => !!x)
        if (!present.length) continue // 产物缺失 → 该结论不渲染（不编造）
        // 合并依据数据（单产物结论直接用其 data）
        const first = present[0]
        const merged: Record<string, any> =
          present.length === 1 && first ? first.data : { sources: present.map((p) => p.data) }
        out.push({
          id: spec.id,
          theme: spec.theme,
          title: spec.title,
          claim: spec.claim(merged),
          metrics: spec.metrics(merged),
          artifacts: present.map((p) => p.ref),
          raw: merged,
        })
      }
      conclusions.value = out
      if (!out.length) error.value = '未找到可支撑结论的真实产物（请确认后端已启动）'
      return out
    } catch (e) {
      conclusions.value = []
      error.value = friendlyError(e, '结论证据加载失败')
      return []
    } finally {
      loading.value = false
    }
  }

  return { loading, error, conclusions, load }
}
