import { describe, it, expect } from 'vitest'
import { friendlyError } from '@/utils/api'

// 防回归：friendlyError 是前端错误提示的唯一真相源。
// 曾因网络错误原文直出（"Failed to fetch"）导致用户看到英文报错（见 2026-07 修复）。
describe('friendlyError 错误提示友好化', () => {
  it('网络错误 → 后端未连接提示', () => {
    expect(friendlyError(new Error('Failed to fetch'), 'fallback')).toBe('后端服务未连接，请先运行后端服务（端口 8002）')
    expect(friendlyError(new Error('ECONNREFUSED 127.0.0.1:8002'), 'fallback')).toBe('后端服务未连接，请先运行后端服务（端口 8002）')
    expect(friendlyError(new Error('<!DOCTYPE html>...'), 'fallback')).toBe('后端服务未连接，请先运行后端服务（端口 8002）')
  })

  it('401 → 重新登录提示', () => {
    expect(friendlyError(new Error('Invalid or expired credentials'), 'fb')).toBe('登录已过期，请重新登录')
    expect(friendlyError('401 Unauthorized', 'fb')).toBe('登录已过期，请重新登录')
  })

  it('429 → 频率限制提示', () => {
    expect(friendlyError(new Error('Too Many Requests'), 'fb')).toBe('操作过于频繁，请稍后再试')
    expect(friendlyError(new Error('quota exceeded'), 'fb')).toBe('操作过于频繁，请稍后再试')
  })

  it('500 → 服务器错误提示', () => {
    expect(friendlyError(new Error('500 Internal Server Error'), 'fb')).toBe('服务器内部错误，请稍后重试')
  })

  it('未匹配错误 → 返回原文或 fallback', () => {
    expect(friendlyError(new Error('自定义业务错误'), 'fb')).toBe('自定义业务错误')
    expect(friendlyError(undefined, 'fb')).toBe('fb')
    expect(friendlyError(null, 'fb')).toBe('fb')
  })
})
