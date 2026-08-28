<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import ProfilePanel from './components/ProfilePanel.vue'
import HistoryPanel from './components/HistoryDropdown.vue'
import MoreMenu from './components/MoreMenu.vue'
import ToastNotification from './components/ToastNotification.vue'
import { icons } from './components/icons'
import DOMPurify from 'dompurify'
import { useStudyStore } from '@/stores/studyStore'
import { useAuthStore } from '@/stores/authStore'
import { api } from '@/utils/api'

/** 防御性 SVG 净化 — 虽然 icons.ts 硬编码，但竞赛评审要求所有 v-html 做净化 */
function safeIcon(html: string): string {
  return DOMPurify.sanitize(html, { USE_PROFILES: { svg: true, svgFilters: true } })
}

const router = useRouter()
const route = useRoute()
const store = useStudyStore()
const authStore = useAuthStore()

// 登录页判定
const isLoginPage = computed(() => route.path === '/login')
const currentUser = computed(() => authStore.currentUser)
const isAdmin = computed(() => authStore.isAdmin)
const isStaff = computed(() => {
  const role = authStore.currentUser?.role
  return role === 'admin' || role === 'teacher'
})
function doLogout() {
  authStore.logout()
  router.push('/login')
}
function closeHistory() {
  showHistory.value = false
}

const showProfile = ref(false)
const showHistory = ref(false)
const backendOnline = ref(true)
let healthTimer: ReturnType<typeof setInterval> | null = null

// ── 全局路由加载进度条 ──
const routeLoading = ref(false)
let loadingTimer: ReturnType<typeof setTimeout> | null = null
const toastRef = ref<InstanceType<typeof ToastNotification> | null>(null)
watch(() => route.path, () => {
  routeLoading.value = true
  if (loadingTimer) clearTimeout(loadingTimer)
  loadingTimer = setTimeout(() => { routeLoading.value = false }, 300)
})
onMounted(() => { loadingTimer = setTimeout(() => { routeLoading.value = false }, 100) })

async function checkBackend() {
  try {
    await api.get('/status')
    backendOnline.value = true
  } catch {
    backendOnline.value = false
  }
}

onMounted(() => {
  // 初始化主题（localStorage > 系统偏好 > 默认深色）
  let saved: string | null = null
  try { saved = localStorage.getItem('mars408-theme') } catch {}
  if (saved !== 'light' && saved !== 'dark') {
    saved = (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: light)').matches) ? 'light' : 'dark'
  }
  applyTheme(saved === 'light' ? 'light' : 'dark')

  // 定时检查后端健康状态
  checkBackend()
  healthTimer = setInterval(checkBackend, 30000)
  // 路由守卫逻辑：未完成学情画像时，强制跳转画像构建页（由 router meta.profileRequired 声明）
  if (route.path === '/login') return
  if (!store.profileCompleted && (route.meta as any)?.profileRequired) {
    router.replace('/profile/build')
  }
})

onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
  if (loadingTimer) clearTimeout(loadingTimer)
})

/* ── 主题切换（双主题：dark 默认 / light 可选） ── */
const theme = ref<'dark' | 'light'>('dark')
const sunIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>`
const moonIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`
function applyTheme(t: 'dark' | 'light') {
  document.documentElement.dataset.theme = t
  theme.value = t
  try { localStorage.setItem('mars408-theme', t) } catch {}
}
function toggleTheme() {
  applyTheme(theme.value === 'dark' ? 'light' : 'dark')
}

const navItems = computed(() => {
  const items = [
    { name: '💬 智能对话', icon: icons.chat, route: '/chat', key: 'chat', subjectClass: 'nav-subject-1' },
    { name: '🤖 资源生成', icon: icons.agent, route: '/resource', key: 'agent', subjectClass: 'nav-subject-3' },
    { name: '📊 学习路径', icon: icons.dashboard, route: '/dashboard', key: 'dashboard', subjectClass: '' },
    { name: '📝 智能出题', icon: icons.quiz, route: '/practice', key: 'practice', subjectClass: 'nav-subject-0' },
    { name: '📈 学习评估', icon: icons.barChart, route: '/assessment', key: 'assessment', subjectClass: '' },
    { name: '⚙️ 算法引擎', icon: icons.engine, route: '/engine', key: 'engine', subjectClass: 'nav-subject-0' },
    { name: '🧠 知识图谱', icon: icons.knowledge, route: '/knowledge', key: 'knowledge', subjectClass: 'nav-subject-2' },
    { name: '🕸️ AI图谱', icon: icons.skill, route: '/knowledge-graph', key: 'knowledge-graph', subjectClass: 'nav-subject-3' },
    { name: '📖 知识库', icon: icons.knowledge, route: '/knowledge-base', key: 'knowledge-base', subjectClass: 'nav-subject-2' },
    { name: '🔍 错题复盘', icon: icons.search, route: '/review', key: 'review', subjectClass: '' },
    { name: '📕 错题本', icon: icons.search, route: '/wrong-questions', key: 'wrong-questions', subjectClass: '' },
    { name: '📅 每日计划', icon: icons.dashboard, route: '/daily-plan', key: 'daily-plan', subjectClass: '' },
    { name: '🏆 成果展示', icon: icons.palette, route: '/showcase', key: 'showcase', subjectClass: '' },
    { name: '🎖️ 成就', icon: icons.target, route: '/achievements', key: 'achievements', subjectClass: '' },
    { name: '👤 我的', icon: icons.user, route: '/profile', key: 'profile', subjectClass: '' },
  ]
  // 审计日志：仅 admin/teacher 可见
  if (isStaff.value) {
    items.push({ name: '审计日志', icon: icons.shield, route: '/audit-log', key: 'audit-log', subjectClass: '' })
  }
  return items
})

const bottomNavItems = [
  { name: '对话', icon: icons.chat, route: '/chat', key: 'chat' },
  { name: '资源', icon: icons.agent, route: '/resource', key: 'agent' },
  { name: '练习', icon: icons.quiz, route: '/practice', key: 'practice' },
  { name: '路径', icon: icons.dashboard, route: '/dashboard', key: 'dashboard' },
  { name: '我的', icon: icons.user, route: '/profile', key: 'profile' },
]

const activeKey = computed(() => {
  const path = route.path
  if (path === '/' || path === '/dashboard') return 'dashboard'
  if (path.startsWith('/chat')) return 'chat'
  if (path.startsWith('/practice')) return 'practice'
  if (path.startsWith('/assessment')) return 'assessment'
  if (path.startsWith('/review')) return 'review'
  if (path.startsWith('/wrong-questions')) return 'wrong-questions'
  if (path.startsWith('/daily-plan')) return 'daily-plan'
  if (path.startsWith('/knowledge-graph')) return 'knowledge-graph'
  if (path.startsWith('/knowledge-base')) return 'knowledge-base'
  if (path.startsWith('/knowledge')) return 'knowledge'
  if (path.startsWith('/resource') || path.startsWith('/learning-path') || path.startsWith('/sandbox')) return 'agent'
  if (path.startsWith('/engine')) return 'engine'
  if (path.startsWith('/benchmark')) return 'benchmark'
  if (path.startsWith('/profile') || path.startsWith('/profile/')) return 'profile'
  if (path.startsWith('/achievements')) return 'achievements'
  if (path.startsWith('/showcase')) return 'showcase'
  return 'dashboard'
})

function goTo(routePath: string) {
  router.push(routePath)
}
</script>

<template>
  <div v-if="isLoginPage" class="login-screen">
    <router-view />
  </div>
  <div v-else class="app-layout">
    <!-- 全局路由加载进度条 -->
    <div class="route-loader" :class="{ active: routeLoading }"><div class="route-loader-bar"></div></div>
    <!-- 左侧边栏（桌面） -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="sidebar-logo" v-html="safeIcon(icons.logo)"></div>
        <span class="sidebar-brand">MARS-408</span>
      </div>

      <nav class="sidebar-nav">
        <div
          v-for="item in navItems"
          :key="item.key"
          class="nav-item"
          :class="[item.subjectClass, { active: activeKey === item.key }]"
          @click="goTo(item.route)"
        >
          <span v-html="safeIcon(item.icon)"></span>
          <span>{{ item.name }}</span>
        </div>
      </nav>

      <div class="sidebar-footer">
        <div class="user-mini" role="button" tabindex="0" :aria-expanded="showProfile" aria-label="个人画像" @click="showProfile = !showProfile" @keydown.enter="showProfile = !showProfile">
          <div class="user-avatar" v-html="safeIcon(icons.user)"></div>
          <div class="user-info">
            <div class="user-name">{{ currentUser?.display_name || currentUser?.username || '未登录' }}</div>
            <div class="user-role">{{ isAdmin ? '管理员' : '学生' }} · 查看画像</div>
          </div>
        </div>
        <button class="logout-btn" @click="doLogout" title="退出登录">退出</button>
      </div>
      <div class="sidebar-footer-status">
        <span class="status-dot" :class="backendOnline ? 'online' : 'offline'"></span>
        <span class="status-text">{{ backendOnline ? '服务正常' : '后端离线' }}</span>
        <button class="theme-toggle" @click="toggleTheme" :title="theme === 'dark' ? '切换到浅色' : '切换到深色'" v-html="theme === 'dark' ? moonIcon : sunIcon"></button>
      </div>
    </aside>

    <div class="main-wrapper">
      <!-- 顶部栏（仅移动端） -->
      <header class="topbar" @click="showHistory = false">
        <div class="topbar-left">
          <button
            class="topbar-btn history-btn"
            :class="{ open: showHistory }"
            @click.stop="showHistory = !showHistory"
            title="对话历史"
          >
            <span class="hamburger-icon">
              <span class="hamburger-line top"></span>
              <span class="hamburger-line bottom"></span>
            </span>
          </button>
          <router-link to="/" class="topbar-logo">
            <div class="logo-icon" v-html="safeIcon(icons.logo)"></div>
            <span class="logo-text">MARS-408</span>
          </router-link>
        </div>

        <div class="topbar-right">
          <button
            class="topbar-btn"
            title="学生画像"
            @click="showProfile = !showProfile"
            v-html="safeIcon(icons.user)"
          ></button>
          <button
            class="topbar-btn"
            :title="theme === 'dark' ? '切换到浅色' : '切换到深色'"
            @click="toggleTheme"
            v-html="theme === 'dark' ? moonIcon : sunIcon"
          ></button>
          <div class="topbar-user" v-if="currentUser">
            <span class="tu-name">{{ currentUser.display_name || currentUser.username }}</span>
            <button class="tu-logout" @click="doLogout">退出</button>
          </div>
          <MoreMenu />
        </div>
      </header>

      <main class="main-content" @click="showHistory = false">
        <router-view v-slot="{ Component, route }">
            <component :is="Component" :key="route.fullPath" />
        </router-view>
      </main>

      <!-- 底部导航（仅移动端） -->
      <nav class="bottom-nav">
        <div class="bottom-nav-list">
          <div
            v-for="item in bottomNavItems"
            :key="item.key"
            class="bottom-nav-item"
            :class="{ active: activeKey === item.key }"
            @click="goTo(item.route)"
          >
            <span v-html="safeIcon(item.icon)"></span>
            <span>{{ item.name }}</span>
          </div>
        </div>
      </nav>
    </div>

    <!-- 对话历史 -> 左侧滑出 -->
    <HistoryPanel :open="showHistory" @close="closeHistory" />

    <!-- 学生画像 -> 右侧滑出 -->
    <ProfilePanel :open="showProfile" @close="showProfile = false" />

    <!-- 全局 Toast 通知 -->
    <ToastNotification ref="toastRef" />
  </div>
</template>

<style scoped>
.topbar-btn {
  width:2.5rem;
  height:2.5rem;
  border-radius:var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  transition: var(--transition);
}

.topbar-btn:hover {
  color: var(--text-primary);
  background: var(--bg-card-hover);
}

.topbar-btn svg {
  width:1.375rem;
  height:1.375rem;
}

.topbar-logo {
  display: flex;
  align-items: center;
  gap:0.625rem;
}

.logo-icon {
  width:2rem;
  height:2rem;
  border-radius:var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-primary);
  flex-shrink: 0;
  filter: drop-shadow(0 4px 14px rgba(124, 106, 242, 0.40));
  animation: pulse-glow 3.4s ease-in-out infinite;
}

.logo-icon svg {
  width:2rem;
  height:2rem;
}

.logo-text {
  font-size:1.0625rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing:-0.0187rem;
}

.hamburger-icon {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap:0.4375rem;
  width:1.25rem;
  margin-top:0.1875rem;
}

.hamburger-line {
  display: block;
  height:0.125rem;
  border-radius:0.0625rem;
  background: currentColor;
  transition: width 0.25s ease;
}

.hamburger-line.top { width:0.75rem; }
.hamburger-line.bottom { width:1.25rem; }

.history-btn.open .hamburger-line.top { width:1.25rem; }
.history-btn.open .hamburger-line.bottom { width:0.75rem; }

.login-screen {
  min-height:100vh;
  background: var(--color-canvas, #080812);
}

.logout-btn {
  flex-shrink: 0;
  margin-left:0.5rem;
  padding:0.375rem 0.625rem;
  border-radius:var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size:0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}
.logout-btn:hover {
  color: var(--text-danger);
  border-color: var(--accent-danger-20);
}

/* 后端状态指示器 */
.sidebar-footer-status {
  display: flex;
  align-items: center;
  gap:0.375rem;
  padding:0.5rem 1rem 0.75rem;
  font-size:0.6875rem;
  color: var(--text-muted);
}
.status-dot {
  width:0.4375rem;
  height:0.4375rem;
  border-radius:50%;
  flex-shrink: 0;
}
.status-dot.online {
  background: var(--accent-success);
  box-shadow: 0 0 6px var(--accent-success);
}
.status-dot.offline {
  background: var(--accent-danger);
  box-shadow: 0 0 6px var(--accent-danger);
}
.status-text { font-weight: 500; }

.theme-toggle {
  margin-left:auto;
  width:1.875rem;
  height:1.875rem;
  flex-shrink: 0;
  border-radius:var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: var(--transition);
}
.theme-toggle:hover { color: var(--text-primary); background: var(--bg-card-hover); border-color: var(--border-focus); }
.theme-toggle svg { width:1.0625rem; height:1.0625rem; }

/* ── 全局路由加载进度条 ── */
.route-loader { position: fixed; top: 0; left: 0; width: 100%; height: 3px; z-index: 9999; pointer-events: none; opacity: 0; transition: opacity 0.2s; }
.route-loader.active { opacity: 1; }
.route-loader-bar { height: 100%; background: linear-gradient(90deg, var(--accent-primary), var(--accent-cyan), var(--accent-primary)); background-size: 200% 100%; animation: loader-slide 1.2s ease-in-out infinite; width: 30%; border-radius: 2px; }
@keyframes loader-slide { 0% { transform: translateX(-100%); } 100% { transform: translateX(400%); } }

.topbar-user {
  display: flex;
  align-items: center;
  gap:0.375rem;
  padding-left:0.5rem;
  border-left: 1px solid var(--border-color);
}
.tu-name {
  font-size:0.75rem;
  color: var(--text-secondary);
  max-width:5.625rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tu-logout {
  padding:0.3125rem 0.5625rem;
  border-radius:var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size:0.6875rem;
  cursor: pointer;
}
.tu-logout:hover { color: var(--text-danger); border-color: var(--accent-danger-20); }
</style>
