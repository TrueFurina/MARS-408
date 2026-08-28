<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

// ── 示例技能 ──
interface SkillShowcase {
  id: string
  name: string
  emoji: string
  category: string
  categoryLabel: string
  desc: string
  prompt: string
  uses: number
  rating: number
  tags: string[]
  rag: boolean
  accent: string
}

const skills: SkillShowcase[] = [
  {
    id: 's1',
    name: '考研重点提炼',
    emoji: '🎯',
    category: 'teaching',
    categoryLabel: '教学讲解',
    desc: '自动提取 408 各章节高频考点，结合历年真题权重生成重点清单，附带记忆口诀与易错预警。',
    prompt: '你是 408 考研重点分析专家。请根据以下章节内容，提取 Top 10 高频考点...',
    uses: 1284,
    rating: 4.9,
    tags: ['数据结构', '高频考点', '真题权重'],
    rag: true,
    accent: 'var(--subject-ds)',
  },
  {
    id: 's2',
    name: '错题变式出题',
    emoji: '🔄',
    category: 'quiz',
    categoryLabel: '出题练习',
    desc: '基于学生错题记录，自动生成同知识点不同题型的变式题目，确保「错过的不再错」。',
    prompt: '你是 408 出题专家。请根据以下错题，生成 3 道同知识点不同考查角度的变式题...',
    uses: 967,
    rating: 4.8,
    tags: ['变式出题', '错题驱动', '自适应'],
    rag: true,
    accent: 'var(--subject-cn)',
  },
  {
    id: 's3',
    name: '知识点诊断',
    emoji: '🔍',
    category: 'diagnosis',
    categoryLabel: '诊断评估',
    desc: '通过对话式追问定位学生知识盲区，生成可视化诊断报告与针对性补救路径。',
    prompt: '你是学习诊断专家。请通过苏格拉底式追问，定位学生在以下知识点的理解偏差...',
    uses: 743,
    rating: 4.7,
    tags: ['诊断', '苏格拉底', '补救路径'],
    rag: true,
    accent: 'var(--subject-co)',
  },
  {
    id: 's4',
    name: '代码实战辅导',
    emoji: '💻',
    category: 'code',
    categoryLabel: '代码实践',
    desc: '数据结构算法实战：自动生成编程题、实时代码审查、复杂度分析与优化建议。',
    prompt: '你是算法辅导教练。请根据学生水平生成一道编程题，并提供逐步提示而非直接解答...',
    uses: 612,
    rating: 4.8,
    tags: ['算法', '代码审查', '复杂度'],
    rag: false,
    accent: 'var(--subject-os)',
  },
  {
    id: 's5',
    name: '思维导图生成',
    emoji: '🧠',
    category: 'mindmap',
    categoryLabel: '思维导图',
    desc: '一键将任意知识点转化为结构化思维导图，标注先修关系与考点权重。',
    prompt: '请将以下知识点转化为 Markdown 格式的思维导图，标注先修关系和考点权重...',
    uses: 534,
    rating: 4.6,
    tags: ['思维导图', '结构化', '先修关系'],
    rag: true,
    accent: 'var(--accent-primary)',
  },
  {
    id: 's6',
    name: '苏格拉底追问',
    emoji: '🗣️',
    category: 'teaching',
    categoryLabel: '教学讲解',
    desc: '不直接给答案，而是通过层层追问引导学生自主发现知识漏洞，培养深度理解。',
    prompt: '你是苏格拉底式教学导师。请用追问的方式引导学生理解以下概念，不要直接给出答案...',
    uses: 489,
    rating: 4.9,
    tags: ['苏格拉底', '深度理解', '引导式'],
    rag: false,
    accent: 'var(--accent-cyan)',
  },
]

// ── 创建流程 ──
const flowSteps = [
  {
    step: '01',
    title: '定义技能',
    desc: '命名技能、选择分类、编写 System Prompt',
    icon: '📝',
    accent: 'var(--accent-primary)',
  },
  {
    step: '02',
    title: '配置引擎',
    desc: '选择 LLM 通道、调节温度、启用 RAG 检索',
    icon: '⚙️',
    accent: 'var(--accent-cyan)',
  },
  {
    step: '03',
    title: '发布市场',
    desc: '一键发布到技能市场，供全校师生使用',
    icon: '🚀',
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

// ── 选中技能（模拟编辑器预览）──
const selectedSkill = ref<SkillShowcase>(skills[0]!)
const selectedPrompt = computed(() => selectedSkill.value.prompt)

function selectSkill(s: SkillShowcase) {
  selectedSkill.value = s
}

function goToStudio() {
  router.push('/studio')
}
function goToMarket() {
  router.push('/skills')
}

// ── 统计 ──
const platformStats = [
  { value: '∞', label: '可扩展技能', color: 'var(--accent-primary)' },
  { value: '6', label: '官方示例', color: 'var(--accent-cyan)' },
  { value: '4', label: 'LLM 通道', color: 'var(--accent-blue)' },
  { value: '7', label: '技能分类', color: 'var(--accent-pink)' },
]
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
        <span class="sp-hero-gradient">AI Skills</span> 教学技能平台
      </h1>
      <p class="sp-hero-desc">
        国内首创用户自定义 AI 教学技能平台——教师与学习者可零代码创建、配置、发布个性化教学 Agent。
        定义 System Prompt、挂载 RAG 知识库、切换多模型通道，让 AI 教学能力<span class="sp-highlight">无限扩展</span>。
      </p>
      <div class="sp-hero-stats">
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
        <h2 class="sp-section-title">零代码 · 三步上线一个 AI 教学技能</h2>
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

    <!-- 技能列表 + 编辑器预览 -->
    <section class="sp-section">
      <div class="sp-section-head">
        <span class="sp-section-idx">示例技能</span>
        <h2 class="sp-section-title">官方推荐教学技能 · 点击查看 Prompt</h2>
      </div>

      <div class="sp-showcase-layout">
        <!-- 技能卡片列表 -->
        <div class="sp-skill-grid">
          <article
            v-for="s in skills"
            :key="s.id"
            class="sp-skill-card"
            :class="{ active: selectedSkill.id === s.id }"
            :style="{ '--card-accent': s.accent }"
            @click="selectSkill(s)"
          >
            <div class="sp-card-top">
              <span class="sp-card-emoji">{{ s.emoji }}</span>
              <span class="sp-card-category" :style="{ color: s.accent, background: `color-mix(in srgb, ${s.accent} 12%, transparent)` }">{{ s.categoryLabel }}</span>
            </div>
            <h3 class="sp-card-name">{{ s.name }}</h3>
            <p class="sp-card-desc">{{ s.desc }}</p>
            <div class="sp-card-tags">
              <span v-for="t in s.tags" :key="t" class="sp-card-tag">{{ t }}</span>
            </div>
            <div class="sp-card-footer">
              <div class="sp-card-meta">
                <span class="sp-meta-uses">🔥 {{ s.uses }}</span>
                <span class="sp-meta-rating">⭐ {{ s.rating }}</span>
              </div>
              <span v-if="s.rag" class="sp-rag-badge">RAG</span>
            </div>
          </article>
        </div>

        <!-- 编辑器预览面板 -->
        <aside class="sp-editor-preview">
          <div class="sp-editor-header">
            <span class="sp-editor-emoji">{{ selectedSkill.emoji }}</span>
            <div>
              <div class="sp-editor-name">{{ selectedSkill.name }}</div>
              <div class="sp-editor-cat">{{ selectedSkill.categoryLabel }}</div>
            </div>
            <span class="sp-editor-live">实时预览</span>
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
              <span class="sp-field-value">讯飞星火</span>
            </div>
            <div class="sp-editor-field">
              <span class="sp-field-label">温度</span>
              <span class="sp-field-value">0.7</span>
            </div>
            <div class="sp-editor-field">
              <span class="sp-field-label">RAG</span>
              <span class="sp-field-value" :class="{ on: selectedSkill.rag, off: !selectedSkill.rag }">
                {{ selectedSkill.rag ? '已启用' : '未启用' }}
              </span>
            </div>
          </div>

          <div class="sp-editor-row">
            <div class="sp-editor-field">
              <span class="sp-field-label">最大 Token</span>
              <span class="sp-field-value">2048</span>
            </div>
            <div class="sp-editor-field">
              <span class="sp-field-label">使用次数</span>
              <span class="sp-field-value">{{ selectedSkill.uses }}</span>
            </div>
            <div class="sp-editor-field">
              <span class="sp-field-label">评分</span>
              <span class="sp-field-value">⭐ {{ selectedSkill.rating }}</span>
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
        <h2 class="sp-section-title">MARS-408 vs 传统学习平台</h2>
      </div>
      <div class="sp-compare">
        <div class="sp-compare-head">
          <div class="sp-compare-feature">能力维度</div>
          <div class="sp-compare-mars">MARS-408</div>
          <div class="sp-compare-comp">传统平台</div>
        </div>
        <div
          v-for="c in comparison"
          :key="c.feature"
          class="sp-compare-row"
        >
          <div class="sp-compare-feature">{{ c.feature }}</div>
          <div class="sp-compare-mars">
            <span v-if="c.mars === true" class="sp-check sp-check-yes">✓</span>
            <span v-else class="sp-check-text">{{ c.mars }}</span>
          </div>
          <div class="sp-compare-comp">
            <span v-if="c.competitor === false" class="sp-check sp-check-no">✕</span>
            <span v-else-if="c.competitor === '部分'" class="sp-check-text-muted">部分</span>
            <span v-else class="sp-check sp-check-yes">✓</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 底部 CTA -->
    <section class="sp-bottom-cta">
      <div class="sp-bottom-inner">
        <h2 class="sp-bottom-title">人人都能成为 AI 教学技能创作者</h2>
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
  padding: 56px 32px 48px;
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
  gap: 8px;
  padding: 6px 16px;
  border-radius: var(--radius-full);
  background: var(--accent-primary-10);
  border: 1px solid var(--color-border-glow);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--accent-primary);
  margin-bottom: 24px;
  animation: fade-up 0.5s ease both;
}
.sp-badge-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--accent-primary);
  box-shadow: 0 0 8px var(--accent-primary);
  animation: pulse-glow 2s ease-in-out infinite;
}
.sp-hero-title {
  font-size: clamp(28px, 4vw, 44px);
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
  font-size: 0.9375rem;
  line-height: 1.8;
  color: var(--color-text-2);
  max-width: 560px;
  margin: 20px auto 0;
  animation: fade-up 0.5s ease 0.2s both;
}
.sp-highlight {
  color: var(--accent-primary);
  font-weight: 700;
}
.sp-hero-stats {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 32px;
  animation: fade-up 0.5s ease 0.3s both;
}
.sp-hero-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 20px;
  border-radius: var(--radius-md);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  min-width: 90px;
}
.sp-stat-value {
  font-size: 1.5rem;
  font-weight: 800;
  font-family: var(--font-mono);
  letter-spacing: -0.03em;
  line-height: 1;
}
.sp-stat-label {
  font-size: 0.6875rem;
  color: var(--color-text-3);
  margin-top: 4px;
}
.sp-hero-cta {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 32px;
  animation: fade-up 0.5s ease 0.4s both;
}
.sp-cta-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 28px;
  border-radius: var(--radius-full);
  border: none;
  background: var(--gradient-primary);
  color: #fff;
  font-size: 0.9375rem;
  font-weight: 700;
  cursor: pointer;
  transition: var(--transition-bounce);
  box-shadow: 0 8px 24px rgba(124,106,242,0.30);
}
.sp-cta-primary svg { width: 18px; height: 18px; }
.sp-cta-primary:hover {
  transform: translateY(-2px) scale(1.03);
  box-shadow: 0 12px 32px rgba(124,106,242,0.40);
}
.sp-cta-secondary {
  padding: 12px 24px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-glass-border);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  color: var(--color-text);
  font-size: 0.9375rem;
  font-weight: 600;
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
  padding: 40px 32px;
}
.sp-section-head {
  text-align: center;
  margin-bottom: 28px;
}
.sp-section-idx {
  display: block;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent-primary);
  margin-bottom: 6px;
}
.sp-section-title {
  font-size: clamp(20px, 2.5vw, 28px);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--color-text);
  margin: 0;
}

/* ── 创建流程 ── */
.sp-flow {
  display: flex;
  align-items: stretch;
  gap: 16px;
  justify-content: center;
}
.sp-flow-step {
  position: relative;
  flex: 1;
  max-width: 280px;
  padding: 24px;
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
  font-size: 0.75rem;
  font-weight: 800;
  font-family: var(--font-mono);
  color: var(--step-accent);
  letter-spacing: 0.1em;
}
.sp-step-icon {
  font-size: 2rem;
  margin: 12px 0 8px;
  line-height: 1;
}
.sp-step-title {
  font-size: 1.0625rem;
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 6px;
}
.sp-step-desc {
  font-size: 0.8125rem;
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
  gap: 20px;
  align-items: start;
}
.sp-skill-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
.sp-skill-card {
  padding: 20px;
  border-radius: var(--radius-lg);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  cursor: pointer;
  transition: var(--transition);
  animation: fade-up 0.4s ease both;
}
.sp-skill-card:hover {
  transform: translateY(-3px);
  border-color: var(--card-accent);
  box-shadow: 0 8px 24px rgba(0,0,0,0.25), 0 0 0 1px var(--card-accent);
}
.sp-skill-card.active {
  border-color: var(--card-accent);
  box-shadow: 0 0 0 2px var(--card-accent), var(--shadow-card-hover);
  background: color-mix(in srgb, var(--card-accent) 4%, var(--color-glass));
}
.sp-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.sp-card-emoji {
  font-size: 1.75rem;
  line-height: 1;
}
.sp-card-category {
  font-size: 0.625rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: var(--radius-full);
}
.sp-card-name {
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text);
  margin: 0 0 6px;
}
.sp-card-desc {
  font-size: 0.75rem;
  line-height: 1.6;
  color: var(--color-text-2);
  margin: 0 0 12px;
}
.sp-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
}
.sp-card-tag {
  font-size: 0.625rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--color-surface-hover);
  color: var(--color-text-3);
}
.sp-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.sp-card-meta {
  display: flex;
  gap: 10px;
  font-size: 0.6875rem;
  color: var(--color-text-3);
}
.sp-rag-badge {
  font-size: 0.5625rem;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: rgba(6,182,212,0.12);
  color: var(--accent-cyan);
  letter-spacing: 0.05em;
}

/* ── 编辑器预览 ── */
.sp-editor-preview {
  position: sticky;
  top: 16px;
  padding: 20px;
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
  padding-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: 16px;
}
.sp-editor-emoji {
  font-size: 1.75rem;
  line-height: 1;
}
.sp-editor-name {
  font-size: 0.9375rem;
  font-weight: 700;
  color: var(--color-text);
}
.sp-editor-cat {
  font-size: 0.6875rem;
  color: var(--color-text-3);
}
.sp-editor-live {
  margin-left: auto;
  font-size: 0.5625rem;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: var(--radius-full);
  background: rgba(34,197,94,0.12);
  color: var(--accent-success);
  letter-spacing: 0.05em;
}
.sp-editor-section {
  margin-bottom: 16px;
}
.sp-editor-label {
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-3);
  margin-bottom: 6px;
}
.sp-editor-prompt {
  padding: 12px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  max-height: 120px;
  overflow-y: auto;
}
.sp-editor-prompt pre {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  line-height: 1.6;
  color: var(--color-text-2);
  white-space: pre-wrap;
  margin: 0;
}
.sp-editor-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 12px;
}
.sp-editor-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}
.sp-field-label {
  font-size: 0.625rem;
  color: var(--color-text-3);
  font-weight: 600;
}
.sp-field-value {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text);
  font-family: var(--font-mono);
}
.sp-field-value.on { color: var(--accent-success); }
.sp-field-value.off { color: var(--color-text-3); }
.sp-editor-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 10px 16px;
  border-radius: var(--radius-md);
  border: none;
  background: var(--gradient-primary);
  color: #fff;
  font-size: 0.8125rem;
  font-weight: 700;
  cursor: pointer;
  transition: var(--transition);
  margin-top: 4px;
}
.sp-editor-btn svg { width: 16px; height: 16px; }
.sp-editor-btn:hover {
  opacity: 0.92;
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(124,106,242,0.25);
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
  padding: 14px 20px;
  background: var(--color-surface-2);
  border-bottom: 1px solid var(--color-border);
  font-size: 0.8125rem;
  font-weight: 700;
  color: var(--color-text);
}
.sp-compare-head .sp-compare-mars { color: var(--accent-primary); text-align: center; }
.sp-compare-head .sp-compare-comp { color: var(--color-text-3); text-align: center; }
.sp-compare-row {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  padding: 12px 20px;
  border-bottom: 1px solid var(--color-border-light);
  align-items: center;
  transition: var(--transition);
}
.sp-compare-row:last-child { border-bottom: none; }
.sp-compare-row:hover { background: var(--color-surface-hover); }
.sp-compare-feature {
  font-size: 0.8125rem;
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
  font-size: 0.875rem;
  font-weight: 800;
}
.sp-check-yes {
  background: rgba(34,197,94,0.15);
  color: var(--accent-success);
}
.sp-check-no {
  background: rgba(239,68,68,0.10);
  color: var(--accent-danger);
}
.sp-check-text {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--accent-success);
}
.sp-check-text-muted {
  font-size: 0.75rem;
  color: var(--color-text-3);
}

/* ── 底部 CTA ── */
.sp-bottom-cta {
  padding: 48px 32px;
}
.sp-bottom-inner {
  max-width: 560px;
  margin: 0 auto;
  text-align: center;
  padding: 40px;
  border-radius: var(--radius-xl);
  background: var(--gradient-hero);
  border: 1px solid var(--color-glass-border);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.sp-bottom-title {
  font-size: clamp(18px, 2.2vw, 24px);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--color-text);
  margin: 0 0 8px;
}
.sp-bottom-desc {
  font-size: 0.8125rem;
  color: var(--color-text-2);
  margin: 0 0 24px;
}
.sp-bottom-actions {
  display: flex;
  gap: 12px;
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
  .sp-hero-stats { flex-wrap: wrap; }
  .sp-hero-cta { flex-direction: column; }
  .sp-section { padding: 28px 20px; }
  .sp-hero { padding: 36px 20px 32px; }
}
</style>
