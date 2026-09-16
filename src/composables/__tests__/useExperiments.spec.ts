import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { useExperiments } from '@/composables/useExperiments'

/**
 * 真实证据画廊前端侧防回归
 *
 * 背景：后端新增 GET /api/experiments 暴露 py-server/experiments/results/ 下
 * 51 份真实产物。本测试守住三条红线：
 *   ① 失败即空 —— 接口 4xx/网络异常时 items 必须置空、detail 必须为 null，
 *      **绝不回退到示例/合成数据**（否则视图会渲染假证据）。
 *   ② 映射不丢字段 —— 列表项与 provenance(sha256) 必须原样透传，键名漂移即失败。
 *   ③ 请求打到唯一入口 —— 必须 /api/experiments，且 real_only 作为查询参数传递。
 *
 * 端到端契约（接口是否真的返回该结构）由 `npm run verify` 门禁与后端实测守。
 */

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    blob: async () => new Blob(),
    text: async () => JSON.stringify(body),
  } as unknown as Response
}

/** 与后端 /api/experiments 实测响应同构（2026-09-16 实测 count=51） */
function listPayload() {
  return {
    count: 3,
    results_dir: 'E:/Program/MARL/study-help-pro/py-server/experiments/results',
    items: [
      {
        name: 'benchmark_2026-08-17',
        file: 'benchmark_2026-08-17.json',
        category: '检索基准',
        title: 'benchmark',
        mode: 'real',
        real: true,
        size_bytes: 261662,
        modified: '2026-08-17T12:00:00',
        keys: ['experiment1', 'experiment2', 'meta'],
      },
      {
        name: 'career_mappo_train_20260914',
        file: 'career_mappo_train_20260914.json',
        category: '职业素养 MAPPO',
        title: 'career mappo train',
        mode: null,
        real: true,
        size_bytes: 1024,
        modified: '2026-09-14T22:00:00',
        keys: ['meta', 'train'],
      },
      {
        name: 'career_mappo_train_20260913',
        file: 'career_mappo_train_20260913.json',
        category: '职业素养 MAPPO',
        title: 'career mappo train',
        mode: null,
        real: true,
        size_bytes: 900,
        modified: '2026-09-13T22:00:00',
        keys: ['meta', 'train'],
      },
    ],
  }
}

function detailPayload() {
  return {
    name: 'benchmark_2026-08-17',
    file: 'benchmark_2026-08-17.json',
    provenance: {
      source: 'E:/Program/MARL/study-help-pro/py-server/experiments/results/benchmark_2026-08-17.json',
      size_bytes: 261662,
      modified: '2026-08-17T12:00:00',
      sha256: '88983a78476ec6e1024a' + '0'.repeat(44),
    },
    data: { meta: { random_seed: 20260719 }, experiment1: { n_queries: 28 } },
  }
}

describe('useExperiments 证据画廊', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    ;(globalThis as any).fetch = fetchMock
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete (globalThis as any).fetch
  })

  it('正确透传列表项，并按分类聚合', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, listPayload()))

    const ex = useExperiments()
    const items = await ex.loadList({ realOnly: true })

    expect(ex.error.value).toBeNull()
    expect(items.length).toBe(3)
    expect(ex.items.value[0]?.name).toBe('benchmark_2026-08-17')
    expect(ex.items.value[0]?.real).toBe(true)
    expect(ex.resultsDir.value).toContain('experiments/results')

    // 分类聚合：职业素养 MAPPO=2 排最前，检索基准=1
    const cats = ex.categories.value
    expect(cats[0]).toEqual({ category: '职业素养 MAPPO', count: 2 })
    expect(cats).toContainEqual({ category: '检索基准', count: 1 })
  })

  it('请求打到唯一入口 /api/experiments，且 real_only 作为查询参数', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, listPayload()))

    const ex = useExperiments()
    await ex.loadList({ realOnly: true })

    const url = String(fetchMock.mock.calls[0]?.[0])
    expect(url).toContain('/api/experiments')
    expect(url).toContain('real_only=true')
  })

  it('明细透传 provenance(sha256) 与 data', async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, detailPayload()))

    const ex = useExperiments()
    const d = await ex.loadDetail('benchmark_2026-08-17')

    expect(d?.provenance.sha256.startsWith('88983a78')).toBe(true)
    expect(d?.provenance.size_bytes).toBe(261662)
    expect((d?.data as any)?.experiment1?.n_queries).toBe(28)
    // 明细请求打成 /api/experiments/{name}
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/experiments/benchmark_2026-08-17')
  })

  it('接口 404 时必须置空且报错，绝不回退示例数据（红线①）', async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { detail: '未找到真实产物' }))

    const ex = useExperiments()
    const items = await ex.loadList()

    expect(items).toEqual([])
    expect(ex.items.value).toEqual([])
    expect(ex.resultsDir.value).toBeNull()
    expect(ex.error.value).toBeTruthy()
    expect(ex.loading.value).toBe(false)
  })

  it('网络异常时同样不得编造数据（红线①）', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const ex = useExperiments()
    await ex.loadList()

    expect(ex.items.value).toEqual([])
    expect(ex.error.value).toBeTruthy()
    expect(ex.error.value).toContain('后端服务未连接')
  })

  it('空列表呈现空态而非补零（红线①的边界）', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, { count: 0, results_dir: '', items: [] }),
    )

    const ex = useExperiments()
    await ex.loadList()

    expect(ex.error.value).toBeNull()
    expect(ex.items.value).toEqual([])
    expect(ex.categories.value).toEqual([])
  })

  it('明细 404 时 detail 置 null 且报错', async () => {
    fetchMock.mockResolvedValue(jsonResponse(404, { detail: '未找到' }))

    const ex = useExperiments()
    const d = await ex.loadDetail('__nope__')

    expect(d).toBeNull()
    expect(ex.detail.value).toBeNull()
    expect(ex.error.value).toBeTruthy()
  })
})
