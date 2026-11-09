<script setup lang="ts">
import { errMessage } from '@/utils/errorMessage'
import { ref, onMounted } from 'vue'
import { api } from '@/utils/api'
import type { operations } from '@/types/api.generated'

type MemoryContextResp = operations['memory_context_api_memory_context_get']['responses'][200]['content']['application/json']

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
      api.get<MemoryContextResp>('/memory/context?max_episodes=6'),
    ])
    if (ov?.status === 'ok') overview.value = ov
    else { overview.value = null; error.value = '获取记忆总览失败' }
    if (ctx?.status === 'ok') context.value = String(ctx.context ?? '')
  } catch (e) {
    error.value = errMessage(e, '加载失败，请检查后端服务')
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
  sessionStorage.setItem('mangdehenzhi_practice_topic', weakPoint)
  window.location.hash = '#/practice'
}

function goPractice() {
  sessionStorage.setItem('mangdehenzhi_practice_focus', 'weak')
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
  <div class="page-section mv-page">
    <div class="mv-eyebrow">MEMORY CENTER</div>
    <div class="mv-title">学情记忆中心</div>
    <div class="mv-desc">L1/L2/L3 三层分级学情记忆，对标 HKU-DeepTutor 的记忆解耦，全程垂直适配专业课程学习</div>

    <!-- 加载 -->
    <div v-if="loading" class="mv-skeletons">
      <div v-for="i in 3" :key="i" class="skeleton mv-skeleton"></div>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="empty-state">
      <div class="empty-title">加载失败</div>
      <div class="empty-desc">{{ error }}</div>
      <button class="engine-btn mv-retry" @click="loadMemory">重新加载</button>
    </div>

    <!-- 记忆总览 -->
    <div v-else-if="overview" class="memory-grid">
      <!-- L2 语义记忆 -->
      <div class="memory-card">
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
        <!-- 这个徽标是全平台记忆等级（当前 L3），放在 L2 卡里会被读成 L2 自己的标签；
             前缀写「平台」而不是「当前」，明确它描述的是整体等级。 -->
        <div class="memory-level-badge">平台记忆等级 · {{ levelLabel(overview.memory_level) }}</div>
      </div>

      <!-- L3 情景记忆 -->
      <div class="memory-card">
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
      <div class="memory-card mastery-card">
        <div class="memory-card-title">知识点掌握度</div>
        <div v-if="overview.weak_points?.length" class="mem-group">
          <div class="mem-tag-label">薄弱（点击可巩固）</div>
          <div class="mem-tags">
            <button v-for="w in overview.weak_points.slice(0, 8)" :key="w" type="button" class="mem-tag weak clickable" :title="'去巩固: ' + w" @click="goDrill(w)">{{ w }}</button>
          </div>
        </div>
        <div v-if="overview.mastered_points?.length" class="mem-group">
          <div class="mem-tag-label">已掌握</div>
          <div class="mem-tags">
            <span v-for="m in overview.mastered_points.slice(0, 8)" :key="m" class="mem-tag mastered">{{ m }}</span>
          </div>
        </div>
        <div v-if="!overview.weak_points?.length && !overview.mastered_points?.length" class="mem-empty">
          暂无掌握度数据，完成练习后自动更新
        </div>

        <!-- 行动转化：针对薄弱点的学习建议 -->
        <div v-if="overview.weak_points?.length" class="mem-actions">
          <div class="mem-actions-title">基于薄弱点的学习建议</div>
          <div class="mem-action-row">
            <button class="mem-action-btn" @click="goPractice">刷题巩固薄弱点</button>
            <button class="mem-action-btn" @click="goChat">向 AI 助教提问</button>
            <button class="mem-action-btn" @click="goPath">调整学习路径</button>
          </div>
        </div>
      </div>

      <!-- 记忆上下文（LLM 视角） -->
      <div class="memory-card context-card">
        <div class="memory-card-title">记忆上下文（注入智能体）</div>
        <div v-if="context" class="mem-context">{{ context }}</div>
        <div v-else class="mem-empty">暂无历史学情记忆，开始学习后自动积累</div>
      </div>
    </div>

    <!-- 无数据 -->
    <div v-else class="empty-state">
      <div class="empty-title">暂无学情记忆</div>
      <div class="empty-desc">完成画像构建与答题后，L1/L2/L3 三层记忆将自动积累</div>
      <button class="engine-btn mv-retry" @click="$router.push('/profile/build')">构建学习画像</button>
    </div>
  </div>
</template>

<style scoped>
.mv-page { max-width: 1100px; }
.mv-eyebrow { font-size: 11px; line-height: 1; letter-spacing: 0.16em; text-transform: uppercase; color: var(--accent-primary); font-weight: 600; margin-bottom: 10px; }
.mv-title { font-size: 30px; font-weight: 700; letter-spacing: -0.02em; color: var(--color-text); line-height: 1.2; }
.mv-desc { font-size: var(--text-sm); color: var(--color-text-2); margin-top: 8px; margin-bottom: var(--space-5); max-width: 640px; line-height: 1.6; }
.mv-skeletons { display: flex; flex-direction: column; gap: var(--space-3); }
.mv-skeleton { width: 100%; height: 90px; border-radius: 12px; }
.mv-retry { margin-top: var(--space-3); }

.memory-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-4); }
/* 原先靠 glass-card 半透明，暗色下几乎与背景同色；改成实心卡片面 + 常规投影 */
.memory-card { padding: var(--space-5); background: var(--color-card); border: 1px solid var(--color-border); border-radius: 12px; box-shadow: var(--shadow-card); }
.memory-card-title { font-size: var(--text-md); font-weight: 700; color: var(--color-text); margin-bottom: var(--space-3); }
.memory-stats { display: flex; gap: var(--space-6); }
.memory-stat { display: flex; flex-direction: column; }
.mem-val { font-size: 26px; font-weight: 800; color: var(--color-text); line-height: 1.1; }
.mem-label { font-size: var(--text-xs); color: var(--color-text-3); margin-top: 4px; }
.memory-level-badge { display: inline-block; margin-top: var(--space-3); font-size: var(--text-xs); padding: 3px var(--space-3); border-radius: var(--radius-full); background: var(--accent-primary-10); color: var(--color-accent); }
.memory-hint { font-size: var(--text-xs); color: var(--color-text-3); margin-top: var(--space-3); line-height: 1.6; }

/* 薄弱/已掌握原先红底红字、绿底绿字两套色相；统一成中性胶囊，薄弱项靠主色文字区分 */
.mem-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: var(--space-2); align-items: center; }
.mem-tag { font-size: var(--text-2xs); padding: 3px 10px; border-radius: 9px; border: 1px solid var(--color-border); background: var(--color-surface-2); color: var(--color-text-2); font: inherit; font-size: var(--text-2xs); cursor: pointer; }
.mem-tag.weak { color: var(--color-accent); border-color: var(--accent-primary-20); background: var(--accent-primary-05); }
.mem-tag.mastered { color: var(--color-text-2); }
.mem-tag.clickable { transition: var(--transition); }
.mem-tag.clickable:hover { border-color: var(--color-border-focus); }
.mem-tag-label { font-size: var(--text-2xs); color: var(--color-text-3); }

.mem-actions { margin-top: var(--space-3); padding-top: var(--space-3); border-top: 1px solid var(--color-border); }
.mem-actions-title { font-size: var(--text-sm); font-weight: 600; color: var(--color-text); margin-bottom: var(--space-2); }
.mem-action-row { display: flex; gap: var(--space-2); flex-wrap: wrap; }
.mem-action-btn { padding: 8px 14px; border-radius: 9px; border: 1px solid var(--color-border); background: var(--color-surface-2); color: var(--color-text-2); font-size: var(--text-sm); cursor: pointer; transition: var(--transition); }
.mem-action-btn:hover { border-color: var(--color-border-focus); color: var(--color-text); }

.mem-empty { font-size: var(--text-sm); color: var(--color-text-3); padding: var(--space-2) 0; }
.mem-context { color: var(--color-text-2); line-height: 1.7; max-height: 200px; overflow-y: auto; white-space: pre-wrap; font-size: 12px; }
.context-card { grid-column: 1 / -1; }
/* 掌握度卡内容最多，独自半列时右侧留白，改为整行 */
.mastery-card { grid-column: 1 / -1; }
.mem-group { margin-bottom: var(--space-3); }

@media (max-width: 768px) {
  .memory-grid { grid-template-columns: 1fr; }
  .context-card { grid-column: auto; }
}
@media (max-width: 640px) {
  .mv-title { font-size: 24px; }
  .memory-card { padding: var(--space-4); }
  .mem-action-row { flex-direction: column; }
  .mem-action-btn { width: 100%; text-align: center; }
}
</style>
