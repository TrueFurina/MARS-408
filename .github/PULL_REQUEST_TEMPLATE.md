<!--
  NetLearn / study-help-pro PR 模板
  配套：docs/代码审查标准.md · docs/代码审查流程.md
  审查者请按标准 §0 红线速查表与 §4 分级清单逐项核对。
-->

## 变更摘要
<!-- 一句话说明"改了什么、为什么"。勿堆砌 diff，讲意图。 -->

## 变更类型
<!-- 勾选适用项 -->
- [ ] 后端 agent / 引擎（GOMARL / FrugalRAG / Quality Gate）
- [ ] 后端 API / 数据层 / 迁移
- [ ] 前端 view / composable / store
- [ ] 安全相关（auth / guard / prompt / 密码学）
- [ ] 测试 / 评测脚本新增或修改
- [ ] career 线新增（`career_*` 模块/路由）

## 关联决策
<!-- 列出相关 ADR / CLAUDE 条款 / issue；无则填"无" -->
- ADR:
- CLAUDE.md 条款:
- Issue / 需求:

## 作者自检（提交前必过）
- [ ] 本地 CI 三件套通过（pytest 离线 / type-check+lint+vitest / build）
- [ ] 红线自查（标准 §0 速查表）：未改 embedding(e5-base-v2/768)、未破坏单写者(--workers 1)、未改 CSP/动词门控、无裸 fetch、无合成兜底数字、无 `except pass`
- [ ] 安全自查：无密钥提交(.env/config.json/*.db)、端点鉴权未缺失、v-html 过 DOMPurify
- [ ] 变更最小化：未夹带他人文件、未混入无关重构
- [ ] 关键改动有对应测试（如适用已做变异验证）

## 测试证据
<!-- 贴关键测试命令与结果行（passed/failed，勿只看退出码）；评测/诊断脚本须说明与生产同口径(ADR-017) -->

## 风险与回滚
<!-- 已知风险、影响面、如何回滚（如迁移/通道优先级/并发模型改动必填） -->

## 审查结论（审查者填）
- 结论：✅ Approve / 🔴 Request Changes / 💬 Comment
- 阻断项（🔴）：
- 应改项（🟡）：
- 建议项（💭）：
