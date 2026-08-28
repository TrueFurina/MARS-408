<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useStudyStore } from '@/stores/studyStore'
import { icons } from '@/components/icons'
import EmptyState from '@/components/EmptyState.vue'
import ForceGraph from '@/components/ForceGraph.vue'
import { api } from '@/utils/api'

interface GraphNode {
  id: string
  label: string
  group: number
  x?: number
  y?: number
  vx?: number
  vy?: number
  radius?: number
}
interface GraphEdge {
  source: string
  target: string
}

const store = useStudyStore()
const forceGraphRef = ref<InstanceType<typeof ForceGraph> | null>(null)

const currentSubject = ref('all')
const allGraphData = ref<{ nodes: GraphNode[]; edges: GraphEdge[] }>({ nodes: [], edges: [] })
const nodes = ref<GraphNode[]>([])
const edges = ref<GraphEdge[]>([])
const loading = ref(true)
const error = ref('')

const SUBJECT_TOKENS: string[] = [
  '--subject-cn',  // 计网 — 蓝
  '--subject-ds',  // 数据结构 — 紫
  '--subject-co',  // 计组 — 青
  '--subject-os',  // 操作系统 — 粉
]

/** Canvas 取色：把语义令牌解析为实际色值（双主题安全，避免裸 hex） */
function resolveToken(name: string): string {
  if (typeof window === 'undefined') return '#7c6af2'
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || '#7c6af2'
}

function groupColor(g: number): string {
  // groups 1-7 计网, 8-14 数据结构, 15-21 计组, 22-26 操作系统
  if (g <= 7) return SUBJECT_TOKENS[0] || '--subject-cn'
  if (g <= 14) return SUBJECT_TOKENS[1] || '--subject-ds'
  if (g <= 21) return SUBJECT_TOKENS[2] || '--subject-co'
  return SUBJECT_TOKENS[3] || '--subject-os'
}

function groupToLabel(g: number): string {
  const keys = Object.keys(store.subjects)
  const key = keys[g - 1]
  return key ? store.subjects[key]?.name || `分组 ${g}` : `分组 ${g}`
}

// 图谱组点击 → 跳转该科目
function onGroupClick(group: number) {
  const keys = Object.keys(store.subjects)
  const subjectKey = keys[group - 1]
  if (subjectKey && store.subjects[subjectKey]) {
    currentSubject.value = subjectKey
    applyFilter()
  }
}

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const data = await store.fetchKnowledgeGraph('all')
    if (!data || !data.nodes || !data.edges) {
      throw new Error('知识图谱数据为空')
    }
    allGraphData.value = data
    applyFilter()
  } catch (e: any) {
    error.value = e?.message || '加载知识图谱失败，请检查后端服务是否运行'
    console.warn('KnowledgeGraph load error:', e)
  } finally {
    loading.value = false
  }
}

function applyFilter() {
  if (currentSubject.value === 'all') {
    const allNodes = allGraphData.value.nodes.map(n => ({ ...n }))
    const allEdges = allGraphData.value.edges.map(e => ({ ...e }))
    // 全量图（>80节点）按 group 聚合展示，避免杂乱
    if (allNodes.length > 80) {
      const groupMap = new Map<number, { group: number; ids: string[]; label: string }>()
      allNodes.forEach(n => {
        const g = n.group || 0
        if (!groupMap.has(g)) groupMap.set(g, { group: g, ids: [], label: groupToLabel(g) })
        groupMap.get(g)!.ids.push(n.id)
      })
      const groupNodes = Array.from(groupMap.values()).map((g, i) => ({
        id: `group-${g.group}`,
        label: `${g.label} (${g.ids.length})`,
        group: g.group,
        x: 0, y: 0, vx: 0, vy: 0,
        radius: 18 + g.ids.length * 0.3,
        _isGroup: true,
        _memberIds: g.ids,
      }))
      // group 之间保留原跨组边
      const groupEdges = allEdges.filter(e => {
        const srcGroup = allNodes.find(n => n.id === e.source)?.group
        const tgtGroup = allNodes.find(n => n.id === e.target)?.group
        return srcGroup && tgtGroup && srcGroup !== tgtGroup
      }).map(e => ({ source: `group-${allNodes.find(n => n.id === e.source)?.group}`, target: `group-${allNodes.find(n => n.id === e.target)?.group}` }))
      // 去重
      const uniqueEdges: typeof groupEdges = []
      groupEdges.forEach(e => {
        const key = [e.source, e.target].sort().join('--')
        if (!uniqueEdges.some(u => [u.source, u.target].sort().join('--') === key)) uniqueEdges.push(e)
      })
      nodes.value = groupNodes
      edges.value = uniqueEdges
    } else {
      nodes.value = allNodes
      edges.value = allEdges
    }
  } else {
    const subjectKeys = Object.keys(store.subjects)
    const groupIdx = subjectKeys.indexOf(currentSubject.value)
    const targetGroup = groupIdx >= 0 ? groupIdx + 1 : -1
    if (targetGroup < 0) { nodes.value = []; edges.value = []; return }
    nodes.value = allGraphData.value.nodes.filter(n => n.group === targetGroup).map(n => ({ ...n }))
    const nodeIds = new Set(nodes.value.map(n => n.id))
    edges.value = allGraphData.value.edges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target)).map(e => ({ ...e }))
  }
}

function zoomIn() { forceGraphRef.value?.zoomIn() }
function zoomOut() { forceGraphRef.value?.zoomOut() }
function resetZoom() { forceGraphRef.value?.resetZoom() }

onMounted(async () => {
  await loadData()
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：知识图谱页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞知识图谱页 */ }
}

watch(currentSubject, () => {
  if (allGraphData.value.nodes.length > 0) {
    applyFilter()
  }
})
</script>

<template>
  <div class="page-section">
    <div class="section-title">知识图谱</div>
    <div class="section-desc">408考研四科知识点之间的关联关系可视化</div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <div class="rag-config" style="justify-content:center;">
      <select class="rag-select" v-model="currentSubject" :disabled="loading">
        <option value="all">所有章节</option>
        <option v-for="(info, id) in store.subjects" :key="id" :value="id">{{ info.name }}</option>
      </select>
      <button v-if="currentSubject !== 'all'" class="back-all-btn" @click="currentSubject = 'all'">
        ← 返回全量
      </button>
      <div class="kg-controls">
        <button class="kg-btn" @click="zoomIn" title="放大"><span class="kg-ic" v-html="icons.zoomIn"></span></button>
        <button class="kg-btn" @click="zoomOut" title="缩小"><span class="kg-ic" v-html="icons.zoomOut"></span></button>
        <button class="kg-btn" @click="resetZoom" title="重置"><span class="kg-ic" v-html="icons.refresh"></span></button>
      </div>
    </div>

    <!-- 加载态 -->
    <div v-if="loading" class="empty-state">
      <div class="skeleton" style="width:200px;height:200px;border-radius:50%;margin-bottom:16px;"></div>
      <div class="empty-title">加载知识图谱中...</div>
    </div>

    <!-- 错误态 -->
    <EmptyState
      v-else-if="error"
      :icon="icons.warning"
      title="加载失败"
      :description="error"
    >
      <template #action>
        <button class="engine-btn" @click="loadData">重新加载</button>
      </template>
    </EmptyState>

    <!-- 空数据 -->
    <EmptyState
      v-else-if="!nodes.length"
      :icon="icons.knowledge"
      title="暂无知识图谱数据"
      description="请检查后端是否已启动，或种子数据是否导入"
    />

    <!-- 图谱渲染 -->
    <div v-else class="graph-container">
      <ForceGraph
        ref="forceGraphRef"
        :nodes="nodes"
        :edges="edges"
        :subject-tokens="SUBJECT_TOKENS"
        :group-to-label="groupToLabel"
        @group-click="onGroupClick"
      />
    </div>
  </div>
</template>

<style scoped>
.back-all-btn {
  padding:0.4375rem 1rem;
  border-radius:var(--radius-full);
  border: 1px solid var(--border-color);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  color: var(--accent-primary);
  font-size:0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
  white-space: nowrap;
}
.back-all-btn:hover {
  border-color: var(--accent-primary);
  background: var(--accent-primary-10);
  transform: translateY(-1px);
}
.kg-controls {
  display: flex;
  gap: 0.5rem;
}
.kg-btn {
  width: 2.25rem;
  height: 2.25rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
}
.kg-btn:hover {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background: var(--accent-primary-10);
}
.kg-ic {
  width: 1.125rem;
  height: 1.125rem;
  display: inline-flex;
}
.kg-ic :deep(svg) {
  width: 100%;
  height: 100%;
}

/* ── 多角色2：移动端响应式适配 ── */
@media (max-width: 768px) {
  .graph-container { min-height: 50vh; }
  .kg-controls { gap: 0.375rem; }
  .kg-btn { width: 2rem; height: 2rem; }
  .kg-header { flex-direction: column; align-items: stretch; gap: 0.5rem; }
}
@media (max-width: 480px) {
  .graph-container { min-height: 45vh; }
  .back-all-btn { padding: 0.375rem 0.75rem; font-size: 0.75rem; }
}
</style>
