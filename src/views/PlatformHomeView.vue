<script setup lang="ts">
/**
 * 平台首页（双场景入口）—— 单 main 合体 · F1
 *
 * 「芒得很职」= 一个平台、两个业务场景：
 *   · 专业能力训练（专业核心四科）  —— 低年级，夯实专业功底
 *   · 职业素养实训（芒得很职主线）  —— 高年级，AI 对抗式软技能训练
 *
 * 本页是登录后的统一入口（2026-10-04 导师裁决正式接入）：
 *   路由 `/` = 本页；专业总览移至 `/kaoyan`（旧 `/dashboard` redirect 兼容）；
 *   侧栏「我的 · 平台首页」提供回入口；场景跳转真值 = useScene.SCENE_META。
 * 体系定位（导师口径）：双场景都是同一个人才体系的组成部分——
 *   专业能力（核心四科）夯实功底 → 职业素养实训完成就业衔接，
 *   与统一能力画像（useAbilityProfile）贯通两场景。
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
  /** 卡片右上角徽标：主推场景用实心，验证场景用静音样式 */
  badge?: string
  /** secondary = 次级入口（技术底座复用验证），视觉上不与主推卡等权 */
  tier: 'primary' | 'secondary'
}

const cards: SceneCard[] = [
  {
    // 主推场景置顶：平台定位是职业素养实训，学生首屏应先看到它。
    // 此前专业能力训练排第一，手机端第一屏完全看不到"主推"场景。
    key: 'career',
    title: '职业素养实训',
    sub: 'AI 对抗式能力训练 · 高年级 · 主推',
    points: ['证据链（ECD）对抗实训', '答辩 / 评审 / 应急 / 冲突对抗场景', '六维软素养评估报告'],
    icon: icons.target,
    accent: 'teal',
    badge: '主推',
    tier: 'primary',
  },
  {
    // 考研场景降为次级入口：它是"同一套多智能体+RAG 底座可复用"的验证场景，
    // 不是本平台的主营业务，故不与职业素养等权陈列，并明示为教学验证。
    key: 'kaoyan',
    title: '专业能力训练',
    sub: '专业核心四科智能学习 · 低年级',
    points: ['学情诊断 → 个性化学习路径', '多智能体对话 · RAG 知识底座', '智能出题 · 错题复盘 · 能力画像'],
    icon: icons.graduation,
    accent: 'blue',
    badge: '教学验证',
    tier: 'secondary',
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
      <div class="ph-hero-main">
        <span class="ph-track">一个平台 · 两个业务场景</span>
        <div class="ph-brand">
          <span class="ph-logo"><img class="brand-img" src="/brand/mangxiaocheng.png" alt="芒得很职" /></span>
          <h1 class="ph-title">芒得很职</h1>
        </div>
        <p class="ph-sub">新一代多智能体赋能的计算机类学生职业素养对抗实训平台</p>
      </div>
      <p class="ph-welcome">欢迎回来，{{ userName }}</p>
    </header>

    <section class="ph-scenes" aria-label="场景入口">
      <button
        v-for="c in cards"
        :key="c.key"
        class="ph-card"
        :class="[`ph-card--${c.accent}`, c.tier === 'secondary' ? 'ph-card--secondary' : '']"
        @click="enterScene(c)"
      >
        <div class="ph-card-top">
          <span class="ph-card-icon" v-html="safeIcon(c.icon)"></span>
          <div class="ph-card-heading">
            <span class="ph-card-title">{{ c.title }}</span>
            <span v-if="c.badge" class="ph-tag" :class="{ 'ph-tag--muted': c.tier === 'secondary' }">{{ c.badge }}</span>
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
        <div class="ph-ability-col" :data-on="ability.professional">
          <div class="ph-ability-row">
            <span class="ph-ability-label">专业能力（核心四科）</span>
            <span class="ph-ability-state">{{ ability.professional ? '已构建' : '待诊断' }}</span>
          </div>
          <span class="ph-ability-hint">学情诊断 · 个性化路径 · 智能出题 · 错题复盘</span>
        </div>
        <div class="ph-ability-col" :data-on="ability.soft_skills">
          <div class="ph-ability-row">
            <span class="ph-ability-label">软素养（职业素养实训）</span>
            <span class="ph-ability-state">{{ ability.soft_skills ? '已评估' : '待实训' }}</span>
          </div>
          <span class="ph-ability-hint">证据链对抗 · 六维评估 · 前后测对比 · 证据金句</span>
        </div>
      </div>
    </section>

    <section class="ph-stats" aria-label="平台能力">
      <div class="ph-stat"><b>4</b><span>对抗实训场景</span></div>
      <div class="ph-stat"><b>6</b><span>维 ECD 职业素养评估</span></div>
      <div class="ph-stat"><b>49</b><span>前端视图已落地</span></div><!-- 口径：ls src/views/*.vue 实测 49（2026-10-17） -->
      <div class="ph-stat"><b>40+</b><span>真实实验产物可复现</span></div>
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
/* 浅色底上同样的紫光晕会显得脏，压到只剩一点空气感 */
[data-theme="light"] .ph-aura { opacity: 0.32; }

/* 页头：左对齐的控制台式页头。居中堆叠会读成个人主页/落地页，不像平台入口。 */
.ph-hero {
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-6);
  text-align: left;
  margin-bottom: var(--space-10);
  padding-bottom: var(--space-7, 28px);
  border-bottom: 1px solid var(--color-border);
}
.ph-hero-main { min-width: 0; }

/* 小字英文 eyebrow，不用胶囊——胶囊会抢掉标题的注意力 */
.ph-track {
  display: block;
  font-size: 11px;
  font-weight: var(--weight-semibold);
  letter-spacing: 0.16em;
  color: var(--accent-primary);
  margin-bottom: 12px;
}

.ph-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 10px;
}

.ph-logo {
  display: inline-flex;
  width: 40px;
  height: 40px;
  color: var(--accent-primary);
  border-radius: var(--radius-md);
  overflow: hidden;
  flex-shrink: 0;
}
.ph-logo :deep(svg) { width: 100%; height: 100%; }

.ph-title {
  font-size: 34px;
  font-weight: var(--weight-bold);
  color: var(--color-text);
  margin: 0;
  letter-spacing: 0.01em;
  line-height: 1.2;
}

.ph-sub {
  margin: 0;
  max-width: 640px;
  font-size: var(--text-md);
  color: var(--color-text-2);
  line-height: 1.55;
}

.ph-welcome {
  margin: 0 0 2px;
  font-size: var(--text-sm);
  color: var(--color-text-3);
  white-space: nowrap;
  flex-shrink: 0;
}
@media (max-width: 720px) {
  .ph-hero { flex-direction: column; align-items: flex-start; gap: var(--space-3); }
  .ph-title { font-size: 26px; }
  .ph-welcome { white-space: normal; }
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
  gap: var(--space-5);
  padding: var(--space-8);
  text-align: left;
  /* 深色底上必须靠"底、边、阴影"三层把卡片托起来：
     原来卡片色与页面底色几乎一致，只留一根细边，视觉上是平的。
     现在提一档底色 + 顶部内高光 + 外投影，卡片才有实体感。 */
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  box-shadow: var(--shadow-card);
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

/* 场景卡配色统一跟随全局 --color-accent。
   此前 kaoyan 卡写死 --color-info，切到 teal/amber/rose 时这张卡仍是固定信息蓝，
   与主色打架；主次改由"主推徽标 + 图标语义"承担，不靠第二个色相。 */
.ph-card--blue { --card-accent: var(--color-accent); }
.ph-card--teal { --card-accent: var(--color-accent); }

/* 场景卡层级：主推场景占主列，验证场景收窄为次级入口（宽屏才分栏，窄屏仍按序堆叠）。
   考研是"同一套底座可复用"的验证场景，不是本平台主营业务，故不与职业素养等权。 */
@media (min-width: 900px) {
  .ph-scenes {
    grid-template-columns: minmax(0, 1.3fr) minmax(0, 0.7fr);
    align-items: start;
  }
}

.ph-card--secondary {
  padding: var(--space-6);
  box-shadow: none;
}
.ph-card--secondary::before { opacity: 0.25; }
.ph-card--secondary .ph-card-title { font-size: var(--text-lg); }
.ph-card--secondary .ph-card-points li { font-size: var(--text-sm); }

.ph-card-top {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.ph-card-icon {
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  flex: 0 0 56px;
  border-radius: 14px;
  background: rgba(var(--accent-rgb), 0.14);
  border: 1px solid rgba(var(--accent-rgb), 0.22);
  color: var(--card-accent);
}
/* 蓝色卡的图标底压淡一档，与主推卡拉开层次，同时仍跟随全局配色 */
.ph-card--blue .ph-card-icon {
  background: rgba(var(--accent-rgb), 0.08);
  border-color: rgba(var(--accent-rgb), 0.16);
}
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
  color: var(--color-text-on-accent);
  background: var(--card-accent);
  padding: 2px 9px;
  border-radius: var(--radius-full);
}
/* 次级入口的徽标不抢主推卡的实心注意力 */
.ph-tag--muted {
  color: var(--color-text-2);
  background: transparent;
  border: 1px solid var(--color-border);
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
  justify-content: center;
  gap: 6px;
  margin-top: auto;
  padding: 11px 16px;
  border-radius: 10px;
  background: rgba(var(--accent-rgb), 0.10);
  border: 1px solid rgba(var(--accent-rgb), 0.26);
  font-size: var(--text-sm);
  font-weight: var(--weight-semibold);
  color: var(--color-accent-text);
  transition: var(--transition);
}
.ph-card:hover .ph-card-cta {
  background: rgba(var(--accent-rgb), 0.18);
  border-color: rgba(var(--accent-rgb), 0.42);
}
.ph-card-cta svg { width: 16px; height: 16px; transition: transform var(--transition); }
.ph-card:hover .ph-card-cta svg { transform: translateX(4px); }

/* ── 能力画像（保留并发会话区块，仅对齐间距） ── */
.ph-ability {
  position: relative;
  margin-top: var(--space-14);
}
.ph-section-title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: var(--text-lg);
  font-weight: var(--weight-bold);
  color: var(--color-text);
  margin: 0 0 var(--space-4);
}
.ph-section-title::before {
  content: "";
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: var(--accent-primary);
  flex-shrink: 0;
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
  gap: 8px;
  padding: 18px var(--space-5);
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  box-shadow: var(--shadow-card);
}
.ph-ability-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}
.ph-ability-label {
  font-size: var(--text-xs);
  color: var(--color-text-3);
}
/* 状态徽标：已构建/已评估用主色，待办用中性色，颜色只在状态上有意义 */
.ph-ability-state {
  flex-shrink: 0;
  font-size: var(--text-2xs);
  font-weight: var(--weight-semibold);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  color: var(--color-text-3);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
}
.ph-ability-col[data-on="true"] .ph-ability-state {
  color: var(--color-accent-text);
  background: rgba(var(--accent-rgb), 0.12);
  border-color: rgba(var(--accent-rgb), 0.28);
}
.ph-ability-hint {
  font-size: var(--text-sm);
  color: var(--color-text-2);
  line-height: 1.5;
}

/* ── 能力数据条 ── */
.ph-stats {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-top: var(--space-12);
  padding-top: var(--space-7, 28px);
  border-top: 1px solid var(--color-border);
}
.ph-stat { text-align: left; }
.ph-stat b {
  display: block;
  font-size: 30px;
  font-weight: var(--weight-bold);
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
  letter-spacing: -0.02em;
}
.ph-stat span {
  display: block;
  margin-top: 4px;
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
  .platform-home { padding: var(--space-10) var(--space-5) var(--space-16); }
  .ph-scenes { gap: var(--space-4); }
  .ph-card { padding: var(--space-5); gap: var(--space-4); border-radius: 16px; }
  .ph-card-icon { width: 44px; height: 44px; flex: 0 0 44px; }
  .ph-card-icon :deep(svg) { width: 22px; height: 22px; }
  .ph-card-title { font-size: var(--text-xl); }
  .ph-stats { grid-template-columns: repeat(2, 1fr); gap: var(--space-5); }
  .ph-stat b { font-size: 26px; }
  .ph-edge { padding: var(--space-5); }
}
</style>
