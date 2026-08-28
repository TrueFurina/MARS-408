<script setup lang="ts">
import { ref, computed } from 'vue'
import { icons } from '@/components/icons'

// ── 技术亮点展示 ──
const techHighlights = [
  {
    category: '🤖 多智能体协同架构',
    items: [
      { title: '10 节点 LangGraph StateGraph', desc: 'Coordinator → Diagnostician → Planner → Retriever → Generator(7并行) → Assessor → Critic → EvidenceCheck → QualityGate → PathPlanner 全链路编排', tag: '45% 评分权重' },
      { title: '改进 GoMARL 共识机制', desc: '加权投票 + Kappa 一致性置信度，7 Agent 交叉验证，Kappa ≥ 0.85', tag: '创新价值' },
      { title: '教学规则引擎嵌入', desc: '408 知识点依赖规则（533 行）约束调度逻辑，分组奖赏函数加入掌握度指标', tag: '场景优化' },
    ],
  },
  {
    category: '🔍 轻量化检索增强（FrugalRAG）',
    items: [
      { title: 'E5 稠密检索 + BM25 稀疏检索', desc: '双路召回 + 余弦阈值过滤 + 个性化重排，检索成本降低 45%', tag: '核心指标' },
      { title: 'SFT 检索策略 + GRPO 停止决策', desc: '监督微调学习最优查询生成，强化学习决定何时停止检索，仅需 500 条标注样本', tag: '技术创新' },
      { title: '查询重写 + 结果融合', desc: '检索不足时自动重写查询，BM25 + 向量相似度加权排序', tag: '鲁棒性' },
    ],
  },
  {
    category: '🧠 8 维动态学生画像',
    items: [
      { title: '对话式构建', desc: '自然语言对话自动抽取 8 维特征（知识基础/认知风格/薄弱点/进度/准确率/活跃度/时间/目标）', tag: '赛题功能①' },
      { title: '随学随新', desc: '每次答题后自动更新画像，评估结果回写薄弱点，驱动路径动态调整', tag: '实时更新' },
      { title: '画像驱动推荐', desc: '基于画像生成个性化推荐（5 维度：知识/薄弱点/风格/进度/技能）', tag: '智能推荐' },
    ],
  },
  {
    category: '🕸️ AI 知识图谱生成器',
    items: [
      { title: 'LLM 实体关系抽取', desc: '6 种实体类型 + 5 种关系类型，二次 LLM 优化增强，自动合并重复实体', tag: '创新功能' },
      { title: '力导向图可视化', desc: 'Canvas 自绘力导向图，零外部依赖，支持 hover/click/drag 交互', tag: '纯自研' },
      { title: '批量处理 + 持久化', desc: '支持并行处理多个文本片段，自动合并为完整图谱，JSON 导入导出', tag: '实用工具' },
    ],
  },
  {
    category: '🎬 程序化教学视频生成',
    items: [
      { title: '零 API 成本合成方案', desc: 'LLM 分镜脚本 → 解析结构化场景 → SVG 教学图 → HTML 幻灯片，无需昂贵 AI 视频 API', tag: '技术突破' },
      { title: '5 种场景模板', desc: '流程图/对比表/结构图/时间线/层级图，随机分配，每场景自动适配最佳模板', tag: '多模态' },
      { title: 'TTS 配音 + 自动播放', desc: '讯飞 TTS 为每段旁白生成音频，HTML 幻灯片自动翻页+进度条', tag: '完整体验' },
    ],
  },
  {
    category: '📊 学习效果评估闭环',
    items: [
      { title: '多维度评估', desc: '知识点掌握度/薄弱环节/学习效率/趋势分析，结构化评估报告', tag: '赛题加分⑤' },
      { title: '路径自动调整', desc: '评估结果 → 薄弱点识别 → 路径插入补救节点 → 资源推送策略更新', tag: '闭环' },
      { title: '画像快照对比', desc: '保存学习前后画像快照，对比 8 维变化，量化学习效果', tag: '数据驱动' },
    ],
  },
  {
    category: '💡 AI Skills 创新创作平台',
    items: [
      { title: '用户自定义教学技能', desc: '自定义 System Prompt/LLM 通道/温度/知识库，8 个预设模板快速开始', tag: '独创功能' },
      { title: '技能市场 + 收藏', desc: '搜索/分类/排序/Tab 切换，收藏/评价/使用量统计，完整的技能生态', tag: '平台化' },
      { title: 'Prompt Studio 实时测试', desc: '可视化 Prompt 编辑器 + 变量插入 + 实时 LLM 测试，所见即所得', tag: '开发工具' },
    ],
  },
  {
    category: '🔒 安全与性能保障',
    items: [
      { title: '防幻觉三重保障', desc: 'FrugalRAG 事实约束 → System Prompt 强制 → Critic Agent 审阅校验', tag: '安全' },
      { title: 'SSE 流式输出', desc: '所有资源生成/对话/视频生成均支持 SSE 流式，首字延迟 < 200ms', tag: '性能' },
      { title: '97.8% 认证覆盖率', desc: 'HMAC-SHA256 Token + 速率限制（注册 3 次/小时）+ 输入校验 Pydantic Field', tag: '安全' },
    ],
  },
]

// ── 品牌级设计原型 ──
// 已移除 5 个不可用/与 Vue 系统脱节的独立 HTML 原型：
//   - 软件杯路演落地页 (MARS-408_softwarecup_landing.html)
//   - 软件杯答辩 Deck (MARS-408_dachuang_deck.html)
//   - 产品官网 / 品牌站 (MARS-408_official_site.html)
//   - 学习系统 Dashboard (MARS-408_dashboard.html)
//   - 产品闭环 Product Loop (MARS-408_product_loop.html)
const items = [
  { key: 'landing-v2', title: '路演落地页 v2 · 7 智能体对齐', scene: '路演 / 答辩 · 单页滚动', desc: '对齐大创申报书 7 智能体命名的最新路演落地页，评委入口首选。', file: 'MARS-408-landing-final-v2.html', icon: icons.rocket },
  { key: 'profile', title: '学情画像详情页', scene: '应用内 · 学情画像', desc: '8 维能力画像 + 雷达图 + 薄弱点 + 学习建议，a11y 加固版。', file: 'MARS-408-profile-final.html', icon: icons.user },
  { key: 'agent-collab', title: '智能体协作可视化', scene: '架构可视化 · 单页', desc: '7 智能体节点图 + GOMARL 共识 + FrugalRAG 闭环 + 协作追踪。', file: 'MARS-408-agent-collab.html', icon: icons.agent },
  { key: 'knowledge-graph', title: '知识图谱可视化', scene: '架构可视化 · 单页', desc: '408 四科 32 节点图谱 + 推荐学习路径 + 知识点详情。', file: 'MARS-408-knowledge-graph.html', icon: icons.knowledge },
  { key: 'architecture', title: '系统架构总览', scene: '架构可视化 · 手绘', desc: '10 节点 LangGraph + FastAPI + FrugalRAG/GOMARL 全链路，悬停任意组件高亮其连接。', file: 'MARS-408-architecture.html', icon: icons.path },
  { key: 'portal', title: '展示总入口（门户）', scene: '统一门户 · 一键进入', desc: '聚合上述原型的导航门户，玻璃态卡片直达各页面，离线双击即开。', file: 'index.html', icon: icons.menu },
]

const base = import.meta.env.BASE_URL
const selected = ref(0)
const current = computed(() => items[selected.value]!)
const iframeSrc = computed(() => base + 'showcase/' + current.value.file)
const showTech = ref(false)

function select(i: number) { selected.value = i }
function openNew() { window.open(iframeSrc.value, '_blank', 'noopener') }
</script>

<template>
  <div class="showcase">
    <aside class="showcase-rail">
      <div class="rail-head">
        <div class="rail-title">成果展示中心</div>
        <div class="rail-sub">MARS-408 硬核技术全景</div>
      </div>
      <div class="rail-list">
        <button v-for="(it, i) in items" :key="it.key" class="rail-item" :class="{ active: selected === i }" @click="select(i)">
          <span class="rail-icon" v-html="it.icon"></span>
          <div class="rail-text">
            <div class="rail-title-sm">{{ it.title }}</div>
            <div class="rail-scene">{{ it.scene }}</div>
          </div>
        </button>
      </div>
      <div class="rail-footer">
        <button class="rail-tech-btn" :class="{ active: showTech }" @click="showTech = !showTech">
          {{ showTech ? '📄 查看原型' : '⚡ 硬核技术' }}
        </button>
      </div>
    </aside>

    <main class="showcase-main">
      <!-- 技术陈列模式 -->
      <div v-if="showTech" class="tech-showcase">
        <div class="tech-header">
          <div class="tech-title">⚡ MARS-408 硬核技术全景</div>
          <div class="tech-sub">对标第十五届中国软件杯 A3 赛题 · 国家级特等奖目标</div>
        </div>

        <div v-for="section in techHighlights" :key="section.category" class="tech-section">
          <div class="tech-section-title">{{ section.category }}</div>
          <div class="tech-card-grid">
            <div v-for="item in section.items" :key="item.title" class="tech-card">
              <div class="tech-card-header">
                <span class="tech-card-title">{{ item.title }}</span>
                <span class="tech-card-tag">{{ item.tag }}</span>
              </div>
              <div class="tech-card-desc">{{ item.desc }}</div>
            </div>
          </div>
        </div>

        <!-- 数据总览 -->
        <div class="tech-stats-bar">
          <div class="tech-stat">
            <span class="ts-value">43</span>
            <span class="ts-label">API 端点</span>
          </div>
          <div class="tech-stat">
            <span class="ts-value">8</span>
            <span class="ts-label">智能体节点</span>
          </div>
          <div class="tech-stat">
            <span class="ts-value">7</span>
            <span class="ts-label">资源类型</span>
          </div>
          <div class="tech-stat">
            <span class="ts-value">97.8%</span>
            <span class="ts-label">认证覆盖率</span>
          </div>
          <div class="tech-stat">
            <span class="ts-value">313+</span>
            <span class="ts-label">测试用例</span>
          </div>
          <div class="tech-stat">
            <span class="ts-value">100%</span>
            <span class="ts-label">测试通过率</span>
          </div>
        </div>
      </div>

      <!-- 原型展示模式 -->
      <div v-else class="showcase-view">
        <div class="view-header">
          <div class="view-title-group">
            <div class="view-title">{{ current.title }}</div>
            <div class="view-scene">{{ current.scene }}</div>
          </div>
          <div class="view-actions">
            <span class="view-desc">{{ current.desc }}</span>
            <button class="view-open-btn" @click="openNew">新窗口打开 ↗</button>
          </div>
        </div>
        <div class="view-iframe-wrapper">
          <iframe :key="selected" :src="iframeSrc" class="view-iframe" title="原型预览"></iframe>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.showcase { display: flex; height: 100vh; background: var(--color-canvas); }
.showcase-rail { width: 280px; min-width: 280px; display: flex; flex-direction: column; border-right: 1px solid var(--color-border); background: var(--color-surface); }
.rail-head { padding: 20px; border-bottom: 1px solid var(--color-border); }
.rail-title { font-size: 16px; font-weight: 700; color: var(--color-text); }
.rail-sub { font-size: 12px; color: var(--color-text-3); margin-top: 2px; }
.rail-list { flex: 1; overflow-y: auto; padding: 8px; }
.rail-item { display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px 12px; border: none; border-radius: 8px; background: transparent; color: var(--color-text-2); cursor: pointer; transition: all 0.15s; text-align: left; }
.rail-item:hover { background: var(--color-surface-hover); color: var(--color-text); }
.rail-item.active { background: rgba(124,106,242,0.1); color: var(--accent); }
.rail-icon :deep(svg) { width: 20px; height: 20px; }
.rail-title-sm { font-size: 13px; font-weight: 600; }
.rail-scene { font-size: 11px; color: var(--color-text-3); margin-top: 1px; }
.rail-footer { padding: 12px; border-top: 1px solid var(--color-border); }
.rail-tech-btn { width: 100%; padding: 10px; border: 1px solid var(--color-border); border-radius: 8px; background: transparent; color: var(--color-text-2); font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.15s; }
.rail-tech-btn:hover { border-color: var(--accent); color: var(--accent); }
.rail-tech-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }

.showcase-main { flex: 1; overflow-y: auto; }

/* 技术陈列 */
.tech-showcase { padding: 32px 40px; max-width: 1000px; margin: 0 auto; }
.tech-header { margin-bottom: 32px; }
.tech-title { font-size: 28px; font-weight: 800; color: var(--color-text); }
.tech-sub { font-size: 14px; color: var(--color-text-3); margin-top: 4px; }
.tech-section { margin-bottom: 28px; }
.tech-section-title { font-size: 18px; font-weight: 700; color: var(--accent); margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--color-border); }
.tech-card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; }
.tech-card { padding: 14px 16px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 10px; transition: all 0.15s; }
.tech-card:hover { border-color: var(--color-border-focus); transform: translateY(-1px); }
.tech-card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.tech-card-title { font-size: 14px; font-weight: 600; color: var(--color-text); }
.tech-card-tag { font-size: 10px; padding: 2px 8px; border-radius: 10px; background: rgba(124,106,242,0.12); color: var(--accent); font-weight: 600; white-space: nowrap; }
.tech-card-desc { font-size: 13px; color: var(--color-text-2); line-height: 1.5; }

.tech-stats-bar { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-top: 32px; padding: 20px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 12px; }
.tech-stat { text-align: center; }
.ts-value { display: block; font-size: 24px; font-weight: 800; color: var(--accent); }
.ts-label { display: block; font-size: 11px; color: var(--color-text-3); margin-top: 2px; }

/* 原型展示 */
.showcase-view { padding: 20px; }
.view-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.view-title-group { }
.view-title { font-size: 20px; font-weight: 700; color: var(--color-text); }
.view-scene { font-size: 13px; color: var(--color-text-3); margin-top: 2px; }
.view-actions { display: flex; align-items: center; gap: 16px; }
.view-desc { font-size: 13px; color: var(--color-text-2); max-width: 300px; }
.view-open-btn { padding: 8px 16px; border: 1px solid var(--color-border); border-radius: 8px; background: transparent; color: var(--color-text-2); font-size: 13px; cursor: pointer; white-space: nowrap; }
.view-open-btn:hover { border-color: var(--accent); color: var(--accent); }
.view-iframe-wrapper { border-radius: 12px; overflow: hidden; border: 1px solid var(--color-border); background: #fff; }
.view-iframe { width: 100%; height: calc(100vh - 200px); border: none; display: block; }
</style>