import { computed, ref, onUnmounted } from 'vue'

/**
 * 停滞判定阈值：距上次事件超过 15s 视为停滞（沿用 ResourceView 原有口径）。
 */
export const STALL_THRESHOLD_MS = 15000

/**
 * 模块级共享时钟：同一页面上所有使用方共用同一个 nowTs 与同一个 tick 定时器。
 *
 * 这样做的两个原因：
 * 1. 保证同一页面多处停滞显示（状态 chip 与告警条）的数值严格一致，不会各 tick 各的。
 * 2. 把「每秒重渲染」的影响范围限制在使用方组件内部 —— 父组件不再持有
 *    每秒变化的响应式状态，因此不会每 1s 整页重渲染（原先 nowTs 在父组件，
 *    导致整页所有节点每 1s 重渲）。
 */
const nowTs = ref(Date.now())
let timer: number | null = null
let refCount = 0

function acquireClock() {
  refCount += 1
  if (timer === null) {
    timer = window.setInterval(() => {
      nowTs.value = Date.now()
    }, 1000)
  }
}

function releaseClock() {
  refCount = Math.max(0, refCount - 1)
  if (refCount === 0 && timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

/** 仅暴露给测试：校验共享定时器的引用计数与释放行为 */
export function __clockRefCount() {
  return refCount
}

/**
 * 停滞监测。时钟下沉到调用方组件内，由组件挂载/卸载驱动定时器的获取与释放。
 *
 * @param loading 是否处于进行中（仅进行中才可能判定停滞）
 * @param lastEventAt 上次事件时间戳（0 表示尚无事件）
 */
export function useStallClock(loading: () => boolean, lastEventAt: () => number) {
  acquireClock()
  onUnmounted(releaseClock)

  const stalled = computed(
    () => loading() && lastEventAt() > 0 && nowTs.value - lastEventAt() > STALL_THRESHOLD_MS
  )
  const stalledSec = computed(() => Math.max(0, Math.floor((nowTs.value - lastEventAt()) / 1000)))

  return { stalled, stalledSec }
}
