import { defineStore } from 'pinia'
import { errMessage } from '@/utils/errorMessage'
import { ref, shallowRef } from 'vue'
import { api, friendlyError } from '@/utils/api'
import type { components } from '@/types/api.generated'

// 2026-11-06 批6：四个接口原先是手写"看着对"的投影，后端改名时 tsc 抓不到。
// 现在 /api/skills/* 有了 response_model，直接绑定生成类型作为单一真值源。
type SkillItemOut = components['schemas']['SkillItemOut']
type SkillTemplateOut = components['schemas']['SkillTemplateOut']
type SkillRatingOut = components['schemas']['SkillRatingOut']
type CreatorStatsOut = components['schemas']['CreatorStatsOut']

export type SkillTemplate = SkillTemplateOut
export type SkillRatingItem = SkillRatingOut
export type CreatorStats = CreatorStatsOut

// 批8：后端已补齐 to_dict()/SkillItemOut 的 memory_access 导出与请求模型声明，
// 不再需要可选扩展占位 —— 直接绑定生成类型作为单一真值源。
export type SkillItem = SkillItemOut

// 各端点的响应包装（生成类型，替代原先的 const res: any）。
// 导出供其它视图复用，避免每个文件重复声明同一份别名（dup_scan 克隆门禁）。
export type SkillListResp = components['schemas']['SkillListResponse']
export type SkillDetailResp = components['schemas']['SkillDetailResponse']
export type RatingListResp = components['schemas']['RatingListResponse']
export type TemplateListResp = components['schemas']['TemplateListResponse']
export type CreatorStatsResp = components['schemas']['CreatorStatsResponse']
export type FavoritedResp = components['schemas']['FavoritedResponse']
export type FavoritesResp = components['schemas']['FavoritesResponse']
export type SkillAckResp = components['schemas']['SkillAckResponse']
export type RatingDetailResp = components['schemas']['RatingDetailResponse']
export type PromptTestResp = components['schemas']['PromptTestResponse']

export const useSkillStore = defineStore('skills', () => {
  // ── 状态 ──
  // 三个列表型状态仅做整数组替换（marketItems.value = res.items），无就地改动元素，
  // 用 shallowRef 避免对大数组逐元素建深度响应式代理的开销（INP/内存收益，行为不变）。
  const marketItems = shallowRef<SkillItem[]>([])
  const marketTotal = ref(0)
  const mySkills = shallowRef<SkillItem[]>([])
  const mySkillsTotal = ref(0)
  const officialSkills = shallowRef<SkillItem[]>([])
  const currentSkill = ref<SkillItem | null>(null)
  const templates = ref<SkillTemplate[]>([])
  const ratings = ref<SkillRatingItem[]>([])
  const creatorStats = ref<CreatorStats | null>(null)
  const loading = ref(false)
  const error = ref('')

  // ── 市场 ──
  async function fetchMarket(params?: {
    category?: string
    tag?: string
    search?: string
    sort_by?: string
    sort_desc?: boolean
    limit?: number
    offset?: number
  }) {
    loading.value = true
    error.value = ''
    try {
      const q = new URLSearchParams()
      if (params?.category) q.set('category', params.category)
      if (params?.tag) q.set('tag', params.tag)
      if (params?.search) q.set('search', params.search)
      if (params?.sort_by) q.set('sort_by', params.sort_by)
      if (params?.sort_desc !== undefined) q.set('sort_desc', String(params.sort_desc))
      q.set('limit', String(params?.limit ?? 50))
      q.set('offset', String(params?.offset ?? 0))
      const res = await api.get<SkillListResp>(`/skills/market?${q}`)
      marketItems.value = res.items || []
      marketTotal.value = res.total || 0
    } catch (e) {
      error.value = friendlyError(e, '加载市场失败')
    } finally {
      loading.value = false
    }
  }

  // ── 我的技能 ──
  async function fetchMySkills(params?: { status?: string }) {
    loading.value = true
    error.value = ''
    try {
      const q = new URLSearchParams()
      if (params?.status) q.set('status', params.status)
      const res = await api.get<SkillListResp>(`/skills/my?${q}`)
      mySkills.value = res.items || []
      mySkillsTotal.value = res.total || 0
    } catch (e) {
      error.value = friendlyError(e, '加载我的技能失败')
    } finally {
      loading.value = false
    }
  }

  // ── 官方技能 ──
  async function fetchOfficial() {
    try {
      const res = await api.get<SkillListResp>('/skills/official')
      officialSkills.value = res.items || []
    } catch (e) {
      console.warn('获取官方技能失败:', errMessage(e, String(e)))
    }
  }

  // ── 技能详情 ──
  async function fetchSkill(id: string) {
    loading.value = true
    error.value = ''
    try {
      const res = await api.get<SkillDetailResp>(`/skills/get/${id}`)
      currentSkill.value = res.skill || null
    } catch (e) {
      error.value = friendlyError(e, '加载技能失败')
    } finally {
      loading.value = false
    }
  }

  // ── 创建技能 ──
  async function createSkill(data: {
    name: string
    description?: string
    icon?: string
    system_prompt?: string
    llm_channel?: string
    temperature?: number
    max_tokens?: number
    category?: string
    tags?: string
    rag_enabled?: boolean
    memory_access?: string
    tools?: Record<string, unknown>[]
  }): Promise<SkillItem | null> {
    loading.value = true
    error.value = ''
    try {
      const res = await api.post<SkillDetailResp>('/skills/create', data)
      return res.skill || null
    } catch (e) {
      error.value = errMessage(e, '创建失败')
      return null
    } finally {
      loading.value = false
    }
  }

  // ── 更新技能 ──
  async function updateSkill(id: string, data: Record<string, any>): Promise<boolean> {
    error.value = ''
    try {
      const res = await api.post<SkillDetailResp>(`/skills/update/${id}`, data)
      if (res.skill) currentSkill.value = res.skill
      return true
    } catch (e) {
      error.value = errMessage(e, '更新失败')
      return false
    }
  }

  // ── 删除 ──
  async function deleteSkill(id: string): Promise<boolean> {
    try {
      await api.post<SkillAckResp>(`/skills/delete/${id}`)
      return true
    } catch (e) {
      error.value = errMessage(e, '删除失败')
      return false
    }
  }

  // ── 发布 / 归档 ──
  async function publishSkill(id: string): Promise<boolean> {
    try {
      await api.post<SkillAckResp>(`/skills/publish/${id}`)
      return true
    } catch (e) {
      error.value = errMessage(e, '发布失败')
      return false
    }
  }

  async function archiveSkill(id: string): Promise<boolean> {
    try {
      await api.post<SkillAckResp>(`/skills/archive/${id}`)
      return true
    } catch (e) {
      error.value = errMessage(e, '归档失败')
      return false
    }
  }

  // ── 评价 ──
  async function rateSkill(skillId: string, rating: number, comment?: string): Promise<boolean> {
    try {
      await api.post<RatingDetailResp>(`/skills/rate/${skillId}`, { rating, comment: comment || '' })
      return true
    } catch (e) {
      error.value = errMessage(e, '评价失败')
      return false
    }
  }

  async function fetchRatings(skillId: string) {
    try {
      const res = await api.get<RatingListResp>(`/skills/ratings/${skillId}`)
      ratings.value = res.items || []
    } catch (e) {
      console.warn('获取评价失败:', errMessage(e, String(e)))
    }
  }

  // ── 模板 ──
  async function fetchTemplates() {
    try {
      const res = await api.get<TemplateListResp>('/skills/templates')
      templates.value = res.items || []
    } catch (e) {
      console.warn('获取模板失败:', errMessage(e, String(e)))
    }
  }

  async function createFromTemplate(templateId: string, name: string, description?: string, icon?: string): Promise<SkillItem | null> {
    loading.value = true
    error.value = ''
    try {
      const res = await api.post<SkillDetailResp>(`/skills/from-template/${templateId}`, { name, description: description || '', icon: icon || '' })
      return res.skill || null
    } catch (e) {
      error.value = friendlyError(e, '从模板创建失败')
      return null
    } finally {
      loading.value = false
    }
  }

  // ── 创作者统计 ──
  async function fetchCreatorStats() {
    try {
      const res = await api.get<CreatorStatsResp>('/skills/stats')
      creatorStats.value = res.stats || null
    } catch (e) {
      console.warn('获取创作者统计失败:', errMessage(e, String(e)))
    }
  }

  return {
    // state
    marketItems, marketTotal, mySkills, mySkillsTotal, officialSkills,
    currentSkill, templates, ratings, creatorStats, loading, error,
    // actions
    fetchMarket, fetchMySkills, fetchOfficial,
    fetchSkill, createSkill, updateSkill, deleteSkill,
    publishSkill, archiveSkill,
    rateSkill, fetchRatings,
    fetchTemplates, createFromTemplate,
    fetchCreatorStats,
  }
})