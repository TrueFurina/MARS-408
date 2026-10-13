# ADR-020 — LLM 通道扩展：接入智谱 GLM 作第 4 兜底通道

- **状态**：Accepted（2026-10-14 用户确认对外口径选项 A 后转正；代码先于本确认落地并验证）
- **日期**：2026-10-13（实现）／2026-10-14（口径确认转正）
- **决策人**：用户（张敏杰）—— 2026-10-13 指令「兜底通道：视需要在 config 增补智谱 GLM 通道」；
  2026-10-14 就对外口径答复「A」
- **相关**：ADR-009（LLM 通道策略）§影响「扩展性：新增通道须走 ADR，禁止静默扩大通道枚举」——
  **本 ADR 即该原则要求的程序，未绕过**；`docs/adr/INDEX.md`

## 背景

用户 2026-10-13 指令：把已存在于其环境变量里的智谱凭据接入为兜底通道。
现状：`config.py` 的 `DEFAULTS` 与 `db/llm_provider.py` 枚举均为 `["xfyun", "deepseek", "qwen"]`。

**实测通道可用性（本机，2026-10-13）**：

| 通道 | 实测 | 说明 |
|---|---|---|
| 讯飞星火 X2 | ✅（账号仅 X2 权限） | 4.0Ultra / max / pro-128k 均 11200 |
| DeepSeek | ✅ 0.97s | |
| Qwen（DashScope） | ❌ | 账号欠费/暂停 |
| 智谱 glm-4-flash | ✅ 1.06s | 免费档 |
| 智谱 glm-4-plus / -air / 4.5 | ❌ 429 | 「余额不足或无可用资源包」 |

⇒ **真实可用通道只有 3 段**（讯飞 X2 / DeepSeek / 智谱 GLM）；Qwen 虽在枚举中，但本环境无有效额度。
换言之，现有枚举里的冗余有一半是"名义冗余"。

## 决策

1. **新增 `glm` 通道，排在枚举最后**：`xfyun → deepseek → qwen → glm`。
   **不改既有优先级**——不影响任何已配置环境的运行级通道选择。
2. **配置面**：
   - `DEFAULTS` 增 `glm` 段（`base_url` 含完整 `/chat/completions`，与 qwen 同款写法，`_build_url` 直接采用）；
     `model` 固定 **`glm-4-flash`**（唯一实测可用档）。
   - `env_map` 增 `ZHIPU_API_KEY` / `ZHIPU_BASE_URL` / `ZHIPU_MODEL`，别名 `GLM_API_KEY` / `GLM_MODEL`。
3. **同步全部 5 处硬编码枚举**（漏一处即口径不一致）：
   `config.py` ×1、`db/llm_provider.py` ×3（chat 回退 / stream 回退 / `_resolve`）、`api/config_routes.py` ×1。
4. **与 ADR-009 的关系**：不推翻其「禁止静默扩大通道枚举」原则（本 ADR 即该程序）；
   但其 **§决策 1/3 的「权威口径 = 两通道」已被本 ADR 取代**（口径改为四通道枚举链），
   ADR-009 据此标注为**部分 Superseded**（见「口径决议」）。

## 理由

- **这是"真实冗余"而非 ADR-009 所警惕的"虚假冗余"**：glm-4-flash 实测可用且免费，
  是真能接上的第 4 段；而现有枚举中的 Qwen 在本环境不可用。
- **零成本、零新增依赖**：OpenAI 兼容端点，复用现有 `_openai_compatible_call` + `_build_url`，
  不引入新库、不新增鉴权分支（非 xfyun 走通用分支）。
- **风险面极小**：仅当 xfyun / deepseek / qwen **全部未配置**时才会被选中；
  该场景下原行为是直接抛 `LLMUnavailable("所有 LLM 通道均未配置 API Key")`，新行为是有可用兜底。

## 影响

- **代码**：上述 5 处枚举 + `DEFAULTS` + `env_map`；测试 `tests/test_config_llm_provider_env.py` 增 2 例
  （`ZHIPU_API_KEY` → `glm.api_key` 映射；`GLM_API_KEY` 别名），并扩展 provider 取值枚举。
- **验证（已实测）**：`LLM_PROVIDER=glm` 真实调用成功（1.06s，返回内容正确）；
  同时配置 `DEEPSEEK_API_KEY` + `ZHIPU_API_KEY` 时，auto 仍选中 `deepseek-chat` ⇒ **优先级未被破坏**。
- **文档**：活口径面已按选项 A 同步（清单见「口径决议」）；历史快照有意不改并已在同节登记。

## 口径决议（2026-10-14 已确认：选项 A）

**权威对外口径 = 「四通道容灾：讯飞星火X2 → DeepSeek → Qwen3.8-Max → 智谱GLM」。**

用户于 2026-10-14 就本 ADR 提出的三个选项答复 **A**。同步范围（**活口径面**）：

| 位置 | 改动 |
|---|---|
| `src/data/capabilityComparison.ts` | 「三通道容灾：…」→「四通道容灾：讯飞星火X2 → DeepSeek → Qwen3.8-Max → 智谱GLM」 |
| `py-server/api/chat.py` docstring | 三通道运行级回退 → 四通道 |
| `py-server/db/llm_provider.py`（2 处注释） | 封装三/四通道差异、运行级三/四通道回退 |
| `py-server/README.md` | LLM 三/四通道路由器（并标出优先级链） |
| `py-server/.env.example` | 段标题改四通道，并补 `ZHIPU_*` 三行模板 |
| `py-server/tests/test_career_nodes_fallback.py` 注释 | 桩说明改四通道 |
| `py-server/openapi.json` + `src/types/api.generated.ts` | 随 `chat.py` 描述变更**重生成**（契约门禁已复验一致） |

**有意不改（历史快照，按「归档不回改」原则）**——已在 ADR 中登记，勿当作待办重提：
`docs/overview.md`（2026-08-30）、`docs/reports/PRODUCTION_READINESS_2026-07-12.md`（2026-07-12）、
`docs/芒得很职_PRD_Lite_2026-07.md`（2026-07）、`py-server/*.egg-info/PKG-INFO`（构建产物）。

**副产品发现（与本次改动无关，但一并修正）**：`src/types/api.generated.ts` **长期未随 `openapi.json` 重生成**
（缺 `/api/quiz/knowledge-mastery`、仍写着过时的「10-Agent」与旧沙箱描述等）。
该文件**没有任何门禁守护**（`verify_openapi_snapshot.py` 只守 `openapi.json`）⇒ 静默腐烂。
本次借重生成一并修正；是否为其加门禁另议。

## 备选方案（被否决）

- **把 glm 插在 qwen 之前**：会改变现有 auto 行为（在 deepseek 之外提前启用 glm），无必要，否决。
- **只加配置项、不加进枚举**：那样 auto 永不选中它，等于没有兜底，违背本次需求，否决。
- **用 glm 替换 qwen 位次**：会改变既有枚举语义、且 Qwen 在其它部署环境可能可用，否决。
