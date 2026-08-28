import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/utils/api'

// ── 成就定义 ──

export interface Achievement {
  id: string
  name: string
  description: string
  icon: string
  category: 'milestone' | 'practice' | 'knowledge' | 'streak' | 'master'
  color: string
  /** 已解锁 */
  unlocked: boolean
  /** 解锁时间 */
  unlockedAt?: string
  /** 进度（0-100），100 即解锁 */
  progress: number
  /** 进度描述 */
  progressLabel: string
}

// 成就定义表
const ACHIEVEMENT_DEFS: Omit<Achievement, 'unlocked' | 'unlockedAt' | 'progress' | 'progressLabel'>[] = [
  // ── 学习里程碑 ──
  { id: 'first_login', name: '初次见面', description: '首次登录 MARS-408 学习系统', icon: '👋', category: 'milestone', color: '#7c6af2' },
  { id: 'profile_built', name: '画像大师', description: '完成学生画像构建', icon: '🧠', category: 'milestone', color: '#8b5cf6' },
  { id: 'first_chat', name: '初次对话', description: '完成第一次 AI 对话', icon: '💬', category: 'milestone', color: '#3b82f6' },
  { id: 'first_resource', name: '资源猎人', description: '生成第一份学习资源', icon: '📄', category: 'milestone', color: '#06b6d4' },
  { id: 'first_path', name: '路线规划', description: '查看个性化学习路径', icon: '🗺️', category: 'milestone', color: '#22c55e' },

  // ── 练习达人 ──
  { id: 'quiz_10', name: '初出茅庐', description: '完成 10 道练习题', icon: '📝', category: 'practice', color: '#f59e0b' },
  { id: 'quiz_50', name: '题海战士', description: '完成 50 道练习题', icon: '⚔️', category: 'practice', color: '#f97316' },
  { id: 'quiz_100', name: '刷题狂人', description: '完成 100 道练习题', icon: '🏆', category: 'practice', color: '#ef4444' },
  { id: 'quiz_300', name: '题王之王', description: '完成 300 道练习题', icon: '👑', category: 'practice', color: '#ec4899' },
  { id: 'accuracy_80', name: '精准射手', description: '答题正确率达到 80%', icon: '🎯', category: 'practice', color: '#22c55e' },
  { id: 'accuracy_90', name: '学霸模式', description: '答题正确率达到 90%', icon: '🌟', category: 'practice', color: '#14b8a6' },
  { id: 'perfect_10', name: '十全十美', description: '连续答对 10 题', icon: '💎', category: 'practice', color: '#8b5cf6' },

  // ── 知识探索 ──
  { id: 'knowledge_10', name: '知识学徒', description: '浏览 10 个知识点', icon: '📚', category: 'knowledge', color: '#3b82f6' },
  { id: 'knowledge_50', name: '知识探索者', description: '浏览 50 个知识点', icon: '🔍', category: 'knowledge', color: '#6366f1' },
  { id: 'knowledge_all', name: '博学家', description: '覆盖全部 4 门课程', icon: '🎓', category: 'knowledge', color: '#7c6af2' },
  { id: 'kg_built', name: '图谱构建者', description: '生成知识图谱', icon: '🕸️', category: 'knowledge', color: '#06b6d4' },
  { id: 'mindmap_view', name: '思维导图', description: '查看思维导图', icon: '🧩', category: 'knowledge', color: '#f59e0b' },

  // ── 坚持学习 ──
  { id: 'streak_3', name: '三天打鱼', description: '连续学习 3 天', icon: '🔥', category: 'streak', color: '#f97316' },
  { id: 'streak_7', name: '一周坚持', description: '连续学习 7 天', icon: '📅', category: 'streak', color: '#ef4444' },
  { id: 'streak_14', name: '半月长征', description: '连续学习 14 天', icon: '🚀', category: 'streak', color: '#ec4899' },
  { id: 'streak_30', name: '月度冠军', description: '连续学习 30 天', icon: '🏅', category: 'streak', color: '#14b8a6' },
  { id: 'streak_60', name: '学习铁人', description: '连续学习 60 天', icon: '🦾', category: 'streak', color: '#8b5cf6' },

  // ── 成就大师 ──
  { id: 'collector_5', name: '收藏家', description: '解锁 5 个成就', icon: '🏅', category: 'master', color: '#f59e0b' },
  { id: 'collector_10', name: '成就猎人', description: '解锁 10 个成就', icon: '🎖️', category: 'master', color: '#f97316' },
  { id: 'collector_20', name: '成就大师', description: '解锁 20 个成就', icon: '👑', category: 'master', color: '#ec4899' },
  { id: 'four_in_one', name: '全科通关', description: '四门课程都有练习记录', icon: '🌈', category: 'master', color: '#7c6af2' },
  { id: 'speed_learner', name: '速学者', description: '单日完成 20+ 题', icon: '⚡', category: 'master', color: '#06b6d4' },
]

export const useAchievementStore = defineStore('achievements', () => {
  const achievements = ref<Achievement[]>([])

  // 统计信息
  const stats = ref({
    totalQuestions: 0,
    totalCorrect: 0,
    consecutiveCorrect: 0,
    maxConsecutiveCorrect: 0,
    currentStreak: 0,
    maxStreak: 0,
    knowledgeBrowsed: 0,
    subjectsCovered: new Set<string>(),
    todayQuestions: 0,
    lastActiveDate: '',
    profileBuilt: false,
    firstChat: false,
    firstResource: false,
    firstPath: false,
    kgBuilt: false,
    mindmapView: false,
  })

  const unlockedCount = computed(() => achievements.value.filter(a => a.unlocked).length)
  const totalCount = computed(() => achievements.value.length)
  const progressPercent = computed(() => totalCount.value > 0 ? Math.round(unlockedCount.value / totalCount.value * 100) : 0)

  const recentAchievements = computed(() =>
    achievements.value
      .filter(a => a.unlocked && a.unlockedAt)
      .sort((a, b) => new Date(b.unlockedAt!).getTime() - new Date(a.unlockedAt!).getTime())
      .slice(0, 5)
  )

  const categoryProgress = computed(() => {
    const cats: Record<string, { unlocked: number; total: number }> = {}
    for (const a of achievements.value) {
      if (!cats[a.category]) cats[a.category] = { unlocked: 0, total: 0 }
      cats[a.category]!.total++
      if (a.unlocked) cats[a.category]!.unlocked++
    }
    return cats
  })

  function init() {
    // 从 localStorage 恢复
    const savedAch = localStorage.getItem('mars408_achievements')
    const savedStats = localStorage.getItem('mars408_ach_stats')

    if (savedAch) {
      try { achievements.value = JSON.parse(savedAch) } catch { /* */ }
    }

    if (savedStats) {
      try {
        const parsed = JSON.parse(savedStats)
        stats.value = {
          ...stats.value,
          ...parsed,
          subjectsCovered: new Set(parsed.subjectsCovered || []),
        }
      } catch { /* */ }
    }

    // 首次加载或数据为空时，用定义初始化
    if (achievements.value.length === 0) {
      achievements.value = ACHIEVEMENT_DEFS.map(def => ({
        ...def,
        unlocked: false,
        progress: 0,
        progressLabel: '0%',
      }))
    }

    // 授权后自动解锁"初次见面"
    unlockAchievement('first_login')
  }

  function save() {
    localStorage.setItem('mars408_achievements', JSON.stringify(achievements.value))
    localStorage.setItem('mars408_ach_stats', JSON.stringify({
      ...stats.value,
      subjectsCovered: Array.from(stats.value.subjectsCovered),
    }))
  }

  function unlockAchievement(id: string) {
    const ach = achievements.value.find(a => a.id === id)
    if (!ach || ach.unlocked) return
    ach.unlocked = true
    ach.unlockedAt = new Date().toISOString()
    ach.progress = 100
    ach.progressLabel = '已解锁'
    save()

    // 检查收藏家系列成就
    const count = achievements.value.filter(a => a.unlocked).length
    if (count >= 5) unlockAchievement('collector_5')
    if (count >= 10) unlockAchievement('collector_10')
    if (count >= 20) unlockAchievement('collector_20')
  }

  function updateProgress(id: string, progress: number, label?: string) {
    const ach = achievements.value.find(a => a.id === id)
    if (!ach || ach.unlocked) return
    ach.progress = Math.min(100, Math.max(0, progress))
    ach.progressLabel = label || `${Math.round(progress)}%`
    if (ach.progress >= 100) {
      unlockAchievement(id)
    }
    save()
  }

  // ── 公开方法：供各视图调用 ──

  function recordQuiz(correct: boolean, subject?: string) {
    stats.value.totalQuestions++
    stats.value.todayQuestions++
    if (correct) {
      stats.value.totalCorrect++
      stats.value.consecutiveCorrect++
      stats.value.maxConsecutiveCorrect = Math.max(stats.value.maxConsecutiveCorrect, stats.value.consecutiveCorrect)
    } else {
      stats.value.consecutiveCorrect = 0
    }
    if (subject) {
      stats.value.subjectsCovered.add(subject)
    }

    const total = stats.value.totalQuestions
    const accuracy = stats.value.totalCorrect / Math.max(total, 1)

    // 练习成就
    updateProgress('quiz_10', Math.min(100, total / 10 * 100), `${total}/10 题`)
    updateProgress('quiz_50', Math.min(100, total / 50 * 100), `${total}/50 题`)
    updateProgress('quiz_100', Math.min(100, total / 100 * 100), `${total}/100 题`)
    updateProgress('quiz_300', Math.min(100, total / 300 * 100), `${total}/300 题`)

    // 正确率
    if (total >= 10) {
      updateProgress('accuracy_80', Math.min(100, accuracy / 0.8 * 100), `${(accuracy * 100).toFixed(0)}%`)
      updateProgress('accuracy_90', Math.min(100, accuracy / 0.9 * 100), `${(accuracy * 100).toFixed(0)}%`)
    }

    // 连续正确
    if (stats.value.consecutiveCorrect >= 10) {
      unlockAchievement('perfect_10')
    }

    // 速学者
    if (stats.value.todayQuestions >= 20) {
      unlockAchievement('speed_learner')
    }

    // 全科通关
    if (stats.value.subjectsCovered.size >= 4) {
      unlockAchievement('four_in_one')
    }

    save()
  }

  function recordStreak() {
    const today = new Date().toISOString().slice(0, 10)
    if (stats.value.lastActiveDate === today) return

    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10)
    if (stats.value.lastActiveDate === yesterday) {
      stats.value.currentStreak++
    } else {
      stats.value.currentStreak = 1
    }
    stats.value.maxStreak = Math.max(stats.value.maxStreak, stats.value.currentStreak)
    stats.value.lastActiveDate = today
    stats.value.todayQuestions = 0

    const streak = stats.value.currentStreak
    updateProgress('streak_3', Math.min(100, streak / 3 * 100), `${streak}/3 天`)
    updateProgress('streak_7', Math.min(100, streak / 7 * 100), `${streak}/7 天`)
    updateProgress('streak_14', Math.min(100, streak / 14 * 100), `${streak}/14 天`)
    updateProgress('streak_30', Math.min(100, streak / 30 * 100), `${streak}/30 天`)
    updateProgress('streak_60', Math.min(100, streak / 60 * 100), `${streak}/60 天`)

    save()
  }

  function recordProfileBuilt() {
    if (stats.value.profileBuilt) return
    stats.value.profileBuilt = true
    unlockAchievement('profile_built')
    save()
  }

  function recordFirstChat() {
    if (stats.value.firstChat) return
    stats.value.firstChat = true
    unlockAchievement('first_chat')
    save()
  }

  function recordFirstResource() {
    if (stats.value.firstResource) return
    stats.value.firstResource = true
    unlockAchievement('first_resource')
    save()
  }

  function recordFirstPath() {
    if (stats.value.firstPath) return
    stats.value.firstPath = true
    unlockAchievement('first_path')
    save()
  }

  function recordKnowledgeBrowse(count: number = 1) {
    stats.value.knowledgeBrowsed += count
    updateProgress('knowledge_10', Math.min(100, stats.value.knowledgeBrowsed / 10 * 100), `${stats.value.knowledgeBrowsed}/10`)
    updateProgress('knowledge_50', Math.min(100, stats.value.knowledgeBrowsed / 50 * 100), `${stats.value.knowledgeBrowsed}/50`)
    save()
  }

  function recordKnowledgeGraph() {
    if (stats.value.kgBuilt) return
    stats.value.kgBuilt = true
    unlockAchievement('kg_built')
    save()
  }

  function recordMindMap() {
    if (stats.value.mindmapView) return
    stats.value.mindmapView = true
    unlockAchievement('mindmap_view')
    save()
  }

  function recordKnowledgeAll() {
    unlockAchievement('knowledge_all')
  }

  // ── 后端同步 ──

  async function fetchFromBackend() {
    try {
      const res = await api.get<any>('/achievement/list')
      if (res?.achievements) {
        const merged = ACHIEVEMENT_DEFS.map(def => {
          const serverAch = res.achievements.find((a: any) => a.id === def.id)
          if (serverAch) {
            return {
              ...def,
              unlocked: serverAch.unlocked || false,
              unlockedAt: serverAch.unlockedAt,
              progress: serverAch.progress ?? 0,
              progressLabel: serverAch.progressLabel || '0%',
            }
          }
          return {
            ...def,
            unlocked: false,
            progress: 0,
            progressLabel: '0%',
          }
        })
        achievements.value = merged
        if (res.stats) {
          stats.value = {
            ...stats.value,
            ...res.stats,
            subjectsCovered: new Set(res.stats.subjectsCovered || []),
          }
        }
        save()
      }
    } catch {
      // 后端不可用时保留本地数据
    }
  }

  async function syncToBackend(event: string, subject?: string, correct?: boolean) {
    try {
      await api.post('/achievement/record', { event, subject: subject || '', correct: correct || false })
    } catch {
      // 静默失败，本地数据已保存
    }
  }

  // 初始化
  init()

  return {
    achievements,
    stats,
    unlockedCount,
    totalCount,
    progressPercent,
    recentAchievements,
    categoryProgress,
    recordQuiz,
    recordStreak,
    recordProfileBuilt,
    recordFirstChat,
    recordFirstResource,
    recordFirstPath,
    recordKnowledgeBrowse,
    recordKnowledgeGraph,
    recordMindMap,
    recordKnowledgeAll,
    unlockAchievement,
    fetchFromBackend,
    syncToBackend,
  }
})