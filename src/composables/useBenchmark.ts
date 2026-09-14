/**
 * useBenchmark —— benchmark 真产物的唯一前端入口（证据链 P0）
 *
 * 【背景 2026-09-15】
 * 此前 src/views/BenchmarkView.vue 把四组聚合数硬编码为常量，注释写
 * "来自 scripts/benchmark.py --demo 的真实输出" —— 自相矛盾：
 * scripts/benchmark.py 的 --demo 是**合成数据**模式，其产物
 * scripts/benchmark_results.json 的 results.mode 值就是 "demo"。
 *
 * 真产物在 py-server/experiments/results/benchmark_YYYY-MM-DD.json：
 *   · experiment1：28 条真实查询，FrugalRAG vs 全量检索（含 per_query 明细）
 *   · experiment2：30 题 × 3 次，NeuralMixer vs 加权投票（含 per_question 明细）
 *   · meta：random_seed / env / kb_chunks / top_k
 *
 * 【纪律】
 *   · 本 composable **不提供任何 fallback 数值**：接口失败时 rows 为空、
 *     provenance 为 null，由视图侧渲染空态，绝不回退到示例/合成数据。
 *   · provenance 必须被视图原样展示，使页面上每个数字都可追溯到文件与时间戳。
 */

import { ref, computed, type Ref } from 'vue'
import { api, friendlyError } from '@/utils/api'

export interface BenchmarkProvenance {
  source_file: string
  file_name: string
  file_mtime: string
  file_size_bytes: number
  mode: string
  n_queries: number | null
  n_questions: number | null
  n_trials_per_question: number | null
  random_seed: number | null
  benchmark_date: string | null
  env: Record<string, string>
}

export interface RetrievalRow {
  id: string
  course: string
  query: string
  frugalRecall: number
  fullRecall: number
  frugalPrecision: number
  fullPrecision: number
  frugalLatency: number
  fullLatency: number
  frugalChunks: number
  fullChunks: number
  frugalTokens: number
  fullTokens: number
}

export interface QuestionRow {
  id: string
  stem: string
  type: string
  groundTruth: number | null
  nTrials: number
  /** 3 次试验中答对的次数（0..nTrials） */
  neuralCorrect: number
  votingCorrect: number
  /** 3 次试验的平均共识分 */
  neuralScore: number
  votingScore: number
}

interface ArmSummary {
  mean_recall_5: number | null
  mean_precision_5: number | null
  mean_mrr: number | null
  mean_latency_ms: number | null
  mean_chunks: number | null
  mean_tokens: number | null
}

export interface BenchmarkSummary {
  nQueries: number | null
  nQuestions: number | null
  nTrials: number | null
  frugal: ArmSummary
  full: ArmSummary
  recallDelta: number | null
  precisionDelta: number | null
  mrrDelta: number | null
  tokenReductionPct: number | null
  neuralAccuracy: number | null
  votingAccuracy: number | null
  accuracyDelta: number | null
  kappaNeuralVsTruth: number | null
  kappaVotingVsTruth: number | null
}

function arm(raw: any): ArmSummary {
  return {
    mean_recall_5: raw?.['mean_recall@5'] ?? null,
    mean_precision_5: raw?.['mean_precision@5'] ?? null,
    mean_mrr: raw?.['mean_mrr'] ?? null,
    mean_latency_ms: raw?.['mean_latency_ms'] ?? null,
    mean_chunks: raw?.['mean_chunks'] ?? null,
    mean_tokens: raw?.['mean_tokens'] ?? null,
  }
}

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

export function useBenchmark() {
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)
  const provenance: Ref<BenchmarkProvenance | null> = ref(null)
  const rows: Ref<RetrievalRow[]> = ref([])
  const questions: Ref<QuestionRow[]> = ref([])
  const rawExp1 = ref<any>(null)
  const rawExp2 = ref<any>(null)

  function mapRows(perQuery: any[]): RetrievalRow[] {
    return (Array.isArray(perQuery) ? perQuery : []).map((r: any) => ({
      id: String(r?.id ?? ''),
      course: String(r?.course ?? ''),
      query: String(r?.query ?? ''),
      frugalRecall: num(r?.frugalrag?.['recall@5']) ?? 0,
      fullRecall: num(r?.full_retrieval?.['recall@5']) ?? 0,
      frugalPrecision: num(r?.frugalrag?.['precision@5']) ?? 0,
      fullPrecision: num(r?.full_retrieval?.['precision@5']) ?? 0,
      frugalLatency: num(r?.frugalrag?.['latency_ms']) ?? 0,
      fullLatency: num(r?.full_retrieval?.['latency_ms']) ?? 0,
      frugalChunks: num(r?.frugalrag?.['n_chunks']) ?? 0,
      fullChunks: num(r?.full_retrieval?.['n_chunks']) ?? 0,
      frugalTokens: num(r?.frugalrag?.['tokens']) ?? 0,
      fullTokens: num(r?.full_retrieval?.['tokens']) ?? 0,
    }))
  }

  function mapQuestions(perQuestion: any[]): QuestionRow[] {
    return (Array.isArray(perQuestion) ? perQuestion : []).map((q: any) => {
      const trials: any[] = Array.isArray(q?.trials) ? q.trials : []
      const acc = (key: string) => {
        const vals = trials
          .map((t: any) => t?.[key])
          .filter((v: any) => v && typeof v === 'object')
        const correct = vals.filter((v: any) => v.correct === true).length
        const scores = vals
          .map((v: any) => num(v.consensus_score))
          .filter((v: number | null): v is number => v !== null)
        const mean = scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0
        return { correct, mean, n: vals.length }
      }
      const nn = acc('neural_mixer')
      const vv = acc('weighted_voting')
      return {
        id: String(q?.id ?? ''),
        stem: String(q?.stem ?? ''),
        type: String(q?.type ?? ''),
        groundTruth: num(q?.ground_truth),
        nTrials: Math.max(nn.n, vv.n),
        neuralCorrect: nn.correct,
        votingCorrect: vv.correct,
        neuralScore: nn.mean,
        votingScore: vv.mean,
      }
    })
  }

  const summary = computed<BenchmarkSummary | null>(() => {
    const e1 = rawExp1.value
    const e2 = rawExp2.value
    if (!e1 && !e2) return null
    const d1 = e1?.deltas ?? {}
    const d2 = e2?.deltas ?? {}
    const kappa = e2?.cohens_kappa ?? {}
    return {
      nQueries: num(e1?.n_queries),
      nQuestions: num(e2?.n_questions),
      nTrials: num(e2?.n_trials_per_question),
      frugal: arm(e1?.frugalrag),
      full: arm(e1?.full_retrieval),
      recallDelta: num(d1.recall_delta),
      precisionDelta: num(d1.precision_delta),
      mrrDelta: num(d1.mrr_delta),
      tokenReductionPct: num(d1.token_reduction_pct),
      neuralAccuracy: num(e2?.neural_mixer?.accuracy),
      votingAccuracy: num(e2?.weighted_voting?.accuracy),
      accuracyDelta: num(d2.accuracy_delta),
      kappaNeuralVsTruth: num(kappa.neural_vs_truth),
      kappaVotingVsTruth: num(kappa.voting_vs_truth),
    }
  })

  async function load(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const data = await api.get<any>('/benchmark/results')
      provenance.value = (data?.provenance as BenchmarkProvenance) ?? null
      rawExp1.value = data?.experiment1 ?? null
      rawExp2.value = data?.experiment2 ?? null
      rows.value = mapRows(data?.per_query)
      questions.value = mapQuestions(data?.per_question)
    } catch (e) {
      // 不填充任何 fallback 数值：置空 + 抛友好错误，由视图渲染空态
      provenance.value = null
      rawExp1.value = null
      rawExp2.value = null
      rows.value = []
      questions.value = []
      error.value = friendlyError(e, '基准数据加载失败')
    } finally {
      loading.value = false
    }
  }

  return { loading, error, provenance, rows, questions, summary, load }
}
