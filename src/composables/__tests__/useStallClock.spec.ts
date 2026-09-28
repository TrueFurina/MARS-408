import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { defineComponent, h, nextTick } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import { useStallClock, __clockRefCount, STALL_THRESHOLD_MS } from '@/composables/useStallClock'

const BASE = 1_700_000_000_000

function makeHost() {
  return defineComponent({
    props: {
      loading: { type: Boolean, default: true },
      lastEventAt: { type: Number, default: 0 },
    },
    setup(props) {
      const { stalled, stalledSec } = useStallClock(() => props.loading, () => props.lastEventAt)
      return () => h('div', stalled.value ? `STALLED|${stalledSec.value}` : 'OK')
    },
  })
}

const mounted: VueWrapper[] = []

function mountHost(props: { loading?: boolean; lastEventAt?: number }) {
  const w = mount(makeHost(), { props: { loading: true, lastEventAt: 0, ...props } })
  mounted.push(w)
  return w
}

/** 从托管列表摘除后再卸载，避免 afterEach 二次卸载 */
function unmountNow(w: VueWrapper) {
  const i = mounted.indexOf(w)
  if (i >= 0) mounted.splice(i, 1)
  w.unmount()
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(BASE)
})

afterEach(() => {
  while (mounted.length) mounted.pop()!.unmount()
  vi.useRealTimers()
})

describe('useStallClock 停滞监测', () => {
  it('阈值内不判定停滞，超过阈值才判定（边界锁在 15000ms）', async () => {
    const w = mountHost({ loading: true, lastEventAt: BASE })
    vi.advanceTimersByTime(1000) // nowTs 同步到 BASE+1000
    await nextTick()
    expect(w.text()).toContain('OK')

    // 差值恰好 = 阈值：口径是「超过 15000」，等于时不算停滞
    await w.setProps({ lastEventAt: BASE + 1000 - STALL_THRESHOLD_MS })
    await nextTick()
    expect(w.text()).toContain('OK')

    // 再推进 1s → 差值 16000 > 15000 → 判定停滞
    vi.advanceTimersByTime(1000)
    await nextTick()
    expect(w.text()).toContain('STALLED')
    expect(w.text()).toContain('|16')
  })

  it('loading 为假时不判定停滞', async () => {
    const w = mountHost({ loading: false, lastEventAt: BASE - 60000 })
    vi.advanceTimersByTime(1000)
    await nextTick()
    expect(w.text()).toContain('OK')
  })

  it('尚无事件（lastEventAt = 0）时不判定停滞', async () => {
    const w = mountHost({ loading: true, lastEventAt: 0 })
    vi.advanceTimersByTime(1000)
    await nextTick()
    // 无事件时既不判定停滞，也不渲染秒数（真实 UI 中 stalledSec 仅在 stalled 时出现）
    expect(w.text()).toBe('OK')
  })

  it('多个使用方共享同一时钟，停滞秒数严格一致', async () => {
    const a = mountHost({ loading: true, lastEventAt: BASE - 20000 })
    const b = mountHost({ loading: true, lastEventAt: BASE - 20000 })
    vi.advanceTimersByTime(1000)
    await nextTick()
    expect(a.text()).toBe(b.text())
    expect(a.text()).toContain('|21')
  })

  it('共享定时器按引用计数获取与释放：全部卸载后归零', () => {
    expect(__clockRefCount()).toBe(0)
    const a = mountHost({ lastEventAt: BASE })
    const b = mountHost({ lastEventAt: BASE })
    expect(__clockRefCount()).toBe(2)
    unmountNow(a)
    expect(__clockRefCount()).toBe(1)
    unmountNow(b)
    expect(__clockRefCount()).toBe(0)
  })
})
