<script setup lang="ts">
// ============================================================
// 安全审计日志页 — 展示近期内容安全拦截/告警事件
// 玻璃态风格，admin/teacher 可查
// 消费 GET /api/audit/logs + GET /api/audit/stats
// ============================================================
import { ref, onMounted, computed } from 'vue'
import { api } from '@/utils/api'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { icons } from '@/components/icons'

interface AuditEvent {
  timestamp: number
  time_str: string
  user_id: string
  ip: string
  action: string
  result: string
  detail: string
}

interface AuditStats {
  total: number
  blocked: number
  failure: number
  success: number
  by_action: Record<string, number>
}

const loading = ref(true)
const error = ref('')
const logs = ref<AuditEvent[]>([])
const stats = ref<AuditStats | null>(null)

// 筛选
const filterAction = ref<string>('')
const filterResult = ref<string>('')

// 动作类型中文映射
const ACTION_LABELS: Record<string, string> = {
  content_safety_sensitive: '敏感词拦截',
  content_safety_compliance: '合规审核拦截',
  content_safety_compliance_degrade: '合规降级',
  content_safety_compliance_error: '合规审核异常',
  content_safety_hallucination: '幻觉检测告警',
  login: '登录',
  config_change: '配置变更',
  sandbox_exec: '沙箱执行',
  knowledge_modify: '知识库修改',
}

function actionLabel(a: string): string {
  return ACTION_LABELS[a] || a
}

// 结果配色
const RESULT_STYLE: Record<string, { color: string; bg: string; label: string }> = {
  blocked: { color: 'var(--accent-danger)', bg: 'var(--accent-danger-10)', label: '已拦截' },
  failure: { color: 'var(--accent-warm)', bg: 'color-mix(in srgb, var(--accent-warm) 12%, transparent)', label: '失败' },
  success: { color: 'var(--accent-success)', bg: 'var(--accent-success-10)', label: '成功' },
}

function resultStyle(r: string) {
  return RESULT_STYLE[r] || { color: 'var(--color-text-2)', bg: 'color-mix(in srgb, var(--color-text-2) 12%, transparent)', label: r }
}

const filteredLogs = computed(() => {
  return logs.value.filter((e) => {
    if (filterAction.value && e.action !== filterAction.value) return false
    if (filterResult.value && e.result !== filterResult.value) return false
    return true
  })
})

const actionOptions = computed(() => {
  const set = new Set(logs.value.map((e) => e.action))
  return Array.from(set)
})

async function loadLogs() {
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams()
    params.set('limit', '200')
    if (filterAction.value) params.set('action', filterAction.value)
    if (filterResult.value) params.set('result', filterResult.value)
    const data = await api.get<{ logs: AuditEvent[]; count: number }>(`/audit/logs?${params.toString()}`)
    logs.value = data.logs || []
  } catch (e: any) {
    error.value = e?.message || '加载审计日志失败'
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await api.get<AuditStats>('/audit/stats')
  } catch {
    /* 静默 */
  }
}

function refresh() {
  loadLogs()
  loadStats()
}

onMounted(() => {
  refresh()
})
</script>

<template>
  <ErrorBoundary title="审计日志加载异常">
  <div class="audit-page">
    <!-- 页头 -->
    <div class="audit-header">
      <div class="audit-title-wrap">
        <h1 class="audit-title">
          <span class="ttl-ico" v-html="icons.shield"></span>
          安全审计日志
        </h1>
        <p class="audit-subtitle">内容安全拦截 · 合规告警 · 幻觉检测 · 全链路可观测</p>
      </div>
      <button class="refresh-btn" @click="refresh" :disabled="loading">
        <span class="rf-ico" :class="{ spinning: loading }" v-html="icons.refresh"></span>
        <span>{{ loading ? '加载中...' : '刷新' }}</span>
      </button>
    </div>

    <!-- 统计卡片 -->
    <div v-if="stats" class="stats-grid">
      <div class="stat-card">
        <div class="stat-num">{{ stats.total }}</div>
        <div class="stat-label">总事件</div>
      </div>
      <div class="stat-card stat-blocked">
        <div class="stat-num">{{ stats.blocked }}</div>
        <div class="stat-label">已拦截</div>
      </div>
      <div class="stat-card stat-failure">
        <div class="stat-num">{{ stats.failure }}</div>
        <div class="stat-label">失败</div>
      </div>
      <div class="stat-card stat-success">
        <div class="stat-num">{{ stats.success }}</div>
        <div class="stat-label">成功</div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <select v-model="filterAction" class="filter-select" @change="loadLogs">
        <option value="">全部事件类型</option>
        <option v-for="a in actionOptions" :key="a" :value="a">{{ actionLabel(a) }}</option>
      </select>
      <select v-model="filterResult" class="filter-select" @change="loadLogs">
        <option value="">全部结果</option>
        <option value="blocked">已拦截</option>
        <option value="failure">失败</option>
        <option value="success">成功</option>
      </select>
      <span class="filter-count">共 {{ filteredLogs.length }} 条</span>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-banner">{{ error }}</div>

    <!-- 日志列表 -->
    <div v-if="loading" class="log-skeleton">
      <Skeleton v-for="i in 6" :key="i" variant="block" height="4.5rem" radius="var(--radius-md)" />
    </div>

    <EmptyState v-else-if="filteredLogs.length === 0" :icon="icons.document" title="暂无审计日志记录" description="生成内容后，内容安全拦截/告警事件将在此展示" />

    <div v-else class="log-list">
      <div v-for="(log, i) in filteredLogs" :key="i" class="log-card">
        <div class="log-card-head">
          <span class="log-action" :style="{ background: 'color-mix(in srgb, var(--accent-primary) 12%, transparent)', color: 'var(--accent-primary)' }">
            {{ actionLabel(log.action) }}
          </span>
          <span class="log-result" :style="{ color: resultStyle(log.result).color, background: resultStyle(log.result).bg }">
            {{ resultStyle(log.result).label }}
          </span>
          <span class="log-time">{{ log.time_str }}</span>
        </div>
        <div class="log-card-body">
          <div class="log-meta">
            <span class="log-user"><span class="li-ico" v-html="icons.user"></span>{{ log.user_id }}</span>
            <span class="log-ip"><span class="li-ico" v-html="icons.globe"></span>{{ log.ip }}</span>
          </div>
          <div v-if="log.detail" class="log-detail">{{ log.detail }}</div>
        </div>
      </div>
    </div>
  </div>
  </ErrorBoundary>
</template>

<style scoped>
.audit-page {
  max-width: 56rem;
  margin: 0 auto;
  padding: 1.5rem 1rem 3rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

/* ── 页头 ── */
.audit-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}
.audit-title {
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--color-text);
  margin: 0;
}
.audit-subtitle {
  font-size: 0.8125rem;
  color: var(--color-text-3);
  margin: 0.25rem 0 0;
}
.refresh-btn {
  padding: 0.5rem 1.125rem;
  background: var(--color-glass);
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text);
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
  white-space: nowrap;
}
.refresh-btn:hover:not(:disabled) {
  border-color: var(--accent-primary);
  box-shadow: var(--glow-primary);
}
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── 统计卡片 ── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
}
.stat-card {
  text-align: center;
  padding: 1rem 0.5rem;
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-md);
}
.stat-num {
  font-size: 1.5rem;
  font-weight: 800;
  color: var(--color-text);
}
.stat-label {
  font-size: 0.6875rem;
  color: var(--color-text-3);
  margin-top: 0.25rem;
}
.stat-blocked .stat-num { color: var(--accent-danger); }
.stat-failure .stat-num { color: var(--accent-warm); }
.stat-success .stat-num { color: var(--accent-success); }

/* ── 筛选栏 ── */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}
.filter-select {
  padding: 0.4375rem 0.75rem;
  background: var(--color-glass);
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text);
  font-size: 0.8125rem;
  cursor: pointer;
  transition: var(--transition);
}
.filter-select:hover, .filter-select:focus {
  border-color: var(--accent-primary);
  outline: none;
}
.filter-count {
  font-size: 0.75rem;
  color: var(--color-text-3);
  margin-left: auto;
}

/* ── 错误/空状态 ── */
.error-banner {
  padding: 0.75rem 1rem;
  background: var(--accent-danger-10);
  border: 1px solid var(--accent-danger-20);
  border-radius: var(--radius-md);
  color: var(--text-danger);
  font-size: 0.8125rem;
}
.loading-state {
  text-align: center;
  padding: 3rem;
  color: var(--color-text-3);
  font-size: 0.875rem;
}
.log-skeleton { display: flex; flex-direction: column; gap: 0.625rem; }
.empty-state {
  text-align: center;
  padding: 3rem 1rem;
}
.empty-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
.empty-text { font-size: 0.9375rem; color: var(--color-text-2); font-weight: 600; }
.empty-hint { font-size: 0.75rem; color: var(--color-text-3); margin-top: 0.375rem; }

/* ── 日志卡片 ── */
.log-list {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}
.log-card {
  padding: 0.875rem 1rem;
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-md);
  transition: var(--transition);
}
.log-card:hover {
  border-color: var(--color-border-focus);
  box-shadow: var(--shadow-sm);
}
.log-card-head {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  margin-bottom: 0.5rem;
}
.log-action {
  font-size: 0.6875rem;
  font-weight: 700;
  padding: 0.1875rem 0.625rem;
  border-radius: var(--radius-full);
}
.log-result {
  font-size: 0.6875rem;
  font-weight: 700;
  padding: 0.1875rem 0.625rem;
  border-radius: var(--radius-full);
}
.log-time {
  margin-left: auto;
  font-size: 0.6875rem;
  color: var(--color-text-3);
}
.log-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.log-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.6875rem;
  color: var(--color-text-3);
}
.log-detail {
  font-size: 0.75rem;
  color: var(--color-text-2);
  line-height: 1.5;
  padding: 0.375rem 0.5rem;
  background: var(--color-glass);
  border-radius: var(--radius-sm);
  word-break: break-word;
}

/* ── 语义图标（替代 emoji，统一接入 icons.ts 体系）── */
.ttl-ico {
  display: inline-flex;
  width: 1.5rem;
  height: 1.5rem;
  margin-right: 0.5rem;
  color: var(--accent-primary);
  vertical-align: -0.35rem;
}
.ttl-ico :deep(svg) { width: 1.5rem; height: 1.5rem; }
.rf-ico {
  display: inline-flex;
  width: 1.0625rem;
  height: 1.0625rem;
  color: currentColor;
}
.rf-ico :deep(svg) { width: 1.0625rem; height: 1.0625rem; }
.rf-ico.spinning { animation: rf-spin 0.8s linear infinite; }
@keyframes rf-spin { to { transform: rotate(360deg); } }
.li-ico {
  display: inline-flex;
  width: 0.875rem;
  height: 0.875rem;
  margin-right: 0.3rem;
  color: var(--color-text-3);
  vertical-align: -0.1rem;
}
.li-ico :deep(svg) { width: 0.875rem; height: 0.875rem; }

@media (prefers-reduced-motion: reduce) {
  .rf-ico.spinning { animation: none; }
}

@media (max-width: 640px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .audit-title { font-size: 1.25rem; }
}
</style>
