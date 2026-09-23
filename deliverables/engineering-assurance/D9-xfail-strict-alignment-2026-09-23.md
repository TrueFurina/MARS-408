# D9 消灭永久/陈旧 skip·xfail（P1 技术债 Priority=21）

> 分支：`career-literacy` ｜ 日期：2026-09-23 ｜ 类型：Test hygiene

## 1. 问题

技术债文档原文：

> D9：消灭永久/陈旧 skip·xfail（xfail(strict=False)→strict=True 或移除；确保 CI 装 respx）。

经全仓 grep（`py-server` 主测试套件，crypto_platform 副本已被 `addopts --ignore=tests/crypto_platform` 排除收集）定位到三类标记：

| 位置 | 标记 | 性质 |
|---|---|---|
| `tests/test_import_queue_single_writer.py:260` | `xfail(strict=False)`（TC-12 / Gap B 去重缺口） | 已知缺口跟踪 |
| `tests/test_video_feedback.py:26,44` | `xfail`（默认 strict=False） | "需真实 LLM" 视频生成 |
| `tests/test_xfyun_services.py:164…291` | `skipif(not _HAVE_REPX)` ×9 | respx 缺失时跳过 |
| `tests/test_m3_mappo_policy.py:123` / `test_m4_marl_bench.py:42` | `skipif(_ensure_torch() is None)` | torch 能力门禁 |
| `tests/conftest.py:24-31` | `_skip_milvus`/`_skip_segv`/`_iso_skip` 动态注入 | requires_milvus/segv_env/isolation |

## 2. 关键核实（动手前，避免误删合法标记）

- **respx 已声明且已锁定**：`pyproject.toml` `[project.optional-dependencies] test` 含 `"respx>=0.21.0"`（line 33）；`uv.lock` 已含 `name = "respx"` 且 `marker = "extra == 'test'"`（line 1247/2356）。CI 走 `uv sync --frozen` 必装 → D9「确保 CI 装 respx」**已满足**，`skipif(not _HAVE_REPX)` 保留为安全网即可，无需改。
- **torch skipif / conftest 动态 skip 合法**：均为能力/环境门禁（无 torch 则跳过、无真实 Milvus 则跳过、隔离测试仅 --noconftest 跑），非"永久/陈旧"问题，不动。
- **crypto_platform 副本**：已被 `--ignore=tests/crypto_platform` 排除收集，不在主套件内，D9 不触及（其内 xfail 为 vendored 第三方副本，非本仓库责任）。

## 3. 修复（仅针对 2 处宽松 xfail）

### 3.1 TC-12 `test_import_queue_single_writer.py`
`strict=False` → **`strict=True`**。

理由：该用例跟踪 ADR §6 risk 6「InMemoryVectorStore.add 不去重 / Worker 缺 seen_ids 预过滤」已知缺口；Docstring 明确「Dev 补全 seen_ids 后本用例应转绿」。原 `strict=False` 会在缺口被悄悄修复（意外 XPASS）时**静默通过**，掩盖"应移除标记"的事实。`strict=True` 使意外 XPASS 变为 loud-fail，提示维护者移除标记。

### 3.2 `test_video_feedback.py` ×2
`xfail` → **`xfail(strict=True)`** 并**修正过期 reason**。

原 reason「需要真实 LLM 连接，在 CI 中可能超时」不准确：本套件 `conftest.py` 的 `mock_llm` autouse fixture 已注入 mock LLM，测试环境**永不连真实 LLM**；用例实际失败是因 mock 无法产出有效 `scenes/duration/<svg>` 内容，而非连接超时。修正为准确描述，并加 `strict=True` 使其与 TC-12 一致（缺口闭合即 loud-fail）。

## 4. 验证

- 主套件相关用例实测（venv python + 去污染 env 调用）：
  - `test_video_feedback.py` + `test_import_queue_single_writer.py` 全跑：**13 passed, 3 xfailed**（3 个 xfail 仍按预期 XFAIL，`strict=True` 不改变已预期的 XFAIL 行为，仅对意外 XPASS 生效）。
  - `test_xfyun_services.py`：**21 passed**（respx 本地 0.23.1 已装，9 个 respx 用例实际运行而非跳过，印证 CI 装 respx 后亦如此）。
- `strict=True` 不影响既有 XFAIL 结果，仅把"意外变绿"转为失败信号，符合 D9「xfail(strict=False)→strict=True」要求。

## 5. 边界与未做

- 未改动 `test_m3/test_m4` 的 torch skipif、conftest 动态 skip、crypto_platform 副本（均合法或非本仓库责任）。
- 未删除任何 xfail：TC-12 与视频生成用例均属"需真实能力才能转绿"的合法 xfail，移除会导致 CI 红，故保留并收紧 strict 而非删除。
- 未触发全量回归（改动仅为标记 strict 标志 + reason 文本，已用相关文件 + respx 文件验证；全量 919 passed 基线与本改动无关，未引入新失败面）。
