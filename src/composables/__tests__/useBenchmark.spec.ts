import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { useBenchmark } from '@/composables/useBenchmark'

/**
 * 证据链前端侧防回归（与 tests/benchmark_evidence_gate.py 互补）
 *
 * 背景：BenchmarkView 曾把四组聚合数硬编码为常量，注释谎称来自"真实输出"
 * （实为 benchmark.py --demo 的合成产物）。清理后，前端数字的唯一来源是
 * /api/benchmark/results。
 *
 * 本测试守住两条红线：
 *   ① 失败即空 —— 接口 4xx/网络异常时 rows/questions/provenance 必须置空、
 *      summary 必须为 null，**绝不回退到示例数值**（否则视图会渲染出假数据）。
 *   ② 字段映射 —— composable 必须从真产物结构（recall@5 / per_query /
 *      per_question.trials）正确取数，键名漂移要立刻暴露。
 *
 * 端到端契约（接口是否真的返回该结构）由 tests/benchmark_evidence_gate.py R3 守。
 */

const REAL_RESULTS_DIR = resolve(process.cwd(), 'py-server/experiments/results')

/**
 * 选取最新真产物（与后端 api/benchmark.py `_latest_real_result` 同规则：
 * benchmark_*.json、排除 reproduce/exp2 复现文件；mode 校验由门禁 R2/R3 负责）。
 * 权威挑选逻辑在后端，此处只为测试夹具取最新样本——若两处规则漂移，
 * tests/benchmark_evidence_gate.py 会先红。
 */
function latestRealArtifactPath(): string {
  const files = readdirSync(REAL_RESULTS_DIR)
    .filter((f) => f.startsWith('benchmark_') && f.endsWith('.json'))
    .filter((f) => !f.includes('reproduce') && !f.includes('exp2'))
    .sort()
  if (files.length === 0) {
    throw new Error(
      `真产物缺失：${REAL_RESULTS_DIR} 下无 benchmark_*.json\n` +
        '这不是测试写错，而是证据链断了。请先跑 tests/benchmark_evidence_gate.py 定位。',
    )
  }
  return resolve(REAL_RESULTS_DIR, files[files.length - 1])
}

function loadRealArtifact(): any {
  const path = latestRealArtifactPath()
  return JSON.parse(readFileSync(path, 'utf-8'))
}

function toApiPayload(data: any) {
  const exp1 = data?.experiment1 ?? {}
  const exp2 = data?.experiment2 ?? {}
  const fileName = latestRealArtifactPath().split(/[\\/]/).pop() ?? 'benchmark.json'
  return {
    provenance: {
      source_file: `experiments/results/${fileName}`,
      file_name: fileName,
      file_mtime: '',
      file_size_bytes: 0,
      mode: 'real',
      n_queries: exp1.summary?.n_queries ?? null,
      n_questions: exp2.summary?.n_questions ?? null,
      n_trials_per_question: exp2.summary?.n_trials_per_question ?? null,
      random_seed: data?.meta?.random_seed ?? null,
      benchmark_date: data?.meta?.date ?? null,
      env: data?.meta?.env ?? {},
    },
    meta: data?.meta ?? {},
    experiment1: exp1.summary ?? {},
    experiment2: exp2.summary ?? {},
    per_query: exp1.per_query ?? [],
    per_question: exp2.per_question ?? [],
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

describe('useBenchmark 证据链', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    ;(globalThis as any).fetch = fetchMock
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete (globalThis as any).fetch
  })

  it('从真产物结构正确取数（行数 / 题数 / 关键 delta）', async () => {
    const data = loadRealArtifact()
    const payload = toApiPayload(data)
    fetchMock.mockResolvedValue(jsonResponse(200, payload))

    const bm = useBenchmark()
    await bm.load()

    expect(bm.error.value).toBeNull()
    expect(bm.provenance.value?.mode).toBe('real')
    // 行数必须与真产物明细条数一致（不是硬编码的 10）
    expect(bm.rows.value.length).toBe(data.experiment1.per_query.length)
    expect(bm.questions.value.length).toBe(data.experiment2.per_question.length)
    expect(bm.rows.value.length).toBeGreaterThan(0)
    expect(bm.questions.value.length).toBeGreaterThan(0)

    // summary 必须来自产物，而非本地计算出的常量
    expect(bm.summary.value?.recallDelta).toBeCloseTo(
      data.experiment1.summary.deltas.recall_delta,
      6,
    )
    expect(bm.summary.value?.neuralAccuracy).toBeCloseTo(
      data.experiment2.summary.neural_mixer.accuracy,
      6,
    )
    // 请求必须打到唯一入口
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/benchmark/results')
  })

  it('逐条明细字段映射正确（recall@5 等键名漂移即失败）', async () => {
    const data = loadRealArtifact()
    const src = data.experiment1.per_query[0]
    fetchMock.mockResolvedValue(jsonResponse(200, toApiPayload(data)))

    const bm = useBenchmark()
    await bm.load()

    const row = bm.rows.value[0]
    expect(row?.id).toBe(String(src.id))
    expect(row?.query).toBe(String(src.query))
    expect(row?.frugalRecall).toBeCloseTo(src.frugalrag['recall@5'], 6)
    expect(row?.fullRecall).toBeCloseTo(src.full_retrieval['recall@5'], 6)
    expect(row?.frugalLatency).toBeCloseTo(src.frugalrag['latency_ms'], 6)
    expect(row?.fullLatency).toBeCloseTo(src.full_retrieval['latency_ms'], 6)
  })

  it('逐题 trials 聚合正确（答对次数与平均共识分）', async () => {
    const data = loadRealArtifact()
    const src = data.experiment2.per_question[0]
    fetchMock.mockResolvedValue(jsonResponse(200, toApiPayload(data)))

    const bm = useBenchmark()
    await bm.load()

    const expectedNeural = src.trials.filter((t: any) => t?.neural_mixer?.correct === true).length
    const q = bm.questions.value[0]
    expect(q?.neuralCorrect).toBe(expectedNeural)
    expect(q?.nTrials).toBeGreaterThan(0)
    expect(q?.nTrials).toBeLessThanOrEqual(3)
  })

  it('接口 404 时必须置空且报错，绝不回退示例数值（红线①）', async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { detail: '未找到真实 benchmark 产物' }))

    const bm = useBenchmark()
    await bm.load()

    expect(bm.rows.value).toEqual([])
    expect(bm.questions.value).toEqual([])
    expect(bm.provenance.value).toBeNull()
    // summary 为 null ⇒ 视图渲染空态，而不是渲染 0 或任何编造数字
    expect(bm.summary.value).toBeNull()
    expect(bm.error.value).toBeTruthy()
    expect(bm.loading.value).toBe(false)
  })

  it('网络异常时同样不得编造数据（红线①）', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const bm = useBenchmark()
    await bm.load()

    expect(bm.rows.value).toEqual([])
    expect(bm.questions.value).toEqual([])
    expect(bm.summary.value).toBeNull()
    expect(bm.error.value).toBeTruthy()
    // 站内文案统一：应提示后端未连接，而不是抛原始栈信息
    expect(bm.error.value).toContain('后端服务未连接')
  })

  it('接口返回空明细时呈现空态而非补零（红线①的边界）', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, {
        provenance: { mode: 'real', source_file: 'x.json' },
        experiment1: { n_queries: 0 },
        experiment2: { n_questions: 0 },
        per_query: [],
        per_question: [],
      }),
    )

    const bm = useBenchmark()
    await bm.load()

    expect(bm.error.value).toBeNull()
    expect(bm.rows.value).toEqual([])
    expect(bm.questions.value).toEqual([])
  })
})
