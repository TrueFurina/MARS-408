#!/usr/bin/env bash
# ===========================================================================
#  reencode_remote_onetime.sh —— 生产机一键重编码执行器（安全暂停版）
#
#  用途：在 175.178.234.11（/opt/mangdehenzhi/py-server）上把 netlearn_kb 的
#        2245 条向量从 multilingual-e5-base 重编码到 e5-base-v2。
#
#  设计原则（红线）：
#   1. 先检查（InMemory 模式 + 模型可用性），不通过就退出，绝不硬跑；
#   2. 先备份再写盘（脚本内另有时间戳备份，这里是最后兜底）；
#   3. dry-run 之后**必须手敲 YES** 才做破坏性重编码，防止粘贴即误执行；
#   4. 重编码完成后**不自动重启服务**——只打印后续步骤，由你人工确认再重启。
#
#  用法（在你自己的 SSH 会话里）：
#    bash reencode_remote_onetime.sh            # 默认项目根 = 脚本所在 py-server
#    PY_ROOT=/opt/mangdehenzhi/py-server bash reencode_remote_onetime.sh
# ===========================================================================
set -euo pipefail

# ── 定位 py-server 目录 ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_ROOT="${PY_ROOT:-$SCRIPT_DIR}"
cd "$PY_ROOT"
echo "[step] 工作目录 = $(pwd)"

# ── 0) 运行环境检查 ────────────────────────────────────────────────────────
if [ ! -f "scripts/reencode_kb_e5_base_v2.py" ]; then
  echo "[FATAL] 找不到 scripts/reencode_kb_e5_base_v2.py，请确认在 py-server 目录下运行（或设 PY_ROOT）"
  exit 2
fi
if ! command -v python >/dev/null 2>&1 && ! command -v python3 >/dev/null 2>&1; then
  echo "[FATAL] 未找到 python / python3"
  exit 2
fi
PY_BIN="$(command -v python || command -v python3)"

# ── 1) InMemory 模式确认 ──────────────────────────────────────────────────
KB="vectordb_data/netlearn_kb.json"
NPY="vectordb_data/netlearn_kb.json.emb.npy"
echo "[step] 确认 InMemory 模式（KB 文件存在）..."
if [ ! -f "$KB" ]; then
  echo "[FATAL] 找不到 $KB。若这是 Milvus 模式，本脚本不适用，请改用 rebuild_vectordb.py"
  exit 2
fi
ls -la "$KB" "$NPY" 2>/dev/null || echo "[warn] $NPY 不存在（首次？仍可继续）"

# 看运行态的 vector_db_mode / embedding.model（若后端在跑）
if command -v curl >/dev/null 2>&1; then
  echo "[info] 当前 /api/status 快照（若后端在跑）："
  curl -s -m 5 localhost:8002/api/status | python -m json.tool 2>/dev/null \
    || echo "  (curl 失败或后端未运行，属正常，可继续)"
fi

# ── 2) 模型可用性前置检查 ─────────────────────────────────────────────────
echo "[step] 确认 e5-base-v2 模型可用..."
if [ -d "models/e5-base-v2" ]; then
  echo "  [ok] 本地模型目录 models/e5-base-v2 存在，将直接本地加载"
else
  echo "  [warn] models/e5-base-v2 不存在，脚本将回退到 HuggingFace 下载"
  echo "         若服务器无外网，请先 scp 该模型目录到 py-server/models/e5-base-v2"
fi

# ── 3) 备份（最后兜底） ────────────────────────────────────────────────────
echo "[step] 备份当前向量库（最后兜底）..."
cp -f "$KB" "${KB}.pre_reencode.bak"
[ -f "$NPY" ] && cp -f "$NPY" "${NPY}.pre_reencode.bak"
echo "  [ok] 已备份为 *.pre_reencode.bak"

# ── 4) dry-run（不写盘，确认 cos(old,new)≠1） ──────────────────────────────
echo "[step] dry-run（不写盘）..."
$PY_BIN scripts/reencode_kb_e5_base_v2.py --dry-run
echo
echo "  上面应能看到 sample[i] cos(old,new) ≠ 1，证明目标模型已切换并会产生新向量。"
echo

# ── 5) 硬保险：手敲 YES 才继续 ────────────────────────────────────────────
read -r -p "确认执行【破坏性】正式重编码？键入 YES 继续（其它任意键放弃）: " ANS
if [ "${ANS:-}" != "YES" ]; then
  echo "[abort] 已放弃正式重编码。向量库未改动，备份 *.pre_reencode.bak 可保留或删除。"
  exit 0
fi

# ── 6) 正式重编码 ──────────────────────────────────────────────────────────
echo "[step] 正式重编码（自动再备份 + 同步覆写 .emb.npy）..."
$PY_BIN scripts/reencode_kb_e5_base_v2.py
echo

# ── 7) 后续步骤（不自动执行，由你人工确认） ───────────────────────────────
cat <<'NEXT'

[done] 向量已重编码落盘（含 .emb.npy 缓存）。
下面这些步骤本脚本【不】自动执行，请人工确认后操作：

  A) 切配置：把部署用 config.json 的 embedding 段改为
       "embedding": { "model": "intfloat/e5-base-v2", "dimension": 768 }
     （注意：reencode 脚本运行时用了 monkeypatch，不影响部署 config，这里才真正切）

  B) 重启后端（确认 service 名，当前已知为 mango-backend.service）：
       sudo systemctl restart mango-backend

  C) 核验：
       curl -s localhost:8002/api/status | python -m json.tool
       # 期望 embedding.model == intfloat/e5-base-v2，embedding.loaded == true
       # + 用 cn_01 类查询做 top1 检索，期望 top1_score ≈ 0.94

  D) 回滚（若 loaded=false 或质量退化）：
       sudo systemctl stop mango-backend
       cp vectordb_data/netlearn_kb.json.pre_reencode.bak vectordb_data/netlearn_kb.json
       cp vectordb_data/netlearn_kb.json.emb.npy.pre_reencode.bak vectordb_data/netlearn_kb.json.emb.npy
       # 配置 embedding.model 改回 multilingual-e5-base
       sudo systemctl start mango-backend
NEXT
