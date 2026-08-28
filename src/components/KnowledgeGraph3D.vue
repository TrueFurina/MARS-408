<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'

const props = defineProps<{
  nodes: any[]
  edges: any[]
  width?: number
  height?: number
}>()

const emit = defineEmits<{
  nodeClick: [node: any]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
let animId: number | null = null
let rotationAngle = 0

interface Point3D {
  x: number; y: number; z: number
  label: string; color: string; radius: number
  data: any; mastery?: string
}

const points3d = ref<Point3D[]>([])

function initSphere() {
  const n = props.nodes.length
  if (n === 0) return

  // 将节点分布到球面上（斐波那契球体分布，保证均匀）
  const goldenRatio = (1 + Math.sqrt(5)) / 2
  const radius = 200

  points3d.value = props.nodes.map((node, i) => {
    const theta = 2 * Math.PI * i / goldenRatio
    const phi = Math.acos(1 - 2 * (i + 0.5) / n)
    return {
      x: radius * Math.sin(phi) * Math.cos(theta),
      y: radius * Math.sin(phi) * Math.sin(theta),
      z: radius * Math.cos(phi),
      label: node.label || node.id,
      color: node.color || '#7c6af2',
      radius: (node.value || 22) * 0.8,
      data: node,
      mastery: node.mastery,
    }
  })
}

function getMasteryColor(mastery?: string): string {
  const map: Record<string, string> = { mastered: '#22c55e', weak: '#f59e0b', unlearned: '#ef4444' }
  return map[mastery || ''] || '#7c6af2'
}

function project3D(p: Point3D, angle: number, w: number, h: number) {
  // 绕 Y 轴旋转
  const cosA = Math.cos(angle)
  const sinA = Math.sin(angle)
  const rx = p.x * cosA - p.z * sinA
  const rz = p.x * sinA + p.z * cosA
  const perspective = 600 / (600 + rz)
  return {
    sx: w / 2 + rx * perspective,
    sy: h / 2 + p.y * perspective,
    scale: perspective,
    depth: rz,
  }
}

function draw() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const w = props.width || 800
  const h = props.height || 600
  ctx.clearRect(0, 0, w, h)

  rotationAngle += 0.005

  // 按深度排序（远的先画）
  const projected = points3d.value.map(p => ({
    ...project3D(p, rotationAngle, w, h),
    point: p,
  })).sort((a, b) => a.depth - b.depth)

  // 半透明球体背景
  const grad = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, 220)
  grad.addColorStop(0, 'rgba(124,106,242,0.04)')
  grad.addColorStop(0.5, 'rgba(124,106,242,0.02)')
  grad.addColorStop(1, 'rgba(124,106,242,0)')
  ctx.fillStyle = grad
  ctx.beginPath(); ctx.arc(w / 2, h / 2, 220, 0, Math.PI * 2); ctx.fill()

  // 绘制连线
  for (const edge of props.edges) {
    const from = points3d.value[props.nodes.findIndex(n => n.id === edge.from)]
    const to = points3d.value[props.nodes.findIndex(n => n.id === edge.to)]
    if (!from || !to) continue
    const pf = project3D(from, rotationAngle, w, h)
    const pt = project3D(to, rotationAngle, w, h)
    const avgDepth = (pf.depth + pt.depth) / 2
    ctx.beginPath()
    ctx.moveTo(pf.sx, pf.sy)
    ctx.lineTo(pt.sx, pt.sy)
    ctx.strokeStyle = `rgba(148,163,184,${Math.max(0.1, (avgDepth + 300) / 600) * 0.5})`
    ctx.lineWidth = 1.5
    ctx.stroke()
  }

  // 绘制节点
  for (const p of projected) {
    const r = p.point.radius * p.scale
    const alpha = Math.max(0.3, (p.depth + 300) / 600)
    const color = p.point.mastery ? getMasteryColor(p.point.mastery) : p.point.color

    // 发光
    ctx.beginPath(); ctx.arc(p.sx, p.sy, r + 4, 0, Math.PI * 2)
    ctx.fillStyle = color + `${Math.round(alpha * 20).toString(16).padStart(2, '0')}`
    ctx.fill()

    // 节点
    ctx.beginPath(); ctx.arc(p.sx, p.sy, r, 0, Math.PI * 2)
    ctx.fillStyle = color + `${Math.round(alpha * 30).toString(16).padStart(2, '0')}`
    ctx.fill()
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.stroke()

    // 标签（只显示深度靠前的节点）
    if (p.depth > -50) {
      ctx.fillStyle = `rgba(248,250,252,${alpha})`
      ctx.font = '11px sans-serif'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillText(p.point.label.length > 8 ? p.point.label.slice(0, 8) + '..' : p.point.label, p.sx, p.sy)
    }
  }

  animId = requestAnimationFrame(draw)
}

function onClick(e: MouseEvent) {
  const rect = canvasRef.value?.getBoundingClientRect()
  if (!rect) return
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const w = props.width || 800
  const h = props.height || 600

  const projected = points3d.value.map(p => ({
    ...project3D(p, rotationAngle, w, h),
    point: p,
  }))

  let closest = -1
  let minDist = 30
  for (let i = 0; i < projected.length; i++) {
    const p = projected[i]!
    const dx = mx - p.sx
    const dy = my - p.sy
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist < minDist && p.depth > -100) {
      minDist = dist
      closest = i
    }
  }
  if (closest >= 0) {
    emit('nodeClick', projected[closest]!.point.data)
  }
}

onMounted(() => {
  initSphere()
  animId = requestAnimationFrame(draw)
})

onUnmounted(() => {
  if (animId) cancelAnimationFrame(animId)
})

watch(() => [props.nodes], () => { initSphere() })
</script>

<template>
  <div class="sphere-wrapper">
    <canvas
      ref="canvasRef"
      :width="width || 800"
      :height="height || 600"
      class="sphere-canvas"
      @click="onClick"
    ></canvas>
    <div class="sphere-hint">🌐 3D 球体视图 · 鼠标点击节点查看详情</div>
    <div v-if="nodes.length === 0" class="sphere-empty">
      <div class="empty-icon">🌐</div>
      <div class="empty-text">暂无数据</div>
    </div>
  </div>
</template>

<style scoped>
.sphere-wrapper { position: relative; width: 100%; }
.sphere-canvas { width: 100%; height: auto; display: block; border-radius: 12px; background: rgba(255,255,255,0.02); border: 1px solid var(--color-border); cursor: pointer; }
.sphere-hint { text-align: center; font-size: 12px; color: var(--color-text-3); margin-top: 6px; }
.sphere-empty { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; pointer-events: none; }
.empty-icon { font-size: 48px; }
.empty-text { font-size: 18px; font-weight: 600; color: var(--color-text-2); }
</style>