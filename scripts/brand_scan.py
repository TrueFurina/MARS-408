#!/usr/bin/env python3
"""品牌一致性门禁（gate:brand）

产品对外可见层不得出现旧品牌名（MARS-408 及其变体）或旧赛事名
（火山杯 / 软件杯 / 三创赛 / huoshan），一律统一为「芒得很职」，且不展示任何赛事名称。

本门禁有**两个扫描面**：

── 面 A｜产品可见层（原有，保留）──────────────────────────────
  扫描目录树，只查「旧品牌 / 旧赛事名」硬令牌（MARS / 火山杯 / …）。
  - 前端：src/、public/、index.html、package.json
  - 后端：py-server/{app,api,services,agents,db,engines,tools,scripts} 下的 .py
          + py-server/config.py、py-server/main.py
  - 交付：submission/（豁免 _archive*/ 归档快照与 00_提交清单.md 元清单）

── 面 B｜身份展示面（新增）────────────────────────────────────
  对一份**有限、可枚举**的「对外身份展示」文件清单，额外查**身份定性短语**
  （考研学子 / 408 考研个性化学习 / 个性化学习闭环 / 个性化学习(多智能体)系统）。

  为什么是「文件清单」而不是「把 408 加进全局令牌表」：
    `408` 在本仓是**科目代码不是品牌**（`grep -rn 408 src/` = 89 行 / 41 文件）。
    把它加进面 A 的全局令牌会一次造出 89 条红灯，只能靠一份大白名单压回去，
    而白名单一腐烂门禁就废 —— 等于用一个新的假绿替换旧的假绿。
    py-server 内部（tutor / mindmap / feedback / seed 等 408 考研线业务代码）
    **本来就该有 408 内容**，把业务代码纳入品牌门禁就永远要依赖白名单。

  因此面 B 的设计取舍是：**清单是有限的、可枚举的，措辞不是。**
    只对 9 个"用户/评委真正会看到产品自称是什么"的位置启用身份短语
    （含根目录 Dockerfile / docker-compose.yml 镜像与编排元数据），
    py-server 内部的合法 408 业务代码**不在清单内，永不误伤**。

  清单内文件若丢失 → 视为 DRIFT 并判失败：清单是本门禁的真值源，
  文件被改名/删除会静默关掉一格护栏，这正是本次要根治的"假绿"失效模式。

排除（历史记录 / 生成产物 / 冻结副本 —— 有意保留原名）：
  - docs/ documents/ deliverables/ diagnostics/（历史与交付快照）
  - */crypto_platform/**（AGENTS.md:20 冻结的嵌套副本，未经确认不得改动）
  - submission/_archive*/（有意保留旧名归档快照，非产品品牌展示面）
  - submission/00_提交清单.md（交付元清单，记录旧品牌清理结果，非品牌展示）
  - dist/ node_modules/ .git/ __pycache__/，以及非文本扩展名

特例白名单：仓库/站点真实 URL（GitHub 仓名尚未更名，属功能性引用，非品牌展示）

注：本 gate 是**回归护栏，不是修复手段** —— 它保证改完不退回去，
   但不替代出稿前的人工核对（短语令牌天然只覆盖"已想到的措辞"）。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 令牌：旧品牌 / 旧赛事（面 A + 面 B 共用）────────────────────
# MARS 同时覆盖 MARS-408 / MARS408 / 拆分 span 写法
BRAND_TOKENS = ["MARS", "火山杯", "软件杯", "三创赛", "huoshan", "火星杯"]

# ── 令牌：身份定性短语（仅面 B 启用）──────────────────────────
# 来源：deliverables/gstack/backlog-audit-mangdehenzhi-2026-10-06.md §附2 定稿。
# 实测命中 6 处 / 0 误伤；不误伤"个性化学习路径 / 建议 / 推荐"等合法用法
#（全仓 19 处含"个性化学习"，仅 6 处是身份定性）。
# ⚠️ 场景内部的"408 考研"业务文案是合法内容，不在清单内，不受影响。
IDENTITY_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("考研学子", re.compile(r"考研学子")),
    ("408 考研", re.compile(r"408\s*考研")),
    ("408 考研个性化学习", re.compile(r"408\s*考研个性化学习")),
    ("个性化学习闭环", re.compile(r"个性化学习闭环")),
    ("个性化学习(多智能体)系统", re.compile(r"个性化学习(?:多智能体)?系统")),
]

# ── 面 B：身份展示面清单（有限、可枚举）────────────────────────
# 只列"用户/评委无需登录就能看到产品自称是什么"的位置。
IDENTITY_SURFACE_FILES: list[tuple[str, str]] = [
    ("src/views/LandingView.vue", "落地页（公开路由，评委免登录直达）"),
    ("src/views/ShowcaseView.vue", "展示页（产品能力对外陈列）"),
    ("src/views/DesignUpgradeView.vue", "设计升级页"),
    ("src/views/DesignSystemView.vue", "设计系统页（品牌自述位）"),
    ("src/views/PlatformHomeView.vue", "门户首页"),
    ("index.html", "仓库根 index.html（SEO / og / title）"),
    ("py-server/main.py", "FastAPI OpenAPI 元数据（/docs 标题与描述，评委可见）"),
    ("py-server/openapi.json", "OpenAPI 冻结快照（git 已跟踪、随包发出；防与 main.py 同源身份静默漂移）"),
    ("Dockerfile", "镜像元数据标签（docker inspect / 仓库可见，产品自称）"),
    ("docker-compose.yml", "编排元数据注释（开箱即跑说明，产品自称）"),
]

# 功能性 URL 白名单（仓名未更名前必须保留）
ALLOW_SUBSTRINGS = [
    "truefurina.github.io/MARS-408",
    "github.com/TrueFurina/MARS-408",
    "TrueFurina/MARS-408",
]

SCAN_DIRS = ["src", "public", "submission"]
SCAN_FILES = ["index.html", "package.json"]
BACKEND_DIRS = ["app", "api", "services", "agents", "db", "engines", "tools", "scripts"]
BACKEND_FILES = ["config.py", "main.py"]

EXCLUDE_PARTS = {"node_modules", ".git", "dist", "crypto_platform", "__pycache__", ".pytest_cache"}

# 提交清单元数据清单：记录旧品牌清理结果，属交付元文档而非产品品牌展示面，豁免扫描
EXCLUDE_FILES = {"submission/00_提交清单.md"}

# submission/ 下 _archive* 为有意保留的归档快照（旧名/旧件），整体豁免
EXCLUDE_ARCHIVE_PREFIX = "_archive"

TEXT_EXT = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".json", ".html", ".htm",
    ".css", ".md", ".txt", ".py", ".yml", ".yaml", ".webmanifest", ".sh", ".bat", ".ps1",
}


def _iter_files():
    """面 A：产出产品可见层的全部候选文件。"""
    for d in SCAN_DIRS:
        p = ROOT / d
        if p.exists():
            yield from (f for f in p.rglob("*") if f.is_file())
    for f in SCAN_FILES:
        p = ROOT / f
        if p.exists():
            yield p
    for d in BACKEND_DIRS:
        p = ROOT / "py-server" / d
        if p.exists():
            yield from (f for f in p.rglob("*") if f.is_file())
    for f in BACKEND_FILES:
        p = ROOT / "py-server" / f
        if p.exists():
            yield p


def _excluded(path: Path) -> bool:
    if set(path.parts) & EXCLUDE_PARTS:
        return True
    if any(part.startswith(EXCLUDE_ARCHIVE_PREFIX) for part in path.parts):
        return True
    if path.suffix.lower() not in TEXT_EXT:
        return True
    rel = path.relative_to(ROOT).as_posix()
    if rel in EXCLUDE_FILES:
        return True
    return False


def _allowed(line: str) -> bool:
    """功能性 URL（GitHub 仓名未更名）不算品牌展示，放行。"""
    return any(s in line for s in ALLOW_SUBSTRINGS)


def _scan_text(rel: str, text: str, tokens) -> list[tuple[str, int, str, str]]:
    """对给定文本逐行匹配令牌，返回 (文件, 行号, 令牌, 片段)。

    Args:
        rel: 用于输出的相对路径。
        text: 文件全文。
        tokens: 可迭代的 (标签, 正则) 二元组。

    Returns:
        命中列表；同一行只记第一个命中的令牌，避免重复计数。
    """
    out: list[tuple[str, int, str, str]] = []
    for i, line in enumerate(text.splitlines(), 1):
        if _allowed(line):
            continue
        for label, pattern in tokens:
            if pattern.search(line):
                out.append((rel, i, label, line.strip()[:120]))
                break
    return out


def _brand_tokens():
    """把硬令牌包装成与身份短语一致的 (标签, 正则) 形式。"""
    return [(t, re.compile(re.escape(t))) for t in BRAND_TOKENS]


def scan_visible_layer() -> list[tuple[str, int, str, str]]:
    """面 A：产品可见层 —— 只查旧品牌 / 旧赛事名。"""
    hits: list[tuple[str, int, str, str]] = []
    tokens = _brand_tokens()
    for f in _iter_files():
        if _excluded(f):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = f.relative_to(ROOT).as_posix()
        hits.extend(_scan_text(rel, text, tokens))
    return hits


def scan_identity_surface() -> tuple[list[tuple[str, int, str, str]], list[str]]:
    """面 B：身份展示面 —— 旧品牌名 + 身份定性短语。

    Returns:
        (命中列表, 清单中缺失的文件列表)。缺失文件由调用方判为 DRIFT 失败。
    """
    hits: list[tuple[str, int, str, str]] = []
    missing: list[str] = []
    tokens = _brand_tokens() + IDENTITY_PATTERNS
    for rel, _desc in IDENTITY_SURFACE_FILES:
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        hits.extend(_scan_text(rel, text, tokens))
    return hits, missing


def main() -> int:
    visible_hits = scan_visible_layer()
    identity_hits, missing = scan_identity_surface()

    total = len(visible_hits) + len(identity_hits)
    surface_total = len(IDENTITY_SURFACE_FILES)
    surface_present = surface_total - len(missing)

    print(
        f"[gate:brand] 身份展示面：{surface_present}/{surface_total} 文件在位"
        f"；面A(产品可见层) 命中 {len(visible_hits)} 处"
        f"；面B(身份展示面) 命中 {len(identity_hits)} 处"
    )

    ok = True

    if visible_hits:
        ok = False
        print("\n[gate:brand] FAIL — 面A 产品可见层仍含旧品牌 / 旧赛事名：")
        for rel, i, tok, snippet in visible_hits:
            print(f"  [产品可见层] {rel}:{i}  [{tok}]  {snippet}")

    if identity_hits:
        ok = False
        print("\n[gate:brand] FAIL — 面B 身份展示面仍含旧品牌 / 旧身份词：")
        for rel, i, tok, snippet in identity_hits:
            print(f"  [身份展示面] {rel}:{i}  [{tok}]  {snippet}")

    if missing:
        ok = False
        print("\n[gate:brand] FAIL — 身份展示面清单出现 DRIFT（文件缺失，护栏被静默关掉）：")
        for rel in missing:
            desc = dict(IDENTITY_SURFACE_FILES).get(rel, "")
            print(f"  [DRIFT] {rel}  ({desc})")
        print("  修法：文件若已改名/删除，请同步更新 brand_scan.py 的 IDENTITY_SURFACE_FILES。")

    if not ok:
        print(f"\n共 {total} 处（另有 {len(missing)} 处清单 DRIFT）。")
        print("请统一为「芒得很职」口径，并移除任何赛事名称与旧身份定性。")
        print("注：py-server 内部场景的「408 考研」业务文案属合法内容，勿改。")
        return 1

    print("[gate:brand] PASS — 产品可见层与身份展示面均无旧品牌 / 旧身份词残留。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
