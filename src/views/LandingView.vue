<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { icons } from '@/components/icons'

const router = useRouter()

// ── 数据指标药丸 ──
const metrics = [
  { value: '8', label: '协作 Agent', color: 'var(--accent-primary)' },
  { value: '≥10', label: '资源类型', color: 'var(--accent-cyan)' },
  { value: '1883', label: '知识 chunks', color: 'var(--accent-blue)' },
  { value: '613', label: '图谱节点', color: 'var(--accent-pink)' },
]

// ── 三大创新亮点 ──
const innovations = [
  {
    id: 'xfyun',
    badge: '创新 01',
    title: '讯飞 10 项能力集成',
    subtitle: 'XFYun Full-Stack Integration',
    desc: '深度对接讯飞星火大模型 10 项核心能力——语音识别、语音合成、图像理解、OCR、数学能力、代码生成等，构建多模态教学引擎。',
    stat: '10',
    statLabel: '项能力',
    accent: 'var(--accent-primary)',
    gradient: 'linear-gradient(135deg, color-mix(in srgb, var(--accent-primary) 12%, transparent), color-mix(in srgb, var(--accent-primary) 2%, transparent))',
    iconSvg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>`,
    tags: ['语音识别', '语音合成', 'OCR', '图像理解', '代码生成', '数学推理'],
  },
  {
    id: 'skills',
    badge: '创新 02',
    title: 'AI Skills 教学技能平台',
    subtitle: 'User-Defined Teaching Skills',
    desc: '业内首创用户自定义 AI 教学技能平台——教师与学习者可零代码创建、配置、发布个性化教学 Agent，定义 System Prompt、RAG 策略与多模型通道。',
    stat: '∞',
    statLabel: '可扩展技能',
    accent: 'var(--accent-cyan)',
    gradient: 'linear-gradient(135deg, color-mix(in srgb, var(--accent-cyan) 12%, transparent), color-mix(in srgb, var(--accent-cyan) 2%, transparent))',
    iconSvg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>`,
    tags: ['零代码创建', 'System Prompt', 'RAG 检索', '多模型通道', '技能市场', '一键发布'],
  },
  {
    id: 'graph',
    badge: '创新 03',
    title: '408 领域知识图谱',
    subtitle: 'Domain Knowledge Graph',
    desc: '构建覆盖计算机考研 408 全科的知识图谱视图——26 大知识群组、2083 条知识向量，四科分色着色，支撑知识点关联浏览与个性化路径规划（v1 规则原型）。',
    stat: '26',
    statLabel: '知识群组 / 2083 向量',
    accent: 'var(--accent-pink)',
    gradient: 'linear-gradient(135deg, color-mix(in srgb, var(--accent-pink) 12%, transparent), color-mix(in srgb, var(--accent-pink) 2%, transparent))',
    iconSvg: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><line x1="12" y1="7" x2="5" y2="17"/><line x1="12" y1="7" x2="19" y2="17"/><line x1="5" y1="19" x2="19" y2="19"/></svg>`,
    tags: ['数据结构', '计算机网络', '计算机组成', '操作系统', '先修推理', '路径规划'],
  },
]

// ── 四科分色 ──
const subjects = [
  { name: '数据结构', code: 'DS', color: 'var(--subject-ds)', nodes: 7 },
  { name: '计算机网络', code: 'CN', color: 'var(--subject-cn)', nodes: 7 },
  { name: '计算机组成', code: 'CO', color: 'var(--subject-co)', nodes: 7 },
  { name: '操作系统', code: 'OS', color: 'var(--subject-os)', nodes: 5 },
]

// ── 滚动揭示动画 ──
const scrollY = ref(0)
function onScroll() { scrollY.value = window.scrollY }
onMounted(() => {
  const el = document.querySelector('.main-content')
  el?.addEventListener('scroll', onScroll)
  // fallback: window scroll
  window.addEventListener('scroll', onScroll)
})
onUnmounted(() => {
  document.querySelector('.main-content')?.removeEventListener('scroll', onScroll)
  window.removeEventListener('scroll', onScroll)
})

function enterSystem() {
  router.push('/')
}
function goToGraph() {
  router.push('/knowledge-graph')
}
function goToSkills() {
  router.push('/skill-platform')
}
</script>

<template>
  <div class="landing">
    <!-- 背景光晕层 -->
    <div class="bg-orbs">
      <div class="orb orb-1"></div>
      <div class="orb orb-2"></div>
      <div class="orb orb-3"></div>
    </div>

    <!-- 顶部品牌条 -->
    <header class="landing-nav">
      <div class="nav-brand">
        <span class="nav-logo" v-html="icons.logo"></span>
        <span class="nav-text">MARS-408</span>
      </div>
      <div class="nav-links">
        <button class="nav-link" @click="enterSystem">进入系统</button>
        <button class="nav-link" @click="goToGraph">知识图谱</button>
        <button class="nav-link" @click="goToSkills">技能平台</button>
      </div>
    </header>

    <!-- HERO 区 -->
    <section class="hero">
      <div class="hero-badge">
        <span class="hero-badge-dot"></span>
        国家级竞赛参赛作品 · 个性化学习多智能体系统
      </div>
      <h1 class="hero-title">
        <span class="hero-title-line">MARS-408</span>
        <span class="hero-title-sub">基于大模型的个性化资源生成与学习多智能体系统</span>
      </h1>
      <p class="hero-desc">
        以 8 个协作 Agent 为核心引擎，深度融合讯飞星火 10 项多模态能力、用户自定义 AI 教学技能平台、
        与覆盖 408 全科的领域知识图谱，为每一位考研学子构建「会自愈的个性化学习闭环」。
      </p>

      <!-- 数据指标药丸 -->
      <div class="metric-pills">
        <div v-for="m in metrics" :key="m.label" class="metric-pill">
          <span class="metric-value" :style="{ color: m.color }">{{ m.value }}</span>
          <span class="metric-label">{{ m.label }}</span>
        </div>
      </div>

      <!-- CTA -->
      <div class="hero-cta">
        <button class="cta-primary" @click="enterSystem">
          <span>进入系统</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
        </button>
        <button class="cta-secondary" @click="goToGraph">
          <span v-html="icons.knowledge" class="cta-icon"></span>
          <span>探索知识图谱</span>
        </button>
      </div>
    </section>

    <!-- 三大创新亮点 -->
    <section class="innovations">
      <div class="section-label-row">
        <span class="section-idx">三大真护城河</span>
        <h2 class="section-heading">竞品无法复制的核心壁垒</h2>
      </div>

      <div class="innovation-grid">
        <article
          v-for="(inn, i) in innovations"
          :key="inn.id"
          class="innovation-card"
          :style="{ '--card-accent': inn.accent, '--card-gradient': inn.gradient, animationDelay: i * 0.12 + 's' }"
        >
          <div class="inn-header">
            <span class="inn-badge">{{ inn.badge }}</span>
            <div class="inn-icon" v-html="inn.iconSvg"></div>
          </div>
          <h3 class="inn-title">{{ inn.title }}</h3>
          <div class="inn-subtitle">{{ inn.subtitle }}</div>
          <p class="inn-desc">{{ inn.desc }}</p>
          <div class="inn-stat">
            <span class="inn-stat-value" :style="{ color: inn.accent }">{{ inn.stat }}</span>
            <span class="inn-stat-label">{{ inn.statLabel }}</span>
          </div>
          <div class="inn-tags">
            <span v-for="t in inn.tags" :key="t" class="inn-tag">{{ t }}</span>
          </div>
          <div class="inn-glow"></div>
        </article>
      </div>
    </section>

    <!-- 四科分色条 -->
    <section class="subjects-band">
      <div class="section-label-row">
        <span class="section-idx">408 全科覆盖</span>
        <h2 class="section-heading">四科分色 · 知识全域贯通</h2>
      </div>
      <div class="subjects-grid">
        <div
          v-for="(s, i) in subjects"
          :key="s.code"
          class="subject-chip"
          :style="{ '--subj-color': s.color, animationDelay: i * 0.08 + 's' }"
        >
          <div class="subj-dot"></div>
          <div class="subj-info">
            <span class="subj-name">{{ s.name }}</span>
            <span class="subj-nodes">{{ s.nodes }} 知识群组</span>
          </div>
          <span class="subj-code">{{ s.code }}</span>
        </div>
      </div>
    </section>

    <!-- 底部 CTA -->
    <section class="bottom-cta">
      <div class="bottom-cta-inner">
        <h2 class="bottom-title">让每一道错题，都成为成长的起点</h2>
        <p class="bottom-desc">10 Agent 协作 · 10 项多模态能力 · 无限可扩展教学技能 · 26 大知识群组</p>
        <button class="cta-primary cta-large" @click="enterSystem">
          <span>立即体验</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
        </button>
      </div>
    </section>

    <footer class="landing-footer">
      <span>MARS-408 · 基于大模型的个性化资源生成与学习多智能体系统</span>
      <span class="footer-tech">Vue 3 + Vite + TypeScript · 玻璃态发光设计系统 v8</span>
    </footer>
  </div>
</template>

<style scoped>
.landing {
  position: relative;
  min-height: 100%;
  background: var(--color-canvas);
  color: var(--color-text);
  font-family: var(--font-sans);
  overflow-y: auto;
  overflow-x: hidden;
}

/* ── 背景光晕 ── */
.bg-orbs {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.5;
}
.orb-1 {
  width: 500px; height: 500px;
  top: -100px; left: -100px;
  background: radial-gradient(circle, color-mix(in srgb, var(--accent-primary) 25%, transparent), transparent 70%);
  animation: orb-drift-1 18s ease-in-out infinite alternate;
}
.orb-2 {
  width: 400px; height: 400px;
  top: 30%; right: -80px;
  background: radial-gradient(circle, color-mix(in srgb, var(--accent-tertiary) 18%, transparent), transparent 70%);
  animation: orb-drift-2 22s ease-in-out infinite alternate;
}
.orb-3 {
  width: 450px; height: 450px;
  bottom: -100px; left: 30%;
  background: radial-gradient(circle, color-mix(in srgb, var(--accent-pink) 12%, transparent), transparent 70%);
  animation: orb-drift-3 20s ease-in-out infinite alternate;
}
@keyframes orb-drift-1 { to { transform: translate(60px, 40px) scale(1.1); } }
@keyframes orb-drift-2 { to { transform: translate(-50px, 60px) scale(1.15); } }
@keyframes orb-drift-3 { to { transform: translate(40px, -50px) scale(1.1); } }

/* ── 顶部导航 ── */
.landing-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  height: 64px;
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur-heavy));
  -webkit-backdrop-filter: blur(var(--glass-blur-heavy));
  border-bottom: 1px solid var(--color-glass-border);
}
.nav-brand {
  display: flex; align-items: center; gap: 10px;
  font-weight: 700; font-size: 1.0625rem;
  letter-spacing: -0.02rem;
}
.nav-logo {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
}
.nav-logo :deep(svg) { width: 32px; height: 32px; }
.nav-links { display: flex; gap: 8px; }
.nav-link {
  padding: 8px 16px;
  border-radius: var(--radius-full);
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-2);
  transition: var(--transition);
  cursor: pointer;
}
.nav-link:hover {
  background: var(--accent-primary-10);
  color: var(--accent-primary);
}

/* ── HERO ── */
.hero {
  position: relative;
  z-index: 1;
  max-width: 900px;
  margin: 0 auto;
  padding: 80px 32px 64px;
  text-align: center;
}
.hero-badge {
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
  margin-bottom: 28px;
  animation: fade-up 0.5s ease both;
}
.hero-badge-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--accent-primary);
  box-shadow: 0 0 8px var(--accent-primary);
  animation: pulse-glow 2s ease-in-out infinite;
}
.hero-title {
  margin: 0;
  animation: fade-up 0.6s ease 0.1s both;
}
.hero-title-line {
  display: block;
  font-size: clamp(36px, 5vw, 56px);
  font-weight: 800;
  letter-spacing: -0.04em;
  line-height: 1.05;
  background: var(--gradient-primary);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.hero-title-sub {
  display: block;
  font-size: clamp(18px, 2.2vw, 26px);
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.3;
  margin-top: 12px;
  color: var(--color-text);
}
.hero-desc {
  font-size: 0.9375rem;
  line-height: 1.8;
  color: var(--color-text-2);
  max-width: 640px;
  margin: 24px auto 0;
  animation: fade-up 0.6s ease 0.2s both;
}

/* ── 数据药丸 ── */
.metric-pills {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
  margin-top: 36px;
  animation: fade-up 0.6s ease 0.3s both;
}
.metric-pill {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 14px 24px;
  border-radius: var(--radius-lg);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  min-width: 110px;
  transition: var(--transition);
}
.metric-pill:hover {
  transform: translateY(-3px);
  border-color: var(--color-border-focus);
  box-shadow: var(--shadow-card-hover);
}
.metric-value {
  font-size: 1.75rem;
  font-weight: 800;
  font-family: var(--font-mono);
  letter-spacing: -0.03em;
  line-height: 1;
}
.metric-label {
  font-size: 0.75rem;
  color: var(--color-text-3);
  font-weight: 500;
}

/* ── CTA ── */
.hero-cta {
  display: flex;
  gap: 14px;
  justify-content: center;
  margin-top: 40px;
  animation: fade-up 0.6s ease 0.4s both;
}
.cta-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 32px;
  border-radius: var(--radius-full);
  border: none;
  background: var(--gradient-primary);
  color: var(--text-user);
  font-size: 0.9375rem;
  font-weight: 700;
  cursor: pointer;
  transition: var(--transition-bounce);
  box-shadow: var(--shadow-lg);
}
.cta-primary svg { width: 18px; height: 18px; }
.cta-primary:hover {
  transform: translateY(-2px) scale(1.03);
  box-shadow: var(--shadow-lg), var(--glow-primary);
}
.cta-secondary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 28px;
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
.cta-secondary:hover {
  border-color: var(--color-border-focus);
  background: var(--color-glass-hover);
  transform: translateY(-2px);
}
.cta-icon { display: flex; }
.cta-icon :deep(svg) { width: 18px; height: 18px; color: var(--accent-cyan); }

/* ── 区块标题 ── */
.section-label-row {
  text-align: center;
  margin-bottom: 36px;
}
.section-idx {
  display: block;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--accent-primary);
  margin-bottom: 8px;
}
.section-heading {
  font-size: clamp(22px, 3vw, 30px);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--color-text);
}

/* ── 创新亮点 ── */
.innovations {
  position: relative;
  z-index: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 48px 32px;
}
.innovation-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.innovation-card {
  position: relative;
  padding: 28px;
  border-radius: var(--radius-xl);
  background: var(--card-gradient);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  overflow: hidden;
  transition: var(--transition-slow);
  animation: fade-up 0.5s ease both;
}
.innovation-card:hover {
  transform: translateY(-6px);
  border-color: var(--card-accent);
  box-shadow: var(--shadow-xl), 0 0 0 1px var(--card-accent);
}
.inn-glow {
  position: absolute;
  top: -40px; right: -40px;
  width: 120px; height: 120px;
  border-radius: 50%;
  background: radial-gradient(circle, var(--card-accent), transparent 70%);
  opacity: 0.15;
  pointer-events: none;
  transition: opacity 0.4s;
}
.innovation-card:hover .inn-glow { opacity: 0.3; }
.inn-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.inn-badge {
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  background: color-mix(in srgb, var(--card-accent) 12%, transparent);
  color: var(--card-accent);
}
.inn-icon {
  width: 44px; height: 44px;
  border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--card-accent) 10%, transparent);
  color: var(--card-accent);
}
.inn-icon :deep(svg) { width: 24px; height: 24px; }
.inn-title {
  font-size: 1.1875rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--color-text);
  margin: 0;
}
.inn-subtitle {
  font-size: 0.75rem;
  color: var(--color-text-3);
  font-weight: 500;
  margin-top: 4px;
  margin-bottom: 14px;
}
.inn-desc {
  font-size: 0.8125rem;
  line-height: 1.7;
  color: var(--color-text-2);
  margin: 0 0 20px;
}
.inn-stat {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 16px;
}
.inn-stat-value {
  font-size: 2rem;
  font-weight: 800;
  font-family: var(--font-mono);
  letter-spacing: -0.03em;
  line-height: 1;
}
.inn-stat-label {
  font-size: 0.75rem;
  color: var(--color-text-3);
  font-weight: 500;
}
.inn-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.inn-tag {
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  background: var(--color-surface-hover);
  color: var(--color-text-2);
  border: 1px solid var(--color-border);
}

/* ── 四科分色 ── */
.subjects-band {
  position: relative;
  z-index: 1;
  max-width: 1200px;
  margin: 0 auto;
  padding: 48px 32px;
}
.subjects-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.subject-chip {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
  border-radius: var(--radius-lg);
  background: var(--color-glass);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
  border: 1px solid var(--color-glass-border);
  border-top: 3px solid var(--subj-color);
  transition: var(--transition);
  animation: fade-up 0.4s ease both;
}
.subject-chip:hover {
  transform: translateY(-3px);
  box-shadow: var(--shadow-lg), 0 0 0 1px var(--subj-color);
}
.subj-dot {
  width: 12px; height: 12px;
  border-radius: 50%;
  background: var(--subj-color);
  box-shadow: 0 0 12px var(--subj-color);
  flex-shrink: 0;
}
.subj-info { flex: 1; display: flex; flex-direction: column; }
.subj-name { font-size: 0.9375rem; font-weight: 600; color: var(--color-text); }
.subj-nodes { font-size: 0.6875rem; color: var(--color-text-3); margin-top: 2px; }
.subj-code {
  font-size: 0.75rem;
  font-weight: 800;
  font-family: var(--font-mono);
  color: var(--subj-color);
  letter-spacing: 0.05em;
}

/* ── 底部 CTA ── */
.bottom-cta {
  position: relative;
  z-index: 1;
  padding: 64px 32px;
}
.bottom-cta-inner {
  max-width: 640px;
  margin: 0 auto;
  text-align: center;
  padding: 48px;
  border-radius: var(--radius-xl);
  background: var(--gradient-hero);
  border: 1px solid var(--color-glass-border);
  backdrop-filter: blur(var(--glass-blur));
  -webkit-backdrop-filter: blur(var(--glass-blur));
}
.bottom-title {
  font-size: clamp(20px, 2.5vw, 28px);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--color-text);
  margin: 0 0 12px;
}
.bottom-desc {
  font-size: 0.875rem;
  color: var(--color-text-2);
  margin: 0 0 28px;
  line-height: 1.6;
}
.cta-large {
  padding: 16px 40px;
  font-size: 1rem;
}

/* ── 页脚 ── */
.landing-footer {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 24px 32px;
  border-top: 1px solid var(--color-border);
  font-size: 0.75rem;
  color: var(--color-text-3);
}
.footer-tech { font-family: var(--font-mono); }

/* ── 响应式 ── */
@media (max-width: 900px) {
  .innovation-grid { grid-template-columns: 1fr; }
  .subjects-grid { grid-template-columns: repeat(2, 1fr); }
  .hero { padding: 48px 20px 40px; }
  .innovations, .subjects-band { padding: 32px 20px; }
  .nav-links { gap: 4px; }
  .nav-link { padding: 6px 12px; font-size: 0.75rem; }
}
@media (max-width: 480px) {
  .subjects-grid { grid-template-columns: 1fr; }
  .metric-pills { gap: 8px; }
  .metric-pill { padding: 10px 16px; min-width: 90px; }
  .metric-value { font-size: 1.375rem; }
  .hero-cta { flex-direction: column; }
  .bottom-cta-inner { padding: 32px 20px; }
}
</style>
