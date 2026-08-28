<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useStudyStore } from '@/stores/studyStore'
import { api } from '@/utils/api'
import { icons } from '@/components/icons'
import EmptyState from '@/components/EmptyState.vue'

const router = useRouter()
const store = useStudyStore()

interface PathNode {
  chapter: string
  chapter_num: number
  status: string
  topics: string[]
  priority: number
  mode: string
  estimated_hours: number
  weak_focus: string
  resources: { doc: string; quiz: string; extension: string }
}

const nodes = ref<PathNode[]>([])
const total = ref(0)
const completed = ref(0)
const pct = ref(0)
const loading = ref(true)
const weakFocusChapters = ref<string[]>([])
const llmAdjusted = ref(false)
// BugFix 加固：API 失败时展示错误提示与重试，而非静默空白（避免误判为白屏）
const error = ref<string | null>(null)

// 408四科切换
const subjectOptions = [
  { key: 'computer_network', label: '计算机网络' },
  { key: 'data_structures', label: '数据结构' },
  { key: 'computer_organization', label: '计算机组成原理' },
  { key: 'operating_system', label: '操作系统' },
]
const activeSubject = ref('computer_network')

function switchSubject(key: string) {
  activeSubject.value = key
  loadPath()
}

async function loadPath() {
  loading.value = true
  error.value = null
  try {
    const data = await api.post<any>('/learning-path-with-resources', {
      profile: { ...store.studentProfile, course: activeSubject.value } as any,
      current_chapter: store.studentProfile?.progress || 0,
      subject: activeSubject.value,
    })
    nodes.value = data.nodes
    total.value = data.total
    completed.value = data.completed
    pct.value = data.pct
    weakFocusChapters.value = data.weak_focus_chapters || []
    llmAdjusted.value = data.llm_adjusted || false
  } catch {
    try {
      const data2 = await api.post<any>('/learning-path', {
        profile: { ...store.studentProfile, course: activeSubject.value } as any,
        current_chapter: store.studentProfile?.progress || 0,
        subject: activeSubject.value,
      })
      nodes.value = (data2.nodes || []).map((n: any) => ({
        chapter: n.name, chapter_num: n.chapter, status: n.status,
        topics: n.topics, priority: n.chapter, mode: '主学',
        estimated_hours: 2, weak_focus: '',
        resources: { doc: '', quiz: '', extension: '' },
      }))
      total.value = data2.total
      completed.value = data2.completed
      pct.value = data2.pct
    } catch (e2: any) {
      nodes.value = []
      error.value = e2?.message || '学习路径加载失败，请稍后重试'
    }
  } finally {
    loading.value = false
  }
}

// L1/L2/L3 三层学情记忆健康度（低侵入联动：展示记忆驱动薄弱点，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞路径页 */ }
}

function chapterIconKey(status: string): string {
  const map: Record<string, string> = {
    completed: 'checkCircle', current: 'mapPin', ready: 'bookOpen', locked: 'lock',
  }
  return map[status] || 'bookOpen'
}

function statusText(status: string): string {
  const texts: Record<string, string> = {
    completed: '已完成', current: '学习中', ready: '可开始', locked: '需先学前置',
  }
  return texts[status] || ''
}

// 开始学习某章：更新画像 progress 并持久化，再跳转资源页
function startLearning(node: any) {
  const chapter = node.chapter_num
  const p = store.studentProfile
  if (p) {
    // 仅当目标章节高于当前进度时才推进，避免回退
    const newProgress = Math.max(p.progress || 0, chapter)
    store.saveProfile({ ...p, progress: newProgress })
  }
  // 传递章节名到资源页，自动填入 topic 输入框
  router.push({ path: '/resource', query: { topic: node.chapter, subject: activeSubject.value } })
}

onMounted(() => {
  loadPath()
  loadMemoryOverview()
})

// ── 建议下一步学习（功能⑤：评估→路径闭环 UI 提示）──
// 优先推荐薄弱章节中可开始的，否则推荐第一个 current/ready 章节
const nextStepNode = computed<PathNode | null>(() => {
  if (!nodes.value.length) return null
  // 优先找薄弱章节中 ready/current 的
  const weakReady = nodes.value.find(
    n => n.weak_focus && (n.status === 'ready' || n.status === 'current')
  )
  if (weakReady) return weakReady
  // 否则找第一个 current
  const current = nodes.value.find(n => n.status === 'current')
  if (current) return current
  // 否则找第一个 ready
  return nodes.value.find(n => n.status === 'ready') || null
})
</script>

<template>
  <div class="page-section active">
    <div class="section-header">
      <div class="section-title">个性化学习路径</div>
      <div class="section-desc">基于你的画像、学情记忆和进度自动生成的学习路线图</div>
    </div>

    <!-- L1/L2/L3 三层学情记忆健康度（低侵入联动） -->
    <div v-if="memoryOverview" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
      <span class="memory-mini-chip" style="font-size:11px;padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 {{ memoryOverview.memory_level || 'L3' }}</span>
      <span class="memory-mini-chip" style="font-size:11px;padding:3px 10px;border-radius:12px;background:var(--bg-tertiary);color:var(--text-secondary);">薄弱点: {{ memoryOverview.weak_points?.length ?? 0 }} 个</span>
      <span class="memory-mini-chip" style="font-size:11px;padding:3px 10px;border-radius:12px;background:var(--bg-tertiary);color:var(--text-secondary);">掌握度: {{ memoryOverview.mastery_points ?? 0 }} 点</span>
    </div>

    <!-- 进度总览 -->
    <div class="card" style="margin-bottom:20px;text-align:center;padding:24px;">
      <!-- 408四科切换 -->
      <div class="subject-tabs">
        <button
          v-for="opt in subjectOptions" :key="opt.key"
          class="subject-tab"
          :class="{ active: activeSubject === opt.key }"
          @click="switchSubject(opt.key)"
        >{{ opt.label }}</button>
      </div>

      <div style="font-size:32px;font-weight:700;color:var(--accent-1);margin-top:12px;">{{ pct }}%</div>
      <div style="font-size:14px;color:var(--text-secondary);margin-top:4px;">
        已完成 {{ completed }}/{{ total }} 章
      </div>
      <div style="margin-top:12px;height:8px;background:var(--bg-secondary);border-radius:var(--radius-full);overflow:hidden;max-width:400px;margin-left:auto;margin-right:auto;">
        <div :style="{width: pct+'%', height:'100%', background:'var(--gradient-accent)', borderRadius:'var(--radius-full)', transition:'width 0.6s ease'}"></div>
      </div>
      <div v-if="!store.profileCompleted" style="margin-top:12px;font-size:13px;color:var(--accent-4);">
        建议先完成<a href="/profile/build" style="color:var(--accent-1);text-decoration:underline;">学生画像</a>，获取更精准的学习路径
      </div>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="generation-loading">
      <div class="loading-spinner"></div>
      <div class="loading-text">正在规划学习路径...</div>
    </div>

    <!-- 错误提示 -->
    <div v-else-if="error" class="path-error">
      <div class="path-error-title">⚠️ 加载失败</div>
      <div class="path-error-msg">{{ error }}</div>
      <button class="path-error-retry" @click="loadPath">重试</button>
    </div>

    <!-- 空态兜底 -->
    <EmptyState v-else-if="!nodes.length" :icon="icons.mapPin" title="暂无学习路径" description="尚未生成学习路径，请稍后重试" />

    <!-- 路径列表 -->
    <div v-else class="path-list">
      <div v-if="llmAdjusted" class="card" style="padding:12px 16px;margin-bottom:16px;background:var(--accent-1-light);border-radius:var(--radius-sm);font-size:13px;color:var(--accent-1);">
        AI 已根据你的薄弱点动态调整章节顺序并推荐资源
      </div>
      <!-- 建议下一步学习（功能⑤：评估→路径闭环） -->
      <div v-if="nextStepNode" class="next-step-banner">
        <div class="next-step-icon"><span v-html="icons.sparkle"></span></div>
        <div class="next-step-body">
          <div class="next-step-title">建议下一步学习</div>
          <div class="next-step-desc">{{ nextStepNode.chapter }}<span v-if="nextStepNode.weak_focus" class="next-step-weak"> · 薄弱重点</span></div>
        </div>
        <button class="next-step-btn" @click="startLearning(nextStepNode)">开始学习 →</button>
      </div>
      <div v-for="(node, idx) in nodes" :key="node.chapter" class="path-card" :class="node.status">
        <!-- 连线 -->
        <div v-if="idx > 0" class="path-connector" :class="{ dimmed: node.status === 'locked' }">
          <svg width="20" height="32" viewBox="0 0 20 32"><path d="M10 0 L10 28" stroke="currentColor" stroke-width="2" stroke-dasharray="4,3" fill="none"/></svg>
        </div>

        <div class="path-card-inner">
          <div class="path-card-left">
            <div class="path-icon" :style="{background: node.status === 'locked' ? 'var(--bg-secondary)' : 'var(--gradient-accent)'}">
              <span v-html="icons[chapterIconKey(node.status) as keyof typeof icons]"></span>
            </div>
          </div>
          <div class="path-card-content">
            <div class="path-card-header">
              <span class="path-chapter">第{{ node.chapter_num }}章 · {{ node.mode }}</span>
              <span v-if="node.weak_focus" style="font-size:11px;color:var(--accent-6);margin-left:8px;" v-html="icons.target" class="inline-icon"></span>
              <span v-if="node.weak_focus" style="font-size:11px;color:var(--accent-6);margin-left:2px;">{{ node.weak_focus }}</span>
              <span style="font-size:11px;color:var(--text-muted);margin-left:auto;display:flex;align-items:center;gap:2px;"><span v-html="icons.clock" class="inline-icon-tiny"></span> {{ node.estimated_hours }}h</span>
              <span class="path-status-tag" :class="node.status">{{ statusText(node.status) }}</span>
            </div>
            <div class="path-title">{{ node.chapter }}</div>
            <div class="path-topics">
              <span v-for="topic in node.topics" :key="topic" class="path-topic-tag">{{ topic }}</span>
            </div>
            <!-- 推荐资源（赛题功能3：路径+资源推送联动）-->
            <div v-if="node.resources && (node.resources.doc || node.resources.quiz || node.resources.extension)" class="path-resources">
              <div v-if="node.resources.doc" class="path-resource-item"><span v-html="icons.fileText" class="inline-icon-tiny"></span> {{ node.resources.doc }}</div>
              <div v-if="node.resources.quiz" class="path-resource-item"><span v-html="icons.clipboard" class="inline-icon-tiny"></span> {{ node.resources.quiz }}</div>
              <div v-if="node.resources.extension" class="path-resource-item"><span v-html="icons.bookOpen" class="inline-icon-tiny"></span> {{ node.resources.extension }}</div>
            </div>
            <button
              v-if="node.status === 'ready' || node.status === 'current'"
              class="path-start-btn"
              @click="startLearning(node)"
            >
              开始学习 →
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.subject-tabs {
  display: flex;
  gap:0.375rem;
  justify-content: center;
  margin-bottom:0.5rem;
  flex-wrap: wrap;
}
.subject-tab {
  padding:0.3125rem 0.875rem;
  border-radius:var(--radius-full);
  border: 1px solid var(--border-color);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size:0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
}
.subject-tab.active {
  background: var(--accent-primary-10);
  border-color: var(--accent-primary);
  color: var(--accent-primary);
}
.subject-tab:hover:not(.active) {
  border-color: var(--text-muted);
  color: var(--text-primary);
}
.path-list {
  max-width:40rem;
  margin:0 auto;
}
.path-card {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--glass-border);
  border-radius:var(--radius-md);
  transition: var(--transition);
  animation: fade-up 0.3s ease both;
}
.path-card.completed { opacity: 0.7; }
.path-card.current { border-color: var(--accent-primary); box-shadow: 0 0 0 2px var(--accent-primary-10), var(--glow-primary); }
.path-card.locked { opacity: 0.5; }
.path-card:hover:not(.locked) { transform: translateY(-1px); box-shadow: var(--shadow-card-hover); }
.path-card-inner {
  display: flex;
  gap:1rem;
  padding:1.25rem;
}
.path-card-left { flex-shrink: 0; }
.path-icon {
  width:3rem;
  height:3rem;
  border-radius:var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size:1.375rem;
  color: #fff;
}
.path-card-content { flex: 1; min-width:0; }
.path-card-header {
  display: flex;
  align-items: center;
  gap:0.625rem;
  margin-bottom:0.25rem;
}
.path-chapter { font-size:0.75rem; font-weight: 600; color: var(--text-muted); }
.path-status-tag { font-size:0.6875rem; padding:0.125rem 0.625rem; border-radius:var(--radius-full); font-weight: 600; }
.path-status-tag.completed { background: var(--accent-success-10); color: var(--accent-success); }
.path-status-tag.current { background: var(--accent-primary-10); color: var(--accent-primary); }
.path-status-tag.ready { background: var(--accent-primary-10); color: var(--accent-primary); }
.path-status-tag.locked { background: var(--bg-tertiary); color: var(--text-muted); }
.path-title { font-size:1.0625rem; font-weight: 700; color: var(--text-primary); margin-bottom:0.5rem; }
.path-topics { display: flex; flex-wrap: wrap; gap:0.375rem; }
.path-topic-tag {
  font-size:0.6875rem; padding:0.1875rem 0.625rem;
  border-radius:6.1875rem; background: var(--accent-primary-10);
  color: var(--accent-primary);
}
.path-start-btn {
  margin-top:0.625rem;
  padding:0.5rem 1.25rem;
  background: var(--gradient-primary);
  color: #fff;
  border: none;
  border-radius:var(--radius-full);
  font-size:0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition-bounce);
}
.path-start-btn:hover { transform: translateY(-2px) scale(1.02); box-shadow: var(--shadow-glow), var(--glow-primary); }
.path-resources {
  margin-top:0.625rem;
  padding:0.625rem 0.75rem;
  background: var(--accent-primary-10);
  border-radius:var(--radius-sm);
  border: 1px solid var(--accent-primary-20);
  display: flex;
  flex-direction: column;
  gap:0.25rem;
}
.path-resource-item {
  font-size:0.75rem;
  color: var(--text-secondary);
  line-height:1.5;
}
.path-connector {
  display: flex;
  justify-content: center;
  color: var(--accent-primary);
  opacity: 0.3;
  padding:0.125rem 0;
}
.path-connector.dimmed { opacity: 0.15; }

/* ── 加载失败提示（BugFix 加固） ── */
.path-error {
  max-width: 40rem;
  margin: 0 auto;
  padding: 1.5rem;
  text-align: center;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--accent-danger, #ef4444) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent-danger, #ef4444) 35%, transparent);
}
.path-error-title { font-size: 1rem; font-weight: 700; color: var(--accent-danger, #ef4444); }
.path-error-msg { font-size: 0.8125rem; color: var(--text-secondary); margin: 0.5rem 0 1rem; word-break: break-all; }
.path-error-retry {
  padding: 0.5rem 1.5rem;
  border: none;
  border-radius: var(--radius-full);
  background: var(--gradient-primary);
  color: #fff;
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
}

/* ── 建议下一步学习（功能⑤闭环 UI） ── */
.next-step-banner {
  display: flex;
  align-items: center;
  gap:0.75rem;
  padding:0.875rem 1rem;
  margin-bottom:1rem;
  border-radius:var(--radius-md);
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--accent-primary);
  box-shadow: var(--glow-primary);
  animation: fade-up 0.3s ease both;
}
.next-step-icon {
  width:2.5rem;
  height:2.5rem;
  border-radius:var(--radius-sm);
  background: var(--gradient-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.next-step-icon svg { width:1.25rem; height:1.25rem; }
.next-step-body { flex: 1; min-width:0; }
.next-step-title { font-size:0.75rem; font-weight: 600; color: var(--accent-primary); }
.next-step-desc { font-size:0.9375rem; font-weight: 700; color: var(--text-primary); margin-top:0.125rem; }
.next-step-weak { font-size:0.6875rem; color: var(--accent-danger); font-weight: 500; }
.next-step-btn {
  padding:0.5rem 1.125rem;
  background: var(--gradient-primary);
  color: #fff;
  border: none;
  border-radius:var(--radius-full);
  font-size:0.8125rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: var(--transition-bounce);
  flex-shrink: 0;
}
.next-step-btn:hover { transform: translateY(-2px) scale(1.02); box-shadow: var(--shadow-glow), var(--glow-primary); }

/* ── 多角色2：移动端响应式适配 ── */
@media (max-width: 768px) {
  .subject-tabs { gap: 0.375rem; }
  .subject-tab { padding: 0.375rem 0.75rem; font-size: 0.8125rem; }
  .path-card { padding: 0.875rem; }
  .path-title { font-size: 1rem; }
  .path-topics { gap: 0.25rem; }
  .path-topic { padding: 0.25rem 0.5rem; font-size: 0.6875rem; }
  .path-header { flex-direction: column; align-items: stretch; gap: 0.5rem; }
}
@media (max-width: 480px) {
  .path-meta { font-size: 0.75rem; }
  .path-actions { flex-direction: column; gap: 0.5rem; }
  .path-actions .engine-btn { width: 100%; }
}
</style>
