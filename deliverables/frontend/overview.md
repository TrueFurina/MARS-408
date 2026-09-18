# 交付概览 · 前端战略规划 + P0 落地（2026-09-14 规划 / 09-15 执行）

## 本次增量：P0「证据链打通」已落地

上一轮（09-14）只做分析、未动源码。本轮把 P0 六项 + 两项附加项全部落地，并**更正了原规划的两处错误判断**。

### 两处更正（重要）

1. **`scripts/benchmark_results.json` 不是真产物。** 其 `results.mode === "demo"`，
   由 `scripts/benchmark.py --demo`（合成数据模式）生成。原规划 P0-1/P0-2 指错了数据源。
   真产物在 `py-server/experiments/results/benchmark_2026-08-17.json`。
2. **`getFallback*` 本来就返回空数组。** 真实缺陷是 `fetchRecentSessions/fetchRecommendedTasks`
   中 `if (data.length >= 3)` —— 真实数据不足 3 条就被整批丢弃。

### 改动清单

| 文件 | 改动 |
|---|---|
| `py-server/api/benchmark.py` | **新增** `/benchmark/results`、`/benchmark/results/per-question`；只读真产物，显式排除 `mode=="demo"`，缺失即 404/500，**绝不回退合成数据** |
| `py-server/api/__init__.py`、`py-server/main.py` | 注册新路由 |
| `src/composables/useBenchmark.ts` | **新增**：`provenance` / `rows`（28 查询）/ `questions`（30 题×3 次）/ `summary`，契约层雏形，**无 fallback** |
| `src/views/BenchmarkView.vue` | 四组硬编码常量清零；指标卡改为 recallΔ / precisionΔ / accuracyΔ（pp）；实验2「矛盾检出数」移除（真产物无此字段）→ 改为准确率 + Cohen's κ + 逐题点阵；新增溯源条、空态、如实说明块 |
| `src/views/DashboardView.vue` | 8 Agent 状态灯全删（后端无运行时接口）→ 改展示职责；热力图 `variance` 公式删除 → 无数据整格 `—` |
| `src/stores/studyStore.ts` | 删除 `>= 3` 丢弃门槛 |
| `src/App.vue` | `ErrorBoundary` 提升到路由级，一处覆盖全部 41 页 |
| `src/components/ErrorBoundary.vue` | 修复空图标占位 + 「重试」不重挂载两处缺陷 |
| `src/components/CompareProfilesPanel.vue`、`TeachingRulesPanel.vue` | 裸 `fetch` 收敛到 `utils/api.ts`（试点） |
| `CLAUDE.md` | 新增「前端三条硬约束」章节 |

### 真数据对原叙事的冲击（不可回避）

| 指标 | 旧（demo 合成） | 真产物 |
|---|---|---|
| Top-5 召回率 | 92.4% vs 64.3%（+28pp） | 78.6% vs 67.9%（**+10.7pp**） |
| 平均延迟 | 143ms vs 59ms（2.4×） | 108.2ms vs 5.4ms（**20×**） |
| Token 变化 | 隐含"省 34% 噪声" | **−0.14%（反而略增）** |
| 矛盾检出数 | 40 vs 0 | **字段不存在**，已移除 |

结论：真实实验仍支持"FrugalRAG 检索质量更优、NeuralMixer 共识准确率更高（83.3% vs 76.7%）"，
但幅度远小于旧文案，且伴随显著延迟代价。页面已载明。

### 验证

`vue-tsc --build --force` **0 错误** · `vite build` **4.72s 通过** · `vitest run` **43 passed**
· `py-server/_verify_benchmark_api.py` 断言全过（28 查询 / 30 题 / seed 20260719）。

---

## 上一轮内容（09-14 战略分析，仍然有效）

对 `study-help-pro` 前端做实测基线体检 + 根因诊断 + 战略规划，主文档
`deliverables/frontend/前端战略规划-2026-09-14.md`。

- **首要风险是证据链断裂，不是技术债**：后端无 benchmark 路由，前端把四组聚合数写死（现已修复）。
- **战略主张**：前端从「演示壳」升级为「证据壳（Evidence Shell）」—— 可信 / 可证 / 可演进。
- **路线图**：P0 ✅ → P1 契约与容错（4 人天）→ P2 体验性能（3 人天）→ P3 演示可信度。

### 关键数字（09-14 实测基线）

| 项 | 值 |
|---|---|
| src 源文件 | 101 个 / 31,435 行 |
| 视图 / 路由 | 41 个 view / 37 条路由 |
| 测试 | 8 文件 / 43 用例（仍无组件/视图测试） |
| 首屏 JS (gzip) | ~82 KB（健康） |
| `v-html` / `any` / 裸 fetch | 202 / 327 / 14（本轮收敛 2 处） |
| ErrorBoundary 覆盖 | **41 / 41 页面**（本轮从 1 提升到全覆盖） |

## 遗留 / 下一步

- **P1（契约层）**：无 `src/types/`，327 处 `any` —— 建议从 `useBenchmark.ts` 的 interface 开始，
  用 OpenAPI 生成主力类型。
- **隐患**：`scripts/benchmark_results.json`（demo 合成）仍在仓库中，容易被后人误接，建议加醒目
  文件头注释或移入 `scripts/_demo/`。
- **分支**：本轮改动全部在 `career-literacy` 工作树完成（切 `main` 曾被 SIGTERM 中断造成
  `index.lock` 残留，已恢复）。同步到 `main` 需 `cherry-pick` 指定文件，勿整树合并。
