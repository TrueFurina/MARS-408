#!/usr/bin/env python
"""build_career_pilot_package.py — 从 ``py-server/`` 生成 / 刷新「芒得很职」云部署瘦包骨架

为什么需要
--------------------------------------------------------------------------
``deploy/career-pilot/backend/`` 曾是 ``py-server/`` 的**手工整树拷贝**。手工拷贝无法
随源树自动更新：一旦 ``py-server/``（如 ``main.py``）被改动，拷贝就会**静默漂移**，
而漂移只在公网发布时才暴露（例如绑定地址仍硬编码 ``127.0.0.1``）。本脚本让拷贝**可再生**：
    python scripts/build_career_pilot_package.py         # 生成 / 刷新
    python scripts/build_career_pilot_package.py --check  # 只校验，不一致则 exit 1

它做什么
--------------------------------------------------------------------------
1. 以 ``py-server/`` 为源、``deploy/career-pilot/backend/`` 为目标，**同步**（复制缺失/变动，
   并清理源树已不存在的陈旧文件）；
2. 显式排除与「单端口 HTTP 云沙箱」无关的物：模型权重 / 虚拟环境 / 测试 / 内部文档 /
   训练数据 / 研究实验 / 缓存 / 日志 / 一次性脚本；
3. 落地瘦版运行依赖 ``requirements.txt``、**沙箱专用** ``config.json``（强制
   ``milvus.enabled=false`` / ``redis.enabled=false``，见 :func:`_sandbox_config_bytes`）、
   配置范本 ``config.example.json``、解释器版本 ``.python-version`` 与 ``.env`` 模板 ``.env.example``；
4. **绝不覆盖已存在的 ``.env``**（其中含真实密钥），仅在其缺失时按模板生成；
5. **保留**由 ``vite.deploy.config.ts`` 直接产出到 ``backend/site/`` 的前端产物
   （见 ``PRESERVE_TOP_NAMES``）——前端与后端同根，使 ``STATIC_DIR=site`` 相对包根
   恒定解析，**入口不依赖外部 CWD**（发布时 ``directory`` 即包根）。

能力边界：本包**定型为 career-only**（2026-10-16 确认，勿再塞回 408 检索能力）
--------------------------------------------------------------------------
本包只承载**职业素养对抗实训**闭环，**刻意不含**向量库与 E5 嵌入模型：

- **不含向量库产物**：``backend/vectordb_data/`` 下只允许运行时自建的 ``import_jobs/``
  （``py-server/services/import_worker.py:140`` 处 ``JOURNAL_DIR.mkdir(parents=True,
  exist_ok=True)`` 自行创建，无需预置）。``netlearn_kb.json`` / ``*.emb.npy`` /
  ``e5_embed_cache.npz`` 等向量产物**一律不得出现**，由
  :func:`_vectordb_offenders` 在 ``--check`` 中 **fail-closed 断言**（见
  :data:`VECTORDB_ALLOWED_ENTRIES`）。原先随包的 51MB 预计算向量库已移到仓库内未跟踪目录
  ``_removed_redundant_e5v2_20261015/``（不随包、不入库）。该目录**不在**
  ``PRESERVE_TOP_NAMES`` 内 ⇒ 服务从包目录跑过之后写入的零向量垃圾会被下次 build 清掉，
  不变量自愈（2026-10-22：曾因 PRESERVE 它而永久误报，见 :data:`PRESERVE_TOP_NAMES` 注释）。
- **不含 E5 模型**：嵌入模型为 ``intfloat/multilingual-e5-base``（768 维，约 1.1GB，
  见 ``py-server/db/embedder.py:5``），加载依赖 ``sentence-transformers``
  （``py-server/db/embedder.py:167``），而瘦版 ``requirements.txt`` 明确剔除该依赖
  ⇒ **拿不到真实向量**：调用方捕获时回落零向量占位（启动种子即如此，实测日志
  ``E5 嵌入失败(No module named 'sentence_transformers')，使用零向量占位并标记
  fallback_zero``，2245 条种子全部零向量），未捕获处直接抛错；**不会**给出看似正常的检索结果。

⇒ **后果（如实声明，不掩饰）**：芒得很职 408 考研侧的**检索 / 画像类能力在本包内不可用**
（无嵌入模型、向量全为零向量占位）；``/api/status`` 里 ``embedding.loaded=false``
（``py-server/app/status.py:57-58``）如实反映这一点。
⇒ **career 闭环不受影响**，因为该链路**本就不做 KB/向量检索**：
  · ``py-server/api/career_training.py:267`` ——「本实训链路无 KB/向量库检索」
  · ``py-server/api/career_training.py:419`` ——「未做任何 KB/向量库检索……未伪造任何
    chunk 引用」
  · 评估取自情景种子的静态 BARS 评分量表（``source_type=rule``），不依赖检索质量。

✅ **健康探针现已如实计数（2026-10-18 修复，此前是已记录缺陷）**：``/api/status`` 的
``fallback_zero_docs`` 会真实报出零向量占位文档数。修复前该字段**恒为 0**——
``py-server/app/status.py:59`` 读公开名 ``vector_db.embedding_fallback_count``，而
``py-server/db/milvus_client.py:517`` 只有私有字段 ``_embedding_fallback_count``
（D5 §2.1 设计的只读属性漏做了），``getattr`` 默认值 0 恒生效，于是「embedding 降级」
判定形同虚设、``status:"ok"`` 会掩盖「全部文档都是零向量」的事实。
修复后瘦包启动可见 ``fallback_zero_docs=2245`` 且 ``status:"degraded"``（原因：
``embedding: 2245 个文档因 E5 失败使用零向量占位，检索质量下降``）——这是**如实上报**，
不是回归：瘦包本就未随附 E5，KB 检索确实不可用。守护见
``tests/test_app_status_invariants.py`` 的两条新不变量。

这条边界三处口径一致：本 docstring、随包 ``backend/README.md``
（:func:`_overlay_files` 自持生成，``--check`` 字节校验）、仓库根 ``README.md``
「发布包能力边界」小节。

退出码：0=成功（或 --check 一致）；1=--check 发现漂移或能力边界被破坏；2=环境错误（源目录缺失）。
"""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "py-server"
DST = ROOT / "deploy" / "career-pilot" / "backend"

# ── 排除规则（相对 py-server 的路径）─────────────────────────────────────────
# 目录名（出现在路径中任一非末段即整棵剪枝）
# 注：experiments 已移出本集合（2026-10-20）——它是 /benchmark 与 /evidence 两个对外
# 页面的数据源。此前整棵剪枝 ⇒ 包内 experiments/results 为空 ⇒ 线上
# GET /api/benchmark/results 与 /api/experiments/{name} 全部 404，而这两个页面
# 承载 FrugalRAG 对外口径证据（真源 benchmark_2026-09-18.json）。
# 瘦身改由下方 .jsonl 后缀承担（过程 trace 占 5.5M / 总 7.2M）。
EXCLUDE_DIR_NAMES = {
    "models", ".venv", "venv", "tests", "documents", "data",
    "milvus_lite_data", "node_modules", ".git",
    "__pycache__", ".pytest_cache", ".pytest_tmp", ".ruff_cache",
    "_scratch", "_debug_smoke",
}
# 目录前缀（排除运行时数据目录及其备份，如 vectordb_data / vectordb_data_pre_multi_bak）。
# 也用于测试临时目录：pytest 的 --basetemp 常带后缀（.pytest_tmp_qc / .pytest_tmp_f2 …），
# 精确名匹配会漏掉 ⇒ 实测包内曾混入十余个测试残留目录。
EXCLUDE_DIR_PREFIXES = ("vectordb_data", ".pytest_tmp", ".pytest_cache", ".ruff_cache")
# 目录/文件后缀（备份、旧版本残留）
EXCLUDE_DIR_SUFFIXES = ("_bak", "_backup", "_old")
# 文件后缀
# .jsonl：experiments/results 下的 review_shadow_*.jsonl 是过程 trace（20 个 / 5.5M），
# 前端页面从不消费它们；恢复 experiments 目录后靠这条把包体增量压到约 2M。
EXCLUDE_FILE_SUFFIXES = (".log", ".pyc", ".pyo", ".npz", ".lock", ".jsonl")
# 文件全名（精确匹配）
EXCLUDE_FILE_NAMES = {
    "docker-entrypoint.sh", "uv.lock", "pyproject.toml",
    "pip-audit-report.json", ".coverage", "export_onnx.py",
    "guardian.bat", "import_docling.py", "import_pdfs.py",
    "import_textbook.py", "iq_diag.py", ".env.example", "nul",
    # 解释器版本 pin：发布沙箱的 pyenv 未必装了源码树 pin 的版本（实测 3.12 未装 →
    # 安装阶段直接 exit 1）。沙箱自己选解释器，包内不带版本 pin。
    ".python-version",
    # filelock 的**运行时**单写者锁文件：锁绑定的是「持有进程的文件句柄」而非文件是否存在，
    # 留一个无主锁文件毫无意义；且本地开发服务器持有它时 Windows 会拒绝读取该文件，
    # 使本脚本的字节一致性比对抛 PermissionError（构建随本地进程状态随机失败）。
    ".import_writer.lock",
    # config.json 由本脚本**自持生成**（见 _sandbox_config_bytes）：包内配置必须声明
    # 「沙箱无 Milvus/Redis」，不能让 py-server 的本地配置把它冲掉（曾导致 /api/status 误报 degraded）。
    "config.json",
}

# 目标包内**由其它流程产出、不属于本脚本同步范围**的顶层条目，清理陈旧文件时必须保留。
# ``site`` = 前端 SPA 产物（由 vite.deploy.config.ts 直接产出到 backend/site），
# 与后端同根 → 使入口对 CWD 无关（STATIC_DIR=site 相对包根，恒定解析正确）。
#
# ⚠️ ``vectordb_data`` **不在此列**（2026-10-22 从 PRESERVE 移除）：它是纯**运行时**
# 目录，源码树同名目录整体被 EXCLUDE_DIR_PREFIXES 剪掉、不参与同步，且应用启动时会
# 自建它（``db/milvus_client.py:100`` makedirs + ``services/import_worker.py:140``
# mkdir import_jobs）⇒ 包内根本不需要预置。
# 曾经的误判：把它当运行时状态 PRESERVE 起来不清理。实测服务只要从**包目录**跑过一次，
# 就会往里写 ``netlearn_kb.json``(9.5MB) + ``.emb.npy``(6.9MB) = **16.4MB 零向量垃圾**，
# 而 PRESERVE 让 build 永远清不掉它们 ⇒ 之后 ``--check`` 会**永久**报「career-only
# 定型被破坏」，包体也从 16.8MiB 胀到约 33MiB。移除 PRESERVE 后 build 重置该目录，
# 不变量自愈；「包内不得含向量库产物」由 :func:`_vectordb_offenders` fail-closed 断言
# 保证，**不因本改动放松**。
PRESERVE_TOP_NAMES = {"site"}

# ── career-only 定型：backend/vectordb_data 的白名单与向量库产物特征 ──────────
# 只允许 import_worker 的 journal 目录（运行时自建，见 services/import_worker.py:140）。
VECTORDB_ALLOWED_ENTRIES = {"import_jobs"}
# 出现在 import_jobs/ **内部**也要拒收的向量库/模型产物特征（防把大文件挪进白名单目录规避）。
VECTORDB_FORBIDDEN_SUFFIXES = (
    ".npy", ".npz", ".index", ".db", ".sqlite", ".sqlite3",
    ".safetensors", ".pt", ".pth", ".h5", ".bin", ".pkl", ".faiss",
)
VECTORDB_FORBIDDEN_NAMES = {"netlearn_kb.json", "e5_embed_cache.npz", ".import_writer.lock"}

# ── 瘦版运行依赖（相对 py-server 全量删除了 torch 系 / 向量库 / 关系库客户端）──
THIN_REQUIREMENTS = """\
# 芒得很职 · 职业素养对抗实训试点 —— 轻量运行依赖（规则模式，无需 torch / 向量库 / 关系库）
# 设计：career 链路默认 use_career_mappa=False → 纯规则决策，无需 torch / sentence-transformers / 2.4G 模型。
# 删除项（相对 py-server 全量）：向量库客户端 / 关系库驱动 / 缓存客户端 / sentence-transformers / mcp / matplotlib / pymupdf / python-docx / sse-starlette
#   （具体被剔除的包名见 build 脚本注释；**此处刻意不写包名** —— 发布平台预检对依赖清单做
#     朴素文本匹配，注释里出现"关系库驱动/缓存客户端"的真实包名会让整个部署被误判为
#     "需要外部服务"而拒发，2026-10-15 实测踩坑。）
# 原因：云沙箱单端口 HTTP、无 DB/缓存/队列；向量库走 InMemoryVectorStore 回退，关系库走 SQLite 回退，缓存在 dev 模式 fail-open。

fastapi>=0.136.3
uvicorn[standard]>=0.49.0
pydantic>=2.0.0
pydantic-settings>=2.14.2
httpx>=0.28.1
numpy>=2.4.6
langgraph>=1.2.0
langchain-core>=1.4.0
python-multipart>=0.0.32
filelock>=3.13.0

# 安全下限约束（与 py-server 对齐，防止传递依赖回退漏洞版本）
anyio>=4.14.2
cryptography>=50.0.0
fsspec>=2026.6.0
langgraph-sdk>=0.4.4
pillow>=12.3.0
starlette>=1.3.1
urllib3>=2.8.0
"""

# ── .env 模板（占位，不含任何真实密钥；随包上传的真实 .env 由人工/发布流程注入）──
ENV_TEMPLATE = """\
# 芒得很职 · 试点运行环境（云端沙箱）—— 本文件为模板，真实 .env 不入库。
# 发布通道无环境变量注入项，密钥只能随包 .env 走。
LLM_PROVIDER=deepseek
# ⚠️ 必须 development（不是 production）：沙箱**无 Redis**，而 production 下
# db/redis_client.check_rate_limit 对「Redis 未启用」fail-closed 返回 False →
# /api/auth/login 一律 422「操作过于频繁」（已实跑复现）；且 production 会跳过
# 演示账号播种（app/lifespan._seed_demo_data）。二者叠加 = 无人可登录。
# 开发模式下限流 fail-open、演示账号自动播种，配合下方固定 AUTH_SECRET 即稳定可用。
NETLEARN_ENV=development
# 前端 SPA 产物目录：site/ 与后端同根（backend/site/）。发布时 CWD=包根，
# 故用相对包根的 `site` 即可恒定解析（入口不依赖外部 CWD）。命名 site/ 而非 dist/ 是为
# 避开发布通道对 "dist" 构建产物的上传排除规则。
STATIC_DIR=site
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
# 必填：>=32 字符随机串（dev 下也已显式提供 → token 跨重启稳定）。
# 生成：python -c "import secrets;print(secrets.token_urlsafe(48))"
AUTH_SECRET=REPLACE_WITH_RANDOM_SECRET_AT_LEAST_32_CHARS
# 管理员口令（>=16 字符）；固定后 admin 账号跨重启确定。
ADMIN_PASSWORD=REPLACE_WITH_RANDOM_ADMIN_PASSWORD_AT_LEAST_16
DEEPSEEK_API_KEY=REPLACE_WITH_REAL_DEEPSEEK_API_KEY
"""

# ── 随包 README（脚本自持生成；--check 会做字节校验，防止口径漂移）────────────
# 发布通道只上传本目录，评审/运维在目录里第一眼看到的就是这份文件，因此能力边界
# 必须写在包内，而不是只留在仓库根 README 里。
PACKAGE_README = """\
# 芒得很职 · 职业素养对抗实训 试点包（career-pilot）

单端口 Python 服务：前端 SPA（``site/``）与后端（``main.py``）**同根同源**，
对外只有一个端口，``STATIC_DIR=site`` 相对包根解析，**启动不依赖外部 CWD**。

## 1. 能力边界（career-only 定型，先读这一节）

本包**只承载职业素养对抗实训闭环**，**刻意不含向量库与 E5 嵌入模型**：

| 能力 | 本包内是否可用 | 依据 |
| --- | --- | --- |
| 职业素养对抗实训（情景对话 / 六维 ECD 评估 / 证据链回放） | ✅ 可用 | 规则+评分驱动，不依赖检索 |
| 408 考研侧**检索 / 画像**类能力 | ❌ **不可用** | 向量库已裁空、无 E5 模型 |
| LLM 对话生成（DeepSeek） | ✅ 可用（需 ``DEEPSEEK_API_KEY``） | ``LLM_PROVIDER=deepseek`` |

- **为什么 408 检索不可用**：向量库产物未随包分发（``vectordb_data/`` 只允许运行时自建的
  ``import_jobs/``），嵌入模型 ``intfloat/multilingual-e5-base``（``py-server/db/embedder.py:5``）
  及其依赖 ``sentence-transformers``（``py-server/db/embedder.py:167``）也不在
  ``requirements.txt`` 中 ⇒ **拿不到真实向量**：启动时 2245 条内置种子全部按零向量占位写入
  （实测日志 ``E5 嵌入失败(No module named 'sentence_transformers')，使用零向量占位并标记
  fallback_zero``），未捕获处直接抛错，**不会**给出看似正常的检索结果。
- **为什么 career 闭环不受影响**：该链路**本就不做 KB/向量检索**
  （``py-server/api/career_training.py:267``「本实训链路无 KB/向量库检索」、
  ``:419``「未做任何 KB/向量库检索……未伪造任何 chunk 引用」）；评估取自情景种子的静态
  BARS 评分量表（``source_type=rule``）。
- **健康探针如实上报**：``GET /api/status`` 中 ``embedding_loaded`` 为 ``false``
  （``py-server/app/status.py:57-58``）——未配置即不要求，不存在「假装可用」。
- ✅ **健康探针如实计数（2026-10-18 修复）**：探针的 ``fallback_zero_docs`` 会真实报出
  零向量占位文档数（修复前因公开/私有属性名不一致恒为 0，属已修复缺陷）。瘦包启动后该项
  为 2245，且 ``status`` 为 ``degraded``（``embedding: 2245 个文档因 E5 失败使用零向量
  占位，检索质量下降``）——如实反映「KB 检索在瘦包内不可用」，而非假装健康。

## 2. 安装与启动

```bash
python -m pip install -r requirements.txt     # installCmd
python main.py                                # startCmd（读取 PORT/HOST，默认 127.0.0.1:8002）
```

- ``PORT`` 设置后监听 ``0.0.0.0``（公网托管需要）；``HOST`` 可显式覆盖。
- 单 worker 不可改：``vectordb_data/.import_writer.lock`` 单写者锁强制 ``workers=1``。
- 首次启动约需数十秒（无模型加载，主要是依赖导入与种子写入）。

## 3. 生产姿态必需的环境变量（无环境变量注入项，只能随 .env）

| 变量 | 要求 | 缺失后果 |
| --- | --- | --- |
| ``NETLEARN_ENV`` | ``production`` | dev 下不校验密钥强度 |
| ``AUTH_SECRET`` | ≥32 位随机串 | 启动即 fail-fast（token 不安全） |
| ``ADMIN_PASSWORD`` | ≥16 位 | 启动即 fail-fast（拒绝默认口令） |
| ``RATE_LIMIT_ALLOW_LOCAL_FALLBACK`` | **必须 =1** | 无 Redis 且为 production ⇒ 限流 fail-closed，**第 1 次登录即 422** |
| ``STATIC_DIR`` | ``site`` | 前端 404 / 白屏 |
| ``DEEPSEEK_API_KEY`` | 真实密钥 | LLM 能力不可用（career 规则链路仍可用） |

> ``RATE_LIMIT_ALLOW_LOCAL_FALLBACK=1`` 是**显式降级开关**（默认关闭）：它把「Redis 不可用」
> 从 fail-closed 拒绝改为**进程内滑动窗口限流**——**仍然强制限额，不是放行**。本部署被单写者锁
> 约束为 ``workers=1``，进程内计数即全局计数，与 Redis 限流功能等价；改为多 worker 必须换回
> Redis 等共享存储。

## 4. 冒烟验收（本机实测通过）

```bash
curl -s http://127.0.0.1:8002/api/status          # 200 {"status":"ok", ...}
curl -s http://127.0.0.1:8002/ | grep -o '<div id="app">'   # 200 SPA 挂载
curl -s http://127.0.0.1:8002/career/scenarios    # 401（未带 token，鉴权生效）
```

## 5. 复现方式

本目录由仓库根脚本生成/校验，**请勿手工编辑**：

```bash
python scripts/build_career_pilot_package.py          # 生成 / 刷新
python scripts/build_career_pilot_package.py --check   # 校验一致性与能力边界（fail-closed）
```

口径与仓库根 ``README.md``「发布包能力边界」小节一致。
"""


def _rel_parts(rel: pathlib.PurePosixPath) -> tuple[str, ...]:
    return rel.parts


def _excluded(rel: pathlib.PurePosixPath) -> bool:
    """给定相对 py-server 的路径，判断是否应排除。"""
    parts = _rel_parts(rel)
    # 目录段（除末段）命中 → 排除
    for p in parts[:-1]:
        if p in EXCLUDE_DIR_NAMES or p.endswith(".egg-info"):
            return True
        # 运行时数据/备份目录（含末段同判，见下）：
        # 这类目录由并行工作或运行期产生、体积大且无业务价值 —— 曾把
        # vectordb_data_pre_multi_bak（51MB，含 .npz 缓存）整包复制进发布产物
        # （包体 67MB→118MB），发布时白传且可能触发上传失败。
        if p.startswith(EXCLUDE_DIR_PREFIXES) or p.endswith(EXCLUDE_DIR_SUFFIXES):
            return True
    name = parts[-1]
    if name.startswith(EXCLUDE_DIR_PREFIXES) or name.endswith(EXCLUDE_DIR_SUFFIXES):
        return True
    # .env 系列（.env / .env.example / .env.bak*）：目标包内的 .env 由本脚本单独
    # 管理（保留真实密钥 / 按模板生成），源树的 .env 一律不参与复制与一致性比对。
    if name == ".env" or name.startswith(".env."):
        return True
    if name.endswith(".egg-info"):
        return True
    if name in EXCLUDE_FILE_NAMES:
        return True
    if any(name.endswith(s) for s in EXCLUDE_FILE_SUFFIXES):
        return True
    # 根目录：说明文档 / 一次性脚本（``_`` 前缀）/ 临时文本
    if len(parts) == 1:
        if name.endswith(".md") or name.endswith(".txt"):
            return True
        if name.startswith("_") and name not in {"__init__.py"}:
            return True
    return False


def _iter_src_files():
    """遍历 py-server，产出 (relative_posix_path, 绝对源路径)，已按规则剪枝。"""
    for dirpath, dirnames, filenames in os.walk(SRC):
        dpath = pathlib.Path(dirpath)
        rel_dir = dpath.relative_to(SRC)
        # 就地剪枝：剔除被排除的子目录
        keep = []
        for d in dirnames:
            rel = pathlib.PurePosixPath((rel_dir / d).as_posix())
            if not _excluded(rel):
                keep.append(d)
        dirnames[:] = sorted(keep)
        for f in sorted(filenames):
            rel = pathlib.PurePosixPath((rel_dir / f).as_posix())
            if _excluded(rel):
                continue
            yield rel, dpath / f


def _dst_for(rel: pathlib.PurePosixPath) -> pathlib.Path:
    return DST / rel.as_posix()


def _sandbox_config_bytes() -> bytes:
    """生成**沙箱专用** ``config.json``（本脚本自持，源树同名文件不参与复制）。

    以 ``py-server/config.json`` 为基线，**强制覆写** ``milvus.enabled=false`` 与
    ``redis.enabled=false``。理由：本试点沙箱无 Milvus / 无 Redis，thin 包亦不含
    ``pymilvus``/``redis-py``；把「意图启用却连不上」声明为 ``false`` 才是**如实配置**。
    若沿用 py-server 的 ``milvus.enabled=true``，``app/status.py:96``
    （``milvus_cfg_enabled and not milvus_connected``）会让 ``/api/status`` **误报
    ``degraded``**。此覆盖写进脚本、而非手工改包内文件——否则下次同步又被冲掉。
    """
    base: dict = {}
    src_cfg = SRC / "config.json"
    if src_cfg.is_file():
        try:
            loaded = json.loads(src_cfg.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                base = loaded
        except Exception:  # noqa: BLE001 — 源配置损坏时降级为空基线，不阻断打包
            base = {}
    for key in ("milvus", "redis"):
        section = base.get(key)
        if not isinstance(section, dict):
            section = {}
            base[key] = section
        section["enabled"] = False
    return (json.dumps(base, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _overlay_files() -> dict[pathlib.PurePosixPath, bytes]:
    """脚本自产文件（源树中不存在或以瘦版为准）。"""
    out = {
        pathlib.PurePosixPath("requirements.txt"): THIN_REQUIREMENTS.encode("utf-8"),
        pathlib.PurePosixPath(".env.example"): ENV_TEMPLATE.encode("utf-8"),
        pathlib.PurePosixPath("config.json"): _sandbox_config_bytes(),
        # 随包能力边界说明：发布通道只上传本目录，边界必须写在包内（见 PACKAGE_README 注释）。
        pathlib.PurePosixPath("README.md"): PACKAGE_README.encode("utf-8"),
        # 解释器选择：pin 到 pyenv 已装版本，**不要**写 "system"（沙箱系统 Python 是
        # Debian externally-managed 环境，pip 装任何包都被 PEP 668 拒：exit 1），
        # 也不要沿用源码树的 3.12（实测沙箱 pyenv 未装）。
        # 2026-10-15 实测：3.12 → not installed；system → externally-managed-environment。
        pathlib.PurePosixPath(".python-version"): b"3.11\n",
    }
    return out


def _vectordb_offenders() -> list[str]:
    """列出 ``backend/vectordb_data/`` 下**违反 career-only 定型**的条目。

    career-only 定型要求该目录下**只允许** ``import_jobs/``（import_worker 运行时自建的
    journal 目录，见 ``py-server/services/import_worker.py:140``）。任何向量库产物
    （``netlearn_kb.json`` / ``*.emb.npy`` / ``e5_embed_cache.npz`` / Milvus lite 数据等）
    都意味着「408 检索能力被塞回包内」或「裁空状态被破坏」，与定型冲突。

    白名单目录**内部**再按 :data:`VECTORDB_FORBIDDEN_SUFFIXES` /
    :data:`VECTORDB_FORBIDDEN_NAMES` 扫一遍，防止把大文件挪进 ``import_jobs/`` 规避断言
    （journal 本身是 ``<job_id>.json``，不会被误伤）。

    目录不存在 → 返回空列表（已裁空，合法）。
    """
    root = DST / "vectordb_data"
    if not root.is_dir():
        return []
    offenders: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = pathlib.Path(dirpath).relative_to(root)
        top = rel_dir.parts[0] if rel_dir.parts else None
        if top is not None and top not in VECTORDB_ALLOWED_ENTRIES:
            # 白名单外的整棵子树：只报顶层目录并剪枝，避免一条断言刷屏上百行
            offenders.append(f"目录: vectordb_data/{top}")
            dirnames[:] = []
            continue
        for f in sorted(filenames):
            rel_file = pathlib.PurePosixPath((rel_dir / f).as_posix())
            if rel_file.name in VECTORDB_FORBIDDEN_NAMES or any(
                rel_file.name.endswith(s) for s in VECTORDB_FORBIDDEN_SUFFIXES
            ):
                offenders.append(f"文件: vectordb_data/{rel_file.as_posix()}")
    return sorted(set(offenders))


def build() -> int:
    if not SRC.is_dir():
        print(f"[build_career_pilot_package] ❌ 源目录不存在：{SRC}", file=sys.stderr)
        return 2

    env_path = DST / ".env"
    preserved_env = env_path.read_bytes() if env_path.is_file() else None

    expected: set[pathlib.PurePosixPath] = set()
    copied = 0
    unchanged = 0
    for rel, src_file in _iter_src_files():
        dst_file = _dst_for(rel)
        expected.add(rel)
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        if dst_file.is_file() and filecmp.cmp(src_file, dst_file, shallow=False):
            unchanged += 1
            continue
        shutil.copy2(src_file, dst_file)
        copied += 1

    # 自产文件（瘦版 requirements.txt / .env.example）
    overlay = _overlay_files()
    for rel, data in overlay.items():
        expected.add(rel)
        dst_file = _dst_for(rel)
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        old = dst_file.read_bytes() if dst_file.is_file() else None
        if old != data:
            dst_file.write_bytes(data)
            copied += 1
        else:
            unchanged += 1

    # .env：优先保留已存在（真实密钥），否则从模板生成
    expected.add(pathlib.PurePosixPath(".env"))
    if preserved_env is not None:
        env_path.write_bytes(preserved_env)
    else:
        env_path.write_bytes(ENV_TEMPLATE.encode("utf-8"))
        print("[build_career_pilot_package] ℹ️ .env 缺失 → 已按模板生成（需人工填真实密钥与 AUTH_SECRET）")

    # 清理陈旧文件（源树已不存在者），保留 .env 与 PRESERVE_TOP_NAMES（如 site/）；
    # Windows 保留名（nul）删除失败则跳过
    removed = 0
    for dirpath, _dirnames, filenames in os.walk(DST, topdown=False):
        for f in filenames:
            p = pathlib.Path(dirpath) / f
            rel = pathlib.PurePosixPath(p.relative_to(DST).as_posix())
            if rel in expected:
                continue
            # 受保护的顶层目录（前端产物 site/ 等）不属于本脚本同步范围 → 不清理
            if rel.parts and rel.parts[0] in PRESERVE_TOP_NAMES:
                continue
            try:
                p.unlink()
                removed += 1
            except OSError:
                pass  # 保留名 / 占用中 → 跳过（不影响可运行性）

    # career-only 定型提示：build 不静默删除运行时数据，但发现向量库产物必须**显式警告**
    # （fail-closed 断言在 --check；此处只是把问题摆到台面上，避免「刷新一下就洗白」的错觉）
    offenders = _vectordb_offenders()
    if offenders:
        print(
            f"[build_career_pilot_package] ⚠️ backend/vectordb_data 检出 {len(offenders)} "
            f"处违反 career-only 定型的条目（--check 将 fail-closed 退出 1）："
        )
        for o in offenders[:10]:
            print(f"    - {o}")

    print(
        f"[build_career_pilot_package] ✅ 已刷新 {DST}\n"
        f"    复制/更新 {copied} · 未变 {unchanged} · 清理陈旧 {removed} · 目标文件合计 {len(expected)}"
    )
    return 0


def check() -> int:
    """校验目标瘦包与源树一致（对每份应拷贝文件做字节比对）。

    校验三件事，任一不过即 exit 1：
    1. 源树应拷贝文件与包内**字节一致**（无漂移）；
    2. 脚本自产文件（requirements.txt / .env.example / config.json / README.md）与包内
       **字节一致**——此前只比对拷贝文件，自产文件被手工改过查不出来；
    3. **career-only 能力边界未被破坏**：``backend/vectordb_data/`` 下不得出现向量库产物
       （见 :func:`_vectordb_offenders`）。

    ``.env`` **不参与**本校验：它含真实密钥，且是否注入由发布流程决定；比对它的内容
    等于把密钥写进 CI 日志。
    """
    if not SRC.is_dir():
        print(f"[build_career_pilot_package] ❌ 源目录不存在：{SRC}", file=sys.stderr)
        return 2
    drift: list[str] = []
    for rel, src_file in _iter_src_files():
        dst_file = _dst_for(rel)
        if not dst_file.is_file():
            drift.append(f"缺失: {rel}")
        elif src_file.read_bytes() != dst_file.read_bytes():
            drift.append(f"内容不一致: {rel}")
    for rel, data in _overlay_files().items():
        dst_file = _dst_for(rel)
        if not dst_file.is_file():
            drift.append(f"缺失: {rel}（脚本自产文件）")
        elif dst_file.read_bytes() != data:
            drift.append(f"内容不一致: {rel}（脚本自产文件）")
    offenders = _vectordb_offenders()

    if drift or offenders:
        if drift:
            print(f"[build_career_pilot_package] ❌ 瘦包与 py-server 漂移 {len(drift)} 处：")
            for d in drift[:20]:
                print(f"    - {d}")
            print("    请跑 `python scripts/build_career_pilot_package.py` 刷新。")
        if offenders:
            print(
                f"[build_career_pilot_package] ❌ career-only 定型被破坏："
                f"backend/vectordb_data 检出 {len(offenders)} 处向量库产物/越权条目。"
            )
            for o in offenders[:20]:
                print(f"    - {o}")
            print(
                "    本包为 career-only：只允许 import_jobs/（运行时自建 journal 目录）。\n"
                "    如需恢复 408 检索能力，请改回全量包，不要往瘦包里塞向量库产物。"
            )
        return 1

    vdb_note = (
        "vectordb_data 不存在（已裁空）"
        if not (DST / "vectordb_data").is_dir()
        else "vectordb_data 仅含 import_jobs/（career-only 定型）"
    )
    print(
        "[build_career_pilot_package] ✅ 瘦包与 py-server 源码一致（无漂移）；"
        f"{vdb_note}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成/刷新芒得很职云部署瘦包骨架")
    ap.add_argument("--check", action="store_true", help="只校验一致性，不写盘")
    args = ap.parse_args()
    return check() if args.check else build()


if __name__ == "__main__":
    sys.exit(main())
