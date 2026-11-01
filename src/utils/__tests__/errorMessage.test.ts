import { describe, it, expect } from 'vitest'
import { errMessage, isAbortError } from '@/utils/errorMessage'
import { describeError } from '@/utils/globalErrorHandler'

// 防回归：errMessage 是「catch 变量收敛为 unknown 之后」全仓唯一的取文案出口。
// 它的语义边界比看上去窄，几条都不能随手改：
//   · 只认 Error 与「带字符串 message 的对象」；
//   · **裸字符串不算文案**（`throw 'boom'` 是开发者调试串，不该怼给用户）；
//   · 与 describeError 的差异是**刻意**的，不是遗漏。
describe('errMessage 取值语义', () => {
  it('Error 取 message', () => {
    expect(errMessage(new Error('后端 502'))).toBe('后端 502')
  })

  it('Error 的 message 为空时回落到 fallback', () => {
    expect(errMessage(new Error(''), '操作失败')).toBe('操作失败')
  })

  it('普通对象带字符串 message 时取之（SDK 常这么抛）', () => {
    expect(errMessage({ message: '配额不足' })).toBe('配额不足')
  })

  it('对象 message 不是字符串时回落到 fallback', () => {
    expect(errMessage({ message: 500 }, '操作失败')).toBe('操作失败')
  })

  it('裸字符串不算文案，回落到 fallback', () => {
    // 这条是刻意行为：`throw 'boom'` 里的字符串是调试串，显示给用户不如中文兜底。
    // 需要显示裸字符串的场景走 describeError（见下一条）。
    expect(errMessage('boom', '操作失败')).toBe('操作失败')
  })

  it('null / undefined / 数字 / 布尔一律回落到 fallback', () => {
    for (const v of [null, undefined, 0, 42, false, true]) {
      expect(errMessage(v, '兜底')).toBe('兜底')
    }
  })

  it('fallback 可自定义，默认值为「操作失败」', () => {
    expect(errMessage(null)).toBe('操作失败')
    expect(errMessage(null, '加载失败')).toBe('加载失败')
  })
})

// 这一组锁定的是「两个函数不一样」这件事本身。
// 若哪天有人把 describeError 改成直接委托 errMessage，这里会红 —— 那是提醒，
// 不是障碍：改之前请先想清楚全局 toast 是否还要显示 `throw '后端 502'` 的原文。
describe('errMessage 与 describeError 的刻意差异', () => {
  it('同一个裸字符串：errMessage 走兜底，describeError 原样显示', () => {
    expect(errMessage('后端 502', '操作失败')).toBe('操作失败')
    expect(describeError('后端 502')).toBe('后端 502')
  })

  it('Error 场景两者一致（不因为分层而分叉）', () => {
    expect(errMessage(new Error('同一条'), 'x')).toBe('同一条')
    expect(describeError(new Error('同一条'))).toBe('同一条')
  })
})

describe('isAbortError 判定', () => {
  it('AbortError 判为中断', () => {
    const e = new Error('The operation was aborted.')
    e.name = 'AbortError'
    expect(isAbortError(e)).toBe(true)
  })

  it('普通 Error / 字符串 / null 都不是中断', () => {
    expect(isAbortError(new Error('boom'))).toBe(false)
    expect(isAbortError('AbortError')).toBe(false)
    expect(isAbortError(null)).toBe(false)
    expect(isAbortError(undefined)).toBe(false)
  })

  it('类 AbortError 的普通对象也认（SDK 可能抛非 Error）', () => {
    expect(isAbortError({ name: 'AbortError' })).toBe(true)
  })
})
