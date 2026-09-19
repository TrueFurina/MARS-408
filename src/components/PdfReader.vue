<script setup lang="ts">
import { ref, computed } from 'vue'
import { api } from '@/utils/api'

const props = defineProps<{
  textbookId: string
  textbookName: string
  chapters: any[]
}>()

const emit = defineEmits<{
  askAboutText: [text: string]
}>()

const currentChapter = ref(0)
const selectedText = ref('')
const showSelectionMenu = ref(false)
const menuPos = ref({ x: 0, y: 0 })

const chapter = computed(() => props.chapters[currentChapter.value] || null)

function onMouseUp(e: MouseEvent) {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || !sel.toString().trim()) {
    showSelectionMenu.value = false
    return
  }
  selectedText.value = sel.toString().trim()
  menuPos.value = { x: e.clientX, y: e.clientY }
  showSelectionMenu.value = true
}

function askAboutSelection() {
  showSelectionMenu.value = false
  if (selectedText.value) {
    emit('askAboutText', selectedText.value)
  }
}

function selectChapter(i: number) {
  currentChapter.value = i
  showSelectionMenu.value = false
  window.getSelection()?.removeAllRanges()
}
</script>

<template>
  <div class="pdf-reader">
    <!-- 章节侧栏 -->
    <div class="pdf-sidebar">
      <div class="pdf-sidebar-title">{{ textbookName }}</div>
      <div class="pdf-chapter-list">
        <button v-for="(ch, i) in chapters" :key="ch.id" class="pdf-chapter-item"
          :class="{ active: currentChapter === i }" @click="selectChapter(i)">
          <span class="pdf-chapter-num">{{ i + 1 }}</span>
          <span class="pdf-chapter-title">{{ ch.title }}</span>
        </button>
      </div>
    </div>

    <!-- 文本阅读区 -->
    <div class="pdf-content" @mouseup="onMouseUp">
      <div v-if="chapter" class="pdf-chapter-header">
        <h2>{{ chapter.title }}</h2>
      </div>
      <div class="pdf-text">
        {{ chapter?.content || '暂无内容' }}
      </div>
      <div v-if="!chapter" class="pdf-empty">
        <div class="empty-icon"></div>
        <div class="empty-text">选择章节开始阅读</div>
      </div>
    </div>

    <!-- 选中文本操作菜单 -->
    <Teleport to="body">
      <div v-if="showSelectionMenu" class="selection-menu" :style="{ left: menuPos.x + 'px', top: menuPos.y + 'px' }">
        <button class="selection-btn" @click="askAboutSelection"> 问选中</button>
        <button class="selection-btn" @click="showSelectionMenu = false"></button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.pdf-reader { display: flex; height: calc(100vh - 120px); border: 1px solid var(--color-border); border-radius: 12px; overflow: hidden; }
.pdf-sidebar { width: 260px; min-width: 260px; border-right: 1px solid var(--color-border); display: flex; flex-direction: column; background: var(--color-surface); }
.pdf-sidebar-title { padding: var(--space-4); font-size: var(--text-md); font-weight: var(--weight-bold); color: var(--color-text); border-bottom: 1px solid var(--color-border); }
.pdf-chapter-list { flex: 1; overflow-y: auto; padding: var(--space-2); }
.pdf-chapter-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px var(--space-3); border: none; border-radius: 8px; background: transparent; color: var(--color-text-2); cursor: pointer; text-align: left; transition: var(--transition); font-size: var(--text-sm); }
.pdf-chapter-item:hover { background: var(--color-surface-hover); color: var(--color-text); }
.pdf-chapter-item.active { background: rgba(var(--accent-rgb),0.1); color: var(--accent); }
.pdf-chapter-num { width: 22px; height: 22px; border-radius: 50%; background: var(--color-surface-2); display: flex; align-items: center; justify-content: center; font-size: var(--text-2xs); font-weight: var(--weight-semibold); flex-shrink: 0; }
.pdf-chapter-item.active .pdf-chapter-num { background: var(--accent); color: var(--color-text-on-accent); }
.pdf-chapter-title { flex: 1; line-height: 1.4; }
.pdf-content { flex: 1; overflow-y: auto; padding: var(--space-6) var(--space-8); }
.pdf-chapter-header { margin-bottom: var(--space-5); }
.pdf-chapter-header h2 { font-size: 22px; font-weight: var(--weight-bold); color: var(--color-text); margin: 0; }
.pdf-text { font-size: var(--text-md); line-height: 1.8; color: var(--color-text-2); white-space: pre-wrap; }
.pdf-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: var(--space-2); }
.empty-icon { font-size: 48px; }
.empty-text { font-size: var(--text-xl); font-weight: var(--weight-semibold); color: var(--color-text-2); }

.selection-menu { position: fixed; z-index: 1000; display: flex; gap: var(--space-1); padding: var(--space-1); background: var(--color-elevated); border: 1px solid var(--color-border); border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); transform: translate(-50%, -100%); }
.selection-btn { padding: 6px var(--space-3); border: none; border-radius: 6px; background: transparent; color: var(--color-text); font-size: var(--text-sm); cursor: pointer; white-space: nowrap; }
.selection-btn:hover { background: var(--color-surface-hover); }

/* 移动端适配 */
@media (max-width: 768px) {
  .pdf-reader { flex-direction: column; height: auto; }
  .pdf-sidebar { width: 100%; min-width: unset; max-height: 200px; border-right: none; border-bottom: 1px solid var(--color-border); }
  .pdf-chapter-list { display: flex; flex-wrap: wrap; gap: var(--space-1); padding: 6px; }
  .pdf-chapter-item { width: auto; padding: 6px 10px; font-size: var(--text-xs); }
  .pdf-chapter-num { display: none; }
  .pdf-content { padding: var(--space-4); }
  .pdf-text { font-size: var(--text-base); }
}
</style>