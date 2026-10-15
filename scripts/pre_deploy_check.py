#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""发布前检查（pre-deploy check）—— 只读，不改动任何文件。

为什么需要它（2026-10-15 两次实战教训）：
  1. `build_career_pilot_package.py` 会**原样复制 py-server 全部文件** ⇒
     工作区里任何未提交的改动（例如另一个会话正在做的 E5 模型迁移）
     都会被打进包并随发布上线 —— 而它们可能根本没验证过。
  2. 指标数字（docs/METRICS_CURRENT.md）会随改码漂移，而 `verify_metrics.py`
     是 CI 阻断项，发布后才发现就要再补一次发布。
  两件事都能在**发布前几秒**查出来，故固化为本脚本。

用法：
    python scripts/pre_deploy_check.py          # 检查并给出 Go/No-Go
    python scripts/pre_deploy_check.py --quiet  # 仅输出结论行

退出码：0 = Go；1 = No-Go（存在阻断项）
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import pathlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# 会被打进发布产物的源码目录（前端 src/ 经构建；后端 py-server/ 由打包脚本整树复制）
WATCHED = ("py-server", "src")

# 复用打包脚本自己的排除规则，避免两处维护两套口径
_BPP = REPO / "scripts" / "build_career_pilot_package.py"
_spec = importlib.util.spec_from_file_location("_build_career_pilot_package", _BPP)
_bpp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bpp)  # 模块有 __main__ 保护，导入不触发构建

OK, WARN, BLOCK = "✅", "⚠️ ", "❌"


def _packaged_only(prefix: str, paths: list[str]) -> list[str]:
    """只保留**真正会进包**的文件（排除项按打包脚本的口径过滤）。

    否则 warning 会把 vectordb_data 备份、__pycache__ 之类一股脑算进去
    （实测 5 个真实改动被淹没在 56 个里），警告失去意义。
    """
    base = REPO / prefix
    kept = []
    for p in paths:
        try:
            rel = pathlib.PurePosixPath(str(Path(p).relative_to(prefix)).replace("\\", "/"))
        except ValueError:
            kept.append(p)
            continue
        if not _bpp._excluded(rel):
            kept.append(p)
    return kept


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip() if r.returncode == 0 else ""


def changed_files(prefix: str) -> list[str]:
    """工作区（含暂存）相对 HEAD 的改动文件，限定在 prefix 目录内。

    用两条 git 命令组合而非解析 `status --porcelain`：后者的状态前缀宽度
    容易在解析时错切（曾把 py-server/... 切成 y-server/...）。
    """
    tracked = _git("diff", "--name-only", "HEAD", "--", prefix)
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", prefix)
    seen: list[str] = []
    for chunk in (tracked, untracked):
        for line in chunk.splitlines():
            p = line.strip().strip('"')
            if p and p not in seen:
                seen.append(p)
    return seen


def run_check(script: str, extra: list[str] | None = None) -> tuple[bool, str]:
    """执行只读校验脚本，返回 (是否通过, 摘要行)。"""
    cmd = [sys.executable, str(REPO / script), *(extra or [])]
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    lines = [l for l in (r.stdout or "").splitlines() if l.strip()]
    tail = lines[-1].strip() if lines else "(无输出)"
    return r.returncode == 0, tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="仅输出结论")
    args = ap.parse_args()

    blocked: list[str] = []
    warned: list[str] = []

    # ── 1) 会被打进发布产物的未提交改动 ──
    dirty: dict[str, list[str]] = {}
    skipped: dict[str, int] = {}
    for prefix in WATCHED:
        all_changed = changed_files(prefix)
        kept = _packaged_only(prefix, all_changed) if prefix == "py-server" else all_changed
        dirty[prefix] = kept
        skipped[prefix] = len(all_changed) - len(kept)
    if not args.quiet:
        print("[1/5] 将进入发布产物的未提交改动（打包脚本整树复制）")
        for prefix, files in dirty.items():
            note = f"（另有 {skipped[prefix]} 个改动被打包排除规则挡下，不会上线）" if skipped[prefix] else ""
            if files:
                print(f"  {WARN}{prefix}/ 有 {len(files)} 个未提交文件，会随发布上线：")
                for f in files[:8]:
                    print(f"        - {f}")
                if len(files) > 8:
                    print(f"        … 其余 {len(files) - 8} 个")
                if note:
                    print(f"        {note}")
            else:
                print(f"  {OK} {prefix}/ 干净{(' ' + note) if note else ''}")
    for prefix, files in dirty.items():
        if files:
            warned.append(f"{prefix}/ 有 {len(files)} 个未提交文件将被发布")

    # ── 2) 包内 .env 的 LLM 凭据是否已注入 ──
    # 打包脚本按模板生成包内 .env（占位符，"真实 .env 由人工/发布流程注入"）。
    # 若忘了注入，线上 LLM 全程不可用 ⇒ career 实训退化为**规则兜底**：
    # 六维里多数维度「证据不足不予评分」、追问变模板话术（2026-10-15 真人演练实测到）。
    # 这种退化很隐蔽（页面不报错），所以必须在发布前拦住。
    # 按 LLM_PROVIDER 判定对应通道的 key：provider 换成 glm 后，
    # 残留的 DEEPSEEK_API_KEY 占位符已不参与调用，若仍查它会误报 No-Go。
    PROVIDER_KEYS = {
        "deepseek": ["DEEPSEEK_API_KEY"],
        "glm": ["ZHIPU_API_KEY", "GLM_API_KEY"],
        "qwen": ["QWEN_API_KEY", "DASHSCOPE_API_KEY"],
        "xfyun": ["XF_API_KEY", "XF_API_SECRET"],
    }
    env_path = REPO / "deploy" / "career-pilot" / "backend" / ".env"
    env_vars: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    provider = env_vars.get("LLM_PROVIDER", "auto").strip().lower()
    # auto 时任一通道有真 key 即可（config 会按优先级兜底），故检查全部已知通道
    keys_to_check = PROVIDER_KEYS.get(provider) or [k for ks in PROVIDER_KEYS.values() for k in ks]

    def _is_placeholder(val: str) -> bool:
        return (not val or val.startswith("your_") or "placeholder" in val.lower()
                or "changeme" in val.lower() or len(val) < 20)

    present = [k for k in keys_to_check if not _is_placeholder(env_vars.get(k, ""))]
    llm_placeholder = not present
    if not args.quiet:
        detail = f"provider={provider}；已注入 {present[0]}" if present else \
                 f"provider={provider}；{', '.join(keys_to_check)} 均为占位符/缺失"
        print(f"\n[2/5] 包内 .env 的 LLM 凭据\n  {WARN if llm_placeholder else OK} "
              + (detail + " ⇒ 线上实训会退化为规则兜底（六维多数维度不给分）" if llm_placeholder else detail))
    if llm_placeholder:
        warned.append("包内 .env 的 LLM key 未注入（线上将走兜底模式）")

    # ── 3) 工程规模指标一致性（CI 阻断项）──
    ok, tail = run_check("scripts/verify_metrics.py")
    if not args.quiet:
        print(f"\n[3/5] 工程规模指标（CI 阻断项）\n  {OK if ok else BLOCK} {tail}")
    if not ok:
        blocked.append("verify_metrics 不一致（跑 python scripts/verify_metrics.py --update 同步）")

    # ── 4) 诚实口径机检 ──
    ok, tail = run_check("scripts/pre-commit/honesty_scan.py")
    if not args.quiet:
        print(f"\n[4/5] 诚实口径机检\n  {OK if ok else BLOCK} {tail}")
    if not ok:
        blocked.append("诚实口径机检未通过")

    # ── 5) 瘦包与源码一致性 ──
    ok, tail = run_check("scripts/build_career_pilot_package.py", ["--check"])
    if not args.quiet:
        print(f"\n[5/5] 瘦包与 py-server 源码一致性\n  {OK if ok else BLOCK} {tail}")
    if not ok:
        blocked.append("瘦包与源码存在漂移（重跑 build_career_pilot_package.py）")

    # ── 结论 ──
    verdict = "NO-GO" if blocked else "GO"
    print(f"\n{'=' * 56}\n发布前检查结论：{verdict}")
    if blocked:
        for b in blocked:
            print(f"  {BLOCK} 阻断：{b}")
    if warned:
        for w in warned:
            print(f"  {WARN}注意：{w}")
            print("        ⇒ 若非本次发布内容，请先与对应会话确认收口，或"
                  "用 `git show HEAD:<path> > deploy/career-pilot/backend/<path>` 精确回退包内文件")
    if not blocked and not warned:
        print("  无阻断项、无未提交改动 —— 可以发布")
    print("=" * 56)
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
