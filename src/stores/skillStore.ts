import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, friendlyError } from '@/utils/api'

export interface SkillItem {
  id: string
  name: string
  description: string
  icon: string
  system_prompt: string
  llm_channel: string
  temperature: number
  max_tokens: number
  kb_ids: string[]
  rag_enabled: boolean
  tags: string[]
  category: string
  category_label: string
  version: number
  status: string
  usage_count: number
  user_count: number
  avg_rating: number
  created_at: string
  updated_at: string
  published_at: string | null
  creator_id: string
  creator_name: string
  is_official: boolean
  memory_access: string
}

export interface SkillTemplate {
  id: string
  name: string
  description: string
  category: string
  category_label: string
  icon: string
  system_prompt_template: string
  default_config: Record<string, any>
  sort_order: number
}

export interface SkillRatingItem {
  id: string
  skill_id: string
  user_id: string
  user_name: string
  rating: number
  comment: string
  created_at: string
}

export interface CreatorStats {
  total_skills: number
  published_skills: number
  total_usage: number
  usage_trend: { day: string; count: number }[]
}

export const useSkillStore = defineStore('skills', () => {
  // ── 状态 ──
  const marketItems = ref<SkillItem[]>([])
  const marketTotal = ref(0)
  const mySkills = ref<SkillItem[]>([])
  const mySkillsTotal = ref(0)
  const officialSkills = ref<SkillItem[]>([])
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
      const res: any = await api.get(`/skills/market?${q}`)
      marketItems.value = res.items || []
      marketTotal.value = res.total || 0
    } catch (e: any) {
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
      const res: any = await api.get(`/skills/my?${q}`)
      mySkills.value = res.items || []
      mySkillsTotal.value = res.total || 0
    } catch (e: any) {
      error.value = friendlyError(e, '加载我的技能失败')
    } finally {
      loading.value = false
    }
  }

  // ── 官方技能 ──
  async function fetchOfficial() {
    try {
      const res: any = await api.get('/skills/official')
      officialSkills.value = res.items || []
    } catch (e: any) {
      console.warn('获取官方技能失败:', e?.message)
    }
  }

  // ── 技能详情 ──
  async function fetchSkill(id: string) {
    loading.value = true
    error.value = ''
    try {
      const res: any = await api.get(`/skills/get/${id}`)
      currentSkill.value = res.skill || null
    } catch (e: any) {
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
  }): Promise<SkillItem | null> {
    loading.value = true
    error.value = ''
    try {
      const res: any = await api.post('/skills/create', data)
      return res.skill || null
    } catch (e: any) {
      error.value = e?.message || '创建失败'
      return null
    } finally {
      loading.value = false
    }
  }

  // ── 更新技能 ──
  async function updateSkill(id: string, data: Record<string, any>): Promise<boolean> {
    error.value = ''
    try {
      const res: any = await api.post(`/skills/update/${id}`, data)
      if (res.skill) currentSkill.value = res.skill
      return true
    } catch (e: any) {
      error.value = e?.message || '更新失败'
      return false
    }
  }

  // ── 删除 ──
  async function deleteSkill(id: string): Promise<boolean> {
    try {
      await api.post(`/skills/delete/${id}`)
      return true
    } catch (e: any) {
      error.value = e?.message || '删除失败'
      return false
    }
  }

  // ── 发布 / 归档 ──
  async function publishSkill(id: string): Promise<boolean> {
    try {
      await api.post(`/skills/publish/${id}`)
      return true
    } catch (e: any) {
      error.value = e?.message || '发布失败'
      return false
    }
  }

  async function archiveSkill(id: string): Promise<boolean> {
    try {
      await api.post(`/skills/archive/${id}`)
      return true
    } catch (e: any) {
      error.value = e?.message || '归档失败'
      return false
    }
  }

  // ── 评价 ──
  async function rateSkill(skillId: string, rating: number, comment?: string): Promise<boolean> {
    try {
      await api.post(`/skills/rate/${skillId}`, { rating, comment: comment || '' })
      return true
    } catch (e: any) {
      error.value = e?.message || '评价失败'
      return false
    }
  }

  async function fetchRatings(skillId: string) {
    try {
      const res: any = await api.get(`/skills/ratings/${skillId}`)
      ratings.value = res.items || []
    } catch (e: any) {
      console.warn('获取评价失败:', e?.message)
    }
  }

  // ── 模板 ──
  async function fetchTemplates() {
    try {
      const res: any = await api.get('/skills/templates')
      templates.value = res.items || []
    } catch (e: any) {
      console.warn('获取模板失败:', e?.message)
    }
  }

  async function createFromTemplate(templateId: string, name: string, description?: string, icon?: string): Promise<SkillItem | null> {
    loading.value = true
    error.value = ''
    try {
      const res: any = await api.post(`/skills/from-template/${templateId}`, { name, description: description || '', icon: icon || '🤖' })
      return res.skill || null
    } catch (e: any) {
      error.value = friendlyError(e, '从模板创建失败')
      return null
    } finally {
      loading.value = false
    }
  }

  // ── 创作者统计 ──
  async function fetchCreatorStats() {
    try {
      const res: any = await api.get('/skills/stats')
      creatorStats.value = res.stats || null
    } catch (e: any) {
      console.warn('获取创作者统计失败:', e?.message)
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