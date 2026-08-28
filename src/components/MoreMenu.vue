<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { icons } from '@/components/icons'

const router = useRouter()
const open = ref(false)
const menuRef = ref<HTMLElement | null>(null)

interface MenuItem {
  icon: string
  label: string
  route: string
  badge?: string
}
interface MenuDivider { divider: boolean }
type MenuEntry = MenuItem | MenuDivider

const menuItems: MenuEntry[] = [
  { icon: icons.dashboard, label: '系统首页', route: '/' },
  { icon: icons.sparkle, label: '智能对话', route: '/chat' },
  { icon: icons.knowledge, label: '知识图谱', route: '/knowledge' },
  { divider: true },
  { icon: icons.sparkle, label: 'AI 资源生成', route: '/resource' },
  { icon: icons.history, label: '学生画像', route: '/profile' },
  { icon: icons.history, label: '学情记忆', route: '/memory' },
  { icon: icons.dashboard, label: '重建画像', route: '/profile/build' },
  { icon: icons.quiz, label: '在线练习', route: '/practice' },
  { icon: icons.dashboard, label: '学习路径', route: '/learning-path' },
  { icon: icons.dashboard, label: '效果评估', route: '/assessment' },
  { icon: icons.quiz, label: '代码沙箱', route: '/sandbox' },
  { icon: icons.dashboard, label: 'C/C++ 实验室', route: '/code-lab' },
  { divider: true },
  { icon: icons.setting, label: 'API 管理', route: '/settings' },
  { icon: icons.setting, label: 'RAG 管理', route: '/admin' },
]

function toggle() { open.value = !open.value }
function navigate(route: string) { open.value = false; router.push(route) }

function onDocumentClick(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) open.value = false
}

onMounted(() => {
  if (typeof document !== 'undefined') document.addEventListener('click', onDocumentClick, true)
})
onUnmounted(() => {
  if (typeof document !== 'undefined') document.removeEventListener('click', onDocumentClick, true)
})
</script>

<template>
  <div ref="menuRef" class="more-menu-container">
    <button class="topbar-btn" :class="{ active: open }" @click.stop="toggle" title="更多功能" aria-label="更多功能" v-html="icons.menu"></button>
    <div v-if="open" class="more-dropdown" @click.stop>
      <template v-for="(item, idx) in menuItems" :key="idx">
        <div v-if="'divider' in item && item.divider" class="more-menu-divider"></div>
        <button v-else class="more-menu-item" @click="navigate((item as MenuItem).route)">
          <span class="item-icon" v-html="(item as MenuItem).icon"></span>
          <span>{{ (item as MenuItem).label }}</span>
          <span v-if="(item as MenuItem).badge" class="item-badge">{{ (item as MenuItem).badge }}</span>
        </button>
      </template>
    </div>
  </div>
</template>
