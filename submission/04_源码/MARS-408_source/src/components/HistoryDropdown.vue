<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { icons } from '@/components/icons'
import EmptyState from '@/components/EmptyState.vue'

const router = useRouter()
const store = useStudyStore()
const searchQuery = ref('')

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const filteredConversations = computed(() => {
  const list = store.conversations.filter(c => c.messages.length > 0)
  if (!searchQuery.value.trim()) return list
  const q = searchQuery.value.toLowerCase()
  return list.filter(c =>
    c.title.toLowerCase().includes(q) ||
    c.messages.some(m => m.content.toLowerCase().includes(q))
  )
})

function select(id: string) {
  searchQuery.value = ''
  emit('close')
  router.push('/c/' + id)
}

function newConversation() {
  store.createConversation()
  searchQuery.value = ''
  emit('close')
  router.push('/chat')
}

function handleDelete(e: MouseEvent, id: string) {
  e.stopPropagation()
  const wasCurrent = id === store.currentConversationId
  store.deleteConversation(id)
  if (wasCurrent) {
    router.push('/chat')
  }
}

function formatDate(d: Date): string {
  // P1① 缺陷修复：无效日期（旧 localStorage 数据缺 updatedAt / 后端字段缺失）兜底
  const date = new Date(d)
  if (isNaN(date.getTime())) return '最近'
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  if (diff < 86400000) return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (diff < 604800000) return (['周日','周一','周二','周三','周四','周五','周六'][date.getDay()] ?? '') as string
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div class="history-panel" :class="{ open }">
    <div class="history-panel-header">
      <div class="history-panel-title">对话历史</div>
    </div>

    <div class="history-panel-actions">
      <button class="history-new-btn" @click="newConversation">
        <span v-html="icons.plus"></span>
        <span>新对话</span>
      </button>
    </div>

    <div class="history-search">
      <span class="history-search-icon" v-html="icons.search"></span>
      <input v-model="searchQuery" placeholder="搜索对话..." class="history-search-input" />
    </div>

    <div class="history-list">
      <div
        v-for="conv in filteredConversations"
        :key="conv.id"
        class="history-item"
        :class="{ active: conv.id === store.currentConversationId }"
        role="button"
        tabindex="0"
        @click="select(conv.id)"
        @keydown.enter="select(conv.id)"
        @keydown.space.prevent="select(conv.id)"
      >
        <div class="history-item-content">
          <div class="history-item-title">{{ conv.title }}</div>
          <div class="history-item-meta">
            {{ formatDate(conv.updatedAt) }}
            · {{ conv.messages.length }} 条
          </div>
        </div>
        <button class="history-item-del" :aria-label="`删除对话 ${conv.title}`" @click="(e) => handleDelete(e, conv.id)" v-html="icons.close"></button>
      </div>
      <EmptyState v-if="filteredConversations.length === 0" :icon="icons.history" :title="searchQuery ? '未找到匹配的对话' : '暂无对话'" description="开始一次 408 问答，历史会保存在这里" />
    </div>
  </div>
</template>

<style scoped>
.history-panel {
  position: fixed;
  top:0;
  left:0;
  bottom:0;
  width:20rem;
  max-width:85vw;
  z-index: 950;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  box-shadow: var(--shadow-xl);
  display: flex;
  flex-direction: column;
  transform: translateX(-100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

@media (max-width: 768px) {
  .history-panel {
    top:var(--topbar-height);
    width:100vw;
    max-width:100vw;
  }
}

.history-panel.open {
  transform: translateX(0);
}

.history-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding:1rem 1.25rem;
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.history-panel-title { font-size:1rem; font-weight: 700; color: var(--text-primary); }

.history-panel-actions { padding:0.75rem 1rem 0; flex-shrink: 0; }

.history-new-btn {
  display: flex; align-items: center; justify-content: center; gap:0.375rem;
  width:100%; padding:0.625rem;
  border-radius:var(--radius-sm);
  border: 1.5px dashed var(--border-color);
  background: transparent;
  color: var(--accent-primary); font-size:0.875rem; font-weight: 600;
  cursor: pointer; transition: var(--transition);
}

.history-new-btn svg { width:1rem; height:1rem; }
.history-new-btn:hover { background: var(--accent-primary-10); border-color: var(--accent-primary); }

.history-search { position: relative; padding:0.625rem 1rem; flex-shrink: 0; }
.history-search-icon {
  position: absolute; right: 24px; top: 50%; transform: translateY(-50%);
  color: var(--text-muted); display: flex;
}
.history-search-icon svg { width:1rem; height:1rem; }
.history-search-input {
  width:100%; padding:0.5rem 2rem 0.5rem 0.75rem;
  border-radius:var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-tertiary);
  color: var(--text-primary); font-size:0.8125rem;
  outline: none; transition: var(--transition);
}
.history-search-input:focus { border-color: var(--accent-primary); }
.history-search-input::placeholder { color: var(--text-muted); }

.history-list { flex: 1; overflow-y: auto; padding:0.25rem 0.5rem 1rem; }

.history-item {
  display: flex; align-items: center; gap:0.375rem;
  padding:0.625rem 0.75rem;
  border-radius:var(--radius-sm);
  cursor: pointer; transition: var(--transition);
  margin-bottom:0.125rem;
}
.history-item:hover { background: var(--bg-tertiary); }
.history-item.active { background: var(--accent-primary-10); }

.history-item-content { flex: 1; min-width:0; }
.history-item-title {
  font-size:0.8125rem; font-weight: 500; color: var(--text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.history-item-meta { font-size:0.6875rem; color: var(--text-muted); margin-top:0.125rem; }

.history-item-del {
  width:1.5rem; height:1.5rem; border-radius:var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  color: var(--text-muted); opacity: 0; transition: var(--transition); flex-shrink: 0;
}
.history-item:hover .history-item-del { opacity: 1; }
.history-item-del:hover { color: var(--accent-danger); background: var(--accent-danger-10); }
.history-item-del svg { width:0.875rem; height:0.875rem; }
</style>
