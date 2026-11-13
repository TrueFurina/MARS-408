<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, friendlyError } from '@/utils/api'
import type { operations } from '@/types/api.generated'
import PdfReader from '@/components/PdfReader.vue'
import { SEED_TEXTBOOK_LIST, getSeedTextbook, isSeedTextbook } from '@/data/seedTextbooks'

/**
 * 教材与检索相关类型。
 *
 * **来源说明（重要）**：后端 `/knowledge-base/textbooks` 返回的是 `list_textbooks()`
 * 拼出的 dict，`/knowledge-base/textbook/{id}` 则把导入时的 JSON **原样返回** ——
 * 两个接口都**没有 `response_model`**，所以 `src/types/api.generated.ts` 里没有
 * 可绑定的 schema（这也是本文件此前用 `any` 的原因）。
 * 下面的接口是按「前端实际用到的字段 + 后端 dict 构造处（pdf_reader.list_textbooks）」
 * 反推的契约，**不是从 OpenAPI 生成的**：后端改字段名时 tsc 抓不到，需同步维护。
 */
interface TextbookSummary {
  id: string
  name: string
  subject: string
  chapter_count: number
  total_chars: number
  created_at: string
}

interface TextbookChapter {
  id?: string
  title: string
  content: string
}

/** 详情 = 导入时的原始 JSON；种子教材字段更全，故除 id/name 外均按可选处理 */
interface TextbookDetail {
  id: string
  name: string
  subject?: string
  chapters?: TextbookChapter[]
  total_chars?: number
  chapter_count?: number
  status?: string
  created_at?: string
}

/** 教材内搜索命中（后端无结果时前端在种子教材里拼出来的） */
interface SearchHit {
  source: string
  content: string
}

/** `/rag/search` 的单条结果（模板只渲染 content / distance / metadata.subject / metadata.topic） */
interface RagHit {
  content?: string
  distance?: number
  metadata?: { subject?: string; topic?: string }
}

/** `/memory/overview` 直接绑后端契约（py-server/api/memory.py 的 MemoryOverviewResponse） */
type MemoryOverview =
  operations['memory_overview_api_memory_overview_get']['responses'][200]['content']['application/json']

const router = useRouter()
const textbooks = ref<TextbookSummary[]>(SEED_TEXTBOOK_LIST)
const selectedTextbook = ref<TextbookDetail | null>(null)
const searchQuery = ref('')
const searchResults = ref<SearchHit[]>([])
const showSearch = ref(false)
const askAnswer = ref('')
const askLoading = ref(false)
const askText = ref('')
const loading = ref(false)
const ragStats = ref({ total_docs: 0 })
const ragSearchResults = ref<RagHit[]>([])
const ragSearchQuery = ref('')
const ragSearching = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const [textbookRes, ragRes] = await Promise.all([
      api.get<{ textbooks: TextbookSummary[] }>('/knowledge-base/textbooks'),
      api.get<{ total_docs: number }>('/rag/status'),
    ])
    const list = textbookRes.textbooks || []
    if (list.length > 0) {
      textbooks.value = list
    }
    ragStats.value = { total_docs: ragRes.total_docs || 0 }
  } catch (e) {
    console.warn(friendlyError(e, '加载数据失败'))
  } finally {
    loading.value = false
  }
  loadMemoryOverview()
})

// L1/L2/L3 三层学情记忆（低侵入联动：知识库页展示记忆薄弱点，失败不影响主流程）
const memoryOverview = ref<MemoryOverview | null>(null)
async function loadMemoryOverview() {
  try {
    const memRes = await api.get<MemoryOverview>('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞知识库页 */ }
}

async function searchRag() {
  if (!ragSearchQuery.value.trim()) return
  ragSearching.value = true
  try {
    const res = await api.post<{ results: RagHit[] }>('/rag/search', { query: ragSearchQuery.value, top_k: 20 })
    ragSearchResults.value = res.results || []
  } catch (e) {
    console.warn(friendlyError(e, '搜索知识库失败'))
  } finally {
    ragSearching.value = false
  }
}

async function loadTextbook(id: string) {
  // 种子教材直接使用本地内容，无需调用后端
  if (isSeedTextbook(id)) {
    const seed = getSeedTextbook(id)
    selectedTextbook.value = seed || null
    return
  }
  try {
    const res = await api.get<{ textbook?: TextbookDetail }>(`/knowledge-base/textbook/${id}`)
    selectedTextbook.value = res.textbook || null
  } catch (e) {
    console.warn(friendlyError(e, '加载教材失败'))
  }
}

async function doSearch() {
  if (!searchQuery.value.trim()) return
  showSearch.value = true
  try {
    const res = await api.post<{ results?: SearchHit[] }>('/knowledge-base/search', { query: searchQuery.value })
    searchResults.value = res.results || []
    // 后端无结果时，在种子教材中搜索兜底
    if (searchResults.value.length === 0) {
      searchSeedTextbooks()
    }
  } catch (e) {
    console.warn(friendlyError(e, '搜索失败'))
    // API 不可用时在种子教材中搜索
    searchSeedTextbooks()
  }
}

/** 在种子教材中搜索关键词 */
function searchSeedTextbooks() {
  const q = searchQuery.value.trim().toLowerCase()
  const results: SearchHit[] = []
  for (const tb of SEED_TEXTBOOK_LIST) {
    const seed = getSeedTextbook(tb.id)
    if (!seed) continue
    for (const ch of seed.chapters) {
      const idx = ch.content.toLowerCase().indexOf(q)
      if (idx >= 0) {
        const start = Math.max(0, idx - 40)
        const snippet = ch.content.slice(start, start + 200).replace(/\n/g, ' ')
        results.push({ source: `${tb.name} · ${ch.title}`, content: '...' + snippet + '...' })
      }
    }
  }
  searchResults.value = results.slice(0, 10)
}

async function askAboutText(text: string) {
  askText.value = text
  askAnswer.value = ''
  askLoading.value = true
  try {
    const res = await api.post<{ answer?: string }>('/knowledge-base/ask', {
      selected_text: text,
      question: '请解释这段内容的含义',
    })
    askAnswer.value = res.answer || ''
  } catch (e) {
    askAnswer.value = friendlyError(e, '提问失败，请稍后重试')
  }
  askLoading.value = false
}
</script>

<template>
  <div class="kb-page">
    <div class="kb-head">
      <div class="kb-eyebrow">KNOWLEDGE BASE</div>
      <div class="kb-head-row">
        <div>
          <div class="kb-title">课程知识库</div>
          <div class="kb-desc">读原文 · 问选中 · 回答有出处</div>
        </div>
        <div class="kb-search-row">
          <input v-model="searchQuery" class="kb-search" placeholder="搜索教材内容..." @keyup.enter="doSearch" />
          <button class="btn btn-sm btn-soft" @click="doSearch">搜索</button>
        </div>
      </div>
    </div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip kb-strip">
      <span class="memory-mini-chip kb-strip-label">记忆薄弱点</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" class="memory-mini-chip">{{ w }}</span>
    </div>

    <!-- 教材列表 -->
    <div v-if="!selectedTextbook" class="kb-list-wrap">
      <!-- RAG 知识库统计 -->
      <div class="kb-rag-card">
        <div class="kb-rag-stat">
          <span class="kb-rag-num">{{ ragStats.total_docs }}</span>
          <span class="kb-rag-label">知识文档</span>
          <span class="kb-rag-desc">覆盖专业四科核心知识点</span>
        </div>
        <div class="kb-rag-actions">
          <input v-model="ragSearchQuery" class="kb-input-sm" placeholder="搜索知识库..." @keyup.enter="searchRag" />
          <button class="btn btn-sm btn-soft" @click="searchRag" :disabled="ragSearching">{{ ragSearching ? '搜索中...' : '搜索' }}</button>
        </div>
      </div>

      <!-- RAG 搜索结果 -->
      <div v-if="ragSearchResults.length > 0" class="kb-rag-results">
        <div class="kb-rag-results-title">搜索结果 · {{ ragSearchResults.length }}</div>
        <div v-for="(r, i) in ragSearchResults" :key="i" class="kb-result">
          <div class="kb-result-src">{{ (r.metadata && r.metadata.subject) || '未知科目' }} · {{ (r.metadata && r.metadata.topic) || '' }}</div>
          <div class="kb-result-body">{{ (r.content || '').slice(0, 200) }}{{ (r.content || '').length > 200 ? '...' : '' }}</div>
          <div class="kb-result-meta">相关度 {{ (typeof r.distance === 'number' && isFinite(r.distance)) ? ((1 - r.distance) * 100).toFixed(0) + '%' : '—' }}</div>
        </div>
      </div>

      <div class="kb-list">
        <div v-for="tb in textbooks" :key="tb.id" class="kb-card" role="button" tabindex="0" :aria-label="'教材: ' + (tb.name || tb.id)" @click="loadTextbook(tb.id)" @keydown.enter="loadTextbook(tb.id)" @keydown.space.prevent="loadTextbook(tb.id)">
          <div class="kb-card-name">{{ tb.name }}</div>
          <div class="kb-card-meta">{{ tb.chapter_count }} 章 · {{ (tb.total_chars / 1000).toFixed(0) }}K 字</div>
        </div>
        <div v-if="textbooks.length === 0" class="empty-state kb-empty">
          <div class="empty-title">暂无教材</div>
          <div class="empty-desc">请先上传 PDF 教材文件</div>
        </div>
      </div>
    </div>

    <!-- 搜索面板 -->
    <div v-if="showSearch" class="kb-panel">
      <div class="search-header">
        <span class="search-title">搜索结果 · {{ searchResults.length }}</span>
        <button class="btn btn-sm btn-ghost" @click="showSearch = false; searchResults = []">关闭</button>
      </div>
      <div v-for="r in searchResults" :key="r.source" class="search-item">
        <div class="search-source">{{ r.source }}</div>
        <div class="search-content">{{ r.content }}</div>
      </div>
      <div v-if="searchResults.length === 0" class="search-empty">无匹配结果</div>
    </div>

    <!-- 问答面板 -->
    <div v-if="askAnswer || askLoading" class="kb-panel kb-panel--ask">
      <div class="ask-header">对选中文本提问</div>
      <div class="ask-selected">「{{ askText.slice(0, 100) }}...」</div>
      <div v-if="askLoading" class="ask-loading">思考中...</div>
      <div v-else class="ask-answer" style="white-space:pre-wrap;">{{ askAnswer }}</div>
    </div>

    <!-- PDF 阅读器 -->
    <div v-if="selectedTextbook">
      <div class="back-row">
        <button class="btn btn-ghost btn-sm" @click="selectedTextbook = null">← 返回教材列表</button>
        <span class="kb-back-name">{{ selectedTextbook.name }}</span>
      </div>
      <PdfReader
        :textbook-id="selectedTextbook.id"
        :textbook-name="selectedTextbook.name"
        :chapters="selectedTextbook.chapters || []"
        @ask-about-text="askAboutText"
      />
    </div>
  </div>
</template>

<style scoped>
.kb-page { max-width: 100%; padding: var(--space-5) var(--space-6); }

/* 页头：eyebrow → 30px 标题 → 灰色说明，和全站其他页对齐。
   之前是 section-header 居中 + 内联 max-width，整块缩在中间 75rem 里。 */
.kb-head { margin: 0; padding-bottom: var(--space-4); border-bottom: 1px solid var(--color-border); margin-bottom: var(--space-4); }
.kb-eyebrow { font-size: 0.6875rem; font-weight: 600; letter-spacing: 0.16em; color: var(--color-accent); margin-bottom: 6px; }
.kb-head-row { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--space-4); flex-wrap: wrap; }
.kb-title { font-size: 30px; font-weight: 700; letter-spacing: -0.02em; color: var(--color-text); line-height: 1.2; }
.kb-desc { font-size: var(--text-sm); color: var(--color-text-2); margin-top: 6px; }
.kb-search-row { display: flex; gap: var(--space-2); align-items: center; }
.kb-search { width: 15rem; padding: 0.5rem 0.75rem; border: 1px solid var(--color-border); border-radius: 8px; background: var(--color-surface-2); color: var(--color-text); font-size: var(--text-sm); }
.kb-search:focus { outline: none; border-color: var(--color-border-focus); }

.kb-strip { margin-bottom: var(--space-4); }
.kb-strip-label { color: var(--color-accent); }

.kb-list-wrap { display: flex; flex-direction: column; gap: var(--space-3); }
.kb-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-3); }

/* RAG 统计卡：原来左边是个 emoji 已经丢成空 div，只剩 2rem 空白；改成数字 + 说明的水平排布 */
.kb-rag-card { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); flex-wrap: wrap; padding: var(--space-4) var(--space-5); background: var(--color-card); border: 1px solid var(--color-border); border-radius: 12px; box-shadow: var(--shadow-card); }
.kb-rag-stat { display: flex; align-items: baseline; gap: var(--space-3); flex-wrap: wrap; }
.kb-rag-num { font-size: 28px; font-weight: 800; color: var(--color-accent); line-height: 1; }
.kb-rag-label { font-size: var(--text-sm); color: var(--color-text-2); }
.kb-rag-desc { font-size: var(--text-xs); color: var(--color-text-3); }
.kb-rag-actions { display: flex; gap: var(--space-2); align-items: center; }
.kb-input-sm { width: 11rem; padding: 0.375rem 0.625rem; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-surface-2); color: var(--color-text); font-size: var(--text-xs); }

.kb-rag-results { margin-bottom: var(--space-2); }
.kb-rag-results-title { font-size: var(--text-xs); font-weight: 600; color: var(--color-text-2); margin-bottom: var(--space-2); }
.kb-result { padding: var(--space-3) var(--space-4); margin-bottom: var(--space-2); background: var(--color-card); border: 1px solid var(--color-border); border-radius: 9px; }
.kb-result-src { font-size: var(--text-2xs); font-weight: 600; color: var(--color-accent); margin-bottom: 4px; }
.kb-result-body { font-size: var(--text-xs); color: var(--color-text-2); line-height: 1.6; }
.kb-result-meta { font-size: var(--text-2xs); color: var(--color-text-3); margin-top: 6px; }

/* 教材卡：原先 text-align:center + 40px emoji 图标，emoji 丢失后卡里就剩一块空 */
.kb-card { padding: var(--space-4) var(--space-5); background: var(--color-card); border: 1px solid var(--color-border); border-radius: 12px; cursor: pointer; text-align: left; transition: var(--transition); box-shadow: var(--shadow-card); }
.kb-card:hover { border-color: var(--color-border-focus); box-shadow: var(--shadow-card-hover); transform: translateY(-2px); }
.kb-card-name { font-size: var(--text-base); font-weight: 600; color: var(--color-text); margin-bottom: var(--space-1); }
.kb-card-meta { font-size: var(--text-xs); color: var(--color-text-3); }
.kb-empty { grid-column: 1 / -1; }

.kb-panel { margin-bottom: var(--space-4); padding: var(--space-4) var(--space-5); background: var(--color-card); border: 1px solid var(--color-border); border-radius: 12px; box-shadow: var(--shadow-card); }
.kb-panel--ask { border-color: var(--color-border-focus); }
.search-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3); }
.search-title { font-size: var(--text-md); font-weight: 600; color: var(--color-text); }
.search-item { padding: 10px 0; border-bottom: 1px solid var(--color-border); }
.search-item:last-child { border-bottom: none; }
.search-source { font-size: var(--text-xs); color: var(--color-accent); font-weight: 600; margin-bottom: var(--space-1); }
.search-content { font-size: var(--text-sm); color: var(--color-text-2); line-height: 1.5; }
.search-empty { text-align: left; padding: var(--space-4) 0; color: var(--color-text-3); font-size: var(--text-sm); }
.ask-header { font-size: var(--text-md); font-weight: 600; color: var(--color-text); margin-bottom: var(--space-2); }
.ask-selected { font-size: var(--text-sm); color: var(--color-text-3); font-style: italic; padding: var(--space-2) var(--space-3); background: var(--color-surface-2); border-radius: 6px; margin-bottom: var(--space-3); }
.ask-answer { font-size: var(--text-base); line-height: var(--leading-relaxed); color: var(--color-text-2); }
.ask-loading { font-size: var(--text-base); color: var(--color-text-3); font-style: italic; }

.back-row { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-3); flex-wrap: wrap; }
.kb-back-name { font-size: var(--text-md); font-weight: 600; color: var(--color-text); }

@media (max-width: 640px) {
  .kb-page { padding: var(--space-4) var(--space-4) var(--space-8); }
  .kb-title { font-size: 24px; }
  .kb-head-row { flex-direction: column; align-items: stretch; }
  .kb-search-row { width: 100%; }
  .kb-search { flex: 1; width: auto; }
  .kb-list { grid-template-columns: 1fr; }
  .kb-card { padding: 14px 16px; }
  .kb-rag-card { flex-direction: column; align-items: stretch; }
  .kb-input-sm { flex: 1; width: auto; }
}
</style>