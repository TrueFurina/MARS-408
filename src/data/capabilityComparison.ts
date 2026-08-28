/** 引擎能力对比表数据 */
export interface ComparisonItem {
  category: string
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
      { other: '固定 top-k 检索', ours: '动态停止决策：基于覆盖率阈值的启发式判断，平均减少30%冗余调用', tag: '创新' },
      { other: '检索结果千篇一律', ours: '5因子个性化重排：薄弱点+15% / 已掌握-10% / 考查权重 / 难度匹配 / 目标分数', tag: '独创' },
    ],
  },
  {
    category: 'GOMARL 共识引擎',
    items: [
      { other: '普通多Agent：简单投票或串联', ours: 'GoMARL：NeuralMixer神经网络加权 + 证据冲突消解 + Agent辩论协议', tag: '核心创新' },
      { other: '无冲突检测机制', ours: '20类408矛盾对检测 + E5语义级冲突检测 + FrugalRAG证据检索验证', tag: '独创' },
      { other: '固定权重', ours: '动态权重：EWMA历史表现 + 学生画像 + 教学规则引擎', tag: '创新' },
    ],
  },
  {
    category: 'Agent 协作深度',
    items: [
      { other: '串行/简单路由', ours: 'LangGraph 10节点StateGraph + 条件边回退 + Agent辩论协议', tag: '独创' },
      { other: '输出即终版', ours: '辩论→反思→交叉质询→共识精炼', tag: '独创' },
      { other: '无教学规则约束', ours: '51个知识点DAG + 考查权重 + 跨科目关联 + Agent适配规则', tag: '创新' },
    ],
  },
  {
    category: 'LLM 集成',
    items: [
      { other: '单通道LLM', ours: '三通道容灾：讯飞星火X2 → DeepSeek → Qwen2.5', tag: '合规' },
      { other: '无合规考量', ours: '出题企业讯飞工具深度整合', tag: '合规' },
    ],
  },
  {
    category: '知识库规模',
    items: [
      { other: '单科/少量数据', ours: '408四科全覆盖：620 chunks + 73题 + 知识图谱', tag: '壁垒' },
      { other: '无知识图谱', ours: '四科知识图谱 + 跨科目关联（如TCP→死锁→进程同步）', tag: '壁垒' },
    ],
  },
]
