/**
 * useAbilityProfile —— 统一能力画像的前端唯一入口（双场景集成 · F4）
 *
 * 一个账号、一份画像：后端 GET /api/profile/ability 聚合两个场景的产出：
 *   · professional  —— 场景A 考研408 学情诊断 / 画像
 *   · soft_skills   —— 场景B 职业素养实训六维评估
 *   · kaoyan_score / career_score —— 各自最近一次原始结果
 *
 * 【fail-open 纪律】与 useBenchmark 的"零 fallback"不同：能力画像属**可降级**数据
 * （后端 ability_profiles 表按合体 M1 里程碑后置落地）。接口未就绪（404/500/网络失败）
 * 时回退本地缓存并置 degraded=true，由视图显式提示"画像服务未就绪"，保证首页不白屏。
 */
import { ref } from 'vue'
import { api } from '@/utils/api'

export interface AbilityProfile {
  user_id?: string
  /** 场景A：专业能力（考研408 诊断 / 画像） */
  professional?: Record<string, unknown>
  /** 场景B：软素养（职业素养实训六维评估） */
  soft_skills?: Record<string, unknown>
  kaoyan_score?: Record<string, unknown> | null
  career_score?: Record<string, unknown> | null
  updated_at?: string
  /** 数据来源：'server' | 'local-cache' */
  source?: string
}

const data = ref<AbilityProfile | null>(null)
const degraded = ref(false)
const loading = ref(false)
let loaded = false

/** 本地缓存回退（后端未就绪时） */
function fallbackFromCache(): AbilityProfile | null {
  try {
    const raw = localStorage.getItem('mars408_profile')
    if (raw) return { professional: JSON.parse(raw), source: 'local-cache' }
  } catch { /* localStorage 不可用（隐私模式）时静默 */ }
  return null
}

async function load(force = false): Promise<void> {
  if (loaded && !force) return
  loading.value = true
  try {
    const res = await api.get<AbilityProfile>('/api/profile/ability')
    data.value = { ...res, source: 'server' }
    degraded.value = false
  } catch {
    // fail-open：不抛错、不中断页面
    degraded.value = true
    data.value = fallbackFromCache()
  } finally {
    loading.value = false
    loaded = true
  }
}

/** 本地缓存写入（各场景评估完成后可调用，作为离线回退源） */
function cacheLocal(profile: Record<string, unknown>): void {
  try { localStorage.setItem('mars408_profile', JSON.stringify(profile)) } catch { /* */ }
}

export function useAbilityProfile() {
  return { data, degraded, loading, load, cacheLocal }
}
