# X2 通道恢复双兜底 + Git 历史密钥清理 · 操作手册

> 适用：MARS-408 P0-1（X2 通道 500 清零）与 P0-4（密钥安全收尾）的人工收尾动作。
> 本文件为**可操作步骤**；代码与 CI 已由实施侧完成，以下两步需你（或我辅助你）在本地执行。
> 关联：`scripts/xfyun_x2_diagnosis.md`（根因）、`scripts/git_history_cleanup.md`（B 部分权威手册）。

---

## 任务 A：用 `/api/llm/x2-health` 定位可用通道，恢复真实双兜底

### A0. 前置：确认 APIPassword 已注入（端点探测的 token 来源）
`x2-health` 用 `xfyun.api_password`（即 `.env` 的 `XF_API_PASSWORD`）作为 Bearer token。
先确认已配置：
```bash
grep XF_API_PASSWORD py-server/.env
# 若为空或缺失 → 去讯飞开放平台控制台复制「APIPassword」（注意不是 APPID/APIKey/APISecret），
#   填进 py-server/.env：  XF_API_PASSWORD=xxxxxxxx
```
> 当前 `config.json` 的 `xfyun` 字段已清空，运行期全部从 `.env` 注入；`XF_APP_ID / XF_API_KEY / XF_API_SECRET` 也要在 `.env` 配齐。

### A1. 启动后端（若未运行，端口 8002）
```bash
cd py-server
source .venv/Scripts/activate          # Windows 激活 venv
uvicorn main:app --host 127.0.0.1 --port 8002
# 另开一个终端执行后续 curl（保持此进程运行）
```

### A2. 登录拿 token
```bash
curl -s -X POST http://127.0.0.1:8002/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"你的账号","password":"你的密码"}' -o /tmp/login.json
cat /tmp/login.json                    # 确认返回含 access_token
TOKEN=$(python -c "import json;print(json.load(open('/tmp/login.json'))['access_token'])")
```

### A3. 探测可用通道
```bash
curl -s http://127.0.0.1:8002/api/llm/x2-health \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

### A4. 解读返回的 JSON（`probed` 数组）
- `ok: true` 的候选 → **这就是可用通道**。把 `py-server/config.json` 的 `xfyun.active_preset` 改成对应 key：
  - `"4.0Ultra"` → 通用星火 4.0 Ultra（/v1）
  - `"spark_x2"` → 星火 X2 推理（/x2，需账号开通 X2 能力）
  - `"max"` → generalv3.5
  - `"pro128k"` → Pro-128K
  - 或直接改 `xfyun.base_url` / `xfyun.model` 为可用组合均可（active_preset 与顶层二选一即可，推荐用 preset 单字段切换）。
- 若**全部 `ok:false` 且 `xfyun_configured:true`** → 根因是**账号权限**：当前 APIPassword 对应的讯飞应用未开通对应 LLM 服务。去讯飞控制台确认该 APP 已开通「星火认知大模型」，且用 X2 需单独开通 X2 能力。开通后重启再测。
- 若 `xfyun_configured:false` → `.env` 缺 `XF_API_PASSWORD`，回 A0。

### A5. 重启后端并验证
```bash
# 停掉 A1 的后端进程，重新启动（active_preset 在 load_config 时解析，进程级缓存，必须重启）
# 重启后：
curl -s http://127.0.0.1:8002/api/llm/x2-health -H "Authorization: Bearer $TOKEN" | python -c "import sys,json;d=json.load(sys.stdin);print('可用通道:',[r['label'] for r in d['probed'] if r['ok']])"
```
确认存在 `ok:true` 的通道后，auto 模式即优先走该通道、失败自动 failover 到 DeepSeek → **真实双兜底恢复**。

---

## 任务 B：git 历史密钥清理（破坏性 · 须先轮换 + 团队确认）

> 权威步骤见 `scripts/git_history_cleanup.md`。以下为执行摘要。**当前 config.json 密钥字段已空、.env 已 gitignore，现状已安全；此步仅为清除历史中的旧值。**

### B0. 前置（必须全部满足）
1. **先轮换凭证**：讯飞（XF_APP_ID/API_KEY/API_SECRET/API_PASSWORD）、DeepSeek、Qwen 全部在对应平台重新生成 / 作废旧值。
2. **团队确认**：通知所有协作者，历史重写后需重新 clone。
3. **已落门禁**：`secret-scan.yml`（gitleaks）与 `ci.yml` 已就位。
4. **备份仓库**：`git clone --mirror <repo> /tmp/netlearn-mirror-backup.git`

### B1. 执行（破坏性）
```bash
pip install git-filter-repo

cat > /tmp/secrets.txt <<'EOF'
XF_APP_ID=旧值
XF_API_KEY=旧值
XF_API_SECRET=旧值
XF_API_PASSWORD=旧值
# 以及曾泄露的 DeepSeek / Qwen key 明文
EOF

git filter-repo --replace-text /tmp/secrets.txt      # 命中项替换为 ***REMOVED***

git push --force --all
git push --force --tags
```

### B2. 协作通知
所有协作者必须 `git clone` 新仓库，**禁止 `git pull`**（历史不一致会冲突）。

---

## ⚠️ 时机与风险
- 任务 A 可在软件杯窗口内随时做，约 10 分钟，无破坏性。
- 任务 B **不要在软件杯截稿前 48h 内执行**（强制推送会打断协作）；建议 P0 收尾、且 secret-scan 门禁已绿后做。
- 两者均涉及账号凭证，**切勿把任何密钥值贴进聊天或提交到仓库**；密钥只放 `.env`（已 gitignore）。
