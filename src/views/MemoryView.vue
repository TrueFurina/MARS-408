<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { icons } from '@/components/icons'
import { api } from '@/utils/api'

const loading = ref(true)
const error = ref('')
const overview = ref<{
  has_profile: boolean
  profile_dimensions: number
  mastery_points: number
  weak_points: string[]
  mastered_points: string[]
  episodic_count: number
  working_context: boolean
  memory_level: string
} | null>(null)
const context = ref('')

async function loadMemory() {
  loading.value = true
  error.value = ''
  try {
    // P0② 修复：统一走 api 实例（自动携带 Authorization token），替代裸 fetch（401）
    const [ov, ctx] = await Promise.all([
      api.get<any>('/memory/overview'),
      api.get<any>('/memory/context?max_episodes=6'),
    ])
    if (ov?.status === 'ok') overview.value = ov
    else { overview.value = null; error.value = '获取记忆总览失败' }
    if (ctx?.status === 'ok') context.value = ctx.context || ''
  } catch (e: any) {
    error.value = e?.message || '加载失败，请检查后端服务'
  } finally {
    loading.value = false
  }
}

function levelLabel(level: string): string {
  const map: Record<string, string> = {
    'L1+L2+L3': '完整三层记忆',
    'L2+L3': '长期+情景记忆',
    L3: '情景记忆',
  }
  return map[level] || level || '无记忆'
}

// ── 行动转化：记忆薄弱点 → 具体学习动作 ──
function goDrill(weakPoint: string) {
  // 跳转到刷题页并带薄弱点关键词（PracticeView 可读取）
  sessionStorage.setItem('netlearn_practice_topic', weakPoint)
  window.location.hash = '#/practice'
}

function goPractice() {
  sessionStorage.setItem('netlearn_practice_focus', 'weak')
  window.location.hash = '#/practice'
}

function goChat() {
  window.location.hash = '#/chat'
}

function goPath() {
  window.location.hash = '#/learning-path'
}

onMounted(loadMemory)
</script>

<template>
  <div class="page-section">
    <div class="section-title">🧠 学情记忆中心</div>
    <div class="section-desc">L1/L2/L3 三层分级学情记忆 — 对标 HKU-DeepTutor 记忆解耦，全程垂直适配 408 考研</div>

    <!-- 加载 -->
    <div v-if="loading" class="empty-state">
      <div v-for="i in 3" :key="i" class="skeleton" style="width:100%;height:90px;margin-bottom:12px;"></div>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="empty-state">
      <div class="empty-title">⚠️ 加载失败</div>
      <div class="empty-desc">{{ error }}</div>
      <button class="engine-btn" style="margin-top:12px;" @click="loadMemory">重新加载</button>
    </div>

    <!-- 记忆总览 -->
    <div v-else-if="overview" class="memory-grid">
      <!-- L2 语义记忆 -->
      <div class="memory-card glass-card">
        <div class="memory-card-title">L2 · 长期语义记忆</div>
        <div class="memory-stats">
          <div class="memory-stat">
            <span class="mem-val">{{ overview.profile_dimensions }}/8</span>
            <span class="mem-label">画像维度</span>
          </div>
          <div class="memory-stat">
            <span class="mem-val">{{ overview.mastery_points }}</span>
            <span class="mem-label">掌握度知识点</span>
          </div>
        </div>
        <div class="memory-level-badge">{{ levelLabel(overview.memory_level) }}</div>
      </div>

      <!-- L3 情景记忆 -->
      <div class="memory-card glass-card">
        <div class="memory-card-title">L3 · 情景记忆</div>
        <div class="memory-stats">
          <div class="memory-stat">
            <span class="mem-val">{{ overview.episodic_count }}</span>
            <span class="mem-label">历史事件</span>
          </div>
        </div>
        <div class="memory-hint">答题/行为/资源事件流，90 天保留，支撑效果评估</div>
      </div>

      <!-- 薄弱/已掌握 -->
      <div class="memory-card glass-card">
        <div class="memory-card-title">知识点掌握度</div>
        <div v-if="overview.weak_points?.length" class="mem-tags">
          <span v-for="w in overview.weak_points.slice(0, 8)" :key="w" class="mem-tag weak clickable" :title="'去巩固: ' + w" @click="goDrill(w)">{{ w }}</span>
          <span class="mem-tag-label">薄弱（点击可巩固）</span>
        </div>
        <div v-if="overview.mastered_points?.length" class="mem-tags">
          <span v-for="m in overview.mastered_points.slice(0, 8)" :key="m" class="mem-tag mastered">{{ m }}</span>
          <span class="mem-tag-label">已掌握</span>
        </div>
        <div v-if="!overview.weak_points?.length && !overview.mastered_points?.length" class="mem-empty">
          暂无掌握度数据，完成练习后自动更新
        </div>

        <!-- 行动转化：针对薄弱点的学习建议 -->
        <div v-if="overview.weak_points?.length" class="mem-actions">
          <div class="mem-actions-title">🎯 基于薄弱点的学习建议</div>
          <button class="mem-action-btn" @click="goPractice">📝 刷题巩固薄弱点</button>
          <button class="mem-action-btn" @click="goChat">💬 向 AI 助教提问</button>
          <button class="mem-action-btn" @click="goPath">🗺️ 调整学习路径</button>
        </div>
      </div>

      <!-- 记忆上下文（LLM 视角） -->
      <div class="memory-card glass-card context-card">
        <div class="memory-card-title">记忆上下文（注入智能体）</div>
        <div v-if="context" class="mem-context" style="white-space:pre-wrap;font-size:12px;">{{ context }}</div>
        <div v-else class="mem-empty">暂无历史学情记忆，开始学习后自动积累</div>
      </div>
    </div>

    <!-- 无数据 -->
    <div v-else class="empty-state">
      <div v-html="icons.history" style="opacity:0.3;"></div>
      <div class="empty-title">暂无学情记忆</div>
      <div class="empty-desc">完成画像构建与答题后，L1/L2/L3 三层记忆将自动积累</div>
      <button class="engine-btn" style="margin-top:12px;" @click="$router.push('/profile/build')">构建学习画像</button>
    </div>
  </div>
</template>

<style scoped>
.memory-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.memory-card {
  padding: 20px;
}
.memory-card-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 12px;
}
.memory-stats {
  display: flex;
  gap: 24px;
}
.memory-stat {
  display: flex;
  flex-direction: column;
}
.mem-val {
  font-size: 28px;
  font-weight: 800;
  color: var(--accent-primary);
}
.mem-label {
  font-size: 12px;
  color: var(--text-secondary);
}
.memory-level-badge {
  display: inline-block;
  margin-top: 12px;
  font-size: 12px;
  padding: 3px 12px;
  border-radius: var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
}
.memory-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 12px;
}
.mem-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.mem-tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: var(--radius-xs);
}
.mem-tag.weak { background: rgba(239,68,68,0.12); color: var(--accent-danger); }
.mem-tag.mastered { background: rgba(34,197,94,0.12); color: var(--accent-success); }
.mem-tag.clickable { cursor: pointer; transition: var(--transition); }
.mem-tag.clickable:hover { background: rgba(239,68,68,0.25); transform: scale(1.05); }
.mem-tag-label {
  font-size: 11px;
  color: var(--text-muted);
  align-self: center;
}
.mem-actions { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--glass-border); }
.mem-actions-title { font-size: 13px; font-weight: 600; color: var(--text-primary); margin-bottom: 8px; }
.mem-action-btn { display: block; width: 100%; text-align: left; padding: 10px 14px; margin-bottom: 6px; border-radius: var(--radius-sm); border: 1px solid var(--glass-border); background: var(--glass-bg); color: var(--text-secondary); font-size: 13px; cursor: pointer; transition: var(--transition); }
.mem-action-btn:hover { border-color: var(--accent-primary); color: var(--accent-primary); background: var(--accent-primary-10); }
.mem-empty {
  font-size: 13px;
  color: var(--text-muted);
  padding: 16px 0;
}
.mem-context {
  color: var(--text-secondary);
  line-height: 1.6;
  max-height: 200px;
  overflow-y: auto;
}
.context-card { grid-column: 1 / -1; }
@media (max-width: 768px) {
  .memory-grid { grid-template-columns: 1fr; }
  .context-card { grid-column: auto; }
}
</style>
