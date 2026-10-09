<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { icons } from '@/components/icons'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import SkillCard from '@/components/SkillCard.vue'
import { useSkillStore } from '@/stores/skillStore'

const router = useRouter()
const store = useSkillStore()

/**
 * 本页是「快速开始」引导页。
 * 技能卡片一律来自 skillStore 的真实接口数据，与 /skills 技能市场同源
 * （fetchMarket / fetchOfficial / fetchTemplates + SkillCard 渲染）。
 * 不内置任何写死技能、不伪造使用量/评分；拉不到或为空时渲染空态 + 引导。
 */

// 平台内置技能分类（与技能市场页的分类枚举保持一致）
const SKILL_CATEGORIES = [
  { value: 'teaching', label: '教学讲解' },
  { value: 'quiz', label: '出题练习' },
  { value: 'diagnosis', label: '诊断评估' },
  { value: 'guide', label: '学习引导' },
  { value: 'code', label: '代码实践' },
  { value: 'mindmap', label: '思维导图' },
  { value: 'other', label: '其他' },
]

// 展示列表：优先官方技能，其次市场技能；两者皆空 → 空态
const showcaseItems = computed(() =>
  store.officialSkills.length ? store.officialSkills : store.marketItems,
)

const showcaseTitle = computed(() =>
  store.officialSkills.length
    ? '官方推荐实训技能 · 点击查看 Prompt'
    : '技能市场在售实训技能 · 点击查看 Prompt',
)

// 空态文案：区分「拉不到」与「确实为空」，两种情况都落到空态 + 引导，不做合成兜底
const emptyTitle = computed(() => (store.error ? '技能列表加载失败' : '暂无可展示的技能'))
const emptyDesc = computed(() =>
  store.error
    ? `${store.error}。可前往技能市场重试，或在技能工坊直接创建第一个实训技能。`
    : '技能库当前为空：官方技能需管理员在技能市场执行「播种官方技能」，你也可以直接创建第一个实训技能。',
)

const selectedSkillId = ref('')
const selectedSkill = computed(
  () => showcaseItems.value.find(s => s.id === selectedSkillId.value) ?? null,
)
const selectedPrompt = computed(() => selectedSkill.value?.system_prompt || '')

function selectSkill(id: string) {
  selectedSkillId.value = id
}

function statusLabel(s: string): string {
  return { draft: '草稿', published: '已发布', archived: '已归档' }[s] || s
}

function goToStudio() {
  router.push('/studio')
}
function goToMarket() {
  router.push('/skills')
}

onMounted(async () => {
  await Promise.all([
    store.fetchMarket({ sort_by: 'usage_count' }),
    store.fetchTemplates(),
    store.fetchOfficial(),
  ])
  const first = showcaseItems.value[0]
  if (first) selectedSkillId.value = first.id
})

// ── 创建流程 ──
const flowSteps = [
  {
    step: '01',
    title: '定义技能',
    desc: '命名技能、选择分类、编写 System Prompt（如答辩追问、需求对齐等软素养场景）',
    icon: '',
    accent: 'var(--accent-primary)',
  },
  {
    step: '02',
    title: '配置引擎',
    desc: '选择 LLM 通道、调节温度、挂载岗位知识库并启用 RAG 检索',
    icon: '',
    accent: 'var(--accent-cyan)',
  },
  {
    step: '03',
    title: '发布市场',
    desc: '一键发布到技能市场，供师生在对抗实训中复用',
    icon: '',
    accent: 'var(--accent-pink)',
  },
]

// ── 对比 ──
const comparison = [
  { feature: '用户自定义 AI 技能', mars: true, competitor: false },
  { feature: 'System Prompt 可视化编辑', mars: true, competitor: false },
  { feature: '多模型通道切换', mars: true, competitor: '部分' },
  { feature: 'RAG 知识库挂载', mars: true, competitor: false },
  { feature: '技能市场与分享', mars: true, competitor: false },
  { feature: '技能使用数据分析', mars: true, competitor: false },
]

// ── 统计：全部取自真实接口；三个技能来源全为 0 时不展示统计条 ──
const platformStats = computed(() => [
  { value: String(store.marketTotal), label: '市场技能', color: 'var(--accent-primary)' },
  { value: String(store.officialSkills.length), label: '官方技能', color: 'var(--accent-cyan)' },
  { value: String(store.templates.length), label: '创建模板', color: 'var(--accent-blue)' },
  { value: String(SKILL_CATEGORIES.length), label: '内置分类', color: 'var(--accent-pink)' },
])
const hasStats = computed(
  () => store.marketTotal > 0 || store.officialSkills.length > 0 || store.templates.length > 0,
)
</script>

<template>
  <div class="sp-page">
    <!-- HERO -->
    <section class="sp-hero">
      <div class="sp-hero-badge">
        <span class="sp-badge-dot"></span>
        竞品无法复制的差异化壁垒
      </div>
      <h1 class="sp-hero-title">
        <span class="sp-hero-gradient">AI Skills</span> 实训技能平台
      </h1>
      <p class="sp-hero-desc">
        支持用户自定义 AI 实训技能——教师与学习者可零代码创建、配置、发布职业素养对抗实训 Agent。
        定义 System Prompt、挂载 RAG 知识库、切换多模型通道，让 AI 实训能力<span class="sp-highlight">无限扩展</span>。
      </p>
      <div v-if="hasStats" class="sp-hero-stats">
        <div v-for="s in platformStats" :key="s.label" class="sp-hero-stat">
          <span class="sp-stat-value" :style="{ color: s.color }">{{ s.value }}</span>
          <span class="sp-stat-label">{{ s.label }}</span>
        </div>
      </div>
      <div class="sp-hero-cta">
        <button class="sp-cta-primary" @click="goToStudio">
          <span>创建技能</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
        </button>
        <button class="sp-cta-secondary" @click="goToMarket">浏览技能市场</button>
      </div>
    </section>

    <!-- 创建流程 -->
    <section class="sp-section">
      <div class="sp-section-head">
        <span class="sp-section-idx">三步创建</span>
        <h2 class="sp-section-title">零代码 · 三步上线一个 AI 实训技能</h2>
      </div>
      <div class="sp-flow">
        <div
          v-for="(step, i) in flowSteps"
          :key="step.step"
          class="sp-flow-step"
          :style="{ '--step-accent': step.accent }"
        >
          <div class="sp-step-num">{{ step.step }}</div>
          <div class="sp-step-icon">{{ step.icon }}</div>
          <h3 class="sp-step-title">{{ step.title }}</h3>
          <p class="sp-step-desc">{{ step.desc }}</p>
          <div v-if="i < flowSteps.length - 1" class="sp-flow-arrow">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </div>
        </div>
      </div>
    </section>

    <!-- 技能列表 + 编辑器预览（数据来自 skillStore，与 /skills 同源） -->
    <section class="sp-section">
      <div class="sp-section-head">
        <span class="sp-section-idx">技能速览</span>
        <h2 class="sp-section-title">{{ showcaseTitle }}</h2>
      </div>

      <div class="sp-showcase-layout">
        <!-- 技能卡片列表 -->
        <div>
          <div v-if="store.loading" class="sp-skeleton-grid">
            <Skeleton v-for="i in 4" :key="i" variant="card" />
          </div>
          <EmptyState
            v-else-if="showcaseItems.length === 0"
            :icon="icons.skill"
            :title="emptyTitle"
            :description="emptyDesc"
          >
            <template #action>
              <button class="sp-cta-primary" @click="goToStudio">创建第一个技能</button>
              <button class="sp-cta-secondary" @click="goToMarket">去技能市场看看</button>
            </template>
          </EmptyState>
          <div v-else class="sp-skill-grid">
            <div
              v-for="s in showcaseItems"
              :key="s.id"
              class="sp-skill-slot"
              :class="{ active: selectedSkillId === s.id }"
              @click="selectSkill(s.id)"
            >
              <SkillCard :skill="s" />
            </div>
          </div>
        </div>

        <!-- 编辑器预览面板（仅选中真实技能时渲染） -->
        <aside v-if="selectedSkill" class="sp-editor-preview">
          <div class="sp-editor-header">
            <span class="sp-editor-emoji">{{ selectedSkill.icon }}</span>
            <div>
              <div class="sp-editor-name">{{ selectedSkill.name }}</div>
              <div class="sp-editor-cat">{{ selectedSkill.category_label }}</div>
            </div>
            <span class="sp-editor-live">Prompt 预览</span>
          </div>

          <div class="sp-editor-section">
            <div class="sp-editor-label">System Prompt</div>
            <div class="sp-editor-prompt">
              <pre>{{ selectedPrompt }}</pre>
            </div>
          </div>

          <div class="sp-editor-row">
            <div class="sp-editor-field">
              <span class="sp-field-label">LLM 通道</span>
              <span class="sp-field-value">{{ selectedSkill.llm_channel }}</span>
            </div>
            <div class="sp-editor-field">
              <span class="sp-field-label">温度</span>
              <span class="sp-field-value">{{ selectedSkill.temperature }}</span>
            </div>
            <div class="sp-editor-field">
              <span class="sp-field-label">最大 Token</span>
              <span class="sp-field-value">{{ selectedSkill.max_tokens }}</span>
            </div>
          </div>

          <div class="sp-editor-row">
            <div class="sp-editor-field">
              <span class="sp-field-label">RAG</span>
              <span class="sp-field-value" :class="{ on: selectedSkill.rag_enabled, off: !selectedSkill.rag_enabled }">
                {{ selectedSkill.rag_enabled ? '已启用' : '未启用' }}
              </span>
            </div>
            <div class="sp-editor-field">
              <span class="sp-field-label">分类</span>
              <span class="sp-field-value">{{ selectedSkill.category_label }}</span>
            </div>
            <div class="sp-editor-field">
              <span class="sp-field-label">状态</span>
              <span class="sp-field-value">{{ statusLabel(selectedSkill.status) }}</span>
            </div>
          </div>

          <button class="sp-editor-btn" @click="goToStudio">
            在技能工坊中编辑
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
          </button>
        </aside>
      </div>
    </section>

    <!-- 竞品对比 -->
    <section class="sp-section">
      <div class="sp-section-head">
        <span class="sp-section-idx">差异化</span>
        <h2 class="sp-section-title">芒得很职 vs 传统学习平台</h2>
      </div>
      <div class="sp-compare">
        <div class="sp-compare-head">
          <div class="sp-compare-feature">能力维度</div>
          <div class="sp-compare-mars">芒得很职</div>
          <div class="sp-compare-comp">传统平台</div>
        </div>
        <div
          v-for="c in comparison"
          :key="c.feature"
          class="sp-compare-row"
        >
          <div class="sp-compare-feature">{{ c.feature }}</div>
          <div class="sp-compare-mars">
            <span v-if="c.mars === true" class="sp-check sp-check-yes"></span>
            <span v-else class="sp-check-text">{{ c.mars }}</span>
          </div>
          <div class="sp-compare-comp">
            <span v-if="c.competitor === false" class="sp-check sp-check-no"></span>
            <span v-else-if="c.competitor === '部分'" class="sp-check-text-muted">部分</span>
            <span v-else class="sp-check sp-check-yes"></span>
          </div>
        </div>
      </div>
    </section>

    <!-- 底部 CTA -->
    <section class="sp-bottom-cta">
      <div class="sp-bottom-inner">
        <h2 class="sp-bottom-title">人人都能成为 AI 实训技能创作者</h2>
        <p class="sp-bottom-desc">零代码 · 三步上线 · 全校共享 · 无限扩展</p>
        <div class="sp-bottom-actions">
          <button class="sp-cta-primary" @click="goToStudio">
            <span>立即创建技能</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          </button>
          <button class="sp-cta-secondary" @click="goToMarket">浏览全部技能</button>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.sp-page {
  min-height: 100%;
  overflow-y: auto;
  background: var(--color-canvas);
}

/* ── HERO ── */
.sp-hero {
  position: relative;
  text-align: center;
  padding: var(--space-14) var(--space-8) var(--space-12);
  max-width: 760px;
  margin: 0 auto;
  overflow: hidden;
}
.sp-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background: var(--gradient-hero);
  border-radius: var(--radius-xl);
  z-index: -1;
}
.sp-hero-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px var(--space-4);
  border-radius: var(--radius-full);
  background: var(--accent-primary-10);
  border: 1px solid var(--color-border-glow);
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  color: var(--accent-primary);
  margin-bottom: var(--space-6);
  animation: fade-up 0.5s ease both;
}
.sp-badge-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--accent-primary);
  animation: mars-pulse-soft 2s var(--ease-standard) infinite;
}
.sp-hero-title {
  font-size: clamp(28px, 4vw, var(--text-6xl));
  font-weight: 800;
  letter-spacing: -0.04em;
  margin: 0;
  animation: fade-up 0.5s ease 0.1s both;
}
.sp-hero-gradient {
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.sp-hero-desc {
  font-size: var(--text-md);
  line-height: 1.8;
  color: var(--color-text-2);
  max-width: 560px;
  margin: var(--space-5) auto 0;
  animation: fade-up 0.5s ease 0.2s both;
}
.sp-highlight {
  color: var(--accent-primary);
  font-weight: var(--weight-bold);
}
.sp-hero-stats {
  display: flex;
  justify-content: center;
  gap: var(--space-3);
  margin-top: var(--space-8);
  animation: fade-up 0.5s ease 0.3s both;
}
.sp-hero-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-3) var(--space-5);
  border-radius: var(--radius-md);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  min-width: 90px;
}
.sp-stat-value {
  font-size: var(--text-3xl);
  font-weight: 800;
  font-family: var(--font-mono);
  letter-spacing: -0.03em;
  line-height: var(--leading-none);
}
.sp-stat-label {
  font-size: var(--text-2xs);
  color: var(--color-text-3);
  margin-top: var(--space-1);
}
.sp-hero-cta {
  display: flex;
  gap: var(--space-3);
  justify-content: center;
  margin-top: var(--space-8);
  animation: fade-up 0.5s ease 0.4s both;
}
.sp-cta-primary {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-7);
  border-radius: var(--radius-full);
  border: none;
  background: var(--gradient-primary);
  color: var(--color-text-on-accent);
  font-size: var(--text-md);
  font-weight: var(--weight-bold);
  cursor: pointer;
  transition: var(--transition-bounce);
  box-shadow: 0 8px 24px rgba(var(--accent-rgb),0.30);
}
.sp-cta-primary svg { width: 18px; height: 18px; }
.sp-cta-primary:hover {
  transform: translateY(-2px) scale(1.03);
  box-shadow: 0 12px 32px rgba(var(--accent-rgb),0.40);
}
.sp-cta-secondary {
  padding: var(--space-3) var(--space-6);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-glass-border);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  color: var(--color-text);
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
  cursor: pointer;
  transition: var(--transition);
}
.sp-cta-secondary:hover {
  border-color: var(--color-border-focus);
  transform: translateY(-2px);
}

/* ── 通用区块 ── */
.sp-section {
  max-width: 1100px;
  margin: 0 auto;
  padding: var(--space-10) var(--space-8);
}
.sp-section-head {
  text-align: center;
  margin-bottom: var(--space-7);
}
.sp-section-idx {
  display: block;
  font-size: var(--text-xs);
  font-weight: var(--weight-bold);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent-primary);
  margin-bottom: 6px;
}
.sp-section-title {
  font-size: clamp(var(--text-2xl), 2.5vw, 28px);
  font-weight: var(--weight-bold);
  letter-spacing: -0.03em;
  color: var(--color-text);
  margin: 0;
}

/* ── 创建流程 ── */
.sp-flow {
  display: flex;
  align-items: stretch;
  gap: var(--space-4);
  justify-content: center;
}
.sp-flow-step {
  position: relative;
  flex: 1;
  max-width: 280px;
  padding: var(--space-6);
  border-radius: var(--radius-lg);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  border-top: 3px solid var(--step-accent);
  text-align: center;
  transition: var(--transition);
  animation: fade-up 0.4s ease both;
}
.sp-flow-step:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-card-hover);
}
.sp-step-num {
  font-size: var(--text-xs);
  font-weight: 800;
  font-family: var(--font-mono);
  color: var(--step-accent);
  letter-spacing: 0.1em;
}
.sp-step-icon {
  font-size: 2rem;
  margin: var(--space-3) 0 var(--space-2);
  line-height: var(--leading-none);
}
.sp-step-title {
  font-size: 1.0625rem;
  font-weight: var(--weight-bold);
  color: var(--color-text);
  margin: 0 0 6px;
}
.sp-step-desc {
  font-size: var(--text-sm);
  color: var(--color-text-2);
  line-height: 1.6;
  margin: 0;
}
.sp-flow-arrow {
  position: absolute;
  right: -20px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-text-3);
  z-index: 2;
}
.sp-flow-arrow svg { width: 20px; height: 20px; }

/* ── 技能展示布局 ── */
.sp-showcase-layout {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: var(--space-5);
  align-items: start;
}
.sp-skill-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
.sp-skill-slot {
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  cursor: pointer;
  transition: var(--transition);
}
.sp-skill-slot.active {
  border-color: var(--accent-primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent-primary) 40%, transparent);
}
.sp-skeleton-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
/* ── 编辑器预览 ── */
.sp-editor-preview {
  position: sticky;
  top: 16px;
  padding: var(--space-5);
  border-radius: var(--radius-lg);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur-heavy));
  -webkit-backdrop-filter: blur(var(--glass-blur-heavy));
  border: 1px solid var(--color-glass-border);
  box-shadow: var(--shadow-card);
}
.sp-editor-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border);
  margin-bottom: var(--space-4);
}
.sp-editor-emoji {
  font-size: 1.75rem;
  line-height: var(--leading-none);
}
.sp-editor-name {
  font-size: var(--text-md);
  font-weight: var(--weight-bold);
  color: var(--color-text);
}
.sp-editor-cat {
  font-size: var(--text-2xs);
  color: var(--color-text-3);
}
.sp-editor-live {
  margin-left: auto;
  font-size: 0.5625rem;
  font-weight: var(--weight-bold);
  padding: 3px var(--space-2);
  border-radius: var(--radius-full);
  background: rgba(var(--success-rgb),0.12);
  color: var(--accent-success);
  letter-spacing: 0.05em;
}
.sp-editor-section {
  margin-bottom: var(--space-4);
}
.sp-editor-label {
  font-size: var(--text-2xs);
  font-weight: var(--weight-bold);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-3);
  margin-bottom: 6px;
}
.sp-editor-prompt {
  padding: var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  max-height: 120px;
  overflow-y: auto;
}
.sp-editor-prompt pre {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: 1.6;
  color: var(--color-text-2);
  white-space: pre-wrap;
  margin: 0;
}
.sp-editor-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}
.sp-editor-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2) 10px;
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  min-width: 0;
}
.sp-field-label {
  font-size: 0.625rem;
  color: var(--color-text-3);
  font-weight: var(--weight-semibold);
}
.sp-field-value {
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  color: var(--color-text);
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}
.sp-field-value.on { color: var(--accent-success); }
.sp-field-value.off { color: var(--color-text-3); }
.sp-editor-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 10px var(--space-4);
  border-radius: var(--radius-md);
  border: none;
  background: var(--gradient-primary);
  color: var(--color-text-on-accent);
  font-size: var(--text-sm);
  font-weight: var(--weight-bold);
  cursor: pointer;
  transition: var(--transition);
  margin-top: var(--space-1);
}
.sp-editor-btn svg { width: 16px; height: 16px; }
.sp-editor-btn:hover {
  opacity: 0.92;
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(var(--accent-rgb),0.25);
}

/* ── 竞品对比 ── */
.sp-compare {
  max-width: 680px;
  margin: 0 auto;
  border-radius: var(--radius-lg);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  overflow: hidden;
}
.sp-compare-head {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  padding: 14px var(--space-5);
  background: var(--color-surface-2);
  border-bottom: 1px solid var(--color-border);
  font-size: var(--text-sm);
  font-weight: var(--weight-bold);
  color: var(--color-text);
}
.sp-compare-head .sp-compare-mars { color: var(--accent-primary); text-align: center; }
.sp-compare-head .sp-compare-comp { color: var(--color-text-3); text-align: center; }
.sp-compare-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--color-border-light);
  align-items: center;
  transition: var(--transition);
}
.sp-compare-row:last-child { border-bottom: none; }
.sp-compare-row:hover { background: var(--color-surface-hover); }
.sp-compare-feature {
  font-size: var(--text-sm);
  color: var(--color-text-2);
}
.sp-compare-mars, .sp-compare-comp {
  text-align: center;
}
.sp-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px; height: 24px;
  border-radius: 50%;
  font-size: var(--text-base);
  font-weight: 800;
}
.sp-check-yes {
  background: rgba(var(--success-rgb),0.15);
  color: var(--accent-success);
}
.sp-check-no {
  background: rgba(var(--danger-rgb),0.10);
  color: var(--accent-danger);
}
.sp-check-text {
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  color: var(--accent-success);
}
.sp-check-text-muted {
  font-size: var(--text-xs);
  color: var(--color-text-3);
}

/* ── 底部 CTA ── */
.sp-bottom-cta {
  padding: var(--space-12) var(--space-8);
}
.sp-bottom-inner {
  max-width: 560px;
  margin: 0 auto;
  text-align: center;
  padding: var(--space-10);
  border-radius: var(--radius-xl);
  background: var(--gradient-hero);
  border: 1px solid var(--color-glass-border);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.sp-bottom-title {
  font-size: clamp(var(--text-xl), 2.2vw, var(--text-3xl));
  font-weight: var(--weight-bold);
  letter-spacing: -0.03em;
  color: var(--color-text);
  margin: 0 0 var(--space-2);
}
.sp-bottom-desc {
  font-size: var(--text-sm);
  color: var(--color-text-2);
  margin: 0 0 var(--space-6);
}
.sp-bottom-actions {
  display: flex;
  gap: var(--space-3);
  justify-content: center;
  flex-wrap: wrap;
}

/* ── 响应式 ── */
@media (max-width: 900px) {
  .sp-showcase-layout { grid-template-columns: 1fr; }
  .sp-editor-preview { position: static; }
  .sp-flow { flex-direction: column; align-items: center; }
  .sp-flow-step { max-width: 100%; width: 100%; }
  .sp-flow-arrow { display: none; }
}
@media (max-width: 600px) {
  .sp-skill-grid { grid-template-columns: 1fr; }
  .sp-skeleton-grid { grid-template-columns: 1fr; }
  .sp-hero-stats { flex-wrap: wrap; }
  .sp-hero-cta { flex-direction: column; }
  .sp-section { padding: var(--space-7) var(--space-5); }
  .sp-hero { padding: var(--space-9) var(--space-5) var(--space-8); }
}
</style>
