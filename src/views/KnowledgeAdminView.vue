<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useStudyStore } from '@/stores/studyStore'
import { getAuthHeaders } from '@/utils/api'
import { icons } from '@/components/icons'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'

const store = useStudyStore()
const API_BASE = ''

// ── 状态 ──
const statusInfo = ref({ status: '', vector_db: '', collection_size: 0, llm_available: false })
const stats = ref({ total_docs: 0, by_subject: {} as Record<string, number>, by_type: {} as Record<string, number> })
const documents = ref<any[]>([])
const totalDocs = ref(0)
const loading = ref(false)
const loadError = ref('')
const searchQuery = ref('')
const filterSubject = ref('')
const page = ref(1)
const pageSize = 10

// ── 添加文档 ──
const showAddForm = ref(false)
const newContent = ref('')
const newSubject = ref('math')
const newChapter = ref('')
const newType = ref('knowledge_point')

// ── 选中删除 ──
const selectedIds = ref<Set<string>>(new Set())
const selectAll = ref(false)
const reindexing = ref(false)

// ── 文件上传 + 预览审查 ──
const showUploadForm = ref(false)
const uploadFile = ref<File | null>(null)
const uploadSubject = ref('math')
const uploadChapter = ref('')
const uploading = ref(false)

const previewResult = ref<null | {
  filename: string
  total_chars: number
  items: PreviewItem[]
  default_subject: string
  default_chapter: string
}>(null)

interface PreviewItem {
  id: string
  content: string
  detected_type: string
  detected_subject?: string
  subject: string
  chapter: string
  source: string
  _selected?: boolean
  _type?: string
}

async function previewFile() {
  if (!uploadFile.value) return
  uploading.value = true
  previewResult.value = null
  try {
    const form = new FormData()
    form.append('file', uploadFile.value)
    form.append('subject', uploadSubject.value)
    form.append('chapter', uploadChapter.value)
    const r = await fetch(`${API_BASE}/api/knowledge/preview`, { method: 'POST', headers: getAuthHeaders(), body: form })
    const data = await r.json()
    if (r.ok) {
      data.items = data.items.map((item: PreviewItem) => ({
        ...item,
        _selected: true,
        _type: item.detected_type,
      }))
      previewResult.value = data
    } else {
      alert(`❌ ${data.detail || '解析失败'}`)
    }
  } catch {
    alert('❌ 解析失败，请检查后端是否运行')
  } finally {
    uploading.value = false
  }
}

async function commitSelected() {
  if (!previewResult.value) return
  const selected = previewResult.value.items
    .filter(item => item._selected)
    .map(item => ({
      content: item.content,
      subject: item.subject,
      chapter: item.chapter,
      type: item._type,
      source: item.source,
    }))
  if (selected.length === 0) {
    alert('请至少选择一条分块')
    return
  }
  if (!confirm(`确定提交 ${selected.length} 条分块到知识库？`)) return
  try {
    const r = await fetch(`${API_BASE}/api/knowledge/batch-commit`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(selected),
    })
    const data = await r.json()
    if (r.ok) {
      alert(`✅ 成功提交 ${data.committed} 条分块`)
      previewResult.value = null
      uploadFile.value = null
      showUploadForm.value = false
      await Promise.all([fetchStats(), fetchDocuments()])
    } else {
      alert(`❌ ${data.detail || '提交失败'}`)
    }
  } catch {
    alert('❌ 提交失败，请检查后端')
  }
}

function cancelPreview() {
  previewResult.value = null
  uploadFile.value = null
  showUploadForm.value = false
}

const paginatedItems = computed(() => documents.value)

const pageCount = computed(() => Math.max(1, Math.ceil(totalDocs.value / pageSize)))

function subjectLabel(s: string): string {
  if (!s) return '—'
  if (store.subjects[s]) return store.subjects[s].name
  const legacy: Record<string, string> = { overview: '计网·概述', physical: '计网·物理层', datalink: '计网·数据链路层', network: '计网·网络层', transport: '计网·运输层', application: '计网·应用层', security: '计网·网络安全', general: '通用' }
  return legacy[s] || s
}

function typeLabel(s: string): string {
  const map: Record<string, string> = { knowledge_point: '知识点', strategy: '策略', question: '题目' }
  return map[s] || s || '—'
}

function shortId(id: string): string {
  return id.length > 10 ? id.slice(0, 10) + '…' : id
}

function toggleSelectAll() {
  selectAll.value = !selectAll.value
  if (selectAll.value) {
    selectedIds.value = new Set(documents.value.map(d => d.id))
  } else {
    selectedIds.value = new Set()
  }
}

function toggleSelect(id: string) {
  const s = new Set(selectedIds.value)
  if (s.has(id)) { s.delete(id) } else { s.add(id) }
  selectedIds.value = s
}

async function fetchStatus() {
  try {
    const r = await fetch(`${API_BASE}/api/status`, { headers: getAuthHeaders() })
    statusInfo.value = await r.json()
  } catch { /* offline */ }
}

async function fetchStats() {
  try {
    const r = await fetch(`${API_BASE}/api/knowledge/stats`, { headers: getAuthHeaders() })
    stats.value = await r.json()
  } catch { /* offline */ }
}

async function fetchDocuments() {
  loading.value = true
  try {
    const params = new URLSearchParams({ skip: String((page.value - 1) * pageSize), limit: String(pageSize) })
    if (searchQuery.value) params.set('query', searchQuery.value)
    if (filterSubject.value) params.set('subject', filterSubject.value)
    const r = await fetch(`${API_BASE}/api/knowledge/list?${params}`, { headers: getAuthHeaders() })
    const data = await r.json()
    documents.value = data.items
    totalDocs.value = data.total
    selectedIds.value = new Set()
    selectAll.value = false
  } catch { loadError.value = '知识库加载失败，请确认后端服务已启动' }
  finally { loading.value = false }
}

async function totalPages() {
  return Math.ceil(totalDocs.value / pageSize)
}

async function addDocuments() {
  if (!newContent.value.trim()) return
  const meta: Record<string, string> = {}
  if (newSubject.value) meta.subject = newSubject.value
  if (newChapter.value) meta.chapter = newChapter.value
  meta.type = newType.value

  try {
    await fetch(`${API_BASE}/api/knowledge/upsert`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ documents: [{ content: newContent.value, metadata: meta }] }),
    })
    newContent.value = ''
    showAddForm.value = false
    await fetchStats()
    await fetchDocuments()
  } catch { /* offline */ }
}

async function deleteSelected() {
  if (selectedIds.value.size === 0) return
  if (!confirm(`确定删除 ${selectedIds.value.size} 条文档？`)) return
  try {
    await fetch(`${API_BASE}/api/knowledge/delete`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: Array.from(selectedIds.value) }),
    })
    await fetchStats()
    await fetchDocuments()
  } catch { /* offline */ }
}

async function reindex() {
  if (!confirm('重置为种子数据将清空所有自定义数据，确定？')) return
  reindexing.value = true
  try {
    await fetch(`${API_BASE}/api/knowledge/reindex`, { method: 'POST', headers: getAuthHeaders() })
    await Promise.all([fetchStatus(), fetchStats(), fetchDocuments()])
  } catch { /* offline */ }
  finally { reindexing.value = false }
}

async function clearAll() {
  if (!confirm('确定清空向量库所有文档？此操作不可撤销！')) return
  if (!confirm('⚠️ 再次确认：所有知识数据将被永久删除')) return
  try {
    const r = await fetch(`${API_BASE}/api/knowledge/clear`, { method: 'POST', headers: getAuthHeaders() })
    const data = await r.json()
    if (r.ok) {
      alert(`✅ 已清空 ${data.deleted} 条文档`)
      await Promise.all([fetchStatus(), fetchStats(), fetchDocuments()])
    }
  } catch { /* offline */ }
}

function search() {
  page.value = 1
  fetchDocuments()
}

function goPage(p: number) {
  page.value = p
  fetchDocuments()
}

onMounted(async () => {
  await Promise.all([fetchStatus(), fetchStats(), fetchDocuments()])
})
</script>

<template>
  <ErrorBoundary title="知识库管理加载异常">
  <div class="page-section active">
    <div class="section-header">
      <div class="section-title">RAG 知识库管理</div>
      <div class="section-desc">管理向量数据库中的知识文档和配置</div>
    </div>

    <!-- 状态卡片 -->
    <div class="grid-4 ka-block-lg">
      <div class="stat-card">
        <div class="stat-card-header">
          <span class="stat-label">服务状态</span>
          <div class="stat-ic" :class="statusInfo.status === 'ok' ? 'stat-ic--ok' : 'stat-ic--err'">
            <span v-html="statusInfo.status === 'ok' ? icons.checkCircle : icons.xCircle"></span>
          </div>
        </div>
        <div class="stat-value ka-stat-lg">{{ statusInfo.status === 'ok' ? '运行中' : '离线' }}</div>
        <div class="stat-change" :class="statusInfo.status === 'ok' ? 'up' : 'down'">{{ statusInfo.vector_db || '—' }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-header">
          <span class="stat-label">文档总数</span>
          <div class="stat-ic stat-ic--doc"><span v-html="icons.document"></span></div>
        </div>
        <div class="stat-value">{{ stats.total_docs }}</div>
        <div class="stat-change up">LLM {{ statusInfo.llm_available ? '已接入' : '未配置' }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-card-header">
          <span class="stat-label">按科目</span>
          <div class="stat-ic stat-ic--book"><span v-html="icons.book"></span></div>
        </div>
        <div class="stat-lines">
          <div v-for="(v,k) in stats.by_subject" :key="k">{{ subjectLabel(k) }}: {{ v }}</div>
          <div v-if="Object.keys(stats.by_subject).length === 0" class="stat-empty"><span v-html="icons.chart" class="inline-icon"></span>无数据</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-card-header">
          <span class="stat-label">按类型</span>
          <div class="stat-ic stat-ic--tag"><span v-html="icons.clipboard"></span></div>
        </div>
        <div class="stat-lines">
          <div v-for="(v,k) in stats.by_type" :key="k">{{ typeLabel(k) }}: {{ v }}</div>
          <div v-if="Object.keys(stats.by_type).length === 0" class="stat-empty"><span v-html="icons.chart" class="inline-icon"></span>无数据</div>
        </div>
      </div>
    </div>

    <!-- 操作栏 -->
    <div class="card ka-block">
      <div class="op-bar">
        <input class="form-input op-search" v-model="searchQuery" placeholder="语义搜索文档..." @keyup.enter="search" />
        <select class="rag-select" v-model="filterSubject" @change="search">
          <option value="">全部科目</option>
          <option v-for="(info, id) in store.subjects" :key="id" :value="id">{{ info.name }}</option>
        </select>
        <button class="rag-btn" @click="search">
          <span v-html="icons.search" class="ka-btn-ic"></span>搜索
        </button>
        <button class="rag-btn op-add" @click="showAddForm = !showAddForm">
          <span v-html="showAddForm ? icons.close : icons.plus" class="ka-btn-ic"></span>
          {{ showAddForm ? '取消' : '添加文档' }}
        </button>
        <button class="rag-btn op-upload" @click="showUploadForm = !showUploadForm">
          <span v-html="showUploadForm ? icons.close : icons.package" class="ka-btn-ic"></span>
          {{ showUploadForm ? '取消' : '上传文件' }}
        </button>
        <button class="rag-btn op-delete" :disabled="selectedIds.size === 0" @click="deleteSelected">
          <span v-html="icons.trash" class="ka-btn-ic"></span>
          删除 ({{ selectedIds.size }})
        </button>
        <button class="rag-btn op-reindex" :disabled="reindexing" @click="reindex">
          <span v-html="reindexing ? icons.hourglass : icons.refresh" class="ka-btn-ic"></span>
          {{ reindexing ? '重建中...' : '重置种子数据' }}
        </button>
        <button class="rag-btn op-clear" @click="clearAll">
          <span v-html="icons.trash" class="ka-btn-ic"></span>
          清空向量库
        </button>
      </div>

      <!-- 添加文档表单 -->
      <div v-if="showAddForm" class="ka-panel">
        <div class="ka-form-grid">
          <select class="rag-select" v-model="newSubject">
            <option v-for="(info, id) in store.subjects" :key="id" :value="id">{{ info.name }}</option>
          </select>
          <input class="form-input" v-model="newChapter" placeholder="章节名称" />
          <select class="rag-select" v-model="newType">
            <option value="knowledge_point">知识点</option>
            <option value="strategy">学习策略</option>
            <option value="question">题目</option>
          </select>
        </div>
        <textarea class="form-input ka-textarea" v-model="newContent" placeholder="输入知识内容..."></textarea>
        <div class="ka-form-actions">
          <button class="rag-btn op-commit" @click="addDocuments" :disabled="!newContent.trim()">
            <span v-html="icons.check" class="ka-btn-ic"></span>提交
          </button>
          <button class="rag-btn op-cancel" @click="showAddForm = false">取消</button>
        </div>
      </div>

      <!-- 上传文件 → 预览审查 -->
      <div v-if="showUploadForm" class="ka-panel ka-panel--cyan">
        <template v-if="!previewResult">
          <div class="ka-file-row">
            <input type="file" accept=".pdf,.docx,.txt" @change="(e: any) => uploadFile = e.target?.files?.[0] || null" class="ka-file" />
            <select class="rag-select ka-sel-sm" v-model="uploadSubject">
              <option v-for="(info, id) in store.subjects" :key="id" :value="id">{{ info.name }}</option>
              <option value="general">通用</option>
            </select>
            <input class="form-input ka-input-sm" v-model="uploadChapter" placeholder="章节（可选）" />
          </div>
          <div class="ka-parse-row">
            <button class="rag-btn" @click="previewFile" :disabled="!uploadFile || uploading">
              <span v-html="uploading ? icons.hourglass : icons.search" class="ka-btn-ic"></span>
              {{ uploading ? '解析中...' : '语义解析预览' }}
            </button>
            <span class="ka-filename-meta" v-if="uploadFile">{{ uploadFile.name }}</span>
          </div>
        </template>

        <template v-if="previewResult">
          <div class="ka-prev-head">
            <div>
              <strong class="ka-filename"><span v-html="icons.document" class="ka-filename-ic"></span>{{ previewResult.filename }}</strong>
              <span class="ka-filename-meta">
                {{ previewResult.items.length }} 个分块 · {{ previewResult.total_chars }} 字符
              </span>
            </div>
            <div class="ka-prev-actions">
              <button class="rag-btn op-commit" @click="commitSelected">
                <span v-html="icons.checkCircle" class="ka-btn-ic"></span>
                提交选中项 ({{ previewResult.items.filter(i => i._selected).length }})
              </button>
              <button class="rag-btn op-cancel" @click="cancelPreview">取消</button>
            </div>
          </div>

          <div class="ka-prev-list">
            <div v-for="(item, idx) in previewResult.items" :key="item.id" class="ka-prev-item">
              <div class="ka-prev-item-head">
                <input type="checkbox" v-model="item._selected" class="ka-prev-check" />
                <span class="ka-idx">#{{ idx + 1 }}</span>
                <select v-model="item.subject" class="ka-mini-select">
                  <option v-for="(info, id) in store.subjects" :key="id" :value="id">{{ info.name }}</option>
                  <option value="general">通用</option>
                </select>
                <input v-model="item.chapter" placeholder="章节" class="ka-mini-input" />
                <select v-model="item._type" class="ka-mini-select">
                  <option value="knowledge_point">知识点</option>
                  <option value="strategy">策略</option>
                  <option value="question">题目</option>
                </select>
                <span v-if="item.detected_type !== item._type" class="ka-modified">
                  <span v-html="icons.sparkleSmall" class="ka-modified-ic"></span>已修改
                </span>
              </div>
              <div class="ka-detect-note">
                自动识别：科目 <strong>{{ item.detected_subject || '?' }}</strong> · 类型 <strong>{{ item.detected_type }}</strong>
              </div>
              <textarea v-model="item.content" class="ka-prev-textarea"></textarea>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 文档列表 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">文档列表</span>
        <span class="ka-count">共 {{ totalDocs }} 条</span>
      </div>

      <div v-if="loading" class="doc-skeleton">
        <Skeleton v-for="i in 5" :key="i" variant="block" height="3.5rem" radius="var(--radius-md)" />
      </div>

      <div v-else-if="loadError" class="error-bar ka-error">
        <span>{{ loadError }}</span>
        <button class="btn btn-soft ka-retry" @click="fetchDocuments">重试</button>
      </div>

      <EmptyState v-else-if="documents.length === 0" :icon="icons.document" title="暂无文档" description="点击「添加文档」导入知识内容" />

      <template v-else>
        <div class="ka-list-head">
          <div class="ka-col-check"><input type="checkbox" :checked="selectAll" @change="toggleSelectAll" /></div>
          <div class="ka-col-content">内容</div>
          <div class="ka-col-subject">科目</div>
          <div class="ka-col-type">类型</div>
          <div class="ka-col-id">ID</div>
        </div>
        <div v-for="doc in documents" :key="doc.id" class="ka-list-row">
          <div class="ka-col-check ka-col-check--row">
            <input type="checkbox" :checked="selectedIds.has(doc.id)" @change="toggleSelect(doc.id)" />
          </div>
          <div class="ka-col-content ka-col-content--body">
            <div class="ka-clamp">{{ doc.content }}</div>
            <div v-if="doc.metadata?.chapter" class="ka-chapter">
              <span v-html="icons.bookOpen" class="ka-chapter-ic"></span>{{ doc.metadata.chapter }}
            </div>
          </div>
          <div class="ka-col-subject">
            <span class="session-subject-tag" :class="doc.metadata?.subject">{{ subjectLabel(doc.metadata?.subject) }}</span>
          </div>
          <div class="ka-col-type">{{ typeLabel(doc.metadata?.type) }}</div>
          <div class="ka-col-id" :title="doc.id">{{ shortId(doc.id) }}</div>
        </div>

        <!-- 分页 -->
        <div v-if="pageCount > 1" class="ka-pager">
          <button class="rag-btn op-page" :disabled="page <= 1" @click="goPage(page - 1)">← 上一页</button>
          <span class="ka-page-ind">第 {{ page }} / {{ pageCount }} 页</span>
          <button class="rag-btn op-page" :disabled="page >= pageCount" @click="goPage(page + 1)">下一页 →</button>
        </div>
      </template>
    </div>
  </div>
  </ErrorBoundary>
</template>

<style scoped>
input[type="checkbox"] {
  cursor: pointer;
  width: 1rem;
  height: 1rem;
  accent-color: var(--accent-primary);
}
.doc-skeleton { display: flex; flex-direction: column; gap: 0.75rem; }

/* ── 区块间距 ── */
.ka-block { margin-bottom: 1rem; }
.ka-block-lg { margin-bottom: 1.5rem; }

/* ── 状态卡片图标 ── */
.stat-ic {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: var(--radius-sm);
  color: var(--accent-primary);
}
.stat-ic svg { width: 1.1rem; height: 1.1rem; }
.stat-ic--ok { background: var(--accent-success-10); color: var(--accent-success); }
.stat-ic--err { background: var(--accent-danger-10); color: var(--accent-danger); }
.stat-ic--doc { background: color-mix(in srgb, var(--accent-primary) 12%, transparent); color: var(--accent-primary); }
.stat-ic--book { background: color-mix(in srgb, var(--accent-tertiary) 12%, transparent); color: var(--accent-tertiary); }
.stat-ic--tag { background: color-mix(in srgb, var(--subject-ds) 12%, transparent); color: var(--subject-ds); }
.ka-stat-lg { font-size: 1.125rem; }
.stat-lines { font-size: 0.8125rem; line-height: 1.8; }
.stat-empty { color: var(--text-muted); }

/* ── 操作栏 ── */
.op-bar { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; }
.op-search { flex: 1; min-width: 200px; }
.op-add { background: var(--accent-success); }
.op-upload { background: var(--accent-secondary); }
.op-delete { background: var(--accent-danger); }
.op-reindex { background: var(--accent-pink); }
.op-clear { background: var(--accent-danger); border-color: var(--accent-danger); }
.op-commit { background: var(--accent-success); padding: 0.5rem 1.25rem; }
.op-cancel { background: transparent; border: 1px solid var(--border-color); color: var(--text-secondary); }
.op-page { padding: 0.375rem 0.875rem; font-size: 0.75rem; }
.ka-btn-ic { display: inline-flex; align-items: center; width: 1rem; height: 1rem; margin-right: 0.4rem; }
.ka-btn-ic svg { width: 1rem; height: 1rem; }

/* ── 添加 / 上传面板 ── */
.ka-panel {
  margin-top: 1rem;
  padding: 1rem;
  border: 1px solid var(--border-glow);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--accent-primary) 3%, transparent);
}
.ka-panel--cyan { background: color-mix(in srgb, var(--accent-cyan) 3%, transparent); }
.ka-form-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem; }
.ka-textarea { min-height: 80px; resize: vertical; font-family: inherit; }
.ka-form-actions { margin-top: 0.5rem; display: flex; gap: 0.5rem; }

.ka-file-row { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.75rem; }
.ka-file { flex: 1; min-width: 200px; color: var(--text-primary); font-size: 0.875rem; }
.ka-sel-sm { width: 140px; }
.ka-input-sm { width: 140px; }
.ka-parse-row { display: flex; align-items: center; gap: 0.75rem; }
.ka-filename-meta { font-size: 0.75rem; color: var(--text-muted); }

/* ── 预览审查 ── */
.ka-prev-head { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
.ka-filename { font-size: 0.875rem; font-weight: 600; display: inline-flex; align-items: center; }
.ka-filename-ic { display: inline-flex; width: 1rem; height: 1rem; margin-right: 0.4rem; }
.ka-filename-ic svg { width: 1rem; height: 1rem; }
.ka-prev-actions { display: flex; gap: 0.5rem; }
.ka-prev-list { max-height: 55vh; overflow-y: auto; border: 1px solid var(--border-color); border-radius: var(--radius-sm); }
.ka-prev-item { padding: 0.75rem; border-bottom: 1px solid var(--color-glass-border); background: var(--color-surface); }
.ka-prev-item-head { display: flex; gap: 0.5rem; margin-bottom: 0.375rem; align-items: flex-start; }
.ka-prev-check { margin-top: 0.1875rem; width: 1rem; height: 1rem; flex-shrink: 0; }
.ka-idx { font-size: 0.6875rem; color: var(--text-muted); white-space: nowrap; }
.ka-mini-select, .ka-mini-input {
  font-size: 0.6875rem;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-card);
  color: var(--text-primary);
  outline: none;
}
.ka-mini-input { width: 100px; }
.ka-modified { font-size: 0.625rem; color: var(--accent-pink); white-space: nowrap; display: inline-flex; align-items: center; }
.ka-modified-ic { display: inline-flex; width: 0.75rem; height: 0.75rem; margin-right: 0.2rem; }
.ka-modified-ic svg { width: 0.75rem; height: 0.75rem; }
.ka-detect-note { font-size: 0.625rem; color: var(--text-muted); margin: 0.125rem 0 0.25rem 1.5rem; }
.ka-prev-textarea {
  width: 100%;
  min-height: 80px;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 0.8125rem;
  resize: vertical;
  font-family: inherit;
  line-height: 1.6;
}

/* ── 文档列表 ── */
.ka-count { font-size: 0.8125rem; color: var(--text-muted); }
.ka-error { margin-bottom: 1rem; }
.ka-retry { margin-left: auto; }
.ka-list-head {
  display: flex;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-color);
  font-size: 0.75rem;
  color: var(--text-muted);
  font-weight: 600;
}
.ka-list-row {
  display: flex;
  align-items: flex-start;
  padding: 0.625rem 0;
  border-bottom: 1px solid var(--border-color);
  font-size: 0.8125rem;
  gap: 0.5rem;
}
.ka-col-check { width: 36px; }
.ka-col-check--row { padding-top: 0.125rem; }
.ka-col-content { flex: 1; min-width: 0; }
.ka-col-subject { width: 60px; }
.ka-col-type { width: 70px; font-size: 0.6875rem; color: var(--text-secondary); }
.ka-col-id { width: 60px; font-size: 0.625rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ka-clamp { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ka-chapter { font-size: 0.6875rem; color: var(--text-muted); margin-top: 0.125rem; display: inline-flex; align-items: center; }
.ka-chapter-ic { display: inline-flex; width: 0.75rem; height: 0.75rem; margin-right: 0.25rem; }
.ka-chapter-ic svg { width: 0.75rem; height: 0.75rem; }

/* ── 分页 ── */
.ka-pager { display: flex; justify-content: center; align-items: center; gap: 0.5rem; margin-top: 1rem; }
.ka-page-ind { display: flex; align-items: center; font-size: 0.8125rem; color: var(--text-muted); }

@media (max-width: 640px) {
  .ka-form-grid { grid-template-columns: 1fr; }
  .op-bar { gap: 0.5rem; }
  .ka-file-row { flex-direction: column; align-items: stretch; }
  .ka-sel-sm, .ka-input-sm { width: 100%; }
}
</style>
