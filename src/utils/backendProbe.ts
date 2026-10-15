/**
 * 后端可用性探测（全站唯一判据）
 * ============================================================================
 * 背景：项目历史上「公网域名」= 纯静态展示站（无后端），故落地页与路由守卫都用
 * 「hostname 是否 localhost」判断能否直接使用系统。2026-10-15 后端随平台发布上线后，
 * 该判据全面过时 —— 公网访客明明是可用系统，却被引导去「本地运行」/被守卫弹回落地页。
 *
 * 现改为**运行时探测 `/api/status`**：
 *   - true  → 后端在线，未登录访客应能进登录页（而非被弹回落地页）
 *   - false → 确实只有静态前端（如实保留「本地运行」引导）
 *   - null  → 尚未探测出结果：调用方按「乐观」处理（当下事实就是有后端）
 */
let reachable: boolean | null = null
let inflight: Promise<boolean> | null = null

/** 已探测到的结果（null = 还在探测中）；同步可读，供路由守卫使用 */
export function backendReachable(): boolean | null {
  return reachable
}

/** 探测后端是否在线（并发调用复用同一个请求） */
export function probeBackend(): Promise<boolean> {
  if (inflight) return inflight
  inflight = fetch('/api/status', { headers: { Accept: 'application/json' } })
    .then((r) => {
      reachable = r.ok
      return r.ok
    })
    .catch(() => {
      reachable = false
      return false
    })
  return inflight
}

// 模块加载即开始探测（router / landing 任一先 import 都会被覆盖）：
// 尽早拿到结果，压缩"探测中"这一不确定窗口，避免访客手快点击时误判。
if (typeof window !== 'undefined') {
  void probeBackend()
}
