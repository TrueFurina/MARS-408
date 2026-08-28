# Git 历史密钥清理（安全收尾 · 需人工授权执行）

> ⚠️ 本文件为**操作手册**，**不会自动执行**。历史重写是破坏性操作，须先完成前置条件并获得明确授权。
> 关联任务 #2（P0-4 密钥安全收尾）

## 一、前置条件（必须全部满足）
1. **先轮换凭证**：所有曾进入过 git 历史的密钥（XF_APP_ID / XF_API_KEY / XF_API_SECRET / XF_API_PASSWORD、DeepSeek key、Qwen key 等）必须在对应平台**重新生成 / 作废旧值**。
2. **团队确认**：通知所有协作者，历史重写后需重新 clone 仓库。
3. **已落门禁**：`secret-scan.yml`（gitleaks）与 `ci.yml` 的 G4/G11 等门禁已就位，防止复泄。
4. **当前状态已安全**：`config.json` 密钥字段已空、`.gitignore` 已忽略 `.env`（实施侧已验证）。

## 二、操作步骤（git filter-repo）
```bash
# 1. 安装
pip install git-filter-repo

# 2. 准备替换清单（仅写密钥值/模式，本文件勿提交到仓库）
cat > /tmp/secrets.txt <<'EOF'
XF_APP_ID=???
XF_API_KEY=???
XF_API_SECRET=???
XF_API_PASSWORD=???
# 以及曾泄露的 DeepSeek / Qwen key 明文
EOF

# 3. 重写历史（命中项替换为 ***REMOVED***）
git filter-repo --replace-text /tmp/secrets.txt

# 4. 强制推送（需 maintainer 权限 + 与团队协调）
git push --force --all
git push --force --tags
```
- 或用 BFG：`java -jar bfg.jar --replace-text /tmp/secrets.txt repo.git`

## 三、注意
- 重写后所有协作者必须 `git clone` 新仓库，禁止 `git pull`（历史不一致会导致冲突）。
- 本操作不影响已迁至 `.env` 的当前配置；当前 `config.json` 密钥字段已空、`.gitignore` 已忽略 `.env`。
- 执行前务必备份（mirror clone）以便回滚。
