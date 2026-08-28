import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/DashboardView.vue'),
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/diagnostic/start',
      name: 'diagnostic',
      component: () => import('@/views/DiagnosticView.vue'),
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
    },
    {
      path: '/c/:convId',
      name: 'chat-conv',
      component: () => import('@/views/ChatView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
    },
    {
      path: '/dashboard',
      redirect: '/',
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('@/views/ProfileView.vue'),
    },
    {
      path: '/knowledge',
      name: 'knowledge',
      component: () => import('@/views/KnowledgeView.vue'),
    },
    {
      path: '/admin',
      name: 'admin',
      meta: { requiresRole: 'admin' },
      component: () => import('@/views/AdminView.vue'),
    },
    {
      path: '/teacher',
      name: 'teacher',
      component: () => import('@/views/TeacherView.vue'),
    },
    {
      path: '/admin/knowledge',
      name: 'admin-knowledge',
      meta: { requiresRole: 'admin' },
      component: () => import('@/views/KnowledgeAdminView.vue'),
    },
    {
      path: '/practice',
      name: 'practice',
      meta: { profileRequired: true },
      component: () => import('@/views/PracticeView.vue'),
    },
    {
      path: '/quiz-history',
      name: 'quiz-history',
      component: () => import('@/views/QuizHistoryView.vue'),
    },
    {
      path: '/profile/build',
      name: 'profile-build',
      component: () => import('@/views/ProfileBuilder.vue'),
    },
    {
      path: '/resource',
      name: 'resource',
      meta: { profileRequired: true },
      component: () => import('@/views/ResourceView.vue'),
    },
    {
      path: '/learning-path',
      name: 'learning-path',
      meta: { profileRequired: true },
      component: () => import('@/views/LearningPathView.vue'),
    },
    {
      path: '/sandbox',
      name: 'sandbox',
      component: () => import('@/views/SandboxView.vue'),
    },
    {
      path: '/code-lab',
      name: 'code-lab',
      component: () => import('@/views/CodeLabView.vue'),
    },
    {
      path: '/memory',
      name: 'memory',
      component: () => import('@/views/MemoryView.vue'),
    },
    {
      path: '/assessment',
      name: 'assessment',
      component: () => import('@/views/AssessmentView.vue'),
    },
    {
      path: '/achievements',
      name: 'achievements',
      component: () => import('@/views/AchievementView.vue'),
    },
    {
      path: '/review',
      name: 'review',
      component: () => import('@/views/ReviewView.vue'),
    },
    {
      path: '/benchmark',
      name: 'benchmark',
      component: () => import('@/views/BenchmarkView.vue'),
    },
    {
      path: '/engine',
      name: 'engine',
      component: () => import('@/views/EngineView.vue'),
    },
    {
      path: '/showcase',
      name: 'showcase',
      meta: { public: true },
      component: () => import('@/views/ShowcaseView.vue'),
    },
    {
      path: '/design-system',
      name: 'design-system',
      component: () => import('@/views/DesignSystemView.vue'),
    },
    {
      path: '/skills',
      name: 'skills',
      component: () => import('@/views/SkillMarketView.vue'),
    },
    {
      path: '/skills/:id',
      name: 'skill-detail',
      component: () => import('@/views/SkillDetailView.vue'),
    },
    {
      path: '/studio',
      name: 'skill-studio',
      component: () => import('@/views/SkillStudioView.vue'),
    },
    {
      path: '/studio/:id',
      name: 'skill-studio-edit',
      component: () => import('@/views/SkillStudioView.vue'),
    },
    {
      path: '/prompt-studio',
      name: 'prompt-studio',
      component: () => import('@/views/PromptStudioView.vue'),
    },
    {
      path: '/creator-dashboard',
      name: 'creator-dashboard',
      component: () => import('@/views/CreatorDashboardView.vue'),
    },
    {
      path: '/knowledge-graph',
      name: 'knowledge-graph',
      component: () => import('@/views/KnowledgeGraphView.vue'),
    },
    {
      path: '/knowledge-base',
      name: 'knowledge-base',
      component: () => import('@/views/KnowledgeBaseView.vue'),
    },
    {
      path: '/audit-log',
      name: 'audit-log',
      meta: { requiresRole: ['admin', 'teacher'] },
      component: () => import('@/views/AuditLogView.vue'),
    },
    {
      path: '/landing',
      name: 'landing',
      meta: { public: true },
      component: () => import('@/views/LandingView.vue'),
    },
    {
      path: '/skill-platform',
      name: 'skill-platform',
      component: () => import('@/views/SkillPlatformView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
    },
  ],
})

export default router

// ── 登录守卫 ──
// 注：router 在 Pinia 初始化前加载，因此直接读 localStorage 而非 authStore；
// 权限通过路由 meta 声明（requiresRole / public / profileRequired），消除硬编码 path 判断。
router.beforeEach((to) => {
  let token: string | null = null
  let user: any = null
  try {
    token = localStorage.getItem('mars408_token')
    const u = localStorage.getItem('mars408_user')
    if (u) user = JSON.parse(u)
  } catch { /* */ }

  // 公开路由（meta.public）免登录：评委入口 /landing、设计原型聚合 /showcase
  if ((to.meta as any)?.public) return true

  // 未登录且非登录页 → 跳登录
  if (!token && to.path !== '/login') return { path: '/login' }
  // 已登录访问登录页 → 跳首页
  if (token && to.path === '/login') return { path: '/' }

  // 角色校验：meta.requiresRole 可为字符串或字符串数组
  const required = (to.meta as any)?.requiresRole
  if (required) {
    const ok = Array.isArray(required)
      ? required.includes(user?.role)
      : user?.role === required
    if (!ok) return { path: '/' }
  }
  return true
})
