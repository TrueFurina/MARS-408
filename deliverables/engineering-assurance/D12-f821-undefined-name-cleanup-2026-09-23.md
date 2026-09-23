# D12 · F821 未定义名（8 处 latent 缺陷）清理 — 2026-09-23

> 承接 D11（ruff F401 清零）之后，对 ruff 扫描出的 **8 处 F821（Undefined name）** 专项清理。
> 这 8 处均经 `git show HEAD` 核对为 **D11 之前既有的 latent 缺陷**（ruff 此前从未在仓库跑过），非 D11 引入。
> 本项仍守红线：**零行为改动**（仅补缺失的 import / 模块级定义，未删任何既有逻辑）。

## 一、8 处 F821 清单与判定

| # | 文件:行 | 未定义名 | 上下文 | 性质 | 修复方式 |
|---|---------|---------|--------|------|---------|
| 1 | `api/engine.py:98` | `logger` | `except` 降级分支 `logger.debug(...)`，全文无 `logger`/`logging` 定义 → 降级路径会再抛 `NameError` 掩盖原错 | 真实 latent bug（运行时可达） | 模块级加 `import logging` + `logger = logging.getLogger(__name__)` |
| 2 | `api/knowledge_base.py:133` | `Path` | API 端点 `api_map_pdf_pages` 真实可达，缺 `pathlib` import → 调用即 `NameError` | 真实 latent bug（运行时可达） | `from pathlib import Path`（仅原 `import os`，`Optional` 已 import） |
| 3 | `api/knowledge_base.py:134` | `Path` | 同上（`pdf_path: Optional[Path]`） | 同上 | 同上一处修复覆盖 |
| 4 | `api/knowledge_base.py:138` | `Path` | 同上（`Path(f).stem` / `Path(target).stem`） | 同上 | 同上 |
| 5 | `api/knowledge_base.py:139` | `Path` | 同上（`Path(root) / f`） | 同上 | 同上 |
| 6 | `services/tts_service.py:49` | `TTS` | `_melo_instances: dict[str, "TTS"] = {}` 字符串注解内未定义 forward ref（文件无 `from __future__ import annotations`） | 类型注解名缺失（运行时不求值，但 ruff 报 F821） | 该文件 `from typing import Optional` → `Optional, Any`，注解改 `dict[str, Any]` |
| 7 | `train_mixer.py:57` | `logger` | `if GroupMixerNet is None:` 防御分支 `logger.error(...)`，但 `logger` 在 line 61 才定义（早于它） | 真实 latent bug（torch 装但 mixer 加载失败时触发） | 将 `logger = logging.getLogger("train_mixer")` 上移至 line 30 `import logging` 之后；删除 line 61 重复定义（保留 `logging.basicConfig`） |
| 8 | `train_mixer.py`（line 57 同处引用） | — | 与上同一条语句 | — | 同上 |

> 行号以 `uvx ruff@latest check --select F821 --output-format concise .` 实测；knowledge_base 5 处 + engine 1 处 + tts 1 处 + train_mixer 1 处 = **8 处**。

## 二、修复原则（守红线）

- **只补缺失，不删既有**：4 个文件共 `+9 / -3` 行，净增定义/import，未移除任何业务代码。
- **不做行为改动**：
  - `engine.py` 仅在 `except` 降级分支新增可用的 `logger`（之前该路径会 `NameError`，修复后正常 `logger.debug`，行为更正确而非改变主流程）。
  - `knowledge_base.py` 仅让 `api_map_pdf_pages` 端点从"必然崩溃"变为"可正常执行"（消除了一个真实死端点）。
  - `train_mixer.py` 仅调整 `logger` 初始化顺序（防御分支现在能正确 log 而非 `NameError`）。
  - `tts_service.py` 仅将注解中的未定义 `"TTS"` 改为 `Any`（运行时注解本就不求值，无副作用）。
- **未触及 `cn_distinction` dead route**：属于 D11 已上报的 finding，本次不接线不删模块（保持零行为）。

## 三、验证（证据先行）

| 验证项 | 命令 / 方式 | 结果 |
|--------|------------|------|
| F821 归零 | `uvx ruff@latest check --select F821 .` | **All checks passed!**（0 处） |
| F401 仍 0（新增 import 必须被使用，不能引入新未用 import） | `uvx ruff@latest check --select F401 .` | **0 处**（与 D11 后一致） |
| 语法全树通过 | `.venv/.../python.exe -m compileall -q -x '(\.venv\|crypto_platform)' .` | exit 0 |
| 运行时 import 冒烟 | `import api.engine`（logger 已定义）/ `import api.knowledge_base`（Path 已定义）/ `import services.tts_service`（Any 已定义） | 三模块均 `OK` |
| 相关 pytest 子集零回归 | `pytest test_engine_modules / test_knowledge_base_english / test_knowledge_graph / test_path_traversal_knowledge_base` | **43 passed, 57 skipped, 0 failed, 0 error**（exit 1 仅因子集覆盖率 21% < addopts 阈值 54%，非功能失败） |

## 四、提交与推送

- 改动文件：`py-server/api/engine.py`、`py-server/api/knowledge_base.py`、`py-server/services/tts_service.py`、`py-server/train_mixer.py`（共 +9/-3）。
- 提交经 5 道门禁（密钥 / 诚实口径 / 口径数字 / 结构守卫 / **F401**）全过。
- SSH 推送 `refs/heads/career-literacy`。

## 五、结论

P1 序列（D5/D6/D2/D14/D16/D9/D11）收口后，本次顺手消除 8 处 pre-existing F821 latent 缺陷，仓库 py-server 静态未定义名归零。
工程保证：ruff F401=0、F821=0、整树 compileall 通过、核心 API/服务模块 import 冒烟通过、相关测试零回归。
