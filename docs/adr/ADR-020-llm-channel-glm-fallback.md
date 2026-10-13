# ADR-020 — LLM 通道扩展：接入智谱 GLM 作第 4 兜底通道

- **状态**：Proposed（代码已实现并验证；**对外口径表述变更待确认**，见「待确认」）
- **日期**：2026-10-13
- **决策人**：待确认（用户 张敏杰 于 2026-10-13 指令「兜底通道：视需要在 config 增补智谱 GLM 通道」）
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
   但其「权威口径 = 两通道」的表述**需要重新表述** —— 见「待确认」。

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
- **文档**：口径表述待统一（**待确认后 sweep**）——已知出现处：
  `src/data/capabilityComparison.ts:39`（「三通道容灾：讯飞星火X2 → DeepSeek → Qwen3.8-Max」）、
  `docs/overview.md:21`、`py-server/README.md:85`、`py-server/.env.example:5`、
  `docs/芒得很职_PRD_Lite_2026-07.md:245`。

## 待确认（唯一一项）

**对外口径如何表述？** 在确认前**不修改任何对外文案**，本 ADR 保持 Proposed。

- **选项 A**：改为「四通道容灾：讯飞星火X2 → DeepSeek → Qwen → 智谱 GLM」（与代码枚举完全一致）
- **选项 B**：不报具体路数，改为「多通道按优先级自动回退（含智谱 GLM 兜底）」
- **选项 C**：保持现有「三通道」表述不动（**会与实际枚举不符**，不推荐；ADR-009 已把这类漂移记为文档债）

## 备选方案（被否决）

- **把 glm 插在 qwen 之前**：会改变现有 auto 行为（在 deepseek 之外提前启用 glm），无必要，否决。
- **只加配置项、不加进枚举**：那样 auto 永不选中它，等于没有兜底，违背本次需求，否决。
- **用 glm 替换 qwen 位次**：会改变既有枚举语义、且 Qwen 在其它部署环境可能可用，否决。
