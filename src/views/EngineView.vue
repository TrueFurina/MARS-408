<script setup lang="ts">
import { ref } from 'vue'
import { api } from '@/utils/api'
import Skeleton from '@/components/Skeleton.vue'
import LangGraphFlow from '@/components/LangGraphFlow.vue'
import DebateSimulation from '@/components/DebateSimulation.vue'
import TeachingRulesPanel from '@/components/TeachingRulesPanel.vue'
import FrugalRAGPanel from '@/components/FrugalRAGPanel.vue'
import GOMARLPanel from '@/components/GOMARLPanel.vue'
import CompareProfilesPanel from '@/components/CompareProfilesPanel.vue'
import EvidenceCheckPanel from '@/components/EvidenceCheckPanel.vue'
import { capabilityComparison } from '@/data/capabilityComparison'
import { icons } from '@/components/icons'

// LangGraph 10 节点进度
const flowActive = ref(false)
const flowCurrentNode = ref(-1)
const flowCompleted = ref<number[]>([])
const flowStepDetails = [
  '分析学习目标与画像',
  '诊断知识薄弱点',
  '制定检索策略与路径',
  '执行FrugalRAG多轮检索',
  '多Agent协同生成内容',
  'GoMARL共识评估质量',
  '审核冲突消解与一致性',
  '证据校验与防幻觉 grounding',
  '产物验收闸门质量把关',
  '输出最终个性化路径',
]
const flowNodeLabels = [
  '协调', '诊断', '规划', '检索',
  '生成', '评估', '审核', '证据校验', '产物验收', '路径规划',
]

async function animateFlow(durationMs: number = 2800) {
  flowActive.value = true
  flowCurrentNode.value = -1
  flowCompleted.value = []
  const totalNodes = 10
  const stepDelay = durationMs / totalNodes
  for (let i = 0; i < totalNodes; i++) {
    if (!flowActive.value) break
    flowCurrentNode.value = i
    await new Promise(r => setTimeout(r, stepDelay * 0.5))
    flowCompleted.value = [...flowCompleted.value, i]
    if (i < totalNodes - 1) {
      await new Promise(r => setTimeout(r, stepDelay * 0.5))
    }
  }
  // 最后微微停顿
  await new Promise(r => setTimeout(r, 200))
}

// ── 引擎状态 ──
const engineStatus = ref<any>(null)
const engineLoading = ref(true)
async function loadStatus() {
  try {
    engineStatus.value = await api.get<any>('/engine/status')
  } catch (e) {
    engineStatus.value = { status: 'error', message: String(e) }
  } finally {
    engineLoading.value = false
  }
}
loadStatus()

// L1/L2/L3 三层学情记忆健康度（低侵入联动：引擎页展示记忆驱动证据，失败不影响主流程）
const memoryOverview = ref<any>(null)
async function loadMemoryOverview() {
  try {
    const memRes: any = await api.get('/memory/overview')
    if (memRes?.status === 'ok') memoryOverview.value = memRes
  } catch { /* 记忆服务不可用时不阻塞引擎页 */ }
}
loadMemoryOverview()

// 格式化模块名
function formatModuleName(name: string): string {
  const map: Record<string, string> = {
    frugal_rag_lite: 'FrugalRAG Lite',
    frugal_rag_sft: 'LLM查询优化(SFT风格)',
    frugal_rag_stop_decision: '启发式停止决策',
    frugal_rag_query_rewrite: '查询重写',
    frugal_rag_lora: 'LoRA适配',
    frugal_rag_personalized_rerank: '个性化排序',
    gomarl_lite: 'GoMARL Lite',
    gomarl_neural_mixer: 'NeuralMixer',
    gomarl_evidence_conflict: '证据冲突消解',
    gomarl_teaching_rules: '教学规则引擎',
  }
  return map[name] || name
}
</script>

<template>
  <div class="page-section">
    <div class="section-header">
      <div class="section-title">
        <span v-html="icons.engine" class="section-title-icon"></span>
        算法引擎可视化
      </div>
      <div class="section-desc">FrugalRAG + GoMARL + Agent辩论 + 教学规则引擎 — 核心技术壁垒</div>
    </div>

    <!-- L1/L2/L3 三层学情记忆健康度（低侵入联动：引擎页展示记忆驱动证据） -->
    <div v-if="memoryOverview" class="memory-mini-strip" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;font-size:12px;">
      <span style="padding:3px 10px;border-radius:12px;background:var(--accent-primary-10);color:var(--accent-primary);">🧠 {{ memoryOverview.memory_level || 'L3' }}</span>
      <span style="padding:3px 10px;border-radius:12px;background:var(--bg-tertiary);color:var(--text-secondary);">画像 {{ memoryOverview.profile_dimensions ?? 0 }}/8 维</span>
      <span style="padding:3px 10px;border-radius:12px;background:var(--bg-tertiary);color:var(--text-secondary);">掌握度 {{ memoryOverview.mastery_points ?? 0 }} 点</span>
      <span style="padding:3px 10px;border-radius:12px;background:var(--bg-tertiary);color:var(--text-secondary);">情景事件 {{ memoryOverview.episodic_count ?? 0 }}</span>
    </div>

    <!-- ── 核心差异对比面板 ── -->
    <div class="diff-panel glass-card engine-enter" style="animation-delay:0s">
      <div class="diff-panel-header">
        <span v-html="icons.shield" class="engine-icon-svg"></span>
        核心技术壁垒 — 与普通多Agent系统的差异化
        <span class="diff-panel-tag">评审必看</span>
      </div>
      <div class="diff-category" v-for="cat in capabilityComparison" :key="cat.category">
        <div class="diff-category-title">{{ cat.category }}</div>
        <table class="diff-table">
          <thead>
            <tr>
              <th class="diff-th-other">普通方案</th>
              <th class="diff-th-ours">MARS-408 真版</th>
              <th class="diff-th-tag"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, i) in cat.items" :key="i">
              <td class="diff-td-other">{{ item.other }}</td>
              <td class="diff-td-ours">{{ item.ours }}</td>
              <td class="diff-td-tag"><span class="diff-tag" :class="item.tag">{{ item.tag }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── 引擎状态卡片 ── -->
    <div v-if="engineLoading" class="engine-status-grid engine-enter" style="animation-delay:0.05s">
      <Skeleton v-for="n in 6" :key="n" variant="title" width="7rem" height="1.75rem" radius="var(--radius-full)" />
    </div>
    <div v-else-if="engineStatus?.status === 'error'" class="engine-error">
      ⚠️ 引擎状态获取失败：{{ engineStatus.message }}
    </div>
    <div v-else-if="engineStatus?.status === 'ok'" class="engine-status-grid engine-enter" style="animation-delay:0.05s">
      <div class="engine-status-card glass-card" v-for="(enabled, name) in engineStatus.modules" :key="name">
        <span class="engine-status-dot" :class="{ on: enabled }"></span>
        <span class="engine-status-name">{{ formatModuleName(String(name)) }}</span>
      </div>
    </div>

    <!-- ── 循环11-P1: 熔断器/令牌桶实时状态（可观测性） ── -->
    <div v-if="engineStatus?.status === 'ok' && engineStatus.reliability" class="engine-section glass-card engine-enter" style="animation-delay:0.07s">
      <div class="engine-section-title">
        <span v-html="icons.shield" class="engine-icon-svg"></span>
        容灾可观测性
        <span class="engine-tag">熔断器 + 令牌桶实时状态</span>
      </div>
      <div class="engine-desc">多级兜底降级：限流快速失败 + 熔断隔离，故障自动切换通道</div>

      <!-- 熔断器 -->
      <div class="reli-sub-title">🛡️ 熔断器（LLM 通道 / Skill 插件）</div>
      <div v-if="Object.keys(engineStatus.reliability.breakers || {}).length" class="reli-grid">
        <div v-for="(b, name) in engineStatus.reliability.breakers" :key="name" class="reli-card">
          <div class="reli-name">{{ name }}</div>
          <span class="reli-badge" :class="`st-${b.state}`">{{ b.state }}</span>
          <div class="reli-meta">失败 {{ b.failures }}/{{ b.failure_threshold }} · 熔断 {{ b.open_timeout }}s</div>
        </div>
      </div>
      <div v-else class="reli-empty">暂无熔断器实例（服务运行后自动注册）</div>

      <!-- 令牌桶 -->
      <div class="reli-sub-title" style="margin-top:0.75rem;">🪙 令牌桶（LLM 通道突发限流）</div>
      <div v-if="Object.keys(engineStatus.reliability.token_buckets || {}).length" class="reli-grid">
        <div v-for="(tb, name) in engineStatus.reliability.token_buckets" :key="name" class="reli-card">
          <div class="reli-name">{{ name }}</div>
          <div class="reli-tokens">
            <span class="reli-token-fill" :style="{ width: Math.min(100, (tb.tokens / Math.max(tb.capacity, 1)) * 100) + '%' }"></span>
          </div>
          <div class="reli-meta">{{ tb.tokens }}/{{ tb.capacity }} 令牌 · {{ tb.rate_per_sec }}/s</div>
        </div>
      </div>
      <div v-else class="reli-empty">暂无令牌桶实例（调用 LLM 后自动注册）</div>
    </div>

    <!-- ── §5.2.2 核心#1: Agent协同流 ── -->
    <div class="engine-section glass-card engine-enter" style="animation-delay:0.10s">
      <div class="engine-section-title">
        <span v-html="icons.agent" class="engine-icon-svg"></span>
        LangGraph 10 节点协同流程
        <span class="engine-tag">StateGraph 实时状态</span>
      </div>
      <div class="engine-desc">协调→诊断→规划→检索→生成→评估→审核→证据校验→产物验收→路径规划，每节点含动画spinner+完成checkmark</div>

      <LangGraphFlow
        :current-node="flowCurrentNode"
        :completed-nodes="flowCompleted"
        :step-details="flowStepDetails"
        :node-labels="flowNodeLabels"
        :loading="false"
      />

      <!-- 演示按钮：手动触发可视化 -->
      <div class="demo-trigger-row">
        <button class="demo-btn" @click="animateFlow(3500)">▶ 演示完整流转</button>
        <span class="demo-hint">点击按钮查看 10 节点 LangGraph StateGraph 协同流程动画</span>
      </div>
    </div>

    <!-- ── §3.3.3: 教学规则可视化 ── -->
    <TeachingRulesPanel class="engine-enter" style="animation-delay:0.15s" />

    <!-- ── Agent 辩论模拟 ── -->
    <div class="engine-section glass-card engine-enter" style="animation-delay:0.20s">
      <DebateSimulation />
    </div>

    <!-- ── 幻觉防控演示（现场构造矛盾输入 → 冲突检测 → 展示） ── -->
    <div class="engine-section glass-card engine-enter" style="animation-delay:0.22s">
      <div class="engine-section-title">
        <span v-html="icons.shield" class="engine-icon-svg"></span>
        幻觉防控 · 证据校验演示
        <span class="engine-tag">现场构造矛盾输入</span>
      </div>
      <div class="engine-desc">点击演示按钮，系统将构造两个 Agent 的矛盾回答并现场检测——答辩时可直接展示幻觉防控真实工作</div>
      <EvidenceCheckPanel :report="null" />
    </div>

    <!-- ── FrugalRAG 检索 ── -->
    <FrugalRAGPanel class="engine-enter" style="animation-delay:0.25s" />

    <!-- ── 个性化对比演示 ── -->
    <CompareProfilesPanel class="engine-enter" style="animation-delay:0.30s" />

    <!-- ── GoMARL 共识 ── -->
    <GOMARLPanel class="engine-enter" style="animation-delay:0.35s" />
  </div>
</template>

<style scoped>
.engine-section {
  margin-bottom:2rem;
  padding:1.5rem;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius:var(--radius-lg);
  backdrop-filter: blur(12px);
}

.glass-card {
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-color);
  border-radius:var(--radius-md);
}

.engine-section-title {
  display: flex;
  align-items: center;
  gap:0.5rem;
  font-size:1.125rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom:0.25rem;
}

.engine-icon { font-size:1.375rem; }

.engine-icon-svg { display: inline-flex; vertical-align: middle; }
.engine-icon-svg svg { width:1.375rem; height:1.375rem; }

.section-title-icon { display: inline-flex; vertical-align: middle; margin-right:0.375rem; }
.section-title-icon svg { width:1.375rem; height:1.375rem; }

/* 交错入场 */
.engine-enter {
  animation: engine-fade-up 0.4s ease both;
}
@keyframes engine-fade-up {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

.engine-tag {
  margin-left:auto;
  font-size:0.6875rem;
  padding:0.1875rem 0.75rem;
  border-radius:var(--radius-full);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-weight: 500;
}

.engine-desc {
  font-size:0.8125rem;
  color: var(--text-secondary);
  margin-bottom:1rem;
}

.engine-input-row {
  display: flex;
  gap:0.5rem;
  margin-bottom:1rem;
}

.engine-select {
  padding:0.625rem 0.875rem;
  border-radius:var(--radius-sm);
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size:0.875rem;
  outline: none;
}

.engine-input {
  flex: 1;
  padding:0.625rem 1rem;
  border-radius:var(--radius-sm);
  background: var(--bg-input);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size:0.875rem;
  outline: none;
  transition: var(--transition);
}

.engine-input:focus {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 3px var(--accent-primary-10);
}

.engine-btn {
  padding:0.625rem 1.5rem;
  border-radius:var(--radius-full);
  border: none;
  background: var(--gradient-primary);
  color: #fff;
  font-size:0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition-bounce);
  white-space: nowrap;
}

.engine-btn:hover {
  transform: translateY(-1px) scale(1.02);
  box-shadow: var(--glow-primary);
}

.engine-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.glow-primary { box-shadow: var(--glow-primary); }

.engine-status-grid {
  display: flex;
  flex-wrap: wrap;
  gap:0.5rem;
  margin-bottom:1.5rem;
  padding:1rem;
  background: var(--bg-card);
  border-radius:var(--radius-md);
  border: 1px solid var(--border-color);
}

.engine-status-card {
  display: flex;
  align-items: center;
  gap:0.375rem;
  padding:0.25rem 0.625rem;
  border-radius:var(--radius-full);
  background: var(--bg-tertiary);
  font-size:0.75rem;
}

/* ── 循环11-P1: 容灾可观测性（熔断器/令牌桶） ── */
.reli-sub-title { font-size:0.8125rem; font-weight:600; color: var(--text-secondary); margin-bottom:0.5rem; }
.reli-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap:0.5rem; }
.reli-card { padding:0.625rem 0.75rem; border-radius:var(--radius-sm); border:1px solid var(--border-color); background: var(--bg-tertiary); }
.reli-name { font-size:0.75rem; font-weight:600; color: var(--text-primary); margin-bottom:0.25rem; word-break: break-all; }
.reli-badge { display:inline-block; padding:0.125rem 0.5rem; border-radius:var(--radius-full); font-size:0.6875rem; font-weight:700; text-transform:uppercase; }
.reli-badge.st-closed { background: rgba(34,197,94,0.15); color: var(--accent-success); }
.reli-badge.st-open { background: rgba(239,68,68,0.15); color: var(--accent-danger); }
.reli-badge.st-half_open { background: rgba(245,158,11,0.15); color: var(--accent-warm); }
.reli-meta { font-size:0.6875rem; color: var(--text-muted); margin-top:0.25rem; }
.reli-tokens { height:0.375rem; border-radius:var(--radius-full); background: var(--bg-card); overflow:hidden; margin-top:0.25rem; }
.reli-token-fill { display:block; height:100%; border-radius:var(--radius-full); background: var(--accent-primary); transition: width 0.3s ease; }
.reli-empty { font-size:0.75rem; color: var(--text-muted); padding:0.5rem 0; }

.engine-status-dot {
  width:0.5rem;
  height:0.5rem;
  border-radius:50%;
  background: var(--text-muted);
}

.engine-status-dot.on {
  background: var(--accent-success);
  box-shadow: 0 0 6px var(--accent-success);
}

.engine-status-name { color: var(--text-secondary); font-weight: 500; }

/* ── 差异对比表 ── */
.diff-panel { padding:1.25rem; margin-bottom:1.5rem; }
.diff-panel-header {
  display: flex; align-items: center; gap:0.5rem;
  font-size:1.125rem; font-weight: 700; color: var(--text-primary);
  margin-bottom:1.25rem; flex-wrap: wrap;
}
.diff-panel-tag {
  margin-left:auto; font-size:0.625rem; font-weight: 700;
  padding:0.1875rem 0.625rem; border-radius:var(--radius-full);
  background: linear-gradient(135deg, var(--accent-warm), var(--accent-danger));
  color: #fff; text-transform: uppercase; letter-spacing: 0.5px;
}
.diff-category { margin-bottom:1.25rem; }
.diff-category-title {
  font-size:0.875rem; font-weight: 700; color: var(--accent-primary);
  margin-bottom:0.625rem; padding-bottom:0.375rem;
  border-bottom: 1px solid var(--border-color);
}
.diff-table { width:100%; border-collapse: collapse; table-layout: fixed; }
.diff-table th, .diff-table td {
  padding:0.625rem 0.75rem; text-align: left; font-size:0.8125rem;
  border-bottom: 1px solid var(--border-light);
  vertical-align: top; line-height:1.5;
}
.diff-th-other { width:28%; color: var(--text-muted); font-weight: 600; }
.diff-th-ours { width:52%; color: var(--accent-primary); font-weight: 600; }
.diff-th-tag { width:20%; }
.diff-td-other { color: var(--text-muted); }
.diff-td-ours { color: var(--text-primary); font-weight: 500; }
.diff-tag {
  display: inline-block; font-size:0.625rem; font-weight: 700;
  padding:0.125rem 0.625rem; border-radius:var(--radius-full);
  text-transform: uppercase; letter-spacing: 0.3px;
}
.diff-tag.核心创新 { background: color-mix(in srgb, var(--subject-co) 12%, transparent); color: var(--subject-co); }
.diff-tag.创新 { background: color-mix(in srgb, var(--subject-ds) 12%, transparent); color: var(--subject-ds); }
.diff-tag.独创 { background: color-mix(in srgb, var(--subject-os) 12%, transparent); color: var(--subject-os); }
.diff-tag.壁垒 { background: color-mix(in srgb, var(--accent-warm) 12%, transparent); color: var(--accent-warm); }
.diff-tag.合规 { background: var(--accent-success-10); color: var(--accent-success); }

@media (max-width: 768px) {
}

/* ── 演示按钮 ── */
.demo-trigger-row {
  display: flex;
  align-items: center;
  gap:0.75rem;
  margin-top:1rem;
}

.demo-btn {
  padding:0.5rem 1.25rem;
  border-radius:1.25rem;
  border: 1px solid var(--accent-primary);
  background: var(--accent-primary-10);
  color: var(--accent-primary);
  font-size:0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.demo-btn:hover {
  background: var(--accent-primary);
  color: #fff;
  transform: translateY(-1px);
}

.demo-hint {
  font-size:0.6875rem;
  color: var(--text-muted);
}

.engine-error {
  padding:0.75rem 1rem;
  background: var(--accent-danger-10);
  border-radius:var(--radius-sm);
  color: var(--accent-danger);
  font-size:0.8125rem;
}
</style>
