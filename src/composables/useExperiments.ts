/**
 * useExperiments —— 真实实验产物（证据画廊）的唯一前端入口
 *
 * 【背景 2026-09-16 · 后端变现】
 *   py-server/experiments/results/ 下沉淀了 51 份 mode=real 的真实实验产物
 *   （career_mappo_train / diag_calib_alignment / review_mappo_* /
 *    review_shadow_summary_* / sweep_shadow_budget_* / benchmark_* 等），
 *   是平台相对"PPT 项目"的决定性护城河，但此前仅 benchmark 被接通。
 *   本模块对接新后端接口 GET /api/experiments（列表）与 /api/experiments/{name}（明细）。
 *
 * 【P1 契约层】响应类型优先取自 src/types/api.generated.ts（由 py-server/openapi.json
 *   自动生成），不再手写 any —— 后端返回 Dict[str, Any] 时生成类型为
 *   { [key: string]: unknown }，本模块以精确接口收窄，保持契约层是单一真值源。
 *
 * 【纪律（与 useBenchmark 对齐）】
 *   · 不提供任何 fallback 数值：接口失败 → items 为空、detail 为 null，
 *     由视图渲染空态，绝不回退到示例/合成数据。
 *   · provenance（来源文件 + sha256）必须被视图原样展示，使每份证据可溯源。
 */

import { ref, computed, type Ref } from 'vue'
import { api, friendlyError } from '@/utils/api'
import type { operations } from '@/types/api.generated'

/* ── 契约锚点：直接引用 OpenAPI 生成的 operation 类型 ── */
type ListOp = operations['list_experiments_api_experiments_get']
type DetailOp = operations['get_experiment_api_experiments__name__get']
type ListResponseContract = ListOp['responses'][200]['content']['application/json']
type DetailResponseContract = DetailOp['responses'][200]['content']['application/json']

export interface ExperimentMeta {
  name: string
  file: string
  category: string
  title: string
  mode: string | null
  real: boolean
  size_bytes: number
  modified: string | null
  keys: string[]
  read_error?: string
}

export interface ExperimentProvenance {
  source: string
  size_bytes: number
  modified: string
  sha256: string
}

export interface ExperimentDetail {
  name: string
  file: string
  provenance: ExperimentProvenance
  data: unknown
}

export interface ExperimentList {
  count: number
  results_dir: string
  items: ExperimentMeta[]
}

export interface CategoryBucket {
  category: string
  count: number
}

function asList(raw: ListResponseContract): ExperimentList {
  const d = raw as unknown as Partial<ExperimentList>
  return {
    count: typeof d.count === 'number' ? d.count : 0,
    results_dir: typeof d.results_dir === 'string' ? d.results_dir : '',
    items: Array.isArray(d.items) ? (d.items as ExperimentMeta[]) : [],
  }
}

function asDetail(raw: DetailResponseContract): ExperimentDetail {
  return raw as unknown as ExperimentDetail
}

export function useExperiments() {
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)
  const items: Ref<ExperimentMeta[]> = ref([])
  const resultsDir: Ref<string | null> = ref(null)
  const detail: Ref<ExperimentDetail | null> = ref(null)

  /** 按分类聚合（用于过滤芯片），按数量降序 */
  const categories = computed<CategoryBucket[]>(() => {
    const m = new Map<string, number>()
    for (const it of items.value) {
      m.set(it.category, (m.get(it.category) ?? 0) + 1)
    }
    return [...m.entries()]
      .map(([category, count]) => ({ category, count }))
      .sort((a, b) => b.count - a.count || a.category.localeCompare(b.category))
  })

  async function loadList(params?: { category?: string; realOnly?: boolean }): Promise<ExperimentMeta[]> {
    loading.value = true
    error.value = null
    try {
      const qs = new URLSearchParams()
      if (params?.category) qs.set('category', params.category)
      if (params?.realOnly) qs.set('real_only', 'true')
      const suffix = qs.toString() ? `?${qs.toString()}` : ''
      const raw = await api.get<ListResponseContract>(`/experiments${suffix}`)
      const d = asList(raw)
      items.value = d.items
      resultsDir.value = d.results_dir || null
      return d.items
    } catch (e) {
      // 不填充任何 fallback 数据：置空 + 友好错误，由视图渲染空态
      items.value = []
      resultsDir.value = null
      error.value = friendlyError(e, '实验证据加载失败')
      return []
    } finally {
      loading.value = false
    }
  }

  async function loadDetail(name: string): Promise<ExperimentDetail | null> {
    loading.value = true
    error.value = null
    try {
      const raw = await api.get<DetailResponseContract>(`/experiments/${encodeURIComponent(name)}`)
      const d = asDetail(raw)
      detail.value = d
      return d
    } catch (e) {
      detail.value = null
      error.value = friendlyError(e, '产物详情加载失败')
      return null
    } finally {
      loading.value = false
    }
  }

  function clearDetail(): void {
    detail.value = null
  }

  return {
    loading,
    error,
    items,
    resultsDir,
    categories,
    detail,
    loadList,
    loadDetail,
    clearDetail,
  }
}
