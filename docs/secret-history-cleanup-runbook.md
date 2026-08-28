# 密钥历史清理 Runbook（P0-密钥收尾）

> 目的：清除 git 历史中可能残留的密钥/凭证，并给出轮换步骤。
> **本文件只是指引，不会自动执行任何破坏性历史重写。** 请在确认无误、且已备份仓库后，由负责人手动执行。

## 前置确认（先做完再做清理）

1. **确认当前工作区干净**
   - `py-server/.env` 已在 `.gitignore`（仓库未跟踪）。
   - `py-server/config.json` 已在 `.gitignore`，且其 `xfyun` 密钥字段（`api_key`/`api_secret`/`api_password`/`app_id`）已清空（由 `config._strip_secrets` 保证 `save_config` 不落盘密钥）。
   - 运行 `git ls-files | grep -E '\.env$|config\.json$'`，应无输出。

2. **确认 CI 密钥扫描已启用**
   - 见 `.github/workflows/secret-scan.yml`（gitleaks）。每次 push/PR 自动扫描。

## 步骤一：轮换凭证（最高优先级）

无论历史是否残留，**泄露过的密钥一律轮换**：

- 讯飞开放平台：重新生成 APIPassword（及 AppID/APIKey/APISecret），更新到 `py-server/.env` 的 `XF_APP_ID / XF_API_KEY / XF_API_SECRET / XF_API_PASSWORD`。
- DeepSeek：在平台重置 API Key，更新 `DEEPSEEK_API_KEY`。
- 其他（Qwen / Tavily / PostgreSQL / Redis 等）如曾入 VCS，一并轮换。
- 轮换后重启后端使新凭证生效。

## 步骤二：清理 git 历史中的残留密钥

> 警告：以下操作会**重写提交历史**，所有协作者需重新 clone。仅在必要时执行，且提前通知团队。

### 方案 A：git filter-repo（推荐，需 Python）

```bash
# 1) 安装（一次性）
pip install git-filter-repo

# 2) 备份仓库
cp -r netlearn netlearn-backup

# 3) 替换历史中所有出现的密钥字符串为空（把 <SECRET> 换成真实泄露串，可多次执行）
git filter-repo --replace-text <(echo '<SECRET>==>') --force

# 4) 强制推送（需仓库管理员权限，且团队已知会）
git push --force --all
git push --force --tags
```

### 方案 B：BFG Repo-Cleaner（Java）

```bash
# 准备一个 passwords.txt，每行一个要清除的密钥串
java -jar bfg.jar --replace-text passwords.txt netlearn.git
cd netlearn.git && git reflog expire --expire=now --all && git gc --prune=now
git push --force --all
```

## 步骤三：验证

- 本地 `git log -p | grep -iE 'api_key|api_secret|api_password|app_id'`（针对已知字段）应无命中。
- 推送到远程后，GitHub 的「Security → Secret scanning」应无活跃告警。
- 重新 clone，确认 `.env` / `config.json` 仍被忽略、系统正常运行。

## 回滚

若清理出错，使用步骤二之前的 `netlearn-backup` 副本恢复：`rm -rf netlearn && cp -r netlearn-backup netlearn`。
