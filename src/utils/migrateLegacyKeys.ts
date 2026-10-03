// 品牌更名迁移：把旧 localStorage 键（mars408_* / mars408-*）迁移到新前缀 mangdehenzhi_* / mangdehenzhi-*。
// 本模块在 main.ts 中作为「首个 import」引入，利用 ES 模块求值顺序保证它在任何 store
// 读取 localStorage 之前执行，从而不让老用户丢失登录态 / 主题偏好 / 成就进度。
const OLD_PREFIX = 'mars408'
const NEW_PREFIX = 'mangdehenzhi'

function migrateLegacyKeys(): void {
  try {
    const keys = Object.keys(localStorage)
    for (const key of keys) {
      if (!key.startsWith(OLD_PREFIX)) continue
      const newKey = NEW_PREFIX + key.slice(OLD_PREFIX.length)
      // 仅当新键尚不存在时拷贝，避免覆盖已写入的新数据
      if (localStorage.getItem(newKey) === null) {
        const value = localStorage.getItem(key)
        if (value !== null) localStorage.setItem(newKey, value)
      }
      localStorage.removeItem(key)
    }
  } catch {
    // localStorage 不可用（SSR / 隐私模式 / 存储被禁用）时静默跳过
  }
}

migrateLegacyKeys()
