<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, friendlyError } from '@/utils/api'
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

/** `/memory/overview`（只用到 status 与 weak_points，其余字段不参与渲染） */
interface MemoryOverview {
  status?: string
  weak_points?: string[]
}

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
  <div class="page-section" style="max-width:100%;padding:1rem;">
    <div class="section-header" style="max-width:75rem;margin:0 auto 1rem;">
      <div class="section-title-group">
        <div>
          <div class="section-title"> 课程知识库</div>
          <div class="section-desc">读原文 · 问选中 · 回答有出处</div>
        </div>
      </div>
      <div class="section-actions">
        <div class="search-input-wrap" style="position:relative;display:flex;align-items:center;">
          <input v-model="searchQuery" class="search-input" placeholder="搜索教材内容..." @keyup.enter="doSearch" style="padding:8px 14px;border:1px solid var(--color-border);border-radius:8px;background:var(--color-surface-2);color:var(--color-text);font-size:14px;width:250px;" />
        </div>
      </div>
    </div>

    <!-- L1/L2/L3 三层学情记忆薄弱点提示（低侵入联动） -->
    <div v-if="memoryOverview?.weak_points?.length" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;max-width:75rem;margin:0 auto 12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);"> 记忆薄弱点:</span>
      <span v-for="w in memoryOverview.weak_points.slice(0, 6)" :key="w" style="padding:3px 10px;border-radius:12px;background:rgba(239,68,68,0.12);color:var(--accent-danger);">{{ w }}</span>
    </div>

    <!-- 教材列表 -->
    <div v-if="!selectedTextbook" class="textbook-grid" style="max-width:75rem;margin:0 auto;">
      <!-- RAG 知识库统计卡片 -->
      <div class="rag-stats-card" style="grid-column:1/-1;display:flex;align-items:center;gap:1rem;padding:1rem;background:var(--color-surface);border:1px solid var(--color-border);border-radius:12px;margin-bottom:8px;">
        <div style="font-size:2rem;"></div>
        <div style="flex:1;">
          <div style="font-size:1rem;font-weight:600;color:var(--color-text);">知识库文档</div>
          <div style="font-size:0.875rem;color:var(--color-text-2);">共 <strong style="color:var(--accent-primary);">{{ ragStats.total_docs }}</strong> 条知识文档，覆盖专业四科核心知识点</div>
        </div>
        <div style="display:flex;gap:0.5rem;align-items:center;">
          <input v-model="ragSearchQuery" placeholder="搜索知识库..." @keyup.enter="searchRag" style="padding:6px 10px;border-radius:6px;border:1px solid var(--color-border);background:var(--color-surface-2);color:var(--color-text);font-size:13px;width:180px;" />
          <button class="btn btn-sm btn-soft" @click="searchRag" :disabled="ragSearching">{{ ragSearching ? '搜索中...' : '搜索' }}</button>
        </div>
      </div>
      <!-- RAG 搜索结果 -->
      <div v-if="ragSearchResults.length > 0" style="grid-column:1/-1;margin-bottom:12px;">
        <div style="font-size:0.875rem;font-weight:600;margin-bottom:8px;color:var(--color-text-2);">搜索结果 ({{ ragSearchResults.length }})</div>
        <div v-for="(r, i) in ragSearchResults" :key="i" class="rag-result-item" style="padding:8px 12px;margin-bottom:6px;background:var(--color-surface);border:1px solid var(--color-border);border-radius:8px;">
          <div style="font-size:0.75rem;color:var(--accent-primary);font-weight:600;margin-bottom:2px;">{{ (r.metadata && r.metadata.subject) || '未知科目' }} · {{ (r.metadata && r.metadata.topic) || '' }}</div>
          <div style="font-size:0.8125rem;color:var(--color-text-2);line-height:1.5;">{{ (r.content || '').slice(0, 200) }}{{ (r.content || '').length > 200 ? '...' : '' }}</div>
          <div style="font-size:0.6875rem;color:var(--color-text-3);margin-top:4px;">相关度: {{ (typeof r.distance === 'number' && isFinite(r.distance)) ? ((1 - r.distance) * 100).toFixed(0) + '%' : '—' }}</div>
        </div>
      </div>
      <div v-for="tb in textbooks" :key="tb.id" class="textbook-card" role="button" tabindex="0" :aria-label="'教材: ' + (tb.name || tb.id)" @click="loadTextbook(tb.id)" @keydown.enter="loadTextbook(tb.id)" @keydown.space.prevent="loadTextbook(tb.id)">
        <div class="textbook-icon"></div>
        <div class="textbook-name">{{ tb.name }}</div>
        <div class="textbook-meta">{{ tb.chapter_count }} 章 · {{ (tb.total_chars / 1000).toFixed(0) }}K 字</div>
      </div>
      <div v-if="textbooks.length === 0" class="empty-state" style="grid-column:1/-1;text-align:center;padding:60px;">
        <div class="empty-icon"></div>
        <div class="empty-title">暂无教材</div>
        <div class="empty-desc">请先上传 PDF 教材文件</div>
      </div>
    </div>

    <!-- 搜索面板 -->
    <div v-if="showSearch" class="search-panel" style="max-width:75rem;margin:0 auto 1rem;">
      <div class="search-header">
        <span class="search-title"> 搜索结果 ({{ searchResults.length }})</span>
        <button class="btn btn-sm btn-ghost" @click="showSearch = false; searchResults = []">关闭</button>
      </div>
      <div v-for="r in searchResults" :key="r.source" class="search-item">
        <div class="search-source">{{ r.source }}</div>
        <div class="search-content">{{ r.content }}</div>
      </div>
      <div v-if="searchResults.length === 0" class="search-empty">无匹配结果</div>
    </div>

    <!-- 问答面板 -->
    <div v-if="askAnswer || askLoading" class="ask-panel" style="max-width:75rem;margin:0 auto 1rem;">
      <div class="ask-header"> 对选中文本提问</div>
      <div class="ask-selected">「{{ askText.slice(0, 100) }}...」</div>
      <div v-if="askLoading" class="ask-loading">思考中...</div>
      <div v-else class="ask-answer" style="white-space:pre-wrap;">{{ askAnswer }}</div>
    </div>

    <!-- PDF 阅读器 -->
    <div v-if="selectedTextbook" style="max-width:75rem;margin:0 auto;">
      <div class="back-row" style="margin-bottom:8px;">
        <button class="btn btn-ghost btn-sm" @click="selectedTextbook = null">← 返回教材列表</button>
        <span style="margin-left:12px;font-size:16px;font-weight:600;color:var(--color-text);">{{ selectedTextbook.name }}</span>
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
.textbook-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-3); }
.textbook-card { padding: var(--space-5); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 12px; cursor: pointer; text-align: center; transition: var(--transition) }
.textbook-card:hover { border-color: var(--color-border-focus); transform: translateY(-2px); }
.textbook-icon { font-size: 40px; margin-bottom: var(--space-2); }
.textbook-name { font-size: var(--text-base); font-weight: var(--weight-semibold); color: var(--color-text); margin-bottom: var(--space-1); }
.textbook-meta { font-size: var(--text-xs); color: var(--color-text-3); }
.search-panel { padding: var(--space-4); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 12px; }
.search-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3); }
.search-title { font-size: var(--text-md); font-weight: var(--weight-semibold); color: var(--color-text); }
.search-item { padding: 10px 0; border-bottom: 1px solid var(--color-border); }
.search-item:last-child { border-bottom: none; }
.search-source { font-size: var(--text-xs); color: var(--accent); font-weight: var(--weight-semibold); margin-bottom: var(--space-1); }
.search-content { font-size: var(--text-sm); color: var(--color-text-2); line-height: 1.5; }
.search-empty { text-align: center; padding: var(--space-5); color: var(--color-text-3); }
.ask-panel { padding: var(--space-4); background: var(--color-surface); border: 1px solid var(--color-border-focus); border-radius: 12px; }
.ask-header { font-size: var(--text-md); font-weight: var(--weight-semibold); color: var(--color-text); margin-bottom: var(--space-2); }
.ask-selected { font-size: var(--text-sm); color: var(--color-text-3); font-style: italic; padding: var(--space-2) var(--space-3); background: var(--color-surface-2); border-radius: 6px; margin-bottom: var(--space-3); }
.ask-answer { font-size: var(--text-base); line-height: var(--leading-relaxed); color: var(--color-text-2); }
.ask-loading { font-size: var(--text-base); color: var(--color-text-3); font-style: italic; }

/* 移动端适配 */
@media (max-width: 768px) {
  .page-section { padding: var(--space-3); }
  .section-header { flex-direction: column; gap: var(--space-2); }
  .textbook-grid { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
  .section-actions { width: 100%; }
  .search-input-wrap { width: 100%; }
  .search-input { width: 100% !important; }
}
</style>