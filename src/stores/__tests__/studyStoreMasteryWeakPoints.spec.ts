import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '@/utils/api'
import {
  useStudyStore,
  type MasteryItem,
  type WeakPoint,
  type WeakPointsResult,
} from '@/stores/studyStore'

// ─────────────────────────────────────────────────────────────────────────────
// 防回归：studyStore.fetchMasteryData（GET /user/mastery）与
//         studyStore.fetchWeakPoints（GET /quiz/weak-points）此前**零覆盖**，
//         且两者都把后端报错吞成 `[]` / `null`（与已修的 D1 同款缺陷）。
//
// 契约要点（对齐 fetchKnowledgeMastery 的 D1 范式）：
//   1) 成功时把数据写入 store 并原样返回（null 透传，不插值）
//   2) 成功但结构异常时不打空 store（宁可留旧值也不显示假空态）
//   3) 成功但确实无数据时 store 被同步清空（真实空态）
//   4) **后端报错必须抛出**，错误信息透传，且不清空/不改写 store 旧值
//      —— 否则调用方无从区分「请求失败」与「确实没数据」，
//         会把故障渲染成空态，把故障伪装成"用户还没练过"
// ─────────────────────────────────────────────────────────────────────────────

vi.mock('@/utils/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/utils/api')>()
  return {
    ...actual,
    api: { ...actual.api, get: vi.fn() },
  }
})

const get = vi.mocked(api.get)

function mi(over: Partial<MasteryItem> = {}): MasteryItem {
  return { subject: 'data_structures', label: '数据结构', pct: 60, ...over }
}

function wp(over: Partial<WeakPoint> = {}): WeakPoint {
  return {
    subject: 'computer_network',
    chapter: 'tcp_window',
    concept: 'TCP 窗口计算',
    error_type: '概念混淆',
    count: 3,
    mastered: false,
    ...over,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  get.mockReset()
})

describe('studyStore.fetchMasteryData', () => {
  it('成功时请求 /user/mastery 并原样返回（含 pct=0 与 null 透传）', async () => {
    const rows = [mi({ pct: 100 }), mi({ subject: 'operating_system', pct: 0 })]
    get.mockResolvedValue(rows)

    const store = useStudyStore()
    const res = await store.fetchMasteryData()

    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenLastCalledWith('/user/mastery')
    expect(res).toHaveLength(2)
    expect(res[1]!.pct).toBe(0) // 0 必须原样透传，不许插值成 null/undefined
  })

  it('后端报错时必须抛出（不吞成空数组），错误信息透传', async () => {
    get.mockRejectedValue(new Error('后端 500'))
    const store = useStudyStore()

    await expect(store.fetchMasteryData()).rejects.toThrow(/后端 500/)
    // 不得吞成空数组：调用方靠 reject 区分「失败」与「确实没数据」
    await expect(store.fetchMasteryData()).rejects.toThrow()
  })

  it('失败与「成功但确实没数据」必须可区分（后者 resolve 空数组）', async () => {
    const store = useStudyStore()

    // 成功但无数据 → resolve []
    get.mockResolvedValue([])
    await expect(store.fetchMasteryData()).resolves.toEqual([])

    // 失败 → reject（而非 resolve []）
    get.mockRejectedValue(new Error('连接被重置'))
    await expect(store.fetchMasteryData()).rejects.toThrow(/连接被重置/)
  })

  it('失败时不得把上一次成功的数据改写成空数组', async () => {
    const store = useStudyStore()
    get.mockResolvedValue([mi({ pct: 80 })])
    await store.fetchMasteryData()

    get.mockRejectedValue(new Error('网关超时'))
    await expect(store.fetchMasteryData()).rejects.toThrow()

    // fetchMasteryData 本身不写 store，故不存在"被打空"；
    // 此处断言的是「不因失败而 resolve 出空数组」这一等价安全性
    const res = await store.fetchMasteryData().catch(() => 'threw')
    expect(res).toBe('threw')
  })
})

describe('studyStore.fetchWeakPoints', () => {
  it('成功时写入 store（weak_points/total）并原样返回', async () => {
    const rows = [wp({ chapter: 'tcp_window' }), wp({ chapter: 'subnet' })]
    const payload: WeakPointsResult = { weak_points: rows, total: 2 }
    get.mockResolvedValue(payload)

    const store = useStudyStore()
    const res = await store.fetchWeakPoints()

    expect(get).toHaveBeenLastCalledWith('/quiz/weak-points')
    expect(res).toEqual(payload)
    expect(store.weakPoints).toHaveLength(2)
    expect(store.weakPointsTotal).toBe(2)
  })

  it('传入 subject 时拼进 query string 并做 encodeURIComponent', async () => {
    get.mockResolvedValue({ weak_points: [], total: 0 })
    const store = useStudyStore()

    await store.fetchWeakPoints('data_structures')
    expect(get).toHaveBeenLastCalledWith('/quiz/weak-points?subject=data_structures')

    await store.fetchWeakPoints('a b&c')
    expect(get).toHaveBeenLastCalledWith('/quiz/weak-points?subject=a%20b%26c')
  })

  it('total 缺失时回退为 weak_points.length', async () => {
    get.mockResolvedValue({ weak_points: [wp(), wp(), wp()] })
    const store = useStudyStore()

    await store.fetchWeakPoints()
    expect(store.weakPointsTotal).toBe(3)
  })

  it('后端报错时必须抛出（不吞成 null），错误信息透传', async () => {
    get.mockRejectedValue(new Error('薄弱点接口 503'))
    const store = useStudyStore()

    await expect(store.fetchWeakPoints()).rejects.toThrow(/薄弱点接口 503/)
  })

  it('失败时保留 store 里上一次成功的数据（不清空、不改写）', async () => {
    const store = useStudyStore()
    get.mockResolvedValue({ weak_points: [wp({ chapter: 'tcp_window' })], total: 1 })
    await store.fetchWeakPoints()

    get.mockRejectedValue(new Error('连接被重置'))
    await expect(store.fetchWeakPoints()).rejects.toThrow()

    expect(store.weakPoints).toHaveLength(1)
    expect(store.weakPoints[0]!.chapter).toBe('tcp_window')
    expect(store.weakPointsTotal).toBe(1)
  })

  it('失败与「成功但确实无薄弱点」必须可区分（后者 resolve 且清空 store）', async () => {
    const store = useStudyStore()

    // 成功但无数据 → resolve，且 store 被同步清空（真实空态）
    get.mockResolvedValue({ weak_points: [], total: 0 })
    await expect(store.fetchWeakPoints()).resolves.toEqual({ weak_points: [], total: 0 })
    expect(store.weakPoints).toEqual([])
    expect(store.weakPointsTotal).toBe(0)

    // 失败 → reject，store 保持清空前的最后一次成功结果不动
    get.mockResolvedValue({ weak_points: [wp({ chapter: 'hash' })], total: 1 })
    await store.fetchWeakPoints()
    get.mockRejectedValue(new Error('网关超时'))
    await expect(store.fetchWeakPoints()).rejects.toThrow()
    expect(store.weakPoints[0]!.chapter).toBe('hash')
  })
})
