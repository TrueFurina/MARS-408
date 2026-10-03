import { describe, it, expect, vi, afterEach } from 'vitest'
import { toast } from '@/utils/toast'

afterEach(() => {
  delete (window as any).__toast
  vi.restoreAllMocks()
})

// 防回归：toast 全局入口在 __toast 缺失时必须降级为可诊断输出，
// 而不是静默丢失（旧实现 dispatch 一个无人监听的自定义事件，提示会消失）。
describe('toast 全局入口', () => {
  it('__toast 已挂载时调用对应方法，且不打 console', () => {
    const success = vi.fn()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    ;(window as any).__toast = { success }

    toast('success', '已保存')

    expect(success).toHaveBeenCalledWith('已保存')
    expect(warn).not.toHaveBeenCalled()
  })

  it('__toast 缺失时降级为 console.warn 且不抛错', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    expect(() => toast('error', '失败')).not.toThrow()
    expect(warn).toHaveBeenCalledWith(expect.stringContaining('失败'))
  })

  it('__toast 无对应 type 方法时同样降级（不误调）', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    ;(window as any).__toast = { success: vi.fn() }

    toast('nope', 'x')

    expect(warn).toHaveBeenCalled()
  })
})
