<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { icons } from '@/components/icons'

const props = defineProps<{
  content: string
}>()

// 解析 Markdown 大纲为树结构（纯前端，不依赖 markmap-lib）
interface TreeNode { text: string; children: TreeNode[]; level: number }

function parseOutline(text: string): TreeNode {
  // 清理标记
  let outline = text
  for (const m of ['---MEDIA_START---', '---MEDIA_END---']) {
    outline = outline.replace(m, '')
  }

  const lines = outline.split('\n').filter(l => l.trim())
  const root: TreeNode = { text: '知识点结构', children: [], level: 0 }

  // 解析 markdown 列表（- 或 *）和标题（#）
  const stack: TreeNode[] = [root]
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue

    // 标题行
    const headingMatch = trimmed.match(/^#{1,6}\s+(.+)$/)
    if (headingMatch) {
      const level = trimmed.match(/^#{1,6}/)![0].length
      const text = headingMatch[1] ?? ''
      const node: TreeNode = { text, children: [], level }
      // 找到合适的父节点（level 比当前小的最近的）
      while (stack.length > 1 && (stack[stack.length - 1]?.level ?? 0) >= level) stack.pop()
      const parent = stack[stack.length - 1]
      if (parent) parent.children.push(node)
      stack.push(node)
      continue
    }

    // 列表项
    const listMatch = line.match(/^(\s*)([-*+])\s+(.+)$/)
    if (listMatch) {
      const indent = listMatch[1]?.length ?? 0
      const level = Math.floor(indent / 2) + 1
      const text = listMatch[3] ?? ''
      const node: TreeNode = { text, children: [], level }
      while (stack.length > 1 && (stack[stack.length - 1]?.level ?? 0) >= level) stack.pop()
      const parent = stack[stack.length - 1]
      if (parent) parent.children.push(node)
      stack.push(node)
      continue
    }

    // 数字列表或普通文本
    const numMatch = trimmed.match(/^[\d①②③④⑤⑥⑦⑧⑨⑩]+[.、．]\s*(.+)$/)
    if (numMatch) {
      const text = numMatch[1] ?? trimmed
      const node: TreeNode = { text, children: [], level: 1 }
      root.children.push(node)
      stack.length = 1
      stack.push(node)
      continue
    }

    // 普通文本作为根的子项
    root.children.push({ text: trimmed, children: [], level: 1 })
  }

  // 若根无标题，用第一个子节点作根
  if (!root.children.length) return root
  const firstChild = root.children[0]
  if (root.children.length === 1 && firstChild?.level === 1) return firstChild
  return root
}

const tree = computed(() => parseOutline(props.content || ''))

// 扁平化为带缩进的行（纯 CSS 树状图）
interface FlatNode { text: string; depth: number; isLast: boolean; hasChildren: boolean }

function flatten(node: TreeNode, depth = 0, isLast = true, parentHasMore = false): FlatNode[] {
  const result: FlatNode[] = []
  result.push({
    text: node.text,
    depth,
    isLast,
    hasChildren: node.children.length > 0,
  })
  node.children.forEach((child, i) => {
    const childIsLast = i === node.children.length - 1
    result.push(...flatten(child, depth + 1, childIsLast, !isLast))
  })
  return result
}

const flatNodes = computed(() => {
  const root = tree.value
  if (!root.children.length && !root.text) return []
  // 根节点不显示缩进，子节点缩进
  const all: FlatNode[] = [{ text: root.text, depth: 0, isLast: true, hasChildren: root.children.length > 0 }]
  root.children.forEach((child, i) => {
    all.push(...flatten(child, 1, i === root.children.length - 1, false))
  })
  return all
})
</script>

<template>
  <div class="mindmap-wrapper">
    <div v-if="!content" class="mindmap-empty"><span v-html="icons.knowledge" class="inline-icon"></span>暂无思维导图内容</div>
    <div v-else class="mindmap-tree">
      <div
        v-for="(node, idx) in flatNodes"
        :key="idx"
        class="mindmap-node"
        :class="{ root: node.depth === 0, leaf: !node.hasChildren }"
        :style="{ paddingLeft: (node.depth * 24) + 'px' }"
      >
        <span class="mindmap-bullet" :class="{ root: node.depth === 0 }">
          <template v-if="node.depth === 0">🌳</template>
          <template v-else-if="node.hasChildren">📁</template>
          <template v-else>•</template>
        </span>
        <span class="mindmap-text">{{ node.text }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mindmap-wrapper {
  width:100%;
  min-height:18.75rem;
  background: rgba(124, 106, 242, 0.04);
  border: 1px solid var(--border-light);
  border-radius:var(--radius-md);
  overflow: auto;
  padding:1rem;
}
.mindmap-tree {
  font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.mindmap-node {
  display: flex;
  align-items: center;
  gap:0.5rem;
  padding:0.375rem 0.5rem;
  border-radius:0.375rem;
  line-height:1.6;
  transition: background 0.2s;
}
.mindmap-node:hover {
  background: var(--accent-1-light);
}
.mindmap-node.root {
  font-size:1rem;
  font-weight: 700;
  color: var(--accent-1);
  margin-bottom:0.5rem;
  padding-bottom:0.5rem;
  border-bottom: 1px solid var(--border-light);
}
.mindmap-node.leaf {
  color: var(--text-secondary);
  font-size:0.8125rem;
}
.mindmap-bullet {
  flex-shrink: 0;
  width:1.25rem;
  text-align: center;
  font-size:0.875rem;
  color: var(--accent-2);
}
.mindmap-bullet.root {
  font-size:1.125rem;
}
.mindmap-text {
  flex: 1;
  word-break: break-word;
}
.mindmap-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height:18.75rem;
  color: var(--text-muted);
  font-size:0.875rem;
}
</style>
