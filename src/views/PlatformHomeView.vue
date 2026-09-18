<script setup lang="ts">
/**
 * 平台首页（双场景入口）—— 单 main 合体 · F1
 *
 * 「芒得很职」= 一个平台、两个业务场景：
 *   · 专业能力训练（考研408）      —— 低年级，夯实专业功底
 *   · 职业素养实训（芒得很职主线）  —— 高年级，AI 对抗式软技能训练
 *
 * 本页是登录后的统一入口，替代原先"进站即考研 Dashboard"的行为；
 * 考研总览已移至 /kaoyan（旧 /dashboard 经 redirect 兼容）。
 * 共用：单登录态（authStore）+ 统一能力画像（useAbilityProfile，F4 接入）。
 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import { icons } from '@/components/icons'
import { useScene, SCENE_META } from '@/composables/useScene'
import { useAbilityProfile } from '@/composables/useAbilityProfile'
import { useAuthStore } from '@/stores/authStore'

const router = useRouter()
const authStore = useAuthStore()
const { setScene } = useScene()
const { data: ability, degraded: abilityDegraded, load: loadAbility } = useAbilityProfile()

onMounted(() => { loadAbility() })

function safeIcon(html: string): string {
  return DOMPurify.sanitize(html, { USE_PROFILES: { svg: true, svgFilters: true } })
}

interface SceneCard {
  key: 'kaoyan' | 'career'
  title: string
  sub: string
  points: string[]
  icon: string
  accent: 'blue' | 'teal'
}

const cards: SceneCard[] = [
  {
    key: 'kaoyan',
    title: '专业能力训练',
    sub: '考研408智能学习 · 低年级',
    points: ['学情诊断 → 个性化学习路径', '多智能体对话 · RAG 知识底座', '智能出题 · 错题复盘 · 能力画像'],
    icon: icons.graduation,
    accent: 'blue',
  },
  {
    key: 'career',
    title: '职业素养实训',
    sub: 'AI 对抗式能力训练 · 高年级 · 主推',
    points: ['证据链（ECD）对抗实训', '答辩 / 面试 / 冲突沟通场景', '六维软素养评估报告'],
    icon: icons.target,
    accent: 'teal',
  },
]

const userName = computed(
  () => (authStore.currentUser as any)?.display_name || (authStore.currentUser as any)?.username || '同学'
)

function enterScene(c: SceneCard) {
  setScene(c.key) // 切换并持久化当前场景
  router.push(SCENE_META[c.key].route) // 进入对应场景首页
}
</script>

<template>
  <div class="platform-home">
    <div class="ph-aura" aria-hidden="true"></div>

    <header class="ph-hero">
      <span class="ph-track">国创赛 · 高教主赛道 · 创意组</span>
      <div class="ph-brand">
        <span class="ph-logo"><img class="brand-img" src="/brand/mangxiaocheng.png" alt="芒得很职" /></span>
        <h1 class="ph-title">芒得很职</h1>
      </div>
      <p class="ph-sub">新一代多智能体赋能的计算机类学生职业素养对抗实训平台</p>
      <p class="ph-welcome">欢迎回来，{{ userName }} · 选一个场景开始</p>
    </header>

    <section class="ph-scenes" aria-label="场景入口">
      <button
        v-for="c in cards"
        :key="c.key"
        class="ph-card"
        :class="`ph-card--${c.accent}`"
        @click="enterScene(c)"
      >
        <div class="ph-card-top">
          <span class="ph-card-icon" v-html="safeIcon(c.icon)"></span>
          <div class="ph-card-heading">
            <span class="ph-card-title">{{ c.title }}</span>
            <span v-if="c.key === 'career'" class="ph-tag">主推</span>
          </div>
        </div>
        <p class="ph-card-sub">{{ c.sub }}</p>
        <ul class="ph-card-points">
          <li v-for="p in c.points" :key="p">
            <svg class="ph-check" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <span>{{ p }}</span>
          </li>
        </ul>
        <span class="ph-card-cta">进入场景 <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h9M8.5 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
      </button>
    </section>

    <!-- 统一能力画像（一个账号、一份画像；后端未就绪则 fail-open 提示） -->
    <section class="ph-ability" aria-label="能力画像">
      <h2 class="ph-section-title">能力画像</h2>
      <p v-if="abilityDegraded" class="ph-ability-degraded">
        画像服务未就绪，展示本地缓存{{ ability ? '' : '（暂无缓存）' }}
      </p>
      <div v-if="ability" class="ph-ability-grid">
        <div class="ph-ability-col">
          <span class="ph-ability-label">专业能力（考研408）</span>
          <span class="ph-ability-value">{{ ability.professional ? '已构建' : '待诊断' }}</span>
        </div>
        <div class="ph-ability-col">
          <span class="ph-ability-label">软素养（职业素养实训）</span>
          <span class="ph-ability-value">{{ ability.soft_skills ? '已评估' : '待实训' }}</span>
        </div>
      </div>
    </section>

    <section class="ph-stats" aria-label="平台能力">
      <div class="ph-stat"><b>3</b><span>实训模式<br/>自学 / 对抗 / 导师</span></div>
      <div class="ph-stat"><b>6</b><span>维 ECD<br/>职业素养评估</span></div>
      <div class="ph-stat"><b>41</b><span>前端视图<br/>已落地可用</span></div>
      <div class="ph-stat"><b>40+</b><span>真实实验产物<br/>可复现证据</span></div>
    </section>

    <section class="ph-edge" aria-label="核心差异">
      <svg class="ph-edge-ico" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2l2 4 4.5.6-3.3 3.2.8 4.5L10 12.8 5.9 14.3l.8-4.5L3.4 6.6 7.9 6 10 2z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>
      <p><b>证据链（ECD）对抗实训</b>——每一轮对话都是一条证据，六维评分每分都挂原话，可点回溯源。把「软素养」练成可解释、可量、可证的数据。</p>
    </section>
  </div>
</template>

<style scoped>
.platform-home {
  position: relative;
  height: 100%;
  overflow-y: auto;
  max-width: 1120px;
  margin: 0 auto;
  padding: var(--space-16) var(--space-8) var(--space-20);
}

/* 背景光晕：克制，仅顶部两团低饱和紫/青，避免霓虹发光 */
.ph-aura {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(720px 360px at 80% -8%, rgba(var(--accent-rgb), 0.14), transparent 60%),
    radial-gradient(560px 320px at 6% 4%, rgba(var(--subject-co-rgb), 0.07), transparent 58%);
}

.ph-hero {
  position: relative;
  text-align: center;
  margin-bottom: var(--space-12);
}

.ph-track {
  display: inline-block;
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  letter-spacing: 0.14em;
  color: var(--accent-primary);
  background: var(--accent-primary-10);
  border: 1px solid var(--accent-primary-20);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-full);
  margin-bottom: var(--space-5);
}

.ph-brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.ph-logo {
  display: inline-flex;
  width: var(--space-10);
  height: var(--space-10);
  color: var(--accent-primary);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.ph-logo :deep(svg) { width: 100%; height: 100%; }

.ph-title {
  font-size: var(--text-5xl);
  font-weight: var(--weight-bold);
  color: var(--color-text);
  margin: 0;
  letter-spacing: 0.02em;
}

.ph-sub {
  margin: var(--space-3) auto var(--space-2);
  max-width: 560px;
  font-size: var(--text-lg);
  color: var(--color-text-2);
  line-height: 1.5;
}

.ph-welcome {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-3);
}

/* ── 场景卡片 ── */
.ph-scenes {
  position: relative;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: var(--space-6);
}

.ph-card {
  --card-accent: var(--accent-primary);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-4);
  padding: var(--space-8);
  text-align: left;
  background: var(--color-surface);
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-xl);
  cursor: pointer;
  font-family: inherit;
  color: inherit;
  transition: transform var(--transition), border-color var(--transition), box-shadow var(--transition);
  position: relative;
  overflow: hidden;
}
.ph-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: var(--card-accent);
  opacity: 0.55;
}
.ph-card:hover {
  transform: translateY(-4px);
  border-color: rgba(var(--accent-rgb), 0.45);
  box-shadow: var(--shadow-lg);
}
.ph-card:focus-visible {
  outline: 2px solid var(--card-accent);
  outline-offset: 2px;
}

.ph-card--blue { --card-accent: var(--color-info); }
.ph-card--teal { --card-accent: var(--color-accent); }

.ph-card-top {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.ph-card-icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  flex: 0 0 52px;
  border-radius: var(--radius-md);
  background: rgba(var(--accent-rgb), 0.14);
  color: var(--card-accent);
}
.ph-card--blue .ph-card-icon { background: rgba(var(--info-rgb), 0.14); }
.ph-card-icon :deep(svg) { width: 26px; height: 26px; }

.ph-card-heading {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
.ph-card-title {
  font-size: var(--text-2xl);
  font-weight: var(--weight-semibold);
  color: var(--color-text);
}
.ph-tag {
  font-size: var(--text-2xs);
  font-weight: var(--weight-bold);
  letter-spacing: 0.04em;
  color: #fff;
  background: var(--card-accent);
  padding: 2px 9px;
  border-radius: var(--radius-full);
}

.ph-card-sub {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-2);
  line-height: var(--leading-normal);
}

.ph-card-points {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}
.ph-card-points li {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-2);
  line-height: 1.5;
}
.ph-check {
  flex: 0 0 16px;
  width: 16px;
  height: 16px;
  margin-top: 2px;
  color: var(--card-accent);
}

.ph-card-cta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: auto;
  padding-top: var(--space-3);
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  color: var(--card-accent);
}
.ph-card-cta svg { width: 16px; height: 16px; transition: transform var(--transition); }
.ph-card:hover .ph-card-cta svg { transform: translateX(4px); }

/* ── 能力画像（保留并发会话区块，仅对齐间距） ── */
.ph-ability {
  position: relative;
  margin-top: var(--space-14);
}
.ph-section-title {
  font-size: var(--text-2xl);
  font-weight: var(--weight-semibold);
  color: var(--color-text);
  margin: 0 0 var(--space-5);
}
.ph-ability-degraded {
  font-size: var(--text-xs);
  color: var(--color-text-3);
  margin: 0 0 var(--space-4);
}
.ph-ability-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-4);
}
.ph-ability-col {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-5);
  background: var(--color-surface);
  border: 1px solid var(--color-glass-border);
  border-radius: var(--radius-md);
}
.ph-ability-label {
  font-size: var(--text-xs);
  color: var(--color-text-3);
}
.ph-ability-value {
  font-size: var(--text-lg);
  font-weight: var(--weight-semibold);
  color: var(--color-text);
}

/* ── 能力数据条 ── */
.ph-stats {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-top: var(--space-14);
  padding: var(--space-6) 0;
  border-top: 1px solid var(--color-glass-border);
  border-bottom: 1px solid var(--color-glass-border);
}
.ph-stat { text-align: center; }
.ph-stat b {
  display: block;
  font-size: var(--text-4xl);
  font-weight: var(--weight-bold);
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  letter-spacing: -0.02em;
}
.ph-stat span {
  display: block;
  margin-top: 6px;
  font-size: var(--text-2xs);
  color: var(--color-text-3);
  line-height: 1.45;
}

/* ── 核心差异带 ── */
.ph-edge {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  margin-top: var(--space-10);
  padding: var(--space-6) var(--space-7);
  background: rgba(var(--accent-rgb), 0.08);
  border: 1px solid rgba(var(--accent-rgb), 0.24);
  border-radius: var(--radius-lg);
}
.ph-edge-ico {
  flex: 0 0 22px;
  width: 22px;
  height: 22px;
  color: var(--accent-primary);
}
.ph-edge p {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-2);
  line-height: 1.6;
}
.ph-edge b { color: var(--color-text); font-weight: var(--weight-semibold); }

/* ── 响应式 ── */
@media (max-width: 720px) {
  .platform-home { padding: var(--space-12) var(--space-5) var(--space-16); }
  .ph-stats { grid-template-columns: repeat(2, 1fr); gap: var(--space-6); }
  .ph-title { font-size: var(--text-4xl); }
}
</style>
