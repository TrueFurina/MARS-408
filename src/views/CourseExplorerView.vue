<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '@/utils/api'
import KnowledgeGraph from '@/components/KnowledgeGraph.vue'

// ── 四科「专属查看器」定义（真实映射后端 KNOWLEDGE_GRAPH 节点 id 前缀）──
const COURSES = [
  { key: 'ds', label: '数据结构', prefix: 'ds_', color: '#06b6d4', icon: '🧮', tagline: '线性表 · 树 · 图 · 查找 · 排序' },
  { key: 'co', label: '计算机组成原理', prefix: 'co_', color: '#f59e0b', icon: '⚙️', tagline: '数据表示 · 存储 · CPU · 总线 · I/O' },
  { key: 'os', label: '操作系统', prefix: 'os_', color: '#22c55e', icon: '🖥️', tagline: '进程 · 调度 · 内存 · 文件 · I/O' },
  { key: 'cn', label: '计算机网络', prefix: '', color: '#7c6af2', icon: '🌐', tagline: '体系结构 · 各层协议 · 安全' },
] as const

type CourseKey = (typeof COURSES)[number]['key']

const activeCourse = ref<CourseKey>('ds')
const loading = ref(false)
const error = ref('')
const subjects = ref<Record<string, { name: string; chapters: string[] }>>({})
const graph = ref<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] })
const viewMode = ref<'graph' | 'outline' | 'mindmap' | 'map'>('graph')

const viewModes = [
  { value: 'graph', label: '关系图谱', icon: '🕸️' },
  { value: 'mindmap', label: '思维导图', icon: '🧠' },
  { value: 'map', label: '学习地图', icon: '🗺️' },
  { value: 'outline', label: '大纲', icon: '📋' },
] as const

const activeCourseMeta = computed(() => COURSES.find((c) => c.key === activeCourse.value)!)

function matchId(id: string, course: CourseKey): boolean {
  if (course === 'cn') return !id.startsWith('ds_') && !id.startsWith('co_') && !id.startsWith('os_')
  const prefix = COURSES.find((c) => c.key === course)!.prefix
  return id.startsWith(prefix)
}

const courseSubjects = computed(() => {
  const out: { key: string; name: string; chapters: string[] }[] = []
  for (const [k, v] of Object.entries(subjects.value)) {
    if (matchId(k, activeCourse.value)) out.push({ key: k, name: v.name, chapters: v.chapters || [] })
  }
  return out
})

// 去重（后端图谱存在同 id 重复节点，渲染前合并）
function dedupeNodes(nodes: any[]): any[] {
  const seen = new Set<string>()
  const out: any[] = []
  for (const n of nodes) {
    if (seen.has(n.id)) continue
    seen.add(n.id)
    out.push(n)
  }
  return out
}

const courseNodes = computed(() => dedupeNodes(graph.value.nodes.filter((n) => matchId(n.id, activeCourse.value))))
const courseNodeIds = computed(() => new Set(courseNodes.value.map((n) => n.id)))
const courseEdges = computed(() =>
  graph.value.edges.filter((e) => courseNodeIds.value.has(e.source) && courseNodeIds.value.has(e.target)),
)

const totalChapters = computed(() => courseSubjects.value.reduce((s, c) => s + c.chapters.length, 0))

// 每章知识点密度（真实：按节点 id 前缀归并到章节）
function densityFor(key: string): number {
  let n = 0
  for (const id of courseNodeIds.value) {
    if (id === key || id.startsWith(key + '_')) n++
  }
  return n
}
const maxDensity = computed(() => {
  let m = 1
  for (const s of courseSubjects.value) m = Math.max(m, densityFor(s.key))
  return m
})

const stats = computed(() => ({
  chapters: totalChapters.value,
  subjects: courseSubjects.value.length,
  nodes: courseNodes.value.length,
  edges: courseEdges.value.length,
}))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res: any = await api.get('/subjects')
    subjects.value = res.subjects || {}
    graph.value = res.knowledge_graph || { nodes: [], edges: [] }
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page-section course-explorer" :style="{ '--course-color': activeCourseMeta.color }">
    <!-- 顶部：四科切换器 -->
    <div class="ce-course-switch">
      <button
        v-for="c in COURSES"
        :key="c.key"
        class="ce-course-pill"
        :class="{ active: activeCourse === c.key }"
        :style="{ '--pill-color': c.color }"
        @click="activeCourse = c.key"
      >
        <span class="ce-pill-icon">{{ c.icon }}</span>
        <span class="ce-pill-text">
          <span class="ce-pill-label">{{ c.label }}</span>
          <span class="ce-pill-tag">{{ c.tagline }}</span>
        </span>
      </button>
    </div>

    <!-- 课程头 -->
    <div class="ce-hero">
      <div class="ce-hero-icon">{{ activeCourseMeta.icon }}</div>
      <div class="ce-hero-body">
        <h1 class="ce-hero-title">{{ activeCourseMeta.label }}<span class="ce-hero-badge">专属知识查看器</span></h1>
        <p class="ce-hero-sub">{{ activeCourseMeta.tagline }} · 基于真实知识图谱与章节结构渲染</p>
      </div>
      <div class="ce-stat-row">
        <div class="ce-stat"><span class="ce-stat-num">{{ stats.subjects }}</span><span class="ce-stat-cap">知识模块</span></div>
        <div class="ce-stat"><span class="ce-stat-num">{{ stats.chapters }}</span><span class="ce-stat-cap">细分章节</span></div>
        <div class="ce-stat"><span class="ce-stat-num">{{ stats.nodes }}</span><span class="ce-stat-cap">知识点</span></div>
        <div class="ce-stat"><span class="ce-stat-num">{{ stats.edges }}</span><span class="ce-stat-cap">关联关系</span></div>
      </div>
    </div>

    <div v-if="loading" class="ce-loading">
      <span class="loading-spinner-sm"></span> 正在加载真实知识图谱…
    </div>
    <div v-else-if="error" class="ce-error">{{ error }}</div>

    <div v-else class="ce-grid">
      <!-- 左：章节路线图 -->
      <section class="ce-panel ce-roadmap">
        <div class="ce-panel-head">
          <span class="ce-panel-title">📚 章节路线图</span>
          <span class="ce-panel-hint">密度 = 该章知识点数量（真实）</span>
        </div>
        <div class="ce-chapter-list">
          <div v-for="s in courseSubjects" :key="s.key" class="ce-chapter">
            <div class="ce-chapter-head">
              <span class="ce-chapter-name">{{ s.name }}</span>
              <span class="ce-chapter-count">{{ densityFor(s.key) }} 点</span>
            </div>
            <div class="ce-density"><div class="ce-density-fill" :style="{ width: (densityFor(s.key) / maxDensity * 100) + '%' }"></div></div>
            <div class="ce-chapter-chips">
              <span v-for="ch in s.chapters" :key="ch" class="ce-chip">{{ ch }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 右：知识图谱 -->
      <section class="ce-panel ce-graph-panel">
        <div class="ce-panel-head">
          <span class="ce-panel-title">🕸️ {{ activeCourseMeta.label }} 知识图谱</span>
          <div class="view-mode-tabs">
            <button
              v-for="m in viewModes"
              :key="m.value"
              class="view-mode-tab"
              :class="{ active: viewMode === m.value }"
              @click="viewMode = m.value"
            >{{ m.icon }} {{ m.label }}</button>
          </div>
        </div>
        <div class="ce-graph-wrap">
          <KnowledgeGraph
            :nodes="courseNodes"
            :edges="courseEdges"
            :width="760"
            :height="560"
            :view-mode="viewMode"
            :show-search="true"
          />
          <div v-if="!courseNodes.length" class="ce-graph-empty">该科目暂无图谱数据</div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.course-explorer { --course-color: #7c6af2; }

/* 课程切换器 */
.ce-course-switch { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }
@media (max-width: 900px) { .ce-course-switch { grid-template-columns: repeat(2, 1fr); } }
.ce-course-pill {
  --pill-color: #7c6af2;
  display: flex; align-items: center; gap: 12px;
  padding: 14px 16px; border-radius: 14px; cursor: pointer; text-align: left;
  background: var(--color-surface); border: 1px solid var(--color-border);
  transition: all 0.18s ease; color: var(--color-text);
}
.ce-course-pill:hover { border-color: var(--pill-color); transform: translateY(-2px); }
.ce-course-pill.active {
  border-color: var(--pill-color);
  box-shadow: 0 0 0 1px var(--pill-color), 0 8px 24px -8px var(--pill-color);
  background: color-mix(in srgb, var(--pill-color) 12%, var(--color-surface));
}
.ce-pill-icon { font-size: 26px; line-height: 1; }
.ce-pill-text { display: flex; flex-direction: column; min-width: 0; }
.ce-pill-label { font-size: 14px; font-weight: 700; color: var(--color-text); }
.ce-pill-tag { font-size: 11px; color: var(--color-text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Hero */
.ce-hero {
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
  padding: 20px 22px; border-radius: 16px; margin-bottom: 18px;
  background: linear-gradient(120deg, color-mix(in srgb, var(--course-color) 16%, var(--color-surface)), var(--color-surface));
  border: 1px solid var(--color-border);
}
.ce-hero-icon {
  font-size: 40px; width: 64px; height: 64px; display: grid; place-items: center;
  border-radius: 16px; background: color-mix(in srgb, var(--course-color) 20%, transparent);
  border: 1px solid color-mix(in srgb, var(--course-color) 40%, transparent);
}
.ce-hero-body { flex: 1; min-width: 220px; }
.ce-hero-title { font-size: 22px; font-weight: 800; margin: 0; display: flex; align-items: center; gap: 12px; color: var(--color-text); }
.ce-hero-badge { font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px; color: #fff; background: var(--course-color); }
.ce-hero-sub { margin: 6px 0 0; font-size: 13px; color: var(--color-text-2); }
.ce-stat-row { display: flex; gap: 22px; }
.ce-stat { text-align: center; }
.ce-stat-num { display: block; font-size: 24px; font-weight: 800; color: var(--course-color); font-variant-numeric: tabular-nums; }
.ce-stat-cap { font-size: 11px; color: var(--color-text-3); }

/* Grid */
.ce-grid { display: grid; grid-template-columns: 380px 1fr; gap: 18px; align-items: start; }
@media (max-width: 1100px) { .ce-grid { grid-template-columns: 1fr; } }

.ce-panel { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 16px; padding: 16px; }
.ce-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.ce-panel-title { font-size: 15px; font-weight: 700; color: var(--color-text); }
.ce-panel-hint { font-size: 11px; color: var(--color-text-3); }

/* 章节 */
.ce-chapter-list { display: flex; flex-direction: column; gap: 12px; max-height: 620px; overflow: auto; padding-right: 4px; }
.ce-chapter { padding: 12px; border-radius: 12px; background: var(--color-surface-2); border: 1px solid var(--color-border); }
.ce-chapter-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.ce-chapter-name { font-size: 14px; font-weight: 600; color: var(--color-text); }
.ce-chapter-count { font-size: 11px; font-weight: 700; color: var(--course-color); }
.ce-density { height: 6px; border-radius: 4px; background: var(--color-surface-hover); overflow: hidden; margin-bottom: 8px; }
.ce-density-fill { height: 100%; border-radius: 4px; background: var(--course-color); transition: width 0.5s ease; }
.ce-chapter-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ce-chip { font-size: 11px; padding: 3px 8px; border-radius: 6px; background: var(--color-elevated); color: var(--color-text-2); border: 1px solid var(--color-border); }

/* 图谱 */
.ce-graph-panel { min-width: 0; }
.ce-graph-wrap { position: relative; border-radius: 12px; overflow: hidden; background: var(--color-canvas, var(--color-surface-2)); }
.ce-graph-empty { position: absolute; inset: 0; display: grid; place-items: center; color: var(--color-text-3); font-size: 14px; }

/* tabs */
.view-mode-tabs { display: flex; gap: 4px; background: var(--color-surface-2); border-radius: 10px; padding: 3px; }
.view-mode-tab { padding: 6px 12px; border: none; border-radius: 8px; background: transparent; color: var(--color-text-2); font-size: 12px; font-weight: 500; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
.view-mode-tab:hover { color: var(--color-text); }
.view-mode-tab.active { background: var(--color-elevated); color: var(--color-text); box-shadow: 0 1px 4px rgba(0,0,0,0.2); }

.ce-loading, .ce-error { padding: 40px; text-align: center; color: var(--color-text-2); }
.ce-error { color: var(--accent-danger); }

.loading-spinner-sm { display: inline-block; width: 14px; height: 14px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff; animation: spin 0.6s linear infinite; margin-right: 4px; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
