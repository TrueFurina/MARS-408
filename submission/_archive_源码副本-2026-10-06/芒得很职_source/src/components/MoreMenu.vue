<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { icons } from '@/components/icons'
import { buildMoreMenu, resolveRole, type NavItem } from '@/router/navConfig'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const authStore = useAuthStore()
const open = ref(false)
const menuRef = ref<HTMLElement | null>(null)

type MenuEntry = NavItem | { divider: true }

// 单一真值源：更多菜单与侧栏 / 底部导航共用 src/router/navConfig.ts
// 移动端侧栏隐藏，因此这里展示全量导航（含实验室分组），不再维护第二份硬编码清单。
const menuItems = computed<MenuEntry[]>(() =>
  buildMoreMenu(resolveRole(authStore.currentUser?.role)),
)

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
        <div v-if="'divider' in item" class="more-menu-divider"></div>
        <button v-else class="more-menu-item" @click="navigate((item as NavItem).route)">
          <span class="item-icon" v-html="(item as NavItem).icon"></span>
          <span>{{ (item as NavItem).name }}</span>
        </button>
      </template>
    </div>
  </div>
</template>
