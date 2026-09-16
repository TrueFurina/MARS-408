import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

import { useEvidenceConclusions } from '@/composables/useEvidenceConclusions'

/**
 * 结论看板防回归
 *
 * 目的：结论卡里的**头条指标必须等于真实产物字段**（不许手写/漂移）。
 * 手法：直接读 py-server/experiments/results/ 下的真实文件，按后端 /api/experiments/{name}
 * 的响应结构组装 payload，断言 composable 提取值 == 文件值。
 *
 * 红线：产物缺失或接口失败 → 该结论不渲染 / conclusions 置空 + 报错，**绝不编造数值**。
 */

const RESULTS_DIR = resolve(process.cwd(), 'py-server/experiments/results')

function loadReal(name: string): any {
  const p = resolve(RESULTS_DIR, `${name}.json`)
  if (!existsSync(p)) {
    throw new Error(
      `真产物缺失：${p}\n这不是测试写错，而是证据链断了。请先跑 npm run gate:evidence 定位。`,
    )
  }
  return JSON.parse(readFileSync(p, 'utf-8'))
}

function detailResponse(name: string) {
  return {
    name,
    file: `${name}.json`,
    provenance: {
      source: `${RESULTS_DIR}/${name}.json`,
      size_bytes: 1234,
      modified: '2026-09-14T00:00:00',
      sha256: `sha-of-${name}`.padEnd(64, '0'),
    },
    data: loadReal(name),
  }
}

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    blob: async () => new Blob(),
    text: async () => JSON.stringify(body),
  } as unknown as Response
}

/** 按 URL 末段路由到对应真实产物 */
function routeFetch() {
  return vi.fn(async (url: string) => {
    const m = String(url).match(/\/experiments\/([^/?]+)$/)
    if (!m) return jsonResponse(404, { detail: 'not found' })
    return jsonResponse(200, detailResponse(decodeURIComponent(m[1]!)))
  })
}

describe('useEvidenceConclusions 结论看板', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = routeFetch()
    ;(globalThis as any).fetch = fetchMock
  })
  afterEach(() => {
    vi.restoreAllMocks()
    delete (globalThis as any).fetch
  })

  it('渲染出六条结论，且指标数值等于真实文件字段', async () => {
    const accept = loadReal('accept_review')
    const marl = loadReal('marl_algorithms_eval_20260912')
    const budget = loadReal('tune_shadow_budget')
    const calib = loadReal('diag_calib_alignment')
    const bench = loadReal('benchmark_2026-08-17')
    const career = loadReal('career_mappo_train_20260914')

    const c = useEvidenceConclusions()
    const out = await c.load()

    expect(c.error.value).toBeNull()
    expect(out.length).toBe(6)
    const ids = out.map((x) => x.id).sort()
    expect(ids).toEqual([
      'budget-sensitivity',
      'calib-alignment',
      'career-mappo',
      'marl-algorithms',
      'retrieval-benchmark',
      'review-analytic',
    ])

    // 评审线：解析式 main 捕获率必须等于文件值（100.0%）
    const review = out.find((x) => x.id === 'review-analytic')!
    const capMain = review.metrics.find((m) => m.label === '解析式 capture (main)')!
    expect(capMain.value).toBe(`${accept.main.arms.analytic.capture_pct.toFixed(1)}%`)

    // MARL：MAPPO beginner 奖励等于文件值
    const ml = out.find((x) => x.id === 'marl-algorithms')!
    const rw = ml.metrics.find((m) => m.label === 'MAPPO 奖励(beginner)')!
    expect(rw.value).toBe(marl.levels.beginner.mappo.avg_reward.mean.toFixed(2))

    // 预算：最优 capture(main) 等于文件中 main 捕获率的最大值
    const bud = out.find((x) => x.id === 'budget-sensitivity')!
    const bestCapture = Math.max(...budget.rows.map((r: any) => r.main.capture_pct))
    const bestMetric = bud.metrics.find((m) => m.label === '最优 capture (main)')!
    expect(bestMetric.value).toBe(`${bestCapture.toFixed(1)}%`)

    // 校准：R1 最差 smd 等于文件值（3 位小数）
    const ca = out.find((x) => x.id === 'calib-alignment')!
    const smd = ca.metrics.find((m) => m.label === 'R1 最差 smd')!
    expect(smd.value).toBe(calib.R1_distribution_alignment.worst_std_mean_diff.toFixed(3))

    // 检索线：召回@5 等于文件值（百分数 1 位小数），且如实呈现延迟倍数
    const rb = out.find((x) => x.id === 'retrieval-benchmark')!
    const recall = rb.metrics.find((m) => m.label === 'FrugalRAG 召回@5')!
    const fr = bench.experiment1.summary.frugalrag
    const fu = bench.experiment1.summary.full_retrieval
    expect(recall.value).toBe(`${(fr['mean_recall@5'] * 100).toFixed(1)}%`)
    const mult = rb.metrics.find((m) => m.label === '延迟倍数')!
    expect(mult.value).toBe(`≈${(fr.mean_latency_ms / fu.mean_latency_ms).toFixed(0)}×`)
    // 召回提升是"比例差 × 100"的百分点（0.1071 → "+10.7pp"），防止再犯 ×100 遗漏
    const pp = rb.metrics.find((m) => m.label === '召回提升')!
    expect(pp.value).toBe(`+${(bench.experiment1.summary.deltas.recall_delta * 100).toFixed(1)}pp`)

    // 职业素养线：训练轮数与环境来源等于文件值
    const cm = out.find((x) => x.id === 'career-mappo')!
    expect(cm.metrics.find((m) => m.label === '训练轮数')!.value).toBe(String(career.train.episodes))
    expect(cm.metrics.find((m) => m.label === '环境来源')!.value).toBe(career.meta.environment_source)
    expect(cm.metrics.find((m) => m.label === 'passed')!.value).toBe(String(career.passed))
  })

  it('每条结论都携带产物溯源(sha256)', async () => {
    const c = useEvidenceConclusions()
    const out = await c.load()
    for (const conc of out) {
      expect(conc.artifacts.length).toBeGreaterThan(0)
      expect(conc.artifacts[0]!.sha256).toBeTruthy()
      expect(conc.artifacts[0]!.file.endsWith('.json')).toBe(true)
    }
  })

  it('接口全部失败 → conclusions 置空 + 报错，绝不编造（红线）', async () => {
    ;(globalThis as any).fetch = vi.fn(async () => jsonResponse(500, { detail: 'boom' }))

    const c = useEvidenceConclusions()
    const out = await c.load()

    expect(out).toEqual([])
    expect(c.conclusions.value).toEqual([])
    expect(c.error.value).toBeTruthy()
    expect(c.loading.value).toBe(false)
  })
})
