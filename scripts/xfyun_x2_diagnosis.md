# 讯飞 X2 通道 500 诊断与修复说明（P0-1）

> 实施侧：impl-backend ｜ 日期：2026-07-13 ｜ 关联任务 #1

## 一、根因分析
- X2 第一优先级通道指向 `https://spark-api-open.xf-yun.com/v1/chat/completions`，`model=4.0Ultra`。
- `py-server/db/llm_provider.py` 明确说明：`spark-api-open` LLM 端点**仅接受 APIPassword Bearer**；若仅以 `api_key:api_secret` 作为 Bearer，网关通常拒绝（401/500）。
- 当前 `config.json` 的 xfyun 字段（app_id/api_key/api_secret/api_password）全部为空，运行期由 `py-server/.env` 经 `config._apply_env_overrides` 注入。
- **最可能的根因**：`.env` 中 `XF_API_PASSWORD` 未填写 → 代码退回 `api_key:api_secret` 格式 → X2 返回 500 → `auto` 模式自动 failover 到 DeepSeek 兜底（系统仍可用，但 X2 实际失效、仅单兜底）。
- 次可能：账号未开通 `4.0Ultra` 权限，或应使用 preset `spark_x2`（`/x2/chat/completions`，model `spark-x`，见 config.json presets）。

## 二、已做的代码加固（impl-backend）
- `_xfyun_call` / `_xfyun_stream` 增加明确告警：当 `api_password` 未配置时，提示将退回 `api_key:api_secret` 且该格式对 spark-api-open 通常无效（可能是 401/500 根因）。
- 记录 X2 失败响应体前 500 字符（`logger.error`，**不含任何密钥**），使 500 根因清晰可见。
- 不改变现有可用链路：failover 顺序仍为 `xfyun → deepseek → qwen`，DeepSeek 兜底保持不变。

## 三、【需用户确认】账号权限核对步骤
1. 确认 `py-server/.env` 中 **`XF_API_PASSWORD` 已填写**（X2 LLM 端点用 APIPassword Bearer，非 api_key/api_secret）。
2. 登录讯飞开放平台，确认该账号已开通「星火 X2 / 4.0Ultra」，且 domain 与 `base_url` 匹配。
3. 若 `4.0Ultra` 无权限，二选一：
   - 在 `config.json` 将 `active_preset` 改为 `spark_x2`（base_url `/x2/chat/completions`，model `spark-x`）；
   - 或在开放平台为该账号开通 4.0Ultra 并复用现有 `v1` 端点。
4. 重启后端后调用一次真实 `chat`，确认 X2 不再 500、failover 日志显示 X2 成功优先。

## 四、验收标准
- X2 通道返回 200/成功；`auto` 模式下 X2 优先于 DeepSeek；失败时有清晰日志且不泄露密钥。
