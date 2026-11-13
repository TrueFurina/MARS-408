<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { resolveToken, withAlpha } from '@/utils/themeTokens'

interface GraphNode { id: string; label: string; group: number; x?: number; y?: number; vx?: number; vy?: number; radius?: number }
interface GraphEdge { source: string; target: string }

const props = defineProps<{
  nodes: GraphNode[]
  edges: GraphEdge[]
  subjectTokens: string[]
  subjectLabels?: string[]
  groupToLabel: (g: number) => string
  onGroupClick?: (group: number) => void
}>()

const emit = defineEmits<{
  render: []
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let ctx: CanvasRenderingContext2D | null = null
let animationId: number | null = null
let isDragging = false
let dragNode: GraphNode | null = null
let dragOffsetX = 0
let dragOffsetY = 0
let hoveredNode: GraphNode | null = null
let simRunning = false
let alpha = 1
let _zoom = 1
let _panX = 0
let _panY = 0
let isPanning = false
let panStartX = 0
let panStartY = 0

const REPULSION = 20000
const ATTRACTION = 0.005
const DAMPING = 0.9
const CENTER_FORCE = 0
const MIN_VELOCITY = 2
/** 默认态标签最多显示的字数；超出截断。悬停/选中时显示全称。 */
const LABEL_MAX_CHARS = 8
/**
 * 边界留白：上方要给图例胶囊让位（图例绝对定位在画布左上，横跨整行），
 * 下方要给标签留高度，否则节点会被顶到边沿、文字直接被裁掉。
 */
const PAD_TOP = 88
const PAD_SIDE = 44
const PAD_BOTTOM = 54

function groupColor(g: number): string {
  if (g <= 7) return props.subjectTokens[0] || '--subject-cn'
  if (g <= 14) return props.subjectTokens[1] || '--subject-ds'
  if (g <= 21) return props.subjectTokens[2] || '--subject-co'
  return props.subjectTokens[3] || '--subject-os'
}

function lighten(hex: string, pct: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgb(${Math.min(255,(n>>16)+pct)},${Math.min(255,((n>>8)&255)+pct)},${Math.min(255,(n&255)+pct)})`
}

/**
 * 聚合节点名称形如「线性表 (34)」。
 * 默认态只画章节名并按字数截断，括号里的计数留给悬停——否则一行挤 9~12 个字，
 * 27 个节点必然相互压叠，等于没法看。
 */
function labelForDisplay(label: string): string {
  const name = label.replace(/\s*\(\d+\)\s*$/, '')
  return name.length > LABEL_MAX_CHARS ? name.slice(0, LABEL_MAX_CHARS) + '…' : name
}

function initPositions() {
  const c = canvasRef.value; if (!c) return
  const w = (c as any)._w || c.width || 800; const h = (c as any)._h || c.height || 500
  const n = props.nodes.length; const margin = 60; const cx = w / 2; const cy = h / 2
  const maxR = Math.min(w, h) / 2 - margin
  const groups = new Map<number, GraphNode[]>()
  props.nodes.forEach(node => {
    const g = node.group || 0; if (!groups.has(g)) groups.set(g, [])
    groups.get(g)!.push(node)
  })
  const groupEntries = Array.from(groups.entries())
  const groupCount = groupEntries.length; const angleStep = (Math.PI * 2) / Math.max(groupCount, 1)
  groupEntries.forEach(([group, groupNodes], gi) => {
    const baseAngle = gi * angleStep; const gn = groupNodes.length
    groupNodes.forEach((node, ni) => {
      const t = ni / Math.max(gn, 1); const radius = margin + t * maxR * 0.85
      const angle = baseAngle + (t - 0.5) * angleStep * 0.6
      node.x = cx + radius * Math.cos(angle); node.y = cy + radius * Math.sin(angle)
      node.vx = (Math.random() - 0.5) * 2; node.vy = (Math.random() - 0.5) * 2
      node.radius = 4 + (gn > 50 ? 0 : node.label && node.label.length > 2 ? 3 : 0)
    })
  })
}

function resizeCanvas() {
  const c = canvasRef.value; if (!c) return
  const wrapper = c.parentElement; if (!wrapper) return
  const rect = wrapper.getBoundingClientRect(); const dpr = window.devicePixelRatio || 1
  c.width = Math.max(rect.width * dpr, 100); c.height = Math.max(rect.height * dpr, 100)
  c.style.width = Math.max(rect.width, 100) + 'px'; c.style.height = Math.max(rect.height, 100) + 'px'
  ctx = c.getContext('2d'); if (ctx) ctx.scale(dpr, dpr)
  ;(c as any)._w = Math.max(rect.width, 100); (c as any)._h = Math.max(rect.height, 100)
  // 改画布尺寸会清空位图；此时仿真多半已经收敛、不再有下一帧，
  // 不补一次重绘的话，窗口一拉伸图就整个消失。
  if (props.nodes.length) render((c as any)._w, (c as any)._h)
}

function startSim() {
  if (animationId) cancelAnimationFrame(animationId)
  simRunning = true; alpha = 1; simulate()
}

function simulate() {
  const c = canvasRef.value; if (!c || !simRunning) { animationId = null; return }
  const w = (c as any)._w || c.width || 800; const h = (c as any)._h || c.height || 500
  const n = props.nodes.length; if (n === 0) { render(w, h); return }
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const a = props.nodes[i]; const b = props.nodes[j]; if (!a || !b) continue
      let dx = (b.x ?? 0) - (a.x ?? 0); let dy = (b.y ?? 0) - (a.y ?? 0); let dist = Math.sqrt(dx * dx + dy * dy)
      if (dist < 1) dist = 1; const force = (REPULSION * alpha) / (dist * dist)
      const fx = (dx / dist) * force; const fy = (dy / dist) * force
      a.vx = (a.vx ?? 0) - fx; a.vy = (a.vy ?? 0) - fy; b.vx = (b.vx ?? 0) + fx; b.vy = (b.vy ?? 0) + fy
    }
  }
  for (const edge of props.edges) {
    const src = props.nodes.find(n => n.id === edge.source); const tgt = props.nodes.find(n => n.id === edge.target)
    if (!src || !tgt) continue; let dx = (tgt.x ?? 0) - (src.x ?? 0); let dy = (tgt.y ?? 0) - (src.y ?? 0)
    let dist = Math.sqrt(dx * dx + dy * dy); if (dist < 1) dist = 1
    const force = ATTRACTION * dist * alpha; const fx = (dx / dist) * force; const fy = (dy / dist) * force
    src.vx = (src.vx ?? 0) + fx; src.vy = (src.vy ?? 0) + fy; tgt.vx = (tgt.vx ?? 0) - fx; tgt.vy = (tgt.vy ?? 0) - fy
  }
  let totalSpeed = 0; const cx = w / 2; const cy = h / 2
  for (const node of props.nodes) {
    node.vx = (node.vx ?? 0) + (cx - (node.x ?? 0)) * CENTER_FORCE
    node.vy = (node.vy ?? 0) + (cy - (node.y ?? 0)) * CENTER_FORCE
    node.vx = (node.vx ?? 0) * DAMPING; node.vy = (node.vy ?? 0) * DAMPING
    const MAX_V = 40; node.vx = Math.max(-MAX_V, Math.min(MAX_V, node.vx ?? 0))
    node.vy = Math.max(-MAX_V, Math.min(MAX_V, node.vy ?? 0))
    node.x = (node.x ?? 0) + (node.vx ?? 0); node.y = (node.y ?? 0) + (node.vy ?? 0)
    totalSpeed += Math.abs(node.vx ?? 0) + Math.abs(node.vy ?? 0)
    // 边界用反向力而不是硬夹：硬夹会把节点永久钉在边沿，几十个节点沿四边排成列、
    // 标签互相压叠还被面板裁掉。反向力让节点自己回流，分布始终是散开的。
    // 系数要比速度量级（上限 40）大得多才压得住，0.03 在这个速度范围里等于没约束。
    if ((node.x ?? 0) < PAD_SIDE) node.vx = (node.vx ?? 0) + (PAD_SIDE - (node.x ?? 0)) * 0.12
    if ((node.x ?? 0) > w - PAD_SIDE) node.vx = (node.vx ?? 0) - ((node.x ?? 0) - (w - PAD_SIDE)) * 0.12
    if ((node.y ?? 0) < PAD_TOP) node.vy = (node.vy ?? 0) + (PAD_TOP - (node.y ?? 0)) * 0.12
    if ((node.y ?? 0) > h - PAD_BOTTOM) node.vy = (node.vy ?? 0) - ((node.y ?? 0) - (h - PAD_BOTTOM)) * 0.12
  }
  render(w, h); alpha *= 0.97
  if (totalSpeed > MIN_VELOCITY || isDragging || alpha > 0.02)
    animationId = requestAnimationFrame(() => simulate())
  else { animationId = null; simRunning = false }
}

function render(w: number, h: number) {
  if (!ctx || !canvasRef.value) return
  const dpr = window.devicePixelRatio || 1
  // 每次重绘前复位变换再重新应用：否则 zoom 会在上一次缩放下继续叠加，
  // 点两次放大变成 1.3×1.3 累积，且 reset 回不到 1。
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, w, h)
  if (props.nodes.length === 0) return
  if (_zoom !== 1 || _panX !== 0 || _panY !== 0) {
    ctx.translate(w / 2 + _panX, h / 2 + _panY)
    ctx.scale(_zoom, _zoom)
    ctx.translate(-w / 2, -h / 2)
  }
  for (const edge of props.edges) {
    const src = props.nodes.find(n => n.id === edge.source); const tgt = props.nodes.find(n => n.id === edge.target)
    if (!src || !tgt) continue
    const gradient = ctx.createLinearGradient(src.x ?? 0, src.y ?? 0, tgt.x ?? 0, tgt.y ?? 0)
    const srcColor = resolveToken(groupColor(src.group || 0)); const tgtColor = resolveToken(groupColor(tgt.group || 0))
    gradient.addColorStop(0, srcColor + '40'); gradient.addColorStop(1, tgtColor + '40')
    ctx.beginPath(); ctx.moveTo(src.x ?? 0, src.y ?? 0); ctx.lineTo(tgt.x ?? 0, tgt.y ?? 0)
    ctx.strokeStyle = gradient; ctx.lineWidth = 1.5; ctx.stroke()
    const angle = Math.atan2((tgt.y ?? 0) - (src.y ?? 0), (tgt.x ?? 0) - (src.x ?? 0))
    const endX = (tgt.x ?? 0) - ((tgt.radius ?? 8) + 4) * Math.cos(angle)
    const endY = (tgt.y ?? 0) - ((tgt.radius ?? 8) + 4) * Math.sin(angle); const al = Math.PI / 6
    ctx.beginPath(); ctx.moveTo(endX, endY); ctx.lineTo(endX - 8 * Math.cos(angle - al), endY - 8 * Math.sin(angle - al))
    ctx.moveTo(endX, endY); ctx.lineTo(endX - 8 * Math.cos(angle + al), endY - 8 * Math.sin(angle + al))
    ctx.strokeStyle = tgtColor + '60'; ctx.lineWidth = 1.5; ctx.stroke()
  }
  for (const node of props.nodes) {
    const color = resolveToken(groupColor(node.group || 0)); const isHover = hoveredNode && hoveredNode.id === node.id
    const nx = node.x ?? 0; const ny = node.y ?? 0; const r = node.radius ?? 8
    if (isHover) {
      const g = ctx.createRadialGradient(nx, ny, 0, nx, ny, 30)
      g.addColorStop(0, color + '30'); g.addColorStop(1, color + '00')
      ctx.beginPath(); ctx.arc(nx, ny, 30, 0, Math.PI * 2); ctx.fillStyle = g; ctx.fill()
    }
    ctx.beginPath(); ctx.arc(nx, ny, r, 0, Math.PI * 2)
    const g2 = ctx.createRadialGradient(nx - 3, ny - 3, 0, nx, ny, r)
    g2.addColorStop(0, lighten(color, 30)); g2.addColorStop(1, color)
    ctx.fillStyle = g2; ctx.fill(); ctx.strokeStyle = isHover ? resolveToken('--color-text') : color + '80'
    ctx.lineWidth = isHover ? 2 : 1; ctx.stroke()
    ctx.fillStyle = isHover ? resolveToken('--color-text') : withAlpha(resolveToken('--color-text-3'), 0.9)
    // 默认就标注名称。没名字的圆点阵等于没有信息：投屏和触屏上根本没有「悬停」这个动作。
    // 标签画在圆下方，先描一圈卡片底再填字，才能从连线和相邻标签里浮出来。
    const labelText = isHover ? (node.label || '') : labelForDisplay(node.label || '')
    if (labelText) {
      // 上半区的节点把标签放到圆上方，下半区放下方：27 个节点挤在一起时，
      // 统一往下画必然在密集区叠成一团，上下交错能多让出一半的纵向空间。
      const above = ny < h / 2
      const labelX = nx
      const labelY = above ? ny - r - 5 : ny + r + 5
      ctx.font = `${isHover ? 12 : 10}px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`
      ctx.textAlign = 'center'; ctx.textBaseline = above ? 'bottom' : 'top'
      ctx.lineWidth = 3
      ctx.strokeStyle = resolveToken('--color-card')
      ctx.strokeText(labelText, labelX, labelY)
      ctx.fillStyle = isHover ? resolveToken('--color-text') : withAlpha(resolveToken('--color-text-2'), 0.95)
      ctx.fillText(labelText, labelX, labelY)
    }
  }
}

function renderLegend() { emit('render') }

/** 图例按四个科目聚合：分组 1-7 计网 / 8-14 数据结构 / 15-21 计组 / 22+ 操作系统 */
const legendItems = computed(() => {
  const buckets = new Map<number, number>()
  props.nodes.forEach(n => {
    const g = n.group || 0
    const idx = g <= 7 ? 0 : g <= 14 ? 1 : g <= 21 ? 2 : 3
    buckets.set(idx, (buckets.get(idx) || 0) + 1)
  })
  return Array.from(buckets.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([idx, count]) => ({
      key: idx,
      color: props.subjectTokens[idx] || '--subject-cn',
      label: props.subjectLabels?.[idx] || `科目 ${idx + 1}`,
      count,
    }))
})

function onMouseDown(e: MouseEvent) {
  const pos = mousePos(e); const node = findNode(pos)
  if (node) { isDragging = true; dragNode = node; dragOffsetX = pos.x - (node.x ?? 0); dragOffsetY = pos.y - (node.y ?? 0) }
  else {
    // 空白处按下 → 平移画布。放大之后没有平移，就只能看到中间一块。
    isPanning = true
    const raw = rawPos(e); panStartX = raw.x; panStartY = raw.y
    if (canvasRef.value) canvasRef.value.style.cursor = 'grabbing'
  }
}
function onMouseMove(e: MouseEvent) {
  if (isPanning) {
    const raw = rawPos(e)
    _panX += raw.x - panStartX; _panY += raw.y - panStartY
    panStartX = raw.x; panStartY = raw.y
    const w = (canvasRef.value as any)?._w || 800; const h = (canvasRef.value as any)?._h || 500
    render(w, h); return
  }
  const pos = mousePos(e)
  if (isDragging && dragNode) {
    dragNode.x = pos.x - dragOffsetX; dragNode.y = pos.y - dragOffsetY
    if (!animationId && canvasRef.value) animationId = requestAnimationFrame(() => simulate())
  } else {
    const node = findNode(pos)
    if (node !== hoveredNode) {
      hoveredNode = node; if (canvasRef.value) {
        canvasRef.value.style.cursor = node ? 'pointer' : (_zoom !== 1 ? 'grab' : 'default')
        const w = (canvasRef.value as any)._w || 800; const h = (canvasRef.value as any)._h || 500
        render(w, h)
      }
    }
  }
}
function onMouseUp(e: MouseEvent) {
  if (isDragging && dragNode && !animationId && canvasRef.value) animationId = requestAnimationFrame(() => simulate())
  if (!isDragging && dragNode) {
    const dn = dragNode as any
    if (dn._isGroup && dn._memberIds && dn.group) props.onGroupClick?.(dn.group)
  }
  isDragging = false; dragNode = null; isPanning = false
  if (canvasRef.value) canvasRef.value.style.cursor = _zoom !== 1 ? 'grab' : 'default'
}
function rawPos(e: MouseEvent) {
  const r = canvasRef.value!.getBoundingClientRect()
  return { x: e.clientX - r.left, y: e.clientY - r.top }
}
function mousePos(e: MouseEvent) {
  const c = canvasRef.value!
  const w = (c as any)._w || 800; const h = (c as any)._h || 500
  const raw = rawPos(e)
  let x = raw.x; let y = raw.y
  // render 里对画布做过 _zoom+_pan 变换，命中判定要把屏幕坐标反算回图谱坐标，
  // 否则放大或平移之后，鼠标点的位置和节点的实际位置对不上。
  if (_zoom !== 1 || _panX !== 0 || _panY !== 0) {
    x = (x - (w / 2 + _panX)) / _zoom + w / 2
    y = (y - (h / 2 + _panY)) / _zoom + h / 2
  }
  return { x, y }
}
function findNode(pos: { x: number; y: number }): GraphNode | null {
  for (let i = props.nodes.length - 1; i >= 0; i--) {
    const n = props.nodes[i]; if (!n) continue
    if (Math.sqrt((pos.x-(n.x??0))**2 + (pos.y-(n.y??0))**2) < (n.radius??8)+8) return n
  }
  return null
}

function initCanvas() {
  const c = canvasRef.value; if (!c) return
  ctx = c.getContext('2d'); resizeCanvas(); initPositions(); renderLegend(); startSim()
}

onMounted(() => {
  const c = canvasRef.value; if (!c) return
  c.addEventListener('mousedown', onMouseDown); c.addEventListener('mousemove', onMouseMove)
  c.addEventListener('mouseup', onMouseUp); c.addEventListener('mouseleave', onMouseUp)
  window.addEventListener('resize', resizeCanvas); initCanvas()
})
onUnmounted(() => {
  simRunning = false; if (animationId) cancelAnimationFrame(animationId)
  window.removeEventListener('resize', resizeCanvas); const c = canvasRef.value
  if (c) {
    c.removeEventListener('mousedown', onMouseDown); c.removeEventListener('mousemove', onMouseMove)
    c.removeEventListener('mouseup', onMouseUp); c.removeEventListener('mouseleave', onMouseUp)
  }
})
watch(() => props.nodes, () => { if (props.nodes.length > 0) { initCanvas() } })

function zoomIn() { _zoom = Math.min(3, _zoom * 1.3); if (canvasRef.value) { const w = (canvasRef.value as any)._w || 800; const h = (canvasRef.value as any)._h || 500; render(w, h) } }
function zoomOut() { _zoom = Math.max(0.3, _zoom / 1.3); if (canvasRef.value) { const w = (canvasRef.value as any)._w || 800; const h = (canvasRef.value as any)._h || 500; render(w, h) } }
function resetZoom() { _zoom = 1; _panX = 0; _panY = 0; if (canvasRef.value) { const w = (canvasRef.value as any)._w || 800; const h = (canvasRef.value as any)._h || 500; render(w, h) } }
defineExpose({ zoomIn, zoomOut, resetZoom })
</script>

<template>
  <div class="graph-container">
    <div class="graph-canvas-wrapper"><canvas ref="canvasRef" id="knowledgeGraph"></canvas></div>
    <!-- 图例原来是个空 div：renderLegend() 只 emit('render')，父组件没监听，
         所以左上角一直挂着一个空的圆角胶囊。这里按四个科目色直接渲染。 -->
    <div class="graph-legend" v-if="legendItems.length">
      <span class="legend-item" v-for="it in legendItems" :key="it.key">
        <i class="legend-dot" :style="{ background: 'var(' + it.color + ')' }"></i>
        <span>{{ it.label }}</span>
        <b>{{ it.count }}</b>
      </span>
    </div>
    <!-- 名称默认已经全部标注；这里只提示悬停能看到什么额外信息，不再暗示"要去悬停才有名字"。 -->
    <div class="graph-hint" v-if="nodes.length">悬停节点查看完整名称</div>
  </div>
</template>

<style scoped>
.graph-container { height: 520px; position: relative; background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur)); border: 1px solid var(--glass-border); border-radius: var(--radius-md); }
.graph-canvas-wrapper { position: absolute; inset: 0; }
.graph-container canvas { display: block; }
.graph-legend { position: absolute; top: 0.75rem; left: 0.75rem; max-width: calc(100% - 1.5rem); display: flex; flex-wrap: wrap; gap: 0.375rem 0.75rem; background: var(--color-card); border: 1px solid var(--color-border); border-radius: 9px; padding: 0.5rem 0.75rem; font-size: var(--text-xs); color: var(--color-text-2); box-shadow: var(--shadow-card); }
.legend-item { display: inline-flex; align-items: center; gap: 0.375rem; white-space: nowrap; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.legend-item b { color: var(--color-text-3); font-weight: 500; }
.graph-hint { position: absolute; right: 0.75rem; bottom: 0.75rem; padding: 0.25rem 0.5rem; border-radius: 8px; background: var(--color-card); border: 1px solid var(--color-border); font-size: var(--text-2xs); color: var(--color-text-3); pointer-events: none; }
</style>