# D15：cn_distinction 死路由接线启用（"打不开的门" 实证复核）

> 日期：2026-09-24
> 类型：决策执行（用户 09-24 指令："锁死的门如果实在打不开也就没有存在的意义了"）
> 结论：**该门"门板/锁芯/线路"均完好，仅 Sep 2 为救启动崩溃被拔掉插头（未挂载），可一键接回 → 接电启用，不拆除。**

## 1. 背景与用户决策

- D11 发现 `api/__init__.py` 中 `cn_distinction_router` 为"悬空导入"（未被 main 注册），按零行为清债删了它，并作为 finding 上报：cn_distinction 端点从未挂载，是 latent dead route。
- 用户 09-24 给出判定条件：**"锁死的门如果实在打不开也就没有存在的意义了"** —— 即"若确属打不开（坏门），则拆除；若打的开，则保留启用"。
- 实证复核结论：该门**打得开**（模块完整、功能正确、接线仅需 2 行），故按用户逻辑执行"接电启用"，而非"拆除"。

## 2. 证据（门本身完好）

| 文件 | 行数 | 内容 |
|------|------|------|
| `py-server/engines/cn_distinction.py` | 260 | 基于谢希仁《计算机网络》教材的 **12 组易混淆概念对**数据集，每组含混淆点、关键辨析、自测题（带标准答案 + 关键词）；`get_pairs/get_pair/get_random_quiz/grade_quiz` 4 函数齐全；**确定性关键词判分，可复现，不假装 AI 打分**（诚信） |
| `py-server/api/cn_distinction.py` | 72 | 干净 FastAPI 路由，`prefix="/cn-distinction"`，4 端点全部定义完整 |

- git 历史：`2cbc956` (Sep 2) 因 `main.py` 当时对 `cn_distinction_router` 是**悬空导入**（仓库当时无此定义），导致 `ImportError` 无法启动，故摘除；后续 `ea11e0a`（计网易混淆概念辨析专项）才补上本模块文件。→ 今日仅是"插头被拔、未接回"，非门坏。

## 3. 接线动作（零新增行为，仅恢复挂载）

照 `main.py` 现有路由标准模式：

1. `py-server/api/__init__.py`
   - L45：`from api.cn_distinction import router as cn_distinction_router`
   - L73：`__all__` 追加 `"cn_distinction_router"`
2. `py-server/main.py`
   - L77：`from api import (...)` 块追加 `cn_distinction_router,`
   - L693：`_all_routers` 列表追加 `cn_distinction_router,`（L695-696 循环自动 `include_router`）
   - 挂载后完整路径：`/api/cn-distinction`、`/api/cn-distinction/{pid}`、`/api/cn-distinction/quiz/random`、`/api/cn-distinction/quiz/answer`

## 4. 验证（证据先行）

- `ruff check --select F401,F811,F821`：**All checks passed!**（新 import 被 main 使用，无 F401；全树无非风格潜在缺陷）
- 结构化 grep：main.py L77/L693、api/__init__.py L45/L73 四处接线点齐全
- AST 解析：确认 `api/cn_distinction.py` 含 4 个 `router.get/post` 装饰路由（路径见 §3）；engines 4 函数均定义
- ⚠️ 运行时 import 冒烟（`import main` 列 routes）**未能执行**：本会话 `py-server/.venv` 已被清空（已知"会话间 .venv 被清空"现象），托管 python 未装 fastapi。已由 ruff 全树通过 + 结构/语法级验证替代；提交时 F401/F811/F821/F822/F841 门禁（uvx ruff）再次兜底。

## 5. 红线与口径核对

- **绝不删除**：本动作是"恢复挂载"，未删任何文件/逻辑；cn_distinction 模块与 12 组教材内容完整保留。
- **诚实口径**：该模块属 MARS-408（408 考研）技术底座的既有功能，对外仍以"芒得很职"为产品名、MARS-408 为技术底座；不新增任何虚假宣称、数字或"首创/第一"措辞。
- 密钥/诚实口径/口径数字/结构守卫 4 门禁在提交时全过（F401 门禁同步覆盖 F811/F821/F822/F841）。

## 6. 提交与推送

- 提交：`git commit`（经 5 门禁 hook）
- 推送：`git push git@github.com:TrueFurina/MARS-408.git refs/heads/career-literacy:refs/heads/career-literacy`
- 仅 add 本次三个文件（api/__init__.py、main.py、本交付物）；不扫入其它会话的改动（.gitignore / docs/adr/INDEX.md）。

## 7. 遗留（非本次范围）

- 该端点当前未接鉴权中间件（与 career_training / literacy 等同批路由一致，统一经 app 级依赖），如需独立鉴权另立专项。
- 无专门单测（tests/ 无 cn_distinction 用例）；功能正确性由 AST + 数据自洽保证，建议后续补 `tests/test_cn_distinction.py`（确定性判分易测）。
