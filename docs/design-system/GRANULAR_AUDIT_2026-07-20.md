# 设计系统逐文件深度审计 — 2026-07-20

> 续 07-19 v9 slice（`DESIGN_AUDIT_FINAL_2026-07-19.md`）。本轮按用户「逐个逐个排查与优化」指令，对 `src/**/*.vue` 做两维度全量扫描 + 逐文件修复 + 双门禁验证。

## 结论

| 维度 | 扫描范围 | 命中 | 修复 | 验证 |
|------|----------|------|------|------|
| 色彩/令牌反模式 | 52 个 `.vue` + `utils/*.ts` | 9 文件 | ✅ 全修 | vue-tsc 0 / vite build 0 |
| a11y 键盘可达性 | 52 个 `.vue` `@click` | 11 文件 15 处 | ✅ 全修 | vue-tsc 0 / vite build 0 |

**双门禁**：`vue-tsc --noEmit` EXIT=0；`vite build --outDir dist-vuecheck` EXIT=0（3.59s，221 模块，55 视图全编译）。

---

## 维度 1：色彩/令牌反模式清零

### 保留的文档例外（非违规）
- Canvas `ctx.strokeStyle/fillStyle` 字面量（AssessmentView/KnowledgeView/ProfileView/TcpHandshake 雷达与动画）
- `LangGraphFlow.vue` 运行时注入的局部 `--node-color` var
- `DesignSystemView.vue` 令牌展示表（该视图即设计系统本身）
- `_variables.css` 浅色主题 token 定义
- 有色背景上的 `color:#fff`（白字在紫/蓝/渐变上，双主题恒可读）

### 修复清单

| 文件 | 问题 | 修复 |
|------|------|------|
| `utils/evidence.ts` | `SEVERITY_COLOR`/`DISPOSITION_COLOR` 裸 hex（#ef4444/#f59e0b/#7c6af2/#22c55e） | → `var(--accent-danger/warm/primary/success)`（色值真源，一处改全局；color-mix 合法） |
| `components/EvidenceCheckPanel.vue` | 4 处模板 `\|\| '#7c6af2'/'#f59e0b'` fallback + `.ev-diff-*` CSS 裸 hex | → var() 语义 token |
| `views/KnowledgeView.vue` | `SUBJECT_COLORS` 裸 hex 数组 | → `SUBJECT_TOKENS` token 名 + 新增 `resolveToken()`（getComputedStyle 运行时解析，双主题安全），4 调用点包裹。**镜像 AssessmentView 范式** |
| `views/ProfileView.vue` | `TRAIT_COLORS` 旧 indigo `#6366F1`（非品牌） | → `#7c6af2`；其余 8 维分类色板保留（数据可视化分类色例外） |
| `components/TcpHandshakeAnimation.vue` | 3 处 `#6366F1` | → `#7c6af2`（Canvas 高亮渐变/箭头/状态盒） |
| `components/MindMapViewer.vue` | 调色板外 teal `rgba(15,118,110,0.04)` | → `rgba(124,106,242,0.04)`（品牌紫） |
| `views/ResourceView.vue:838` | 内联硬编码渐变 `linear-gradient(135deg,#7c6af2,#06b6d4)` | → `var(--gradient-primary)` |
| `components/XfyunWorkshop.vue:265` | 按钮 loading "思考中..." 文本 | → `.typing-indicator`（v9 流式三件套，aria-label="思考中"） |
| `views/PromptStudioView.vue:174` | 同上 | → `.typing-indicator` |

### 复核 grep（全 0 残留）
- `SUBJECT_COLORS` → 0 引用
- `#6366F1` / `#0F766E`（大小写不敏感）→ 0
- `EvidenceCheckPanel` 内 `'#7c6af2'` / `'#f59e0b'` → 0

---

## 维度 2：a11y 键盘可达性补齐

### 扫描方法
grep `<(div|span|li|ul|i|p|h[1-6])\s[^>]*@click`，剔除遮罩层（`@click.self` 关闭型 overlay，标准 dismiss 模式，不需 role）。多数可点击卡片在 07-19 已补齐 `role="button" tabindex="0" @keydown.enter/space`（Dashboard 大部分 / SkillCard / StepQuiz / SandboxView）。

### 修复清单（统一模式：role="button" tabindex="0" + @keydown.enter + @keydown.space.prevent，折叠头加 :aria-expanded，无文本加 aria-label）

**核心交互**
| 文件 | 元素 |
|------|------|
| `App.vue:185` | 顶栏 user-mini 菜单（全局可见） |
| `views/DashboardView.vue:246` | rec-card（与同级卡片不一致的唯一缺口） |
| `views/ChatView.vue:538` | send-error 关闭条 |
| `components/EvidenceCheckPanel.vue:140` | 冲突修正折叠头（+ :aria-expanded） |
| `views/ResourceView.vue:589` | 生成历史折叠头（+ :aria-expanded） |
| `views/SkillDetailView.vue:221` | 5 星评分（+ :aria-label="'评分 N 星'"） |

**图谱（`components/KnowledgeGraph.vue`）**
- 4 个资源动作项（讲解文档/练习题/思维导图/教学视频）
- 3 类节点：大纲 outline-node / 思维导图 mindmap-center+mindmap-node / 学习地图 map-node

**活跃视图**
| 文件 | 元素 |
|------|------|
| `views/KnowledgeGraphView.vue:178` | 已保存图谱卡 |
| `views/KnowledgeBaseView.vue:81` | 教材卡 |
| `views/ReviewView.vue:50` | 科目行 |
| `views/EnglishView.vue:90` | 词卡 |

---

## 范围与遗留

- **范围限定** `src/` 设计系统层。`py-server/`、`documents/`、`deliverables/` 属另一「全员冲刺」工作流，未触碰，避免冲突。
- **文档级 P0 待 team-lead 裁决**（非本审计范围）：KG 节点数 613/609 vs 86/82 文档冲突；SFT/GRPO 诚实标注；讯飞 10 vs 12 项；Agent 8 vs 9 节点数。这些需用户决策后再改文档。
- **已知低优先残留**：`SandboxView` 代码编辑器固定深色表面（#1a1a2e/#151528/#e8e8e8，终端式深色编辑器，双主题刻意保持，非违规）；KnowledgeView Canvas 标签灰 `rgba(148,163,184)` 在浅主题画布上对比度偏低（Canvas 字面量例外，可后续用 resolveToken('--color-text-2') 优化）。
- **构建产物** `dist-vuecheck` 清理被 harness safe-delete 回收站拦截（与既有 dist-qa/rem/test/verify 同类），不影响正确性。

## 验证命令
```bash
npx vue-tsc --noEmit                          # EXIT=0
npx vite build --outDir dist-vuecheck         # EXIT=0, 3.59s, 221 modules
```
