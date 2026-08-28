<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/utils/api'
import KnowledgeGraph from '@/components/KnowledgeGraph.vue'
import KnowledgeGraph3D from '@/components/KnowledgeGraph3D.vue'

const router = useRouter()

const inputText = ref('')
const subject = ref('computer_network')
const loading = ref(false)
const error = ref('')
const graphData = ref<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] })
const stats = ref<any>(null)
const savedGraphs = ref<any[]>([])
const filterType = ref('')
const viewMode = ref<'graph' | 'outline' | 'mindmap' | 'map' | 'sphere'>('graph')

const masteryStats = computed(() => {
  const nodes = graphData.value.nodes
  const mastered = nodes.filter((n: any) => n.mastery === 'mastered').length
  const weak = nodes.filter((n: any) => n.mastery === 'weak').length
  const unlearned = nodes.filter((n: any) => n.mastery === 'unlearned').length
  // L1/L2/L3 三层学情记忆薄弱点（后端 weak_memory 打标，记忆驱动高亮）
  const memoryWeak = nodes.filter((n: any) => n.weak_memory === true).length
  const total = mastered + weak + unlearned
  return { total, mastered, weak, unlearned, memoryWeak }
})

const viewModes: { value: 'graph' | 'outline' | 'mindmap' | 'map' | 'sphere'; label: string; icon: string }[] = [
  { value: 'graph', label: '图谱模式', icon: '🕸️' },
  { value: 'outline', label: '大纲模式', icon: '📋' },
  { value: 'mindmap', label: '思维导图', icon: '🧠' },
  { value: 'map', label: '学习地图', icon: '🗺️' },
  { value: 'sphere', label: '3D 球体', icon: '🌐' },
]

const subjects = [
  { value: 'computer_network', label: '计算机网络' },
  { value: 'data_structures', label: '数据结构' },
  { value: 'computer_organization', label: '计算机组成原理' },
  { value: 'operating_system', label: '操作系统' },
]

async function extractGraph() {
  if (!inputText.value.trim()) return
  loading.value = true
  error.value = ''
  try {
    const res: any = await api.post('/knowledge-graph/extract', {
      text: inputText.value,
      subject: subject.value,
      enhance: true,
    })
    graphData.value = res.vis || { nodes: [], edges: [] }
    stats.value = res.stats || null
  } catch (e: any) {
    error.value = e?.message || '提取失败'
  } finally {
    loading.value = false
  }
}

async function loadSavedGraphs() {
  try {
    const res: any = await api.get('/knowledge-graph/list')
    savedGraphs.value = res.graphs || []
  } catch { /* ignore */ }
}

async function loadGraph(id: string) {
  loading.value = true
  error.value = ''
  try {
    const res: any = await api.get(`/knowledge-graph/list`)
    // 从列表中找到对应的图
    const graph = savedGraphs.value.find(g => g.id === id)
    if (graph) {
      // 这里简化处理，实际应该从文件加载
      inputText.value = `加载图谱: ${graph.subject} (${graph.entity_count} 实体)`
    }
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function clearGraph() {
  graphData.value = { nodes: [], edges: [] }
  stats.value = null
  inputText.value = ''
}

onMounted(() => {
  loadSavedGraphs()
})
</script>

<template>
  <div class="page-section">
    <div class="section-header">
      <div class="section-title-group">
        <div>
          <div class="section-title">🕸️ AI 知识图谱</div>
          <div class="section-desc">从课程文本自动抽取知识点实体和关系，构建可视化知识图谱</div>
        </div>
      </div>
      <div class="section-actions">
        <button class="btn btn-ghost" @click="clearGraph" :disabled="!graphData.nodes.length">清除</button>
      </div>
    </div>

    <div class="kg-layout">
      <!-- 左侧：输入区 -->
      <div class="kg-input-panel">
        <div class="form-group">
          <label class="form-label">科目</label>
          <select v-model="subject" class="form-select">
            <option v-for="s in subjects" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">课程文本</label>
          <textarea
            v-model="inputText"
            class="form-textarea code-textarea"
            placeholder="粘贴课程内容、教材章节或知识点描述..."
            rows="12"
          ></textarea>
        </div>

        <button class="btn btn-primary" @click="extractGraph" :disabled="loading || !inputText.trim()" style="width:100%;">
          <span v-if="loading" class="loading-spinner-sm"></span>
          {{ loading ? '提取中...' : '🕸️ 提取知识图谱' }}
        </button>

        <div v-if="error" class="form-error" style="margin-top:8px;">{{ error }}</div>

        <!-- 统计信息 -->
        <div v-if="stats" class="kg-stats">
          <div class="kg-stats-title">📊 图谱统计</div>
          <div class="kg-stats-grid">
            <div class="kg-stat">
              <span class="stat-value">{{ stats.entity_count }}</span>
              <span class="stat-label">实体</span>
            </div>
            <div class="kg-stat">
              <span class="stat-value">{{ stats.relation_count }}</span>
              <span class="stat-label">关系</span>
            </div>
          </div>
          <!-- 掌握度统计 -->
          <div class="kg-mastery-stats" v-if="masteryStats.total > 0">
            <div class="kg-stats-title" style="margin-top:10px;">📈 掌握度分布</div>
            <div class="kg-mastery-bar">
              <div class="kg-mastery-seg" :style="{ flex: masteryStats.mastered || 1, background: '#22c55e' }" :title="'已掌握: ' + masteryStats.mastered"></div>
              <div class="kg-mastery-seg" :style="{ flex: masteryStats.weak || 1, background: '#f59e0b' }" :title="'薄弱: ' + masteryStats.weak"></div>
              <div class="kg-mastery-seg" :style="{ flex: masteryStats.unlearned || 1, background: '#ef4444' }" :title="'未学: ' + masteryStats.unlearned"></div>
            </div>
            <div class="kg-mastery-labels">
              <span>✅ {{ masteryStats.mastered }} 已掌握</span>
              <span>⚠️ {{ masteryStats.weak }} 薄弱</span>
              <span>📕 {{ masteryStats.unlearned }} 未学</span>
              <span v-if="masteryStats.memoryWeak" style="color:var(--accent-primary);">🧠 {{ masteryStats.memoryWeak }} 记忆薄弱</span>
            </div>
          </div>
          <div v-if="stats.entity_types" class="kg-type-list">
            <div v-for="(count, type) in stats.entity_types" :key="type" class="kg-type-item">
              <span class="kg-type-label">{{ type }}</span>
              <span class="kg-type-count">{{ count }}</span>
            </div>
          </div>
        </div>

        <!-- 已保存图谱 -->
        <div v-if="savedGraphs.length" class="kg-saved">
          <div class="kg-stats-title">📁 已保存图谱</div>
          <div v-for="g in savedGraphs.slice(0, 5)" :key="g.id" class="kg-saved-item" role="button" tabindex="0" :aria-label="'加载图谱 ' + g.subject" @click="loadGraph(g.id)" @keydown.enter="loadGraph(g.id)" @keydown.space.prevent="loadGraph(g.id)">
            <span class="kg-saved-subject">{{ g.subject }}</span>
            <span class="kg-saved-count">{{ g.entity_count }} 实体</span>
          </div>
        </div>
      </div>

      <!-- 右侧：可视化 -->
      <div class="kg-vis-panel">
        <div class="panel-title-row">
          <div class="panel-title">🕸️ 知识图谱可视化</div>
          <div class="view-mode-tabs">
            <button v-for="m in viewModes" :key="m.value" class="view-mode-tab" :class="{ active: viewMode === m.value }" @click="viewMode = m.value">
              {{ m.icon }} {{ m.label }}
            </button>
          </div>
        </div>
        <KnowledgeGraph
          v-if="viewMode !== 'sphere'"
          :nodes="graphData.nodes"
          :edges="graphData.edges"
          :width="800"
          :height="600"
          :view-mode="viewMode"
          :show-search="true"
        />
        <KnowledgeGraph3D
          v-if="viewMode === 'sphere'"
          :nodes="graphData.nodes"
          :edges="graphData.edges"
          :width="800"
          :height="600"
        />
        <div v-if="graphData.nodes.length" class="kg-legend">
          <div v-for="(color, type) in {'concept':'#7c6af2','chapter':'#3b82f6','algorithm':'#06b6d4','protocol':'#22c55e','structure':'#f59e0b'}" :key="type" class="kg-legend-item">
            <span class="kg-legend-dot" :style="{ background: color }"></span>
            <span class="kg-legend-label">{{ type }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kg-layout { display: grid; grid-template-columns: 380px 1fr; gap: 20px; margin-top: 16px; }
@media (max-width: 900px) { .kg-layout { grid-template-columns: 1fr; } }
.kg-input-panel { min-width: 0; }
.kg-vis-panel { min-width: 0; }

.form-group { margin-bottom: 12px; }
.form-label { display: block; font-size: 13px; font-weight: 500; color: var(--color-text-2); margin-bottom: 4px; }
.form-select, .form-textarea { width: 100%; padding: 10px 12px; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface-2); color: var(--color-text); font-size: 14px; }
.form-select:focus, .form-textarea:focus { outline: none; border-color: var(--color-border-focus); }
.form-textarea { resize: vertical; min-height: 200px; }
.code-textarea { font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; font-size: 13px; line-height: 1.5; }
.form-error { padding: 10px 12px; background: rgba(239,68,68,0.1); color: var(--accent-danger); border-radius: 8px; font-size: 13px; }
.panel-title { font-size: 16px; font-weight: 600; margin-bottom: 12px; color: var(--color-text); }
.panel-title-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.panel-title-row .panel-title { margin-bottom: 0; }
.view-mode-tabs { display: flex; gap: 4px; background: var(--color-surface-2); border-radius: 10px; padding: 3px; }
.view-mode-tab { padding: 6px 14px; border: none; border-radius: 8px; background: transparent; color: var(--color-text-2); font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
.view-mode-tab:hover { color: var(--color-text); }
.view-mode-tab.active { background: var(--color-elevated); color: var(--color-text); box-shadow: 0 1px 4px rgba(0,0,0,0.2); }

.kg-stats { margin-top: 16px; padding: 14px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 10px; }
.kg-stats-title { font-size: 13px; font-weight: 600; color: var(--color-text-2); margin-bottom: 10px; }
.kg-stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }
.kg-stat { text-align: center; padding: 10px; background: var(--color-surface-2); border-radius: 8px; }
.kg-stat .stat-value { display: block; font-size: 22px; font-weight: 700; color: var(--accent); }
.kg-stat .stat-label { display: block; font-size: 11px; color: var(--color-text-3); margin-top: 2px; }
.kg-type-list { display: flex; flex-wrap: wrap; gap: 6px; }
.kg-type-item { display: flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; background: var(--color-surface-2); font-size: 12px; }
.kg-type-label { color: var(--color-text-2); }
.kg-type-count { color: var(--accent); font-weight: 600; }

/* 掌握度分布 */
.kg-mastery-stats { margin-top: 8px; }
.kg-mastery-bar { display: flex; height: 8px; border-radius: 4px; overflow: hidden; margin: 6px 0; }
.kg-mastery-seg { transition: flex 0.5s ease; }
.kg-mastery-labels { display: flex; justify-content: space-between; font-size: 11px; color: var(--color-text-3); }

.kg-saved { margin-top: 16px; padding: 14px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 10px; }
.kg-saved-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-radius: 6px; cursor: pointer; transition: background 0.15s; }
.kg-saved-item:hover { background: var(--color-surface-hover); }
.kg-saved-subject { font-size: 13px; color: var(--color-text); }
.kg-saved-count { font-size: 11px; color: var(--color-text-3); }

.kg-legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; padding: 10px 14px; background: var(--color-surface-2); border-radius: 8px; }
.kg-legend-item { display: flex; align-items: center; gap: 6px; }
.kg-legend-dot { width: 10px; height: 10px; border-radius: 50%; }
.kg-legend-label { font-size: 11px; color: var(--color-text-2); }

/* 加载动画 */
.loading-spinner-sm { display: inline-block; width: 14px; height: 14px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff; animation: spin 0.6s linear infinite; margin-right: 4px; vertical-align: middle; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>