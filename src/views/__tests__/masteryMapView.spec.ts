import { describe, it, expect, beforeEach, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import type { KnowledgePoint, MasteryItem, WeakPoint } from '@/stores/studyStore'
import { useStudyStore } from '@/stores/studyStore'
import MasteryMapView from '@/views/MasteryMapView.vue'

// ─────────────────────────────────────────────────────────────────────────────
// 防回归：MasteryMapView（P4 掌握度地图）此前是「已实现、零覆盖」状态。
// 本 spec 用假 store（三个动作必须是 vi.fn，可被断言调用）驱动真实组件，
// 只通过**可观测渲染行为**断言，不为测试改动生产结构。
// 覆盖契约：三段状态机 / tierOf 四档 / heatLevel 六档 / CHAPTER_LABELS /
// kpPct(mastery null 不编造) / allZero 占位 / 科目选中联动筛选。
// ─────────────────────────────────────────────────────────────────────────────

vi.mock('@/stores/studyStore', async () => {
  const { reactive } = await import('vue')
  const { vi: viLocal } = await import('vitest')
  const store = reactive({
    weakPoints: [] as WeakPoint[],
    weakPointsTotal: 0,
    knowledgePoints: [] as KnowledgePoint[],
    fetchMasteryData: viLocal.fn(),
    fetchWeakPoints: viLocal.fn(),
    fetchKnowledgeMastery: viLocal.fn(),
  })
  return { useStudyStore: () => store }
})

type MockFn = ReturnType<typeof vi.fn>

interface FakeStudyStore {
  weakPoints: WeakPoint[]
  weakPointsTotal: number
  knowledgePoints: KnowledgePoint[]
  fetchMasteryData: MockFn
  fetchWeakPoints: MockFn
  fetchKnowledgeMastery: MockFn
}

const store = useStudyStore() as unknown as FakeStudyStore

// ── 造数据的小工具（字段与后端真实返回对齐，不引入测试专用假字段）──
function mi(subject: string, label: string, pct: number): MasteryItem {
  return { subject, label, pct }
}
function wp(count: number, over: Partial<WeakPoint> = {}): WeakPoint {
  return {
    subject: 'data_structures',
    chapter: 'tree',
    concept: '二叉搜索树',
    error_type: '概念不清',
    count,
    mastered: false,
    ...over,
  }
}
function kp(mastery: number | null, over: Partial<KnowledgePoint> = {}): KnowledgePoint {
  return {
    subject: 'data_structures',
    chapter: 'tree',
    mastery,
    success_count: 1,
    error_count: 1,
    total: 2,
    ...over,
  }
}

interface Stub {
  mastery?: MasteryItem[]
  weak?: WeakPoint[]
  total?: number
  kps?: KnowledgePoint[]
}
function stubSuccess(s: Stub = {}) {
  store.fetchMasteryData.mockResolvedValue(s.mastery ?? [])
  store.fetchWeakPoints.mockResolvedValue(null)
  store.fetchKnowledgeMastery.mockResolvedValue(s.kps ?? [])
  store.weakPoints = s.weak ?? []
  store.weakPointsTotal = s.total ?? 0
  store.knowledgePoints = s.kps ?? []
}

async function mountLoaded(s: Stub = {}) {
  stubSuccess(s)
  const w = mount(MasteryMapView)
  await flushPromises()
  await nextTick()
  return w
}

function styleOf(el: { attributes: (k: string) => string | undefined }): string {
  return el.attributes('style') ?? ''
}

beforeEach(() => {
  store.weakPoints = []
  store.weakPointsTotal = 0
  store.knowledgePoints = []
  store.fetchMasteryData.mockReset()
  store.fetchWeakPoints.mockReset()
  store.fetchKnowledgeMastery.mockReset()
})

// ─────────────────────────────────────────────────────────────────────────────
describe('MasteryMapView 数据装载与状态机', () => {
  it('挂载时三个数据源各拉取一次且不传参（科目筛选是前端行为，不触发重复请求）', async () => {
    await mountLoaded()
    expect(store.fetchMasteryData).toHaveBeenCalledTimes(1)
    expect(store.fetchWeakPoints).toHaveBeenCalledTimes(1)
    expect(store.fetchKnowledgeMastery).toHaveBeenCalledTimes(1)
    expect(store.fetchKnowledgeMastery).toHaveBeenCalledWith()
    expect(store.fetchMasteryData).toHaveBeenCalledWith()
  })

  it('加载中渲染 4 个骨架屏，数据落地后骨架消失', async () => {
    let resolveMastery!: (v: MasteryItem[]) => void
    store.fetchMasteryData.mockImplementation(
      () => new Promise<MasteryItem[]>((r) => { resolveMastery = r }),
    )
    store.fetchWeakPoints.mockResolvedValue(null)
    store.fetchKnowledgeMastery.mockResolvedValue([])

    const w = mount(MasteryMapView)
    await nextTick()
    expect(w.findAll('.skeleton')).toHaveLength(4)
    expect(w.find('.map-card').exists()).toBe(false)

    resolveMastery([mi('data_structures', '数据结构', 60)])
    await flushPromises()
    await nextTick()
    expect(w.findAll('.skeleton')).toHaveLength(0)
    expect(w.find('.map-card').exists()).toBe(true)
  })

  it('请求失败进入错误态：直出 Error.message 并给出重新加载入口', async () => {
    store.fetchMasteryData.mockRejectedValue(new Error('后端 502'))
    store.fetchWeakPoints.mockResolvedValue(null)
    store.fetchKnowledgeMastery.mockResolvedValue([])

    const w = mount(MasteryMapView)
    await flushPromises()
    await nextTick()

    expect(w.findAll('.skeleton')).toHaveLength(0)
    expect(w.find('.empty-title').text()).toContain('后端 502')
    expect(w.find('button.engine-btn').text()).toContain('重新加载')
    // 错误态不得顺手渲染出一张「看起来有数据」的卡片
    expect(w.find('.map-card').exists()).toBe(false)
  })

  it('失败对象没有 message 时回退到默认文案（不渲染 undefined）', async () => {
    store.fetchMasteryData.mockRejectedValue('boom')
    store.fetchWeakPoints.mockResolvedValue(null)
    store.fetchKnowledgeMastery.mockResolvedValue([])

    const w = mount(MasteryMapView)
    await flushPromises()
    await nextTick()

    expect(w.find('.empty-title').text()).toContain('加载掌握度数据失败')
    expect(w.find('.empty-title').text()).not.toContain('undefined')
  })

  it('点击重新加载会真的再拉一次，成功后退出错误态', async () => {
    store.fetchMasteryData.mockRejectedValueOnce(new Error('后端 502'))
    store.fetchMasteryData.mockResolvedValueOnce([mi('data_structures', '数据结构', 60)])
    store.fetchWeakPoints.mockResolvedValue(null)
    store.fetchKnowledgeMastery.mockResolvedValue([])

    const w = mount(MasteryMapView)
    await flushPromises()
    await nextTick()
    expect(w.find('.empty-title').exists()).toBe(true)

    await w.find('button.engine-btn').trigger('click')
    await flushPromises()
    await nextTick()

    expect(store.fetchMasteryData).toHaveBeenCalledTimes(2)
    expect(store.fetchWeakPoints).toHaveBeenCalledTimes(2)
    expect(store.fetchKnowledgeMastery).toHaveBeenCalledTimes(2)
    expect(w.find('.empty-title').exists()).toBe(false)
    expect(w.findAll('.subject-tile')).toHaveLength(1)
  })

  it('fetchMasteryData 返回 undefined 时不崩、渲染空态（绝不编造占位数据）', async () => {
    store.fetchMasteryData.mockResolvedValue(undefined)
    store.fetchWeakPoints.mockResolvedValue(null)
    store.fetchKnowledgeMastery.mockResolvedValue([])

    const w = mount(MasteryMapView)
    await flushPromises()
    await nextTick()

    expect(w.findAll('.skeleton')).toHaveLength(0)
    expect(w.findAll('.subject-tile')).toHaveLength(0)
    expect(w.find('.map-placeholder').exists()).toBe(false)
    expect(w.find('.weak-empty').text()).toContain('暂无薄弱点数据')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('MasteryMapView 四档分档 tierOf', () => {
  it('边界值 -10/0/1/49/50/74/75/100 落到 未测/未测/薄弱/薄弱/一般/一般/扎实/扎实', async () => {
    const w = await mountLoaded({
      mastery: [
        mi('sNeg', '负十', -10), // 负值也归「未测」：`pct <= 0` 分支（!pct 抓不到负数）
        mi('s0', '零', 0),
        mi('s1', '一', 1),
        mi('s49', '四十九', 49),
        mi('s50', '五十', 50),
        mi('s74', '七十四', 74),
        mi('s75', '七十五', 75),
        mi('s100', '一百', 100),
      ],
    })

    expect(w.findAll('.tile-tier').map((e) => e.text())).toEqual([
      '未测', '未测', '薄弱', '薄弱', '一般', '一般', '扎实', '扎实',
    ])
  })

  it('档位同时驱动色令牌 var(--mastery-*)（标签与配色同源，不允许各写一套）', async () => {
    const w = await mountLoaded({
      mastery: [mi('s0', '零', 0), mi('s49', '四十九', 49), mi('s50', '五十', 50), mi('s75', '七十五', 75)],
    })
    const colors = w.findAll('.tile-tier').map((e) => styleOf(e))
    expect(colors[0]).toContain('var(--mastery-none)')
    expect(colors[1]).toContain('var(--mastery-low)')
    expect(colors[2]).toContain('var(--mastery-mid)')
    expect(colors[3]).toContain('var(--mastery-high)')
  })

  it('梯度图例四档文案与阈值口径一致', async () => {
    const w = await mountLoaded({ mastery: [mi('s1', '一', 80)] })
    const legend = w.find('.tier-legend').text()
    expect(legend).toContain('扎实 (≥75%)')
    expect(legend).toContain('一般 (50–74%)')
    expect(legend).toContain('薄弱 (<50%)')
    expect(legend).toContain('未测 (0%)')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('MasteryMapView allZero 占位', () => {
  it('全部 pct<=0 时展示占位引导，而不是一张全灰的假网格', async () => {
    const w = await mountLoaded({
      mastery: [mi('a', '数据结构', 0), mi('b', '操作系统', 0)],
    })
    expect(w.find('.map-placeholder').text()).toContain('还没有掌握度数据')
    expect(w.find('.subject-grid').exists()).toBe(false)
    expect(w.find('.tier-legend').exists()).toBe(false)
    expect(w.find('.map-hint').text()).toContain('暂无数据')
  })

  it('只要有一个非零就不占位（避免「有一科数据却被占位盖住」）', async () => {
    const w = await mountLoaded({
      mastery: [mi('a', '数据结构', 0), mi('b', '操作系统', 60)],
    })
    expect(w.find('.map-placeholder').exists()).toBe(false)
    expect(w.findAll('.subject-tile')).toHaveLength(2)
  })

  it('空数组不算「全零」——不渲染占位（避免无数据时误报引导）', async () => {
    const w = await mountLoaded({ mastery: [] })
    expect(w.find('.map-placeholder').exists()).toBe(false)
    expect(w.findAll('.subject-tile')).toHaveLength(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('MasteryMapView 薄弱点热力 heatLevel', () => {
  it('错误次数映射到 --seq-1..6 连续色阶（含全部边界）', async () => {
    const counts = [0, 1, 2, 4, 5, 8, 9, 13, 14, 19, 20, 99]
    const expected = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
    const w = await mountLoaded({
      mastery: [mi('a', '数据结构', 60)],
      weak: counts.map((c, i) => wp(c, { concept: `概念${i}` })),
      total: counts.length,
    })

    const heats = w.findAll('.weak-heat').map((e) => styleOf(e))
    expect(heats).toHaveLength(counts.length)
    counts.forEach((_, i) => {
      expect(heats[i]).toContain(`var(--seq-${expected[i]})`)
    })
  })

  it('热力条带出错误次数 title（次数本身不被色阶吞掉）', async () => {
    const w = await mountLoaded({
      mastery: [mi('a', '数据结构', 60)],
      weak: [wp(7)],
      total: 1,
    })
    expect(w.find('.weak-heat').attributes('title')).toBe('错误 7 次')
    expect(w.find('.weak-count-num').text()).toBe('7')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('MasteryMapView 薄弱点区块', () => {
  it('weakPointsTotal>0 显示计数徽标，为 0 时不显示', async () => {
    const withCount = await mountLoaded({
      mastery: [mi('a', '数据结构', 60)],
      weak: [wp(3)],
      total: 3,
    })
    expect(withCount.find('.map-count').text()).toBe('3 个')

    const zero = await mountLoaded({ mastery: [mi('a', '数据结构', 60)], weak: [], total: 0 })
    expect(zero.find('.map-count').exists()).toBe(false)
  })

  it('未筛选无数据 vs 筛选后无数据，文案必须区分（不能都是「暂无数据」）', async () => {
    const unfiltered = await mountLoaded({ mastery: [mi('a', '数据结构', 60)], weak: [], total: 0 })
    expect(unfiltered.find('.weak-empty').text()).toContain('暂无薄弱点数据')

    const filtered = await mountLoaded({
      mastery: [mi('a', '数据结构', 60)],
      weak: [wp(3, { subject: 'operating_system' })],
      total: 1,
    })
    await filtered.findAll('.subject-tile')[0]!.trigger('click')
    await nextTick()
    expect(filtered.find('.weak-empty').text()).toContain('该科目暂无薄弱点记录')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('MasteryMapView 科目点击联动', () => {
  const mastery = [mi('data_structures', '数据结构', 60), mi('operating_system', '操作系统', 20)]
  const weak = [
    wp(3, { subject: 'data_structures', concept: '二叉树' }),
    wp(5, { subject: 'data_structures', concept: '哈希' }),
    wp(2, { subject: 'operating_system', concept: '死锁' }),
  ]
  const kps = [
    kp(0.8, { subject: 'data_structures', chapter: 'tree' }),
    kp(0.2, { subject: 'data_structures', chapter: 'hash' }),
    kp(null, { subject: 'operating_system', chapter: 'process' }),
  ]

  it('点击科目卡片：卡片进入 active 态并联动筛选薄弱点与知识点', async () => {
    const w = await mountLoaded({ mastery, weak, kps, total: 3 })
    expect(w.findAll('.weak-item')).toHaveLength(3)
    expect(w.findAll('.kp-item')).toHaveLength(3)

    await w.findAll('.subject-tile')[0]!.trigger('click')
    await nextTick()

    expect(w.findAll('.subject-tile.active')).toHaveLength(1)
    expect(w.findAll('.weak-item')).toHaveLength(2)
    expect(w.findAll('.kp-item')).toHaveLength(2)
    // 两处「已筛选」标签都要出现，且显示中文科目名
    expect(w.findAll('.map-filter')).toHaveLength(2)
    expect(w.findAll('.map-filter')[0]!.text()).toContain('数据结构')
    // 筛选只影响展示，不触发新的网络请求
    expect(store.fetchKnowledgeMastery).toHaveBeenCalledTimes(1)
  })

  it('再次点击同一科目取消筛选（toggle 而非锁定）', async () => {
    const w = await mountLoaded({ mastery, weak, kps, total: 3 })
    const tile = w.findAll('.subject-tile')[1]!
    await tile.trigger('click')
    await nextTick()
    expect(w.findAll('.weak-item')).toHaveLength(1)
    expect(w.findAll('.kp-item')).toHaveLength(1)

    await tile.trigger('click')
    await nextTick()
    expect(w.findAll('.subject-tile.active')).toHaveLength(0)
    expect(w.findAll('.weak-item')).toHaveLength(3)
    expect(w.findAll('.kp-item')).toHaveLength(3)
    expect(w.findAll('.map-filter')).toHaveLength(0)
  })

  it('知识点列表取 store.knowledgePoints（动作返回值不是数据源）', async () => {
    stubSuccess({ mastery: [mi('a', '数据结构', 60)] })
    store.fetchKnowledgeMastery.mockResolvedValue([]) // 返回值故意为空
    store.knowledgePoints = [kp(0.9, { chapter: 'tree' })] // store 里才是数据源
    const w = mount(MasteryMapView)
    await flushPromises()
    await nextTick()

    expect(w.findAll('.kp-item')).toHaveLength(1)
    expect(w.find('.kp-chapter').text()).toBe('树与二叉树')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('MasteryMapView 知识点下钻（章节级）', () => {
  it('已知章节映射中文名，未知章节原样返回英文 key（不编造中文）', async () => {
    const known: Array<[string, string]> = [
      ['tcp_congestion', 'TCP拥塞控制'],
      ['tree', '树与二叉树'],
      ['cache', '高速缓存'],
      ['page_replacement', '页面置换'],
      ['ip', 'IP与子网'],
      ['hash', '哈希表'],
      ['data', '数据与编码'],
      ['process', '进程调度'],
      ['sorting', '排序'],
    ]
    const w = await mountLoaded({
      mastery: [mi('a', '数据结构', 60)],
      kps: [
        ...known.map(([ch]) => kp(0.5, { chapter: ch })),
        kp(0.5, { chapter: 'some_unknown_chapter' }),
      ],
    })

    expect(w.findAll('.kp-chapter').map((e) => e.text())).toEqual([
      ...known.map(([, label]) => label),
      'some_unknown_chapter',
    ])
    // 原始 key 仍保留在副标题，便于对账
    const tags = w.findAll('.kp-tag').map((e) => e.text())
    expect(tags).toContain('tcp_congestion')
    expect(tags).toContain('some_unknown_chapter')
  })

  it('mastery 为 null 显示「— / 未练习」，不插值成 0% 或其它数字', async () => {
    const w = await mountLoaded({
      mastery: [mi('a', '数据结构', 60)],
      kps: [kp(null, { chapter: 'tree' })],
    })
    const item = w.find('.kp-item')
    expect(item.find('.kp-count-num').text()).toBe('—')
    expect(item.find('.kp-count-num').text()).not.toContain('%')
    expect(item.find('.kp-badge').text()).toBe('未练习')
    expect(item.find('.kp-badge').classes()).toContain('badge-none')
    // 未练习的进度条必须是 0 宽度且用 none 色，不能被算成某个掌握度
    expect(styleOf(item.find('.kp-bar-fill'))).toContain('transform: scaleX(0)')
    expect(styleOf(item.find('.kp-bar-fill'))).toContain('var(--mastery-none)')
    expect(styleOf(item)).toContain('var(--mastery-none)')
  })

  it('mastery 数值按 Math.round 转百分比并落到对应档位', async () => {
    const w = await mountLoaded({
      mastery: [mi('a', '数据结构', 60)],
      kps: [
        kp(0.75, { chapter: 'tree' }),       // 75 扎实（档位下边界）
        kp(0.5, { chapter: 'hash' }),        // 50 一般
        kp(0.0749, { chapter: 'sorting' }),  // 7.49 → 7 薄弱
        kp(0, { chapter: 'process' }),       // 0 未测
        kp(0.666, { chapter: 'ip' }),        // 66.6 → 67 一般
        kp(0.494, { chapter: 'cache' }),     // 49.4 → 49 薄弱（档位上边界外）
        kp(0.495, { chapter: 'data' }),      // 49.5 → 50 一般（四舍五入进位）
      ],
    })
    expect(w.findAll('.kp-count-num').map((e) => e.text())).toEqual([
      '75%', '50%', '7%', '0%', '67%', '49%', '50%',
    ])
    expect(w.findAll('.kp-badge').map((e) => e.text())).toEqual([
      '扎实', '一般', '薄弱', '未测', '一般', '薄弱', '一般',
    ])
  })

  it('进度条 scaleX 与 mastery 一致（不写 width 过渡，遵循动效约束）', async () => {
    const w = await mountLoaded({
      mastery: [mi('a', '数据结构', 60)],
      kps: [kp(0.75, { chapter: 'tree' }), kp(0.25, { chapter: 'hash' })],
    })
    const bars = w.findAll('.kp-bar-fill').map((e) => styleOf(e))
    expect(bars[0]).toContain('width: 100%')
    expect(bars[0]).toContain('transform: scaleX(0.75)')
    expect(bars[1]).toContain('transform: scaleX(0.25)')
  })

  it('知识点为空时给出可操作文案，而不是空白区块', async () => {
    const w = await mountLoaded({ mastery: [mi('a', '数据结构', 60)], kps: [] })
    expect(w.find('.kp-list').exists()).toBe(false)
    expect(w.text()).toContain('暂无知识点掌握度数据，完成步骤化练习后自动点亮')
    expect(w.find('.map-hint').text()).toContain('点击上方科目可下钻')
  })
})
