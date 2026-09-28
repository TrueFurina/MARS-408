/**
 * 路由级预取（Route-level prefetch）
 *
 * 背景：本项目 43 个视图全部为懒加载 chunk（`component: () => import(...)`），
 * 点击导航后才开始下载 → 弱网/冷缓存下存在可感知的白屏与进度条等待。
 *
 * 策略：在用户表达明确导航意图（鼠标悬停 / 键盘聚焦）时提前拉取目标 chunk，
 * 使真正点击时模块已在缓存中，切换接近瞬时。
 *
 * 安全约束（避免过度预取与副作用）：
 *   1. **尊重省流量与弱网**：`Save-Data` 开启或 `effectiveType` 为 2g 时完全不预取。
 *   2. **同一路径只预取一次**：用 Set 去重，重复悬停不再发请求。
 *   3. **延迟触发**：悬停需持续 `PREFETCH_DELAY_MS` 才真正发起，快速划过导航不会批量下载。
 *   4. **失败静默**：预取属于优化而非关键路径，任何异常都不得影响正常导航交互。
 *   5. **只触发模块下载**：调用路由的 lazy component 工厂函数即可，
 *      不做路由跳转、不改变应用状态（Vue Router 的导航守卫不会被触发）。
 */

import type { Router } from 'vue-router'

const PREFETCH_DELAY_MS = 120

const prefetched = new Set<string>()
let timer: ReturnType<typeof setTimeout> | null = null

/** 省流量 / 弱网判定：这两类场景下预取是净负担，直接放弃。 */
function shouldSkip(): boolean {
  if (typeof navigator === 'undefined') return true
  const conn = (navigator as unknown as { connection?: { saveData?: boolean; effectiveType?: string } })
    .connection
  if (!conn) return false
  if (conn.saveData === true) return true
  if (typeof conn.effectiveType === 'string' && /(^|-)2g$/.test(conn.effectiveType)) return true
  return false
}

/**
 * 立即预取某路径对应的所有懒加载 chunk（含嵌套路由的父级布局）。
 * 已预取过的路径会被跳过；异常一律静默吞掉。
 */
export function prefetchRoute(router: Router, path: string): void {
  if (!path || prefetched.has(path)) return
  if (shouldSkip()) return
  prefetched.add(path)

  try {
    const resolved = router.resolve(path)
    for (const record of resolved.matched) {
      // 具名视图可能有多个组件（default / 其它命名视图），全部预取
      const components = record.components
      if (!components) continue
      for (const comp of Object.values(components)) {
        // 惰性路由组件是 `() => import(...)` 工厂函数；静态组件是对象，无需预取
        if (typeof comp === 'function') {
          Promise.resolve((comp as () => unknown)()).catch(() => {})
        }
      }
    }
  } catch {
    // resolve 失败（路径不存在等）不影响导航本身
  }
}

/** 悬停后延迟预取 —— 避免鼠标快速划过侧栏时一次性拉起十几个 chunk。 */
export function schedulePrefetch(router: Router, path: string): void {
  cancelPrefetch()
  if (!path || prefetched.has(path)) return
  if (shouldSkip()) return
  timer = setTimeout(() => {
    timer = null
    prefetchRoute(router, path)
  }, PREFETCH_DELAY_MS)
}

/** 鼠标离开时取消尚未触发的预取。 */
export function cancelPrefetch(): void {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

/** 仅供测试：清空预取记忆，使重复预取可再次发生。 */
export function __resetPrefetchCache(): void {
  prefetched.clear()
  cancelPrefetch()
}
