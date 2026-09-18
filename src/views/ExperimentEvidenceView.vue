<!--
  ExperimentEvidenceView —— 真实实验产物证据台

  【两个视图】
   · 结论看板（默认）：把散落产物按**结论**聚合（v1 规则原型），每条论断 + 头条指标
     （数值全部从真实文件字段提取）+ 溯源（文件 + sha256）。
   · 全部产物：51 份真实产物的完整画廊（分类过滤 + 明细）。

  【纪律】数据源唯一：/api/experiments（后端只返真产物，绝不回退 demo）。
  接口失败 → 空态，绝不回退示例数据。

  【接线说明（重要）】本视图为新增独立文件。src/router/index.ts 当前处于并发会话
  未提交批次（WIP），按协作纪律不代为接线。待 WIP 收口后由 owner 追加一行路由：
    { path: '/evidence', name: 'experiments-evidence',
      component: () => import('@/views/ExperimentEvidenceView.vue') }
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useExperiments, type ExperimentMeta } from '@/composables/useExperiments'
import { useEvidenceConclusions } from '@/composables/useEvidenceConclusions'

const {
  loading,
  error,
  items,
  resultsDir,
  categories,
  detail,
  loadList,
  loadDetail,
  clearDetail,
} = useExperiments()

const {
  loading: cLoading,
  error: cError,
  conclusions,
  load: loadConclusions,
} = useEvidenceConclusions()

type Tab = 'conclusions' | 'gallery'
const activeTab = ref<Tab>('conclusions')
const activeCategory = ref<string>('全部')

const visibleItems = computed<ExperimentMeta[]>(() =>
  activeCategory.value === '全部'
    ? items.value
    : items.value.filter((it) => it.category === activeCategory.value),
)
const totalCount = computed(() => items.value.length)
const realCount = computed(() => items.value.filter((it) => it.real).length)

function fmtBytes(n: number): string {
  if (!n) return '0 B'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(2)} MB`
}
function prettyData(raw: unknown): string {
  try {
    return JSON.stringify(raw, null, 2)
  } catch {
    return String(raw)
  }
}
function openDetail(name: string): void {
  void loadDetail(name)
}
function switchTab(t: Tab): void {
  activeTab.value = t
  clearDetail()
}

onMounted(() => {
  void loadList({ realOnly: true })
  void loadConclusions()
})
</script>

<template>
  <div class="evidence-page">
    <!-- 页头 -->
    <header class="ev-header">
      <div class="ev-header__text">
        <h1 class="ev-title">真实证据台</h1>
        <p class="ev-sub">
          平台<strong>所有结论的可溯源实证</strong>——{{ totalCount }} 份真实实验产物（{{ realCount }} 份 mode=real），
          每份均由后端实验管线产出，附来源文件与 sha256 校验值。
        </p>
        <p v-if="resultsDir" class="ev-dir" :title="resultsDir">
          数据源：<code>{{ resultsDir }}</code>
        </p>
      </div>
    </header>

    <!-- 视图切换 -->
    <div class="ev-tabs" role="tablist" aria-label="证据视图">
      <button
        class="ev-tab"
        :class="{ 'ev-tab--on': activeTab === 'conclusions' }"
        role="tab"
        :aria-selected="activeTab === 'conclusions'"
        type="button"
        @click="switchTab('conclusions')"
      >结论看板</button>
      <button
        class="ev-tab"
        :class="{ 'ev-tab--on': activeTab === 'gallery' }"
        role="tab"
        :aria-selected="activeTab === 'gallery'"
        type="button"
        @click="switchTab('gallery')"
      >全部产物 <span class="ev-tab__n">{{ totalCount }}</span></button>
    </div>

    <!-- ============ 结论看板 ============ -->
    <template v-if="activeTab === 'conclusions'">
      <p class="ev-note">
        结论与产物的映射为<strong>人工策展的 v1 规则原型</strong>（非自动发现）；指标数值全部取自真实产物字段。
      </p>

      <div v-if="cLoading" class="ev-state" role="status" aria-live="polite">正在加载结论证据…</div>
      <div v-else-if="cError" class="ev-state ev-state--error" role="alert">
        <p class="ev-state__title">无法加载结论证据</p>
        <p class="ev-state__msg">{{ cError }}</p>
        <button class="ev-retry" type="button" @click="loadConclusions()">重试</button>
      </div>
      <div v-else-if="!conclusions.length" class="ev-state">暂无可支撑结论的真实产物。</div>

      <section v-else class="ev-conclusions">
        <article v-for="c in conclusions" :key="c.id" class="ev-conc">
          <div class="ev-conc__head">
            <span class="ev-badge ev-badge--cat">{{ c.theme }}</span>
            <h2 class="ev-conc__title">{{ c.title }}</h2>
          </div>
          <p class="ev-conc__claim">{{ c.claim }}</p>
          <dl class="ev-conc__metrics">
            <div v-for="m in c.metrics" :key="m.label" class="ev-metric">
              <dt>{{ m.label }}</dt>
              <dd>{{ m.value }}</dd>
              <small v-if="m.hint" class="ev-metric__hint">{{ m.hint }}</small>
            </div>
          </dl>
          <div class="ev-conc__prov">
            <span class="ev-prov__label">依据产物：</span>
            <button
              v-for="a in c.artifacts"
              :key="a.name"
              class="ev-artifact-ref"
              type="button"
              @click="openDetail(a.name)"
            >
              <code>{{ a.file }}</code>
              <span v-if="a.sha256" class="ev-sha" :title="a.sha256">sha256 {{ a.sha256.slice(0, 12) }}…</span>
            </button>
          </div>
        </article>
      </section>
    </template>

    <!-- ============ 全部产物 ============ -->
    <template v-else>
      <nav class="ev-filters" aria-label="按分类过滤">
        <button
          class="ev-chip"
          :class="{ 'ev-chip--on': activeCategory === '全部' }"
          type="button"
          @click="activeCategory = '全部'"
        >全部 <span class="ev-chip__n">{{ totalCount }}</span></button>
        <button
          v-for="c in categories"
          :key="c.category"
          class="ev-chip"
          :class="{ 'ev-chip--on': activeCategory === c.category }"
          type="button"
          @click="activeCategory = c.category"
        >{{ c.category }} <span class="ev-chip__n">{{ c.count }}</span></button>
      </nav>

      <div v-if="loading && !items.length" class="ev-state" role="status" aria-live="polite">正在加载真实产物…</div>
      <div v-else-if="error" class="ev-state ev-state--error" role="alert">
        <p class="ev-state__title">无法加载真实产物</p>
        <p class="ev-state__msg">{{ error }}</p>
        <p class="ev-state__hint">请确认后端已启动（端口 8002）后重试。</p>
        <button class="ev-retry" type="button" @click="loadList({ realOnly: true })">重试</button>
      </div>
      <div v-else-if="!visibleItems.length" class="ev-state">该分类下暂无真实产物。</div>

      <section v-else class="ev-grid">
        <button v-for="it in visibleItems" :key="it.name" class="ev-card" type="button" @click="openDetail(it.name)">
          <div class="ev-card__top">
            <span class="ev-badge ev-badge--cat">{{ it.category }}</span>
            <span class="ev-badge" :class="it.real ? 'ev-badge--real' : 'ev-badge--demo'">
              {{ it.real ? 'REAL' : (it.mode || 'UNKNOWN') }}
            </span>
          </div>
          <h3 class="ev-card__title">{{ it.title }}</h3>
          <p class="ev-card__file"><code>{{ it.file }}</code></p>
          <dl class="ev-card__meta">
            <div><dt>大小</dt><dd>{{ fmtBytes(it.size_bytes) }}</dd></div>
            <div><dt>字段</dt><dd>{{ it.keys.length }}</dd></div>
            <div><dt>更新</dt><dd>{{ it.modified ? it.modified.slice(0, 10) : '—' }}</dd></div>
          </dl>
          <p v-if="it.read_error" class="ev-card__err">读取异常：{{ it.read_error }}</p>
        </button>
      </section>
    </template>

    <!-- 明细面板（两视图共享） -->
    <section v-if="detail" class="ev-detail" aria-label="产物明细">
      <div class="ev-detail__head">
        <div>
          <h2 class="ev-detail__title">{{ detail.name }}</h2>
          <p class="ev-detail__file"><code>{{ detail.file }}</code></p>
        </div>
        <button class="ev-close" type="button" aria-label="关闭明细" @click="clearDetail()">✕</button>
      </div>
      <dl class="ev-prov">
        <div><dt>来源文件</dt><dd :title="detail.provenance.source">{{ detail.provenance.source }}</dd></div>
        <div><dt>sha256</dt><dd><code>{{ detail.provenance.sha256 }}</code></dd></div>
        <div><dt>大小</dt><dd>{{ fmtBytes(detail.provenance.size_bytes) }}</dd></div>
        <div><dt>修改时间</dt><dd>{{ detail.provenance.modified }}</dd></div>
      </dl>
      <pre class="ev-json"><code>{{ prettyData(detail.data) }}</code></pre>
    </section>
  </div>
</template>

<style scoped>
.evidence-page {
  max-width: var(--content-max-width);
  margin: 0 auto;
  padding: var(--space-6);
  color: var(--color-text);
  font-family: var(--font-sans);
}
.ev-title {
  margin: 0 0 var(--space-2);
  font-size: var(--text-3xl);
  font-weight: var(--weight-bold);
  letter-spacing: var(--tracking-tight);
}
.ev-sub { margin: 0 0 var(--space-1); font-size: var(--text-base); line-height: var(--leading-normal); color: var(--color-text-2); }
.ev-dir { margin: 0; font-size: var(--text-xs); color: var(--color-text-3); }
.ev-dir code { font-family: var(--font-mono); }

/* Tabs */
.ev-tabs {
  display: inline-flex;
  gap: var(--space-1);
  margin: var(--space-4) 0 var(--space-4);
  padding: var(--space-1);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
}
.ev-tab {
  padding: var(--space-2) var(--space-4);
  border: none;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--color-text-2);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
  transition: var(--transition-colors);
}
.ev-tab:hover { color: var(--color-text); }
.ev-tab--on { background: var(--color-accent-solid); color: var(--color-text-on-accent); }
.ev-tab:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.ev-tab__n { font-variant-numeric: tabular-nums; opacity: 0.75; }

.ev-note {
  margin: 0 0 var(--space-4);
  padding: var(--space-2) var(--space-3);
  border-left: 2px solid var(--color-accent-border);
  font-size: var(--text-xs);
  color: var(--color-text-3);
}

/* 结论卡 */
.ev-conclusions { display: flex; flex-direction: column; gap: var(--space-5); }
.ev-conc {
  padding: var(--space-5);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}
.ev-conc__head { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2); }
.ev-conc__title { margin: 0; font-size: var(--text-xl); font-weight: var(--weight-semibold); }
.ev-conc__claim {
  margin: 0 0 var(--space-4);
  font-size: var(--text-md);
  line-height: var(--leading-relaxed);
  color: var(--color-text);
}
.ev-conc__metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--space-3);
  margin: 0 0 var(--space-4);
}
.ev-metric {
  padding: var(--space-3);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
}
.ev-metric dt { font-size: var(--text-2xs); color: var(--color-text-3); }
.ev-metric dd {
  margin: var(--space-1) 0 0;
  font-size: var(--text-lg);
  font-weight: var(--weight-semibold);
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
}
.ev-metric__hint { display: block; font-size: var(--text-2xs); color: var(--color-text-3); }

.ev-conc__prov { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); }
.ev-prov__label { font-size: var(--text-xs); color: var(--color-text-3); }
.ev-artifact-ref {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
  transition: var(--transition-colors);
}
.ev-artifact-ref:hover { border-color: var(--color-accent-border); color: var(--color-accent); }
.ev-artifact-ref:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.ev-artifact-ref code { font-family: var(--font-mono); }
.ev-sha { color: var(--color-text-3); font-variant-numeric: tabular-nums; }

/* 过滤芯片 */
.ev-filters { display: flex; flex-wrap: wrap; gap: var(--space-2); margin: 0 0 var(--space-4); }
.ev-chip {
  display: inline-flex; align-items: center; gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  background: var(--color-surface);
  color: var(--color-text-2);
  font: inherit; font-size: var(--text-sm);
  cursor: pointer; transition: var(--transition-colors);
}
.ev-chip:hover { background: var(--color-surface-hover); color: var(--color-text); }
.ev-chip--on { background: var(--color-accent-subtle); border-color: var(--color-accent-border); color: var(--color-accent); }
.ev-chip:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.ev-chip__n { font-variant-numeric: tabular-nums; color: var(--color-text-3); }
.ev-chip--on .ev-chip__n { color: var(--color-accent); }

/* 状态块 */
.ev-state {
  padding: var(--space-8);
  border: 1px dashed var(--color-border);
  border-radius: var(--radius-md);
  text-align: center;
  color: var(--color-text-2);
}
.ev-state--error { border-color: var(--color-danger-border); background: var(--color-danger-bg); }
.ev-state__title { margin: 0 0 var(--space-2); font-weight: var(--weight-semibold); color: var(--color-danger); }
.ev-state__msg { margin: 0 0 var(--space-1); }
.ev-state__hint { margin: 0 0 var(--space-4); font-size: var(--text-sm); color: var(--color-text-3); }
.ev-retry {
  padding: var(--space-2) var(--space-4);
  border: none; border-radius: var(--radius-sm);
  background: var(--color-accent-solid); color: var(--color-text-on-accent);
  font: inherit; cursor: pointer;
}

/* 网格 */
.ev-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--space-4); }
.ev-card {
  display: flex; flex-direction: column; gap: var(--space-2);
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
  text-align: left; font: inherit; color: inherit; cursor: pointer;
  transition: var(--transition);
}
.ev-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-card-hover); border-color: var(--color-accent-border); }
.ev-card:focus-visible { outline: none; box-shadow: var(--focus-ring); }
.ev-card__top { display: flex; justify-content: space-between; gap: var(--space-2); }
.ev-badge {
  padding: 1px var(--space-2);
  border-radius: var(--radius-2xs);
  font-size: var(--text-2xs); font-weight: var(--weight-semibold);
  letter-spacing: var(--tracking-wide);
}
.ev-badge--cat { background: var(--color-accent-subtle); color: var(--color-accent); }
.ev-badge--real { background: var(--tag-live-bg); color: var(--tag-live-color); }
.ev-badge--demo { background: var(--tag-demo-bg); color: var(--tag-demo-color); }
.ev-card__title { margin: 0; font-size: var(--text-lg); font-weight: var(--weight-semibold); line-height: var(--leading-snug); }
.ev-card__file { margin: 0; font-size: var(--text-xs); color: var(--color-text-3); word-break: break-all; }
.ev-card__file code { font-family: var(--font-mono); }
.ev-card__meta { display: flex; gap: var(--space-4); margin: var(--space-1) 0 0; }
.ev-card__meta div { display: flex; flex-direction: column; }
.ev-card__meta dt { font-size: var(--text-2xs); color: var(--color-text-3); }
.ev-card__meta dd { margin: 0; font-size: var(--text-sm); font-variant-numeric: tabular-nums; }
.ev-card__err { margin: var(--space-1) 0 0; font-size: var(--text-xs); color: var(--color-danger); }

/* 明细 */
.ev-detail {
  margin-top: var(--space-6);
  padding: var(--space-5);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-lg);
  background: var(--color-surface-2);
  box-shadow: var(--shadow-3);
  animation: mars-fade-up var(--duration-normal) var(--ease-out);
}
.ev-detail__head { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-4); }
.ev-detail__title { margin: 0; font-size: var(--text-xl); }
.ev-detail__file { margin: var(--space-1) 0 0; font-size: var(--text-xs); color: var(--color-text-3); }
.ev-detail__file code { font-family: var(--font-mono); }
.ev-close {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-2);
  width: 32px; height: 32px; cursor: pointer;
}
.ev-prov {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--space-3);
  margin: var(--space-4) 0;
  padding: var(--space-3) 0;
  border-top: 1px solid var(--color-border);
  border-bottom: 1px solid var(--color-border);
}
.ev-prov dt { font-size: var(--text-2xs); color: var(--color-text-3); }
.ev-prov dd { margin: 2px 0 0; font-size: var(--text-sm); word-break: break-all; }
.ev-prov code { font-family: var(--font-mono); font-size: var(--text-xs); }
.ev-json {
  max-height: 420px; overflow: auto; margin: 0;
  padding: var(--space-4);
  border-radius: var(--radius-sm);
  background: var(--color-surface-3);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}
</style>
