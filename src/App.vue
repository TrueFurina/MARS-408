<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import ProfilePanel from './components/ProfilePanel.vue'
import HistoryPanel from './components/HistoryDropdown.vue'
import MoreMenu from './components/MoreMenu.vue'
import ToastNotification from './components/ToastNotification.vue'
import ErrorBoundary from './components/ErrorBoundary.vue'
import { icons } from './components/icons'
import DOMPurify from 'dompurify'
import { useStudyStore } from '@/stores/studyStore'
import { useAuthStore } from '@/stores/authStore'
import { api } from '@/utils/api'
import {
  NAV_GROUPS,
  BOTTOM_NAV_KEYS,
  visibleGroups,
  flattenItems,
  resolveActiveKey,
  resolveRole,
  type NavItem,
} from '@/router/navConfig'

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
const currentRole = computed(() => resolveRole(authStore.currentUser?.role))
const roleLabel = computed(() =>
  ({ admin: '管理员', teacher: '教师', student: '学生' })[currentRole.value] ?? '学生',
)
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

// ── 导航：全部由 src/router/navConfig.ts 单一真值源派生 ────────────────
// 此前侧栏 17 项 / 底部 5 项 / 更多菜单 14 项三处硬编码，新增页面极易漏改。
const navGroups = computed(() => visibleGroups(currentRole.value))
const bottomNavItems = computed(() =>
  BOTTOM_NAV_KEYS
    .map((k) => flattenItems(navGroups.value).find((i) => i.key === k))
    .filter((i): i is NavItem => !!i),
)

// 分组折叠状态：初始取 defaultCollapsed（实验室默认收起）
const collapsed = ref<Record<string, boolean>>(
  Object.fromEntries(NAV_GROUPS.map((g) => [g.id, !!g.defaultCollapsed])),
)
const activeTab = computed(() => (typeof route.query.tab === 'string' ? route.query.tab : undefined))

// 高亮：由配置解析，取代原先 17 行 path.startsWith 硬编码
const activeKey = computed(() => resolveActiveKey(navGroups.value, route.path, activeTab.value))
// 当前激活项所属的分组（用于自动展开）
const activeGroupId = computed(() => {
  const all: Array<NavItem & { groupId: string }> = []
  for (const g of navGroups.value) {
    for (const i of g.items) {
      all.push({ ...i, groupId: g.id })
      if (i.children?.length) all.push(...i.children.map((c) => ({ ...c, groupId: g.id })))
    }
  }
  return all.find((i) => i.key === activeKey.value)?.groupId ?? ''
})
// 跳到某个折叠分组内的页面时（例如从更多菜单进入 /engine），自动展开该分组
watch(activeGroupId, (id) => { if (id) collapsed.value[id] = false }, { immediate: true })

function toggleGroup(id: string) { collapsed.value[id] = !collapsed.value[id] }
function isCollapsed(id: string) { return !!collapsed.value[id] }

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
        <section v-for="group in navGroups" :key="group.id" class="nav-group">
          <!-- 分组标题：可折叠分组带展开箭头与徽标 -->
          <div
            class="nav-group-title"
            :class="{ clickable: group.collapsible }"
            role="button"
            tabindex="0"
            :aria-expanded="group.collapsible ? !isCollapsed(group.id) : true"
            @click="group.collapsible && toggleGroup(group.id)"
            @keydown.enter="group.collapsible && toggleGroup(group.id)"
            @keydown.space.prevent="group.collapsible && toggleGroup(group.id)"
          >
            <span class="nav-group-icon" v-html="safeIcon(group.icon)"></span>
            <span class="nav-group-label">{{ group.title }}</span>
            <span v-if="group.badge" class="nav-group-badge">{{ group.badge }}</span>
            <span
              v-if="group.collapsible"
              class="nav-group-chevron"
              :class="{ collapsed: isCollapsed(group.id) }"
              v-html="safeIcon(icons.chevronRight)"
            ></span>
          </div>

          <template v-if="!isCollapsed(group.id)">
            <template v-for="item in group.items" :key="item.key">
              <div
                class="nav-item"
                :class="[item.subjectClass, { active: activeKey === item.key }]"
                @click="goTo(item.route)"
              >
                <span v-html="safeIcon(item.icon)"></span>
                <span>{{ item.name }}</span>
              </div>
              <!-- 归并后的子项：功能重叠页降一级，不再占据主导航 -->
              <div
                v-for="child in item.children"
                :key="child.key"
                class="nav-item nav-subitem"
                :class="{ active: activeKey === child.key }"
                @click="goTo(child.route)"
              >
                <span v-html="safeIcon(child.icon)"></span>
                <span>{{ child.name }}</span>
              </div>
            </template>
          </template>
        </section>
      </nav>

      <div class="sidebar-footer">
        <div class="user-mini" role="button" tabindex="0" :aria-expanded="showProfile" aria-label="个人画像" @click="showProfile = !showProfile" @keydown.enter="showProfile = !showProfile">
          <div class="user-avatar" v-html="safeIcon(icons.user)"></div>
          <div class="user-info">
            <div class="user-name">{{ currentUser?.display_name || currentUser?.username || '未登录' }}</div>
            <div class="user-role">{{ roleLabel }} · 查看画像</div>
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
        <!-- 路由级错误边界：任一页面渲染抛错时降级为错误卡片，而非整站白屏。
             :key="route.fullPath" 让每次路由切换都重建边界，避免上一页的错误态残留到下一页。 -->
        <ErrorBoundary :key="route.fullPath">
          <router-view v-slot="{ Component }">
            <component :is="Component" :key="route.fullPath" />
          </router-view>
        </ErrorBoundary>
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
  animation: mars-pulse-soft 3.4s var(--ease-standard) infinite;
}

.logo-icon svg {
  width:2rem;
  height:2rem;
}

.logo-text {
  font-size:1.0625rem;
  font-weight: var(--weight-bold);
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
  background: var(--color-canvas);
}

.logout-btn {
  flex-shrink: 0;
  margin-left:var(--space-2);
  padding:0.375rem 0.625rem;
  border-radius:var(--radius-sm);
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-secondary);
  font-size:var(--text-xs);
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
  padding:var(--space-2) var(--space-4) var(--space-3);
  font-size:var(--text-2xs);
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
.status-text { font-weight: var(--weight-medium); }

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
  padding-left:var(--space-2);
  border-left: 1px solid var(--border-color);
}
.tu-name {
  font-size:var(--text-xs);
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
  font-size:var(--text-2xs);
  cursor: pointer;
}
.tu-logout:hover { color: var(--text-danger); border-color: var(--accent-danger-20); }
</style>
