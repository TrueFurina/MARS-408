/**
 * 芒得很职 导航配置 —— 单一真值源 (Single Source of Truth)
 *
 * 背景：此前导航被硬编码在三处且互不一致 ——
 *   · src/App.vue          navItems      (17 项平铺，无分组)
 *   · src/App.vue          bottomNavItems(5 项)
 *   · src/components/MoreMenu.vue  menuItems (14 项)
 * 新增/下线页面必须改三处，极易漏改（如「学习路径」标签实际指向 /dashboard）。
 *
 * 本文件是唯一数据源，侧栏 / 底部导航 / 更多菜单全部由它派生。
 *
 * 设计约束（GStack IA 重构 · 2026-09-12）：
 *   1. 6 大分组，取代 17 项平铺：学习 / 练习与复盘 / 知识 / AI 技能工坊 / 实验室 / 我的
 *      （教师与管理员额外可见「教学与管理」）
 *   2. 不删除任何页面：演示与调试页统一收进「实验室」分组，默认折叠 + 「评审演示」标识
 *   3. 导航项 name 纯中文，图形由 icon 承担（ANTI-EMOJI），且 name 中禁止出现 emoji
 *   4. 功能重叠页降为子项（children），通过 router redirect + query.tab 归并，
 *      老 URL 全部保持可用
 *   5. 学情诊断（/diagnostic/start）补进「学习」分组首位 —— 它是学生主路径第一步
 */

import { icons } from '@/components/icons'

export type UserRole = 'student' | 'teacher' | 'admin'

/**
 * 场景域（双场景集成 · 2026-09-15）：
 *   · kaoyan  —— 场景A 专业能力训练（考研408）
 *   · career  —— 场景B 职业素养实训（芒得很职主线）
 *   · common  —— 通用（两场景都显示）
 * 缺省（undefined）等价 common，保证旧数据零改动兼容。
 */
export type Scene = 'kaoyan' | 'career' | 'common'

export interface NavItem {
  /** 唯一标识，用于 activeKey 高亮 */
  key: string
  /** 纯中文名称 —— 严禁 emoji，图形一律由 icon 字段承担 */
  name: string
  /** icons.ts 中的 SVG 字符串 */
  icon: string
  /** 跳转路径 */
  route: string
  /** 学科分色（可选）：nav-subject-0..3 */
  subjectClass?: string
  /**
   * 归并后的子视图标识，对应 URL 上的 ?tab=xxx。
   * 【P3 状态 · 2026-09-12】已完成归并（老 URL 经 router redirect 保持可用，无内容丢失）：
   *   · wrong-questions ← review / history（错题复盘 / 答题记录）
   *   · knowledge       ← course / build  （按科目浏览 / 从文本构建）
   * 其余子项（skills-platform「快速开始」、studio「Prompt 调试」、profile「重建画像」）
   * 因父页是市场 / 编辑器 / 画像看板，子页是不同交互范式，归并为页内 Tab 会损害 UX，
   * 故保持独立页面、仅在侧栏降一级展示。
   */
  tab?: string
  /** 是否匹配子路径，用于 /skills/:id、/studio/:id、/c/:convId 等动态路由 */
  matchChildren?: boolean
  /** 可见角色；不填 = 所有角色可见 */
  roles?: UserRole[]
  /** 场景域；不填 = common（两场景都显示） */
  scene?: Scene
  /** 子项（功能重叠、被归并的页面） */
  children?: NavItem[]
}

export interface NavGroup {
  id: string
  title: string
  icon: string
  items: NavItem[]
  /** 分组可见角色；不填 = 所有角色可见 */
  roles?: UserRole[]
  /** 场景域；不填 = common（两场景都显示） */
  scene?: Scene
  /** 是否可折叠 */
  collapsible?: boolean
  /** 初始是否折叠 */
  defaultCollapsed?: boolean
  /** 分组标题右侧徽标文案 */
  badge?: string
}

/** 角色兜底：未取到角色时按学生处理 */
export function resolveRole(raw: string | undefined | null): UserRole {
  return raw === 'admin' || raw === 'teacher' ? raw : 'student'
}

function visibleForRole<T extends { roles?: UserRole[] }>(entry: T, role: UserRole): boolean {
  return !entry.roles || entry.roles.includes(role)
}

export const NAV_GROUPS: NavGroup[] = [
  // ── 1. 学习（学生主路径）──────────────────────────────────────────────
  {
    id: 'learn',
    title: '学习',
    icon: icons.graduation,
    scene: 'kaoyan',
    roles: ['student'],
    items: [
      {
        // P0：此前完全不在任何导航里，学生主路径第一步
        key: 'diagnostic',
        name: '学情诊断',
        icon: icons.clipboard,
        route: '/diagnostic/start',
      },
      {
        key: 'dashboard',
        name: '今日总览',
        icon: icons.dashboard,
        route: '/kaoyan',
      },
      {
        key: 'chat',
        name: '智能对话',
        icon: icons.chat,
        route: '/chat',
        subjectClass: 'nav-subject-1',
        matchChildren: true, // /c/:convId
      },
      {
        key: 'resource',
        name: '资源生成',
        icon: icons.agent,
        route: '/resource',
        subjectClass: 'nav-subject-3',
      },
      {
        // 修正：原侧栏「学习路径」标签错误指向 /dashboard（首页）
        key: 'learning-path',
        name: '学习路径',
        icon: icons.path,
        route: '/learning-path',
      },
      {
        key: 'daily-plan',
        name: '每日计划',
        icon: icons.clock,
        route: '/daily-plan',
      },
    ],
  },

  // ── 2. 练习与复盘 ────────────────────────────────────────────────────
  {
    id: 'practice',
    title: '练习与复盘',
    icon: icons.quiz,
    scene: 'kaoyan',
    roles: ['student'],
    items: [
      {
        key: 'practice',
        name: '智能出题',
        icon: icons.quiz,
        route: '/practice',
        subjectClass: 'nav-subject-0',
      },
      {
        // 母页：错题本。两个同源视图降为子项，老 URL 由 router redirect 保留
        key: 'wrong-questions',
        name: '错题本',
        icon: icons.bookOpen,
        route: '/wrong-questions',
        children: [
          { key: 'review', name: '错题复盘', icon: icons.search, route: '/review', tab: 'review' },
          { key: 'quiz-history', name: '答题记录', icon: icons.history, route: '/quiz-history', tab: 'history' },
        ],
      },
      {
        key: 'assessment',
        name: '学习评估',
        icon: icons.barChart,
        route: '/assessment',
      },
    ],
  },

  // ── 3. 知识 ──────────────────────────────────────────────────────────
  {
    id: 'knowledge',
    title: '知识',
    icon: icons.knowledge,
    scene: 'kaoyan',
    items: [
      {
        // 母页：知识图谱。另两个图谱视图降为子项
        key: 'knowledge',
        name: '知识图谱',
        icon: icons.knowledge,
        route: '/knowledge',
        subjectClass: 'nav-subject-2',
        children: [
          { key: 'course-explorer', name: '按科目浏览', icon: icons.compass, route: '/course-explorer', tab: 'course' },
          { key: 'knowledge-graph', name: '从文本构建', icon: icons.sparkle, route: '/knowledge-graph', tab: 'build' },
        ],
      },
      {
        // RAG 文档库，与图谱是两种能力，保持独立
        key: 'knowledge-base',
        name: '知识库',
        icon: icons.book,
        route: '/knowledge-base',
      },
    ],
  },

  // ── 4. AI 技能工坊 ───────────────────────────────────────────────────
  {
    id: 'skills',
    title: 'AI 技能工坊',
    icon: icons.skill,
    scene: 'kaoyan',
    items: [
      {
        key: 'skills',
        name: '技能市场',
        icon: icons.skill,
        route: '/skills',
        matchChildren: true, // /skills/:id
        children: [
          { key: 'skill-platform', name: '快速开始', icon: icons.rocket, route: '/skill-platform', tab: 'start' },
        ],
      },
      {
        key: 'studio',
        name: '技能工坊',
        icon: icons.wrench,
        route: '/studio',
        matchChildren: true, // /studio/:id
        children: [
          { key: 'prompt-studio', name: 'Prompt 调试', icon: icons.terminal, route: '/prompt-studio', tab: 'prompt' },
        ],
      },
      {
        key: 'creator-dashboard',
        name: '我的创作',
        icon: icons.chartUp,
        route: '/creator-dashboard',
      },
    ],
  },

  // ── 5. 职业素养实训（场景B · 芒得很职主线）────────────────────────────
  {
    id: 'career',
    title: '职业素养实训',
    icon: icons.target,
    scene: 'career',
    items: [
      {
        key: 'career-training',
        name: '对抗实训',
        icon: icons.target,
        route: '/career/training',
      },
      {
        // P4：对抗实训教师端（建班/花名册/任务码/班级看板）
        key: 'career-teacher',
        name: '实训任务',
        icon: icons.graduation,
        route: '/career/teacher',
        roles: ['teacher', 'admin'],
      },
    ],
  },

  // ── 6. 实验室（演示 / 调试页，默认折叠，一个都不删）──────────────────
  {
    id: 'lab',
    title: '实验室',
    icon: icons.microscope,
    scene: 'common',
    collapsible: true,
    defaultCollapsed: true,
    badge: '评审演示',
    items: [
      { key: 'showcase', name: '技术全景', icon: icons.palette, route: '/showcase' },
      { key: 'engine', name: '算法引擎', icon: icons.engine, route: '/engine', subjectClass: 'nav-subject-0' },
      { key: 'benchmark', name: '效果基准', icon: icons.trendUp, route: '/benchmark' },
      { key: 'memory', name: '学情记忆', icon: icons.brain, route: '/memory' },
      { key: 'sandbox', name: '代码沙箱', icon: icons.play, route: '/sandbox' },
      { key: 'code-lab', name: 'C/C++ 实验室', icon: icons.fileText, route: '/code-lab' },
      { key: 'design-system', name: '设计系统', icon: icons.edit, route: '/design-system' },
    ],
  },

  // ── 6. 我的 ──────────────────────────────────────────────────────────
  {
    id: 'me',
    title: '我的',
    icon: icons.user,
    items: [
      {
        key: 'profile',
        name: '学习画像',
        icon: icons.user,
        route: '/profile',
        matchChildren: true, // /profile/build
        children: [
          { key: 'profile-build', name: '重建画像', icon: icons.refresh, route: '/profile/build' },
        ],
      },
      { key: 'achievements', name: '成就', icon: icons.star, route: '/achievements' },
      { key: 'settings', name: '设置', icon: icons.setting, route: '/settings' },
    ],
  },

  // ── 7. 教学与管理（仅教师 / 管理员）──────────────────────────────────
  {
    id: 'staff',
    title: '教学与管理',
    icon: icons.shield,
    roles: ['teacher', 'admin'],
    items: [
      {
        key: 'teacher',
        name: '教学看板',
        icon: icons.graduation,
        route: '/teacher',
        roles: ['teacher', 'admin'],
      },
      {
        key: 'admin',
        name: '平台数据',
        icon: icons.dashboard,
        route: '/admin',
        roles: ['admin'],
      },
      {
        // 修正：原 MoreMenu 把 /admin 标注为「RAG 管理」，实际 RAG 管理是 /admin/knowledge
        key: 'admin-knowledge',
        name: '知识库管理',
        icon: icons.book,
        route: '/admin/knowledge',
        roles: ['admin'],
      },
      {
        key: 'audit-log',
        name: '审计日志',
        icon: icons.shield,
        route: '/audit-log',
        roles: ['teacher', 'admin'],
      },
    ],
  },
]

/** 移动端底部导航的 key（从 NAV_GROUPS 中按 key 选取，避免二次硬编码） */
export const BOTTOM_NAV_KEYS = ['chat', 'practice', 'learning-path', 'wrong-questions', 'profile']

/** 场景匹配：缺省 / common 视为通用（始终显示）；scene 未指定时不过滤（向后兼容） */
function visibleForScene(entry: { scene?: Scene }, scene?: Scene): boolean {
  if (!scene) return true
  const s = entry.scene ?? 'common'
  return s === 'common' || s === scene
}

/** 按角色 + 场景过滤后的分组 + 分组内条目（含子项）过滤 */
export function visibleGroups(role: UserRole, scene?: Scene): NavGroup[] {
  return NAV_GROUPS
    .filter((g) => visibleForRole(g, role) && visibleForScene(g, scene))
    .map((g) => ({
      ...g,
      items: g.items
        .filter((i) => visibleForRole(i, role) && visibleForScene(i, scene))
        .map((i) => ({
          ...i,
          children: i.children?.filter((c) => visibleForRole(c, role) && visibleForScene(c, scene)),
        })),
    }))
    .filter((g) => g.items.length > 0)
}

/** 展开为扁平列表（父项 + 子项），供高亮匹配与更多菜单使用 */
export function flattenItems(groups: NavGroup[]): NavItem[] {
  const out: NavItem[] = []
  for (const g of groups) {
    for (const i of g.items) {
      out.push(i)
      if (i.children?.length) out.push(...i.children)
    }
  }
  return out
}

/** 更多菜单（移动端 = 全量导航）：保留原 divider 分组语义，但内容由配置派生 */
export function buildMoreMenu(role: UserRole): Array<NavItem | { divider: true }> {
  const out: Array<NavItem | { divider: true }> = []
  visibleGroups(role).forEach((g, gi) => {
    if (gi > 0) out.push({ divider: true })
    for (const i of g.items) {
      out.push(i)
      if (i.children?.length) out.push(...i.children)
    }
  })
  return out
}

/** 路径是否命中该条目 */
export function pathMatches(item: NavItem, path: string): boolean {
  if (path === item.route) return true
  return !!item.matchChildren && path.startsWith(item.route + '/')
}

/** 当前激活项的 key —— 取代原 17 行 path.startsWith 硬编码 */
export function resolveActiveKey(groups: NavGroup[], path: string, tab?: string): string {
  const matched = flattenItems(groups).filter((i) => pathMatches(i, path))
  if (matched.length === 0) return ''
  if (tab) {
    // 归并页：在匹配到的父项及其子项中找 tab 命中，高亮对应子项
    const candidates = matched.flatMap((i) => (i.children?.length ? [i, ...i.children] : [i]))
    const hit = candidates.find((i) => i.tab === tab)
    if (hit) return hit.key
  }
  // 优先最长路径匹配：/profile/build 应高亮「重建画像」而非「学习画像」
  const sorted = [...matched].sort((a, b) => b.route.length - a.route.length)
  // matched 已非空校验；sorted 可能全为带 tab 的项，兜底用 matched[0]
  return (sorted.find((i) => !i.tab) ?? matched[0]!).key
}
