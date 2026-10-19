/** 引擎能力对比表数据 */
export interface ComparisonItem {
  category: string
  /** 左列表头，缺省「普通方案」 */
  otherLabel?: string
  /** 右列表头，缺省「本平台真版」 */
  oursLabel?: string
  items: {
    other: string
    ours: string
    tag: string
  }[]
}

export const capabilityComparison: ComparisonItem[] = [
  {
    category: 'FrugalRAG 检索引擎',
    items: [
      { other: '普通RAG：直接向量检索', ours: 'FrugalRAG：E5向量+BM25融合 → 启发式停止决策 → 个性化重排', tag: '核心创新' },
      { other: '固定 top-k 检索', ours: '动态停止决策：基于覆盖率阈值的启发式判断，命中足够覆盖即停止检索', tag: '创新' },
      { other: '检索结果千篇一律', ours: '5因子个性化重排：薄弱点+15% / 已掌握-10% / 考查权重 / 难度匹配 / 目标分数', tag: '独创' },
    ],
  },
  {
    category: 'GOMARL 共识引擎',
    items: [
      { other: '普通多Agent：简单投票或串联', ours: 'GoMARL：NeuralMixer神经网络加权 + 证据冲突消解 + Agent辩论协议', tag: '核心创新' },
      { other: '无冲突检测机制', ours: '20类专业矛盾对检测 + E5语义级冲突检测 + FrugalRAG证据检索验证', tag: '独创' },
      { other: '固定权重', ours: '动态权重：EWMA历史表现 + 学生画像 + 教学规则引擎', tag: '创新' },
    ],
  },
  {
    category: 'Agent 协作深度',
    items: [
      { other: '串行/简单路由', ours: 'LangGraph 11 节点 StateGraph + 条件边回退 + Agent辩论协议', tag: '独创' },
      { other: '输出即终版', ours: '辩论→反思→交叉质询→共识精炼', tag: '独创' },
      { other: '无教学规则约束', ours: '51个知识点DAG + 考查权重 + 跨科目关联 + Agent适配规则', tag: '创新' },
    ],
  },
  {
    category: 'LLM 集成',
    items: [
      { other: '单通道LLM', ours: '四通道容灾：讯飞星火X2 → DeepSeek → Qwen3.8-Max → 智谱GLM', tag: '合规' },
      { other: '无合规考量', ours: '出题企业讯飞工具深度整合', tag: '合规' },
    ],
  },
  {
    category: '知识库规模',
    items: [
      { other: '单科/少量数据', ours: '专业四科全覆盖：2015 chunks + 230题 + 知识图谱', tag: '壁垒' },
      { other: '无知识图谱', ours: '四科知识图谱 + 跨科目关联（如TCP→死锁→进程同步）', tag: '壁垒' },
    ],
  },
  {
    category: '同类多智能体教育项目对比',
    otherLabel: '同类项目',
    oursLabel: '芒得很职',
    items: [
      { other: 'OpenMAIC（清华）：LangGraph 两段式「课程生产+课堂体验」，内容供给侧（700+学生实测，84.1% 满意度）', ours: '对抗实训 + 六维学情闭环 + 成效证据链，能力评估侧——赛道相邻，非同构竞品', tag: '独创' },
      { other: 'AgentSchool：教师/学生双门户 + 随堂测验自动批改（开源中唯一带班级流程，但较浅）', ours: '全链路教师闭环：建班→花名册→任务码→看板 + AI 简评与报告导出', tag: '壁垒' },
      { other: 'EduPlanner：三智能体对抗协同生成教案（对抗理念与 GOMARL 弱同源，但用于教案而非评估）', ours: 'GOMARL 共识用于学情评估：NeuralMixer 动态加权 + 证据冲突消解', tag: '独创' },
      { other: 'Google Vantage（2026-05 公开报道，未实测）：场景→对抗角色扮演→行为抽取→量规评分，逐分挂证据', ours: 'ECD 证据链评审与之同构，且多一层取证闸退出码契约——零真实用户时禁称成效', tag: '创新' },
      { other: 'AI 陪练剧场：六维雷达结果评分（维度定义与本平台不同，对外须注明差异）', ours: '过程性证据链：每分挂原话证据 + 溯源，不止结果雷达', tag: '壁垒' },
    ],
  },
]
