<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  mode?: 'normal' | 'synflood'
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const isAnimating = ref(false)
const currentStep = ref(0)
const animSpeed = ref(1)

let animationId: number | null = null
let canvas: HTMLCanvasElement | null = null
let ctx: CanvasRenderingContext2D | null = null
let step = 0
let progress = 0
let isFlood = false

// Layout constants
const CX1 = 150  // client x
const CX2 = 450  // server x
const CY = 220   // center y
const ARROW_LEN = 30

function initCanvas() {
  canvas = canvasRef.value
  if (!canvas) return
  const dpr = window.devicePixelRatio || 1
  const w = canvas.clientWidth || 600
  const h = canvas.clientHeight || 400
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = w + 'px'
  canvas.style.height = h + 'px'
  ctx = canvas.getContext('2d')
  if (ctx) ctx.scale(dpr, dpr)
}

function drawBackground() {
  if (!ctx || !canvas) return
  const w = canvas.clientWidth
  const h = canvas.clientHeight

  // Background
  ctx.fillStyle = '#0f0f1a'
  ctx.fillRect(0, 0, w, h)

  // Grid
  ctx.strokeStyle = 'rgba(124, 106, 242, 0.06)'
  ctx.lineWidth = 0.5
  for (let x = 0; x < w; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke()
  }
  for (let y = 0; y < h; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
  }
}

function drawEndpoint(x: number, label: string, isServer: boolean, highlight = false) {
  if (!ctx) return
  const boxW = 110, boxH = 44
  const h = canvas?.clientHeight ?? 400

  // Box shadow
  ctx.shadowColor = 'rgba(0,0,0,0.4)'
  ctx.shadowBlur = 8
  ctx.shadowOffsetY = 3

  // Box
  const grad = ctx.createLinearGradient(x - boxW/2, 0, x + boxW/2, 0)
  if (highlight) {
    grad.addColorStop(0, '#8B5CF6')
    grad.addColorStop(1, '#7c6af2')
  } else {
    grad.addColorStop(0, '#1c1c2b')
    grad.addColorStop(1, '#161622')
  }
  ctx.fillStyle = grad
  ctx.beginPath()
  const r = 10
  ctx.roundRect(x - boxW/2, isServer ? h - 60 : 20, boxW, boxH, r)
  ctx.fill()

  ctx.shadowColor = 'transparent'

  // Border
  ctx.strokeStyle = highlight ? '#8B5CF6' : 'rgba(124,106,242,0.3)'
  ctx.lineWidth = highlight ? 2 : 1
  ctx.stroke()

  // Label
  ctx.fillStyle = highlight ? '#fff' : '#94a3b8'
  ctx.font = '600 14px -apple-system, "PingFang SC", sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, x, isServer ? h - 60 + boxH/2 : 20 + boxH/2)
}

function drawArrow(x1: number, y1: number, x2: number, y2: number, label: string,
                   color: string, progressVal: number, isDashed = false) {
  if (!ctx) return

  const dx = x2 - x1, dy = y2 - y1
  const len = Math.sqrt(dx * dx + dy * dy)
  const px = x1 + dx * progressVal
  const py = y1 + dy * progressVal

  // Line
  ctx.beginPath()
  if (isDashed) ctx.setLineDash([6, 4])
  else ctx.setLineDash([])
  ctx.strokeStyle = color
  ctx.lineWidth = 2.5
  ctx.globalAlpha = Math.min(1, progressVal * 2)
  ctx.moveTo(x1, y1)
  ctx.lineTo(px, py)
  ctx.stroke()
  ctx.setLineDash([])
  ctx.globalAlpha = 1

  // Arrowhead at current position
  if (progressVal > 0.1) {
    const angle = Math.atan2(dy, dx)
    ctx.beginPath()
    ctx.moveTo(px, py)
    ctx.lineTo(px - ARROW_LEN * Math.cos(angle - 0.4), py - ARROW_LEN * Math.sin(angle - 0.4))
    ctx.lineTo(px - ARROW_LEN * Math.cos(angle + 0.4), py - ARROW_LEN * Math.sin(angle + 0.4))
    ctx.closePath()
    ctx.fillStyle = color
    ctx.fill()
  }

  // Label
  if (progressVal > 0.3) {
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2
    ctx.fillStyle = color
    ctx.font = '600 13px -apple-system, "PingFang SC", sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'bottom'
    ctx.fillText(label, mx, my - 8)
  }
}

function drawStateBox(text: string, x: number, y: number, color: string) {
  if (!ctx) return
  ctx.fillStyle = color + '15'
  ctx.fillRect(x - 60, y - 10, 120, 24)
  ctx.strokeStyle = color + '30'
  ctx.lineWidth = 1
  ctx.strokeRect(x - 60, y - 10, 120, 24)
  ctx.fillStyle = color
  ctx.font = '11px monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, x, y + 2)
}

function drawScene() {
  if (!ctx || !canvas) return
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  ctx.clearRect(0, 0, w, h)
  drawBackground()
  drawEndpoint(CX1, '客户端 (Client)', false, step >= 1)
  drawEndpoint(CX2, '服务器 (Server)', true, step >= 2)

  const clientY = h - 60
  const serverY = 20 + 44
  const midY = (clientY + serverY) / 2

  if (isFlood && step === 1) {
    // SYN Flood: multiple SYNs
    for (let i = 0; i < 5; i++) {
      const offset = i * 12
      const p = Math.max(0, Math.min(1, progress * 2 - i * 0.15))
      drawArrow(CX1, clientY + 5, CX2, serverY + 5,
        i === 0 ? 'SYN' : '', '#ef4444', p, true)
    }
    drawStateBox('半连接队列 (SYN_RCVD)', CX2, serverY + 100, '#ef4444')
    if (progress > 0.5) {
      ctx.fillStyle = '#ef4444'
      ctx.font = '13px -apple-system, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('⚠️ 半连接队列满！正常连接被拒绝', CX2, serverY + 130)
    }
    return
  }

  // Step 1: SYN (client → server)
  if (step >= 1) {
    const p = step === 1 ? progress : 1
    drawArrow(CX1, clientY + 5, CX2, serverY + 5, 'SYN\nseq=x', '#8B5CF6', p)
    if (p >= 0.95) drawStateBox('SYN_SENT', CX1, clientY + 30, '#8B5CF6')
    if (p >= 0.95) drawStateBox('LISTEN', CX2, serverY + 30, '#22C55E')
  }

  // Step 2: SYN+ACK (server → client)
  if (step >= 2) {
    const p = step === 2 ? progress : 1
    drawArrow(CX2, serverY - 5, CX1, clientY - 5, 'SYN+ACK\nseq=y,ack=x+1', '#7c6af2', p)
    if (p >= 0.95) drawStateBox('SYN_RCVD', CX2, serverY + 30, '#7c6af2')
  }

  // Step 3: ACK (client → server)
  if (step >= 3) {
    const p = step === 3 ? progress : 1
    drawArrow(CX1, clientY + 5, CX2, serverY + 5, 'ACK\nseq=x+1,ack=y+1', '#22C55E', p)
    if (p >= 0.95) {
      drawStateBox('ESTABLISHED ✓', CX1, clientY + 30, '#22C55E')
      drawStateBox('ESTABLISHED ✓', CX2, serverY + 30, '#22C55E')
      ctx.fillStyle = '#22C55E'
      ctx.font = '700 16px -apple-system, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('✅ TCP 连接建立成功', (CX1 + CX2) / 2, midY)
    }
  }
}

function animate() {
  progress += 0.02 * animSpeed.value
  if (progress >= 1) {
    progress = 0
    step++
    if (isFlood ? step > 1 : step > 3) {
      isAnimating.value = false
      currentStep.value = isFlood ? 1 : 3
      drawScene()
      return
    }
  }
  currentStep.value = step
  drawScene()
  animationId = requestAnimationFrame(animate)
}

function startAnimation() {
  if (isAnimating.value) return
  isFlood = props.mode === 'synflood'
  step = 0
  progress = 0
  isAnimating.value = true
  currentStep.value = 0
  animate()
}

function resetAnimation() {
  if (animationId) cancelAnimationFrame(animationId)
  animationId = null
  isAnimating.value = false
  step = 0
  progress = 0
  currentStep.value = 0
  isFlood = false
  drawScene()
}

function onResize() { initCanvas(); drawScene() }

onMounted(() => {
  initCanvas()
  drawScene()
  // Auto-start after 500ms
  setTimeout(startAnimation, 500)
  window.addEventListener('resize', onResize)
})

onUnmounted(() => {
  if (animationId) cancelAnimationFrame(animationId)
  window.removeEventListener('resize', onResize)
})
</script>

<template>
  <div class="tcp-animation-wrapper">
    <div class="tcp-controls">
      <div class="tcp-title">
        {{ mode === 'synflood' ? '⚠️ SYN Flood 攻击模拟' : 'TCP 三次握手过程' }}
      </div>
      <div class="tcp-step-info" v-if="currentStep > 0 && mode !== 'synflood'">
        <span :style="{color: 'var(--accent-primary)'}">① SYN</span>
        <span :style="{color: 'var(--accent-secondary)'}">② SYN+ACK</span>
        <span :style="{color: 'var(--accent-success)'}">③ ACK</span>
        <span style="margin-left:8px;color:var(--text-secondary);font-size:12px;">
          当前步骤: {{ ['','①','②','③'][currentStep] || '完成' }}
        </span>
      </div>
      <div class="tcp-buttons">
        <button class="rag-btn tcp-btn" @click="startAnimation">▶ 播放</button>
        <button class="rag-btn tcp-btn tcp-btn-ghost" @click="resetAnimation">⟲ 重置</button>
        <select v-model="animSpeed" class="rag-select tcp-select">
          <option :value="0.5">0.5x</option>
          <option :value="1">1x</option>
          <option :value="2">2x</option>
        </select>
      </div>
    </div>
    <canvas ref="canvasRef" class="tcp-canvas"></canvas>
  </div>
</template>

<style scoped>
.tcp-animation-wrapper {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius:var(--radius-md);
  overflow: hidden;
  backdrop-filter: blur(12px);
}
.tcp-btn { padding:0.3125rem 1rem; font-size:0.75rem; }
.tcp-btn-ghost { background: var(--bg-secondary); color: var(--text-primary); border: 1px solid var(--border-color); }
.tcp-select { padding:0.3125rem 0.5rem; font-size:0.75rem; width:auto; }

.tcp-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding:0.75rem 1rem;
  border-bottom: 1px solid var(--border-light);
  flex-wrap: wrap;
  gap:0.5rem;
}
.tcp-title {
  font-size:0.9375rem;
  font-weight: 700;
  color: var(--text-primary);
}
.tcp-step-info {
  display: flex;
  gap:0.75rem;
  font-size:0.8125rem;
  font-weight: 600;
}
.tcp-buttons {
  display: flex;
  gap:0.375rem;
  align-items: center;
}
.tcp-canvas {
  width:100%;
  height:23.75rem;
  display: block;
  cursor: pointer;
}
</style>
