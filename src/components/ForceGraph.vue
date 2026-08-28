<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'

interface GraphNode { id: string; label: string; group: number; x?: number; y?: number; vx?: number; vy?: number; radius?: number }
interface GraphEdge { source: string; target: string }

const props = defineProps<{
  nodes: GraphNode[]
  edges: GraphEdge[]
  subjectTokens: string[]
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

const REPULSION = 6000
const ATTRACTION = 0.008
const DAMPING = 0.9
const CENTER_FORCE = 0
const MIN_VELOCITY = 2

function resolveToken(name: string): string {
  if (typeof window === 'undefined') return '#7c6af2'
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || '#7c6af2'
}

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
      node.radius = 5 + (gn > 50 ? 0 : node.label && node.label.length > 2 ? 4 : 0)
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
  let totalSpeed = 0; const cx = w / 2; const cy = h / 2; const margin = 40
  for (const node of props.nodes) {
    node.vx = (node.vx ?? 0) + (cx - (node.x ?? 0)) * CENTER_FORCE
    node.vy = (node.vy ?? 0) + (cy - (node.y ?? 0)) * CENTER_FORCE
    node.vx = (node.vx ?? 0) * DAMPING; node.vy = (node.vy ?? 0) * DAMPING
    const MAX_V = 40; node.vx = Math.max(-MAX_V, Math.min(MAX_V, node.vx ?? 0))
    node.vy = Math.max(-MAX_V, Math.min(MAX_V, node.vy ?? 0))
    node.x = (node.x ?? 0) + (node.vx ?? 0); node.y = (node.y ?? 0) + (node.vy ?? 0)
    totalSpeed += Math.abs(node.vx ?? 0) + Math.abs(node.vy ?? 0)
    if ((node.x ?? 0) < margin) { node.x = margin; node.vx = 0 }
    if ((node.x ?? 0) > w - margin) { node.x = w - margin; node.vx = 0 }
    if ((node.y ?? 0) < margin) { node.y = margin; node.vy = 0 }
    if ((node.y ?? 0) > h - margin) { node.y = h - margin; node.vy = 0 }
  }
  render(w, h); alpha *= 0.97
  if (totalSpeed > MIN_VELOCITY || isDragging || alpha > 0.02)
    animationId = requestAnimationFrame(() => simulate())
  else { animationId = null; simRunning = false }
}

function render(w: number, h: number) {
  if (!ctx || !canvasRef.value) return; ctx.clearRect(0, 0, w, h)
  if (props.nodes.length === 0) return
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
    ctx.fillStyle = g2; ctx.fill(); ctx.strokeStyle = isHover ? '#fff' : color + '80'
    ctx.lineWidth = isHover ? 2 : 1; ctx.stroke()
    ctx.fillStyle = isHover ? '#fff' : 'rgba(148, 163, 184, 0.90)'
    ctx.font = '12px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif'
    ctx.textAlign = 'center'; ctx.textBaseline = 'top'
    ctx.fillText(node.label || '', nx, ny + r + 5)
  }
}

function renderLegend() { emit('render') }

function onMouseDown(e: MouseEvent) {
  const pos = mousePos(e); const node = findNode(pos)
  if (node) { isDragging = true; dragNode = node; dragOffsetX = pos.x - (node.x ?? 0); dragOffsetY = pos.y - (node.y ?? 0) }
}
function onMouseMove(e: MouseEvent) {
  const pos = mousePos(e)
  if (isDragging && dragNode) {
    dragNode.x = pos.x - dragOffsetX; dragNode.y = pos.y - dragOffsetY
    if (!animationId && canvasRef.value) animationId = requestAnimationFrame(() => simulate())
  } else {
    const node = findNode(pos)
    if (node !== hoveredNode) {
      hoveredNode = node; if (canvasRef.value) {
        canvasRef.value.style.cursor = node ? 'pointer' : 'default'
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
  isDragging = false; dragNode = null
}
function mousePos(e: MouseEvent) { const r = canvasRef.value!.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top } }
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
function resetZoom() { _zoom = 1; if (canvasRef.value) { const w = (canvasRef.value as any)._w || 800; const h = (canvasRef.value as any)._h || 500; render(w, h) } }
defineExpose({ zoomIn, zoomOut, resetZoom })
</script>

<template>
  <div class="graph-container">
    <div class="graph-canvas-wrapper"><canvas ref="canvasRef" id="knowledgeGraph"></canvas></div>
    <div class="graph-legend" id="graphLegend"></div>
  </div>
</template>

<style scoped>
.graph-container { height: 520px; position: relative; background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); -webkit-backdrop-filter: blur(var(--glass-blur)); border: 1px solid var(--glass-border); border-radius: var(--radius-md); }
.graph-canvas-wrapper { position: absolute; inset: 0; }
.graph-container canvas { display: block; }
.graph-legend { position: absolute; top: 0.75rem; left: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.625rem 0.875rem; font-size: 0.75rem; box-shadow: var(--shadow-sm); }
</style>