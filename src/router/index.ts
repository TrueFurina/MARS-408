import { createRouter, createWebHashHistory } from 'vue-router'

// hash 路由（而非 history 路由）：发布域是纯静态托管、无 SPA history 回退，
// history 模式下直接访问 /cloud-lab 等子路由会 404；hash 模式（/#/cloud-lab）
// 的路径部分不发给服务器，任何子页面都能直接打开 / 刷新 / 分享链接。
const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: [
    {
      // 平台统一入口（双场景门户）：登录后首屏，选择「专业能力训练 / 职业素养实训」
      path: '/',
      name: 'platform-home',
      component: () => import('@/views/PlatformHomeView.vue'),
    },
    {
      // 场景A首页：考研408 总览（门户 kaoyan 卡片与侧栏「今日总览」的落点）
      path: '/kaoyan',
      name: 'kaoyan-home',
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
      // 真实证据台：结论看板 + 真实产物画廊（sha256 溯源）
      path: '/evidence',
      name: 'experiments-evidence',
      component: () => import('@/views/ExperimentEvidenceView.vue'),
    },
    {
      // 旧首页别名：原「进站即考研 Dashboard」行为保留为 redirect（语义 = 考研总览）
      path: '/dashboard',
      redirect: '/kaoyan',
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
      meta: { requiresRole: ['teacher', 'admin'] },
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
      // P4 掌握度地图：科目掌握度 + 薄弱点可视化
      path: '/mastery-map',
      name: 'mastery-map',
      meta: { profileRequired: true, title: '掌握度地图' },
      component: () => import('@/views/MasteryMapView.vue'),
    },
    {
      // P3 归并：答题记录并入「错题本」页内 Tab（?tab=history），老 URL 经 redirect 保持可用
      path: '/quiz-history',
      name: 'quiz-history',
      redirect: { path: '/wrong-questions', query: { tab: 'history' } },
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
      // A2（2026-10-14）：navConfig「代码沙箱」项早有 roles: ['teacher','admin']，
      // 但路由本身无 meta —— 学生输 URL 即可打开职员 UI（F2 同款纵深缺失）。
      // 导航隐藏只是可视性，角色守卫必须落在路由上；后端 Sandbox 执行端点另有防线。
      meta: { requiresRole: ['teacher', 'admin'] },
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
      // 职业素养测评（对照实验载体）：10 题行为分档计分，六维前后测
      path: '/literacy',
      name: 'literacy-assessment',
      component: () => import('@/views/LiteracyAssessmentView.vue'),
    },
    {
      // 教师端：班级素养六维报告（前后测聚合 + CSV 导出）
      path: '/literacy/teacher',
      name: 'literacy-teacher',
      meta: { requiresRole: ['teacher', 'admin'] },
      component: () => import('@/views/TeacherLiteracyReportView.vue'),
    },
    {
      path: '/achievements',
      name: 'achievements',
      component: () => import('@/views/AchievementView.vue'),
    },
    {
      path: '/wrong-questions',
      name: 'wrong-questions',
      component: () => import('@/views/WrongQuestionsView.vue'),
    },
    {
      path: '/daily-plan',
      name: 'daily-plan',
      component: () => import('@/views/DailyPlanView.vue'),
    },
    {
      // 云服务接入：源码实验室进度 / 源码文件的云端存档 + 免密钥 AI 助教
      path: '/cloud-lab',
      name: 'cloud-lab',
      component: () => import('@/views/CloudLabView.vue'),
    },
    {
      path: '/career/training',
      name: 'career-training',
      component: () => import('@/views/CareerTrainingView.vue'),
    },
    {
      // F4 学生端：个人成长页（六维趋势 / 前后测对比 / 证据金句）
      path: '/career/growth',
      name: 'career-growth',
      component: () => import('@/views/StudentGrowthView.vue'),
    },
    {
      // P4 教师端：对抗实训建班/发任务/班级看板
      path: '/career/teacher',
      name: 'career-teacher',
      meta: { requiresRole: ['teacher', 'admin'] },
      component: () => import('@/views/TeacherCareerView.vue'),
    },
    {
      // P3 归并：错题复盘并入「错题本」页内 Tab（?tab=review），老 URL 经 redirect 保持可用
      path: '/review',
      name: 'review',
      redirect: { path: '/wrong-questions', query: { tab: 'review' } },
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
      // 设计升级预览：取自 30 关键词落地的可交互样片（公开，便于评审/演示直接预览）
      path: '/design-upgrade',
      name: 'design-upgrade',
      meta: { public: true },
      component: () => import('@/views/DesignUpgradeView.vue'),
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
      // P3 归并：从文本构建并入「知识图谱」页内 Tab（?tab=build），老 URL 经 redirect 保持可用
      path: '/knowledge-graph',
      name: 'knowledge-graph',
      redirect: { path: '/knowledge', query: { tab: 'build' } },
    },
    {
      // P3 归并：按科目浏览并入「知识图谱」页内 Tab（?tab=course），老 URL 经 redirect 保持可用
      path: '/course-explorer',
      name: 'course-explorer',
      redirect: { path: '/knowledge', query: { tab: 'course' } },
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
// 公开展示站（非 localhost）无后端：未登录一律引导到展示落地页 /landing，
// 避免"一进来就落在登不进去的登录页"；本地站保持原行为（未登录 → /login）。
const IS_PUBLIC_SITE = !['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)

router.beforeEach((to) => {
  let token: string | null = null
  let user: any = null
  try {
    token = localStorage.getItem('mangdehenzhi_token')
    const u = localStorage.getItem('mangdehenzhi_user')
    if (u) user = JSON.parse(u)
  } catch { /* */ }

  // 公开路由（meta.public）免登录：评委入口 /landing、设计原型聚合 /showcase
  if ((to.meta as any)?.public) return true

  // 公开展示站：未登录访问受保护页 → 展示落地页；直接访问 /login 仍放行（含"展示版"提示）
  if (!token && IS_PUBLIC_SITE) {
    return to.path === '/login' ? true : { path: '/landing' }
  }

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
