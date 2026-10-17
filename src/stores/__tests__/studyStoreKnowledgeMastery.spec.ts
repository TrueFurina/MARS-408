import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '@/utils/api'
import { useStudyStore, type KnowledgePoint } from '@/stores/studyStore'

// ─────────────────────────────────────────────────────────────────────────────
// 防回归：studyStore.fetchKnowledgeMastery（GET /quiz/knowledge-mastery）此前零覆盖。
// 它是 MasteryMapView 知识点下钻的唯一数据源，契约要点：
//   1) 请求路径与 subject 查询串拼装正确（含 encodeURIComponent）
//   2) 成功时把 knowledge_points 写入 store 并原样返回
//   3) 成功但结构异常时不把 store 打空（宁可留旧值也不显示假空态）
// 注：最后一条「后端报错 → 静默返回 []」是当前实现的**缺陷表征**（见缺陷 D1），
//     不是期望行为；修复后本用例必须同步改写。
// ─────────────────────────────────────────────────────────────────────────────

vi.mock('@/utils/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/utils/api')>()
  return {
    ...actual,
    api: { ...actual.api, get: vi.fn() },
  }
})

const get = vi.mocked(api.get)

function kp(over: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    subject: 'data_structures',
    chapter: 'tree',
    mastery: 0.5,
    success_count: 3,
    error_count: 1,
    total: 4,
    ...over,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  get.mockReset()
})

describe('studyStore.fetchKnowledgeMastery', () => {
  it('成功时请求不带 subject 的端点，并把 knowledge_points 写入 store 且原样返回', async () => {
    const rows = [kp({ chapter: 'tree', mastery: 0.8 }), kp({ chapter: 'hash', mastery: null })]
    get.mockResolvedValue({ knowledge_points: rows, total: 2 })

    const store = useStudyStore()
    const res = await store.fetchKnowledgeMastery()

    expect(get).toHaveBeenCalledTimes(1)
    expect(get).toHaveBeenLastCalledWith('/quiz/knowledge-mastery')
    expect(res).toHaveLength(2)
    expect(res[1]!.mastery).toBeNull() // null 必须原样透传，不许插值成 0
    expect(store.knowledgePoints).toHaveLength(2)
    expect(store.knowledgePoints[0]!.chapter).toBe('tree')
  })

  it('传入 subject 时拼进 query string 并做 encodeURIComponent', async () => {
    get.mockResolvedValue({ knowledge_points: [], total: 0 })
    const store = useStudyStore()

    await store.fetchKnowledgeMastery('data_structures')
    expect(get).toHaveBeenLastCalledWith('/quiz/knowledge-mastery?subject=data_structures')

    await store.fetchKnowledgeMastery('a b&c')
    expect(get).toHaveBeenLastCalledWith('/quiz/knowledge-mastery?subject=a%20b%26c')
  })

  it('subject 为空字符串时不带 query（falsy 短路，不留悬空 ?subject=）', async () => {
    get.mockResolvedValue({ knowledge_points: [], total: 0 })
    const store = useStudyStore()

    await store.fetchKnowledgeMastery('')
    expect(get).toHaveBeenLastCalledWith('/quiz/knowledge-mastery')
  })

  it('成功但返回体结构异常时返回空数组，且不把 store 里已有数据打空', async () => {
    const store = useStudyStore()
    store.knowledgePoints = [kp({ chapter: 'tree' })]
    get.mockResolvedValue({ total: 0 }) // 缺 knowledge_points

    const res = await store.fetchKnowledgeMastery()
    expect(res).toEqual([])
    expect(store.knowledgePoints).toHaveLength(1)
  })

  it('成功但确实没有知识点时，store 被同步清空（真实空态，而非保留上一次的旧数）', async () => {
    const store = useStudyStore()
    store.knowledgePoints = [kp({ chapter: 'tree' })]
    get.mockResolvedValue({ knowledge_points: [], total: 0 })

    const res = await store.fetchKnowledgeMastery()
    expect(res).toEqual([])
    expect(store.knowledgePoints).toEqual([])
  })

  // D1：后端报错时必须**抛出**，不得吞成空数组 —— 否则调用方（MasteryMapView 的
  // Promise.all）拿不到任何错误信号，只能把「请求失败」渲染成「暂无知识点掌握度数据」
  // 的空态，把故障伪装成"用户还没练过"。失败时 store 里的旧值也不得被清空或改写成 []。
  it('后端报错时必须抛出（不吞成空数组），且保留原有错误信息与旧值', async () => {
    const store = useStudyStore()
    store.knowledgePoints = [kp({ chapter: 'tree' })]
    get.mockRejectedValue(new Error('后端 500'))

    // 原始错误信息必须透传出来（而不是被替换成一句无上下文的通用文案）
    await expect(store.fetchKnowledgeMastery()).rejects.toThrow(/后端 500/)
    // 失败不得破坏已有状态：既不打空，也不写成 []
    expect(store.knowledgePoints).toHaveLength(1)
    expect(store.knowledgePoints[0]!.chapter).toBe('tree')
  })

  it('后端报错被抛出后，与「成功但确实没数据」必须可区分（后者 resolve 且清空）', async () => {
    const store = useStudyStore()
    store.knowledgePoints = [kp({ chapter: 'tree' })]

    // 成功但无数据 → resolve 空数组，且 store 被同步清空
    get.mockResolvedValue({ knowledge_points: [], total: 0 })
    await expect(store.fetchKnowledgeMastery()).resolves.toEqual([])
    expect(store.knowledgePoints).toEqual([])

    // 失败 → reject，store 保持清空前的最后一次成功结果不动
    store.knowledgePoints = [kp({ chapter: 'hash' })]
    get.mockRejectedValue(new Error('连接被重置'))
    await expect(store.fetchKnowledgeMastery()).rejects.toThrow()
    expect(store.knowledgePoints).toHaveLength(1)
    expect(store.knowledgePoints[0]!.chapter).toBe('hash')
  })
})
