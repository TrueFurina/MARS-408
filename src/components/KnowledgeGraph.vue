<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue'

const props = defineProps<{
  nodes: any[]
  edges: any[]
  width?: number
  height?: number
  showSearch?: boolean
  viewMode?: string
}>()

const emit = defineEmits<{
  nodeClick: [node: any]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const searchQuery = ref('')
const showDetail = ref(false)
const selectedNode = ref<any>(null)
const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const detailTab = ref<'info' | 'relations' | 'resources' | 'mastery'>('info')

interface Node2D {
  id: string; label: string; x: number; y: number; vx: number; vy: number
  radius: number; color: string; mastery?: string; data: any
}

const nodes2d = ref<Node2D[]>([])
const edges2d = ref<{ from: number; to: number; label: string; color: string }[]>([])
const hoveredNode = ref<number | null>(null)

// 筛选后的节点
const filteredNodes = computed(() => {
  if (!searchQuery.value) return nodes2d.value
  const q = searchQuery.value.toLowerCase()
  return nodes2d.value.filter(n => n.label.toLowerCase().includes(q))
})

// 掌握度颜色映射
function masteryColor(mastery?: string): string {
  const map: Record<string, string> = {
    mastered: '#22c55e', weak: '#f59e0b', unlearned: '#ef4444',
  }
  return map[mastery || ''] || '#7c6af2'
}

function masteryLabel(mastery?: string): string {
  const map: Record<string, string> = { mastered: '已掌握', weak: '薄弱', unlearned: '未学' }
  return map[mastery || ''] || ''
}

function importanceLabel(imp: any): string {
  const map: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return (map[imp as string] ?? imp) || ''
}

function initGraph() {
  const w = props.width || 800
  const h = props.height || 600
  nodes2d.value = props.nodes.map((n, i) => ({
    id: n.id, label: n.label || n.id,
    x: w / 2 + (Math.random() - 0.5) * w * 0.5,
    y: h / 2 + (Math.random() - 0.5) * h * 0.5,
    vx: 0, vy: 0,
    radius: (n.value || 22) * (n.importance === 'high' ? 1.3 : n.importance === 'low' ? 0.8 : 1),
    color: n.mastery ? masteryColor(n.mastery) : (n.color || '#7c6af2'),
    mastery: n.mastery,
    data: n,
  }))
  const nodeMap = new Map(props.nodes.map((n, i) => [n.id, i]))
  edges2d.value = props.edges.map(e => ({
    from: nodeMap.get(e.from) ?? 0, to: nodeMap.get(e.to) ?? 0,
    label: e.label || '', color: e.color?.color || '#94a3b8',
  }))
}

// 力导向模拟
let simTimer: number | null = null
function startSimulation() {
  const w = props.width || 800; const h = props.height || 600
  const nodes = nodes2d.value; const edges = edges2d.value
  let frames = 0

  function simulate() {
    const repulsion = 5000; const attraction = 0.005; const damping = 0.85; const centerForce = 0.01
    for (let i = 0; i < nodes.length; i++) {
      const ni = nodes[i]!
      let fx = 0, fy = 0
      for (let j = 0; j < nodes.length; j++) {
        if (i === j) continue
        const nj = nodes[j]!
        const dx = ni.x - nj.x; const dy = ni.y - nj.y
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
        const force = repulsion / (dist * dist)
        fx += (dx / dist) * force; fy += (dy / dist) * force
      }
      for (const edge of edges) {
        let other = -1
        if (edge.from === i) other = edge.to
        if (edge.to === i) other = edge.from
        if (other === -1) continue
        const no = nodes[other]!
        const dx = no.x - ni.x; const dy = no.y - ni.y
        const dist = Math.sqrt(dx * dx + dy * dy)
        if (dist < 1) continue
        fx += dx * attraction; fy += dy * attraction
      }
      fx += (w / 2 - ni.x) * centerForce; fy += (h / 2 - ni.y) * centerForce
      ni.vx = (ni.vx + fx) * damping; ni.vy = (ni.vy + fy) * damping
      ni.x += ni.vx; ni.y += ni.vy
      ni.x = Math.max(20, Math.min(w - 20, ni.x))
      ni.y = Math.max(20, Math.min(h - 20, ni.y))
    }
    draw()
    frames++
    if (frames < 120) { simTimer = requestAnimationFrame(simulate) }
  }
  simulate()
}

function draw() {
  const canvas = canvasRef.value; if (!canvas) return
  const ctx = canvas.getContext('2d'); if (!ctx) return
  const w = props.width || 800; const h = props.height || 600
  ctx.clearRect(0, 0, w, h)
  ctx.save()
  ctx.translate(offsetX.value, offsetY.value)
  ctx.scale(scale.value, scale.value)

  // 绘制边
  for (const edge of edges2d.value) {
    const from = nodes2d.value[edge.from]; const to = nodes2d.value[edge.to]
    if (!from || !to) continue
    ctx.beginPath(); ctx.moveTo(from.x, from.y); ctx.lineTo(to.x, to.y)
    ctx.strokeStyle = edge.color; ctx.lineWidth = 1.5; ctx.stroke()
    if (edge.label) {
      const mx = (from.x + to.x) / 2; const my = (from.y + to.y) / 2
      ctx.fillStyle = 'rgba(148,163,184,0.8)'; ctx.font = '11px sans-serif'
      ctx.textAlign = 'center'; ctx.textBaseline = 'bottom'
      ctx.fillText(edge.label, mx, my - 4)
    }
  }

  // 绘制节点
  const displayNodes = filteredNodes.value
  for (const n of displayNodes) {
    const isHovered = hoveredNode.value === nodes2d.value.indexOf(n)
    const isSelected = selectedNode.value?.id === n.id
    const r = n.radius * (isHovered || isSelected ? 1.2 : 1)

    if (isHovered || isSelected) {
      ctx.beginPath(); ctx.arc(n.x, n.y, r + 6, 0, Math.PI * 2)
      ctx.fillStyle = n.color + '30'; ctx.fill()
    }
    // 掌握度外圈
    if (n.mastery) {
      ctx.beginPath(); ctx.arc(n.x, n.y, r + 3, 0, Math.PI * 2)
      ctx.strokeStyle = masteryColor(n.mastery)
      ctx.lineWidth = 3; ctx.stroke()
    }
    ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
    ctx.fillStyle = n.color + '20'; ctx.fill()
    ctx.strokeStyle = isSelected ? '#fff' : n.color
    ctx.lineWidth = isHovered || isSelected ? 3 : 2; ctx.stroke()

    ctx.fillStyle = '#f8fafc'
    ctx.font = `${isHovered ? 14 : 12}px sans-serif`
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'
    ctx.fillText(n.label.length > 10 ? n.label.slice(0, 10) + '..' : n.label, n.x, n.y)
  }
  ctx.restore()
}

// 交互
let _lastHovered = -2
function onMouseMove(e: MouseEvent) {
  const rect = canvasRef.value?.getBoundingClientRect(); if (!rect) return
  const mx = (e.clientX - rect.left - offsetX.value) / scale.value
  const my = (e.clientY - rect.top - offsetY.value) / scale.value
  let found = -1
  for (let i = 0; i < nodes2d.value.length; i++) {
    const n = nodes2d.value[i]!; const dx = mx - n.x; const dy = my - n.y
    if (dx * dx + dy * dy < (n.radius + 5) * (n.radius + 5)) { found = i; break }
  }
  if (found !== _lastHovered) {
    _lastHovered = found
    hoveredNode.value = found
    canvasRef.value!.style.cursor = found >= 0 ? 'pointer' : 'grab'
    draw()
  }
}

function onClick(e: MouseEvent) {
  if (hoveredNode.value !== null && hoveredNode.value >= 0) {
    selectedNode.value = nodes2d.value[hoveredNode.value]!.data
    showDetail.value = true
    detailTab.value = 'info'
    emit('nodeClick', selectedNode.value)
  }
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  scale.value = Math.max(0.3, Math.min(3, scale.value * delta))
  draw()
}

function onMouseDown(e: MouseEvent) {
  if (hoveredNode.value === null || hoveredNode.value < 0) {
    isDragging.value = true
    dragStart.value = { x: e.clientX - offsetX.value, y: e.clientY - offsetY.value }
  }
}

function onMouseUp() { isDragging.value = false }

function onMouseLeave() { isDragging.value = false; hoveredNode.value = null }

function zoomIn() { scale.value = Math.min(3, scale.value * 1.2); draw() }
function zoomOut() { scale.value = Math.max(0.3, scale.value * 0.8); draw() }
function resetView() { scale.value = 1; offsetX.value = 0; offsetY.value = 0; draw() }

// 关联节点高亮
const relatedNodes = computed(() => {
  if (!selectedNode.value) return new Set()
  const ids = new Set([selectedNode.value.id])
  for (const edge of edges2d.value) {
    const from = nodes2d.value[edge.from]?.id
    const to = nodes2d.value[edge.to]?.id
    if (from === selectedNode.value.id) ids.add(to)
    if (to === selectedNode.value.id) ids.add(from)
  }
  return ids
})

function closeDetail() { showDetail.value = false; selectedNode.value = null }

function onOutlineClick(node: any) {
  selectedNode.value = node
  showDetail.value = true
  detailTab.value = 'info'
  emit('nodeClick', node)
}

function getMindmapStyle(index: number, total: number) {
  const angle = (360 / total) * index - 90
  const radius = 180
  return { transform: `rotate(${angle}deg) translate(${radius}px) rotate(${-angle}deg)` }
}

onMounted(() => { initGraph(); startSimulation() })
onUnmounted(() => { if (simTimer) cancelAnimationFrame(simTimer) })
watch(() => [props.nodes, props.edges], () => { initGraph(); startSimulation() })
</script>

<template>
  <div class="kg-wrapper">
    <!-- 搜索栏 -->
    <div v-if="showSearch" class="kg-search-bar">
      <input v-model="searchQuery" class="kg-search-input" placeholder="搜索知识点..." @input="draw" />
      <button class="kg-search-clear" v-if="searchQuery" @click="searchQuery = ''; nextTick(() => draw())">✕</button>
    </div>

    <!-- 图谱模式（力导向图） -->
    <template v-if="viewMode === 'graph' || !viewMode">
      <!-- 缩放控件 -->
      <div class="kg-zoom-controls">
        <button class="kg-zoom-btn" @click="zoomIn" title="放大">＋</button>
        <button class="kg-zoom-btn" @click="zoomOut" title="缩小">−</button>
        <button class="kg-zoom-btn" @click="resetView" title="重置">⟲</button>
      </div>
      <!-- 掌握度图例 -->
      <div class="kg-mastery-legend">
        <span class="kg-legend-dot" style="background:#22c55e"></span> 已掌握
        <span class="kg-legend-dot" style="background:#f59e0b;margin-left:10px;"></span> 薄弱
        <span class="kg-legend-dot" style="background:#ef4444;margin-left:10px;"></span> 未学
      </div>
      <div class="kg-canvas-container">
        <canvas ref="canvasRef" :width="width || 800" :height="height || 600" class="kg-canvas"
          @mousemove="onMouseMove" @mousedown="onMouseDown" @mouseup="onMouseUp"
          @mouseleave="onMouseLeave" @click="onClick" @wheel.prevent="onWheel"></canvas>
        <div v-if="nodes.length === 0" class="kg-empty">
          <div class="empty-icon">🕸️</div><div class="empty-text">暂无知识图谱数据</div>
          <div class="empty-hint">请先通过「提取知识图谱」生成数据</div>
        </div>
      </div>
    </template>

    <!-- 大纲模式（树形层级） -->
    <template v-if="viewMode === 'outline'">
      <div class="outline-view">
        <div v-for="node in nodes" :key="node.id" class="outline-node" role="button" tabindex="0" :aria-label="node.label || node.id" @click="onOutlineClick(node)" @keydown.enter="onOutlineClick(node)" @keydown.space.prevent="onOutlineClick(node)">
          <span class="outline-dot" :style="{ background: node.color || '#7c6af2' }"></span>
          <span class="outline-label">{{ node.label || node.id }}</span>
          <span v-if="node.mastery" class="outline-mastery" :style="{ color: masteryColor(node.mastery) }">[{{ masteryLabel(node.mastery) }}]</span>
          <span v-if="node.importance" class="outline-importance" :class="node.importance">{{ node.importance === 'high' ? '★' : '☆' }}</span>
        </div>
        <div v-if="nodes.length === 0" class="kg-empty">
          <div class="empty-icon">📋</div><div class="empty-text">暂无大纲数据</div>
        </div>
      </div>
    </template>

    <!-- 思维导图模式（径向树） -->
    <template v-if="viewMode === 'mindmap'">
      <div class="mindmap-view">
        <div class="mindmap-center" role="button" tabindex="0" :aria-label="nodes[0]?.label || '根节点'" @click="onOutlineClick(nodes[0])" @keydown.enter="onOutlineClick(nodes[0])" @keydown.space.prevent="onOutlineClick(nodes[0])" v-if="nodes.length">
          <span class="mindmap-center-dot" :style="{ background: nodes[0]?.color || '#7c6af2' }"></span>
          <span class="mindmap-center-label">{{ nodes[0]?.label || '根节点' }}</span>
        </div>
        <div class="mindmap-ring">
          <div v-for="(node, i) in nodes.slice(1, 12)" :key="node.id" class="mindmap-node" :style="getMindmapStyle(i, nodes.slice(1, 12).length)" role="button" tabindex="0" :aria-label="node.label || node.id" @click="onOutlineClick(node)" @keydown.enter="onOutlineClick(node)" @keydown.space.prevent="onOutlineClick(node)">
            <span class="mindmap-dot" :style="{ background: node.color || '#7c6af2' }"></span>
            <span class="mindmap-label">{{ node.label || node.id }}</span>
          </div>
        </div>
        <div v-if="nodes.length === 0" class="kg-empty">
          <div class="empty-icon">🧠</div><div class="empty-text">暂无思维导图数据</div>
        </div>
      </div>
    </template>

    <!-- 学习地图模式（横向路径） -->
    <template v-if="viewMode === 'map'">
      <div class="map-view">
        <div class="map-path">
          <div v-for="(node, i) in nodes" :key="node.id" class="map-node" role="button" tabindex="0" :aria-label="node.label || node.id" @click="onOutlineClick(node)" @keydown.enter="onOutlineClick(node)" @keydown.space.prevent="onOutlineClick(node)">
            <div class="map-node-card" :style="{ borderColor: node.color || '#7c6af2' }">
              <div class="map-node-step">{{ i + 1 }}</div>
              <div class="map-node-label">{{ node.label || node.id }}</div>
              <div v-if="node.mastery" class="map-node-mastery" :style="{ background: masteryColor(node.mastery) + '22', color: masteryColor(node.mastery) }">{{ masteryLabel(node.mastery) }}</div>
            </div>
            <div v-if="i < nodes.length - 1" class="map-arrow">→</div>
          </div>
        </div>
        <div v-if="nodes.length === 0" class="kg-empty">
          <div class="empty-icon">🗺️</div><div class="empty-text">暂无学习地图数据</div>
        </div>
      </div>
    </template>

    <!-- 详情面板 -->
    <Teleport to="body">
      <div v-if="showDetail && selectedNode" class="kg-detail-overlay" @click.self="closeDetail">
        <div class="kg-detail-panel">
          <div class="kg-detail-header">
            <div class="kg-detail-title-row">
              <span class="kg-detail-dot" :style="{ background: selectedNode.color || '#7c6af2' }"></span>
              <span class="kg-detail-title">{{ selectedNode.label }}</span>
              <span v-if="selectedNode.mastery" class="kg-detail-mastery" :style="{ background: masteryColor(selectedNode.mastery) + '22', color: masteryColor(selectedNode.mastery) }">
                {{ masteryLabel(selectedNode.mastery) }}
              </span>
            </div>
            <button class="kg-detail-close" @click="closeDetail">✕</button>
          </div>

          <div class="kg-detail-tabs">
            <button class="kg-tab" :class="{ active: detailTab === 'info' }" @click="detailTab = 'info'">📄 信息</button>
            <button class="kg-tab" :class="{ active: detailTab === 'relations' }" @click="detailTab = 'relations'">🔗 关联 ({{ relatedNodes.size - 1 }})</button>
            <button class="kg-tab" :class="{ active: detailTab === 'mastery' }" @click="detailTab = 'mastery'">📊 掌握</button>
            <button class="kg-tab" :class="{ active: detailTab === 'resources' }" @click="detailTab = 'resources'">📚 资源</button>
          </div>

          <div class="kg-detail-body">
            <!-- 信息 Tab -->
            <div v-if="detailTab === 'info'">
              <div class="kg-detail-row">
                <span class="kg-detail-label">类型</span>
                <span class="kg-detail-val">{{ selectedNode.group || selectedNode.type || 'concept' }}</span>
              </div>
              <div class="kg-detail-row">
                <span class="kg-detail-label">描述</span>
                <span class="kg-detail-val">{{ selectedNode.title || selectedNode.description || '暂无描述' }}</span>
              </div>
              <div v-if="selectedNode.importance" class="kg-detail-row">
                <span class="kg-detail-label">重要程度</span>
                <span class="kg-detail-val" :style="{ color: selectedNode.importance === 'high' ? '#ef4444' : selectedNode.importance === 'medium' ? '#f59e0b' : '#94a3b8' }">
                  {{ importanceLabel(selectedNode.importance) }}
                </span>
              </div>
            </div>

            <!-- 关联 Tab -->
            <div v-if="detailTab === 'relations'">
              <div v-for="edge in edges2d" :key="edge.from + '-' + edge.to" class="kg-rel-item">
                <template v-if="nodes2d[edge.from]?.id === selectedNode.id">
                  <span class="kg-rel-node">{{ nodes2d[edge.from]?.label }}</span>
                  <span class="kg-rel-arrow">─{{ edge.label || 'related' }}→</span>
                  <span class="kg-rel-node">{{ nodes2d[edge.to]?.label }}</span>
                </template>
                <template v-else-if="nodes2d[edge.to]?.id === selectedNode.id">
                  <span class="kg-rel-node">{{ nodes2d[edge.from]?.label }}</span>
                  <span class="kg-rel-arrow">←{{ edge.label || 'related' }}─</span>
                  <span class="kg-rel-node">{{ nodes2d[edge.to]?.label }}</span>
                </template>
              </div>
              <div v-if="relatedNodes.size <= 1" class="kg-detail-empty">暂无关联知识点</div>
            </div>

            <!-- 资源 Tab -->
            <div v-if="detailTab === 'resources'">
              <div class="kg-resource-item" role="button" tabindex="0" aria-label="查看讲解文档" @click="emit('nodeClick', selectedNode)" @keydown.enter="emit('nodeClick', selectedNode)" @keydown.space.prevent="emit('nodeClick', selectedNode)">📖 查看讲解文档</div>
              <div class="kg-resource-item" role="button" tabindex="0" aria-label="生成练习题" @click="emit('nodeClick', selectedNode)" @keydown.enter="emit('nodeClick', selectedNode)" @keydown.space.prevent="emit('nodeClick', selectedNode)">📝 生成练习题</div>
              <div class="kg-resource-item" role="button" tabindex="0" aria-label="生成思维导图" @click="emit('nodeClick', selectedNode)" @keydown.enter="emit('nodeClick', selectedNode)" @keydown.space.prevent="emit('nodeClick', selectedNode)">🧩 生成思维导图</div>
              <div class="kg-resource-item" role="button" tabindex="0" aria-label="生成教学视频" @click="emit('nodeClick', selectedNode)" @keydown.enter="emit('nodeClick', selectedNode)" @keydown.space.prevent="emit('nodeClick', selectedNode)">🎬 生成教学视频</div>
            </div>

            <!-- 掌握详情 Tab -->
            <div v-if="detailTab === 'mastery'">
              <div class="kg-detail-row">
                <span class="kg-detail-label">掌握状态</span>
                <span class="kg-detail-val" :style="{ color: selectedNode.mastery ? masteryColor(selectedNode.mastery) : '#94a3b8' }">
                  {{ selectedNode.mastery ? masteryLabel(selectedNode.mastery) : '未评估' }}
                </span>
              </div>
              <div class="kg-detail-row">
                <span class="kg-detail-label">重要程度</span>
                <span class="kg-detail-val">{{ selectedNode.importance === 'high' ? '🔴 高' : selectedNode.importance === 'medium' ? '🟡 中' : '🟢 低' }}</span>
              </div>
              <div class="kg-detail-row">
                <span class="kg-detail-label">认知维度</span>
                <span class="kg-detail-val">{{ selectedNode.cognitive_level || '未标注' }}</span>
              </div>
              <div class="kg-detail-row">
                <span class="kg-detail-label">知识分类</span>
                <span class="kg-detail-val">{{ selectedNode.category || '未标注' }}</span>
              </div>
              <div v-if="selectedNode.tags?.length" class="kg-detail-row">
                <span class="kg-detail-label">标签</span>
                <span class="kg-detail-val">{{ selectedNode.tags.join(', ') }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.kg-wrapper { position: relative; width: 100%; }
.kg-canvas-container { position: relative; width: 100%; }
.kg-canvas { width: 100%; height: auto; display: block; border-radius: 12px; background: rgba(255,255,255,0.02); border: 1px solid var(--color-border); }

.kg-search-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; padding: 0 4px; }
.kg-search-input { flex: 1; padding: 8px 14px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface-2); color: var(--color-text); font-size: 14px; }
.kg-search-input:focus { outline: none; border-color: var(--color-border-focus); }
.kg-search-clear { background: none; border: none; color: var(--color-text-3); cursor: pointer; font-size: 16px; padding: 4px; }

.kg-zoom-controls { position: absolute; top: 50px; right: 10px; display: flex; flex-direction: column; gap: 4px; z-index: 10; }
.kg-zoom-btn { width: 32px; height: 32px; border-radius: 8px; border: 1px solid var(--color-border); background: var(--color-surface); color: var(--color-text-2); font-size: 16px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
.kg-zoom-btn:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

.kg-mastery-legend { position: absolute; top: 50px; left: 10px; display: flex; align-items: center; gap: 4px; padding: 6px 12px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 8px; font-size: 11px; color: var(--color-text-2); z-index: 10; }
.kg-legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

/* 详情面板 */
.kg-detail-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.kg-detail-panel { width: 440px; max-height: 80vh; background: var(--color-canvas); border: 1px solid var(--color-border); border-radius: 14px; display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 16px 40px rgba(0,0,0,0.45); }
.kg-detail-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--color-border); }
.kg-detail-title-row { display: flex; align-items: center; gap: 10px; }
.kg-detail-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.kg-detail-title { font-size: 16px; font-weight: 600; color: var(--color-text); }
.kg-detail-mastery { font-size: 11px; padding: 1px 8px; border-radius: 10px; font-weight: 600; }
.kg-detail-close { background: none; border: none; color: var(--color-text-3); font-size: 18px; cursor: pointer; padding: 4px; }
.kg-detail-close:hover { color: var(--color-text); }
.kg-detail-tabs { display: flex; border-bottom: 1px solid var(--color-border); }
.kg-tab { flex: 1; padding: 10px; border: none; background: transparent; color: var(--color-text-2); font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.kg-tab:hover { color: var(--color-text); background: var(--color-surface-hover); }
.kg-tab.active { color: var(--accent); border-bottom: 2px solid var(--accent); }
.kg-detail-body { flex: 1; overflow-y: auto; padding: 14px 18px; }
.kg-detail-row { display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--color-border); }
.kg-detail-row:last-child { border-bottom: none; }
.kg-detail-label { width: 80px; font-size: 13px; color: var(--color-text-3); flex-shrink: 0; }
.kg-detail-val { flex: 1; font-size: 13px; color: var(--color-text); line-height: 1.5; }
.kg-rel-item { display: flex; align-items: center; gap: 6px; padding: 8px 0; font-size: 13px; }
.kg-rel-node { color: var(--accent); font-weight: 500; }
.kg-rel-arrow { color: var(--color-text-3); font-size: 12px; }
.kg-detail-empty { text-align: center; padding: 30px; color: var(--color-text-3); font-size: 14px; }
.kg-resource-item { padding: 10px 14px; border-radius: 8px; cursor: pointer; font-size: 14px; color: var(--color-text-2); transition: all 0.15s; }
.kg-resource-item:hover { background: var(--color-surface-hover); color: var(--accent); }
.kg-empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; pointer-events: none; }
.empty-icon { font-size: 48px; }
.empty-text { font-size: 18px; font-weight: 600; color: var(--color-text-2); }
.empty-hint { font-size: 14px; color: var(--color-text-3); }

/* 大纲模式 */
.outline-view { padding: 16px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 12px; min-height: 400px; }
.outline-node { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: 8px; cursor: pointer; transition: all 0.15s; border-left: 3px solid transparent; margin-bottom: 4px; }
.outline-node:hover { background: var(--color-surface-hover); border-left-color: var(--accent); }
.outline-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.outline-label { flex: 1; font-size: 14px; color: var(--color-text); font-weight: 500; }
.outline-mastery { font-size: 11px; font-weight: 600; }
.outline-importance { font-size: 12px; }
.outline-importance.high { color: var(--accent-warm); }
.outline-importance.medium { color: var(--accent-cyan); }
.outline-importance.low { color: var(--color-text-3); }

/* 思维导图模式 */
.mindmap-view { position: relative; display: flex; flex-direction: column; align-items: center; padding: 20px; min-height: 400px; }
.mindmap-center { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 16px 24px; border-radius: 14px; background: var(--color-surface); border: 2px solid var(--accent); cursor: pointer; margin-bottom: 40px; }
.mindmap-center:hover { transform: scale(1.05); }
.mindmap-center-dot { width: 12px; height: 12px; border-radius: 50%; }
.mindmap-center-label { font-size: 16px; font-weight: 700; color: var(--color-text); }
.mindmap-ring { display: flex; flex-wrap: wrap; justify-content: center; gap: 12px; max-width: 700px; }
.mindmap-node { display: flex; align-items: center; gap: 6px; padding: 10px 16px; border-radius: 10px; background: var(--color-surface); border: 1px solid var(--color-border); cursor: pointer; transition: all 0.15s; }
.mindmap-node:hover { border-color: var(--accent); transform: translateY(-2px); }
.mindmap-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.mindmap-label { font-size: 13px; color: var(--color-text); }

/* 学习地图模式 */
.map-view { padding: 20px; min-height: 400px; }
.map-path { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; justify-content: center; }
.map-node { display: flex; align-items: center; gap: 8px; }
.map-node-card { padding: 12px 16px; border-radius: 10px; background: var(--color-surface); border: 2px solid var(--color-border); cursor: pointer; transition: all 0.15s; min-width: 120px; text-align: center; }
.map-node-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
.map-node-step { font-size: 11px; font-weight: 700; color: var(--color-text-3); margin-bottom: 4px; }
.map-node-label { font-size: 13px; font-weight: 600; color: var(--color-text); }
.map-node-mastery { font-size: 10px; padding: 1px 8px; border-radius: 8px; margin-top: 4px; display: inline-block; }
.map-arrow { font-size: 20px; color: var(--color-text-3); }
</style>