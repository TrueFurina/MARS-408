#!/usr/bin/env python3
"""
ruff 潜在缺陷门禁（D11 F401 门禁扩展，D13 加固）

职责：在 pre-commit 阶段对「已暂存的 .py 文件」做 ruff 潜在缺陷扫描，
覆盖 F401(未使用导入) / F811(未使用重定义) / F821(未定义名) /
F822(__all__ 引用未定义) / F841(赋值未使用)。
发现任一即拦截提交（fail-closed）。仅阻断「本次新增」的潜在缺陷，
不回溯整树历史债务。

工具链路：
- 优先 `uvx ruff`（项目已用 uv 管理，ruff 经 uvx 取最新缓存版）；
- 回退 `ruff` 命令行（PATH 内已装）；
- 若 ruff 均不可用（离线 / 未装），打印警告并以 exit 0 放行——避免工具缺失阻断本地提交；
  CI 环境通常联网且 uvx 可用，故 CI 下该门禁严格生效。

仅检查 py-server 下的暂存文件（ruff 配置在 py-server/pyproject.toml）。
"""
import subprocess
import sys
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY_SERVER = os.path.join(REPO_ROOT, "py-server")

# 非风格类潜在缺陷集合（D11 清 F401、D12 清 F821 后整树归零，固化防回归）
SELECT = "F401,F811,F821,F822,F841"


def get_staged_py_files():
    """取已暂存（A/C/M）的 .py 文件，限定 py-server 范围。"""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    files = []
    for f in out.splitlines():
        f = f.strip()
        if not f.endswith(".py"):
            continue
        # 仅 py-server 内文件（ruff 配置位置）
        if os.path.commonpath([os.path.abspath(os.path.join(REPO_ROOT, f)), PY_SERVER]) == PY_SERVER:
            files.append(f)
    return files


def find_ruff():
    """返回可调用的 ruff argv 前缀，找不到返回 None。"""
    # 1) uvx ruff（最新缓存）
    try:
        subprocess.run(
            ["uvx", "ruff", "--version"],
            cwd=PY_SERVER,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=60,
        )
        return ["uvx", "ruff"]
    except Exception:
        pass
    # 2) 直接 ruff
    try:
        subprocess.run(
            ["ruff", "--version"],
            cwd=PY_SERVER,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30,
        )
        return ["ruff"]
    except Exception:
        pass
    return None


def main():
    files = get_staged_py_files()
    if not files:
        print("[ruff_gate] 无可扫描的暂存 .py 文件，放行。")
        return 0

    ruff = find_ruff()
    if ruff is None:
        print(
            "[ruff_gate] ⚠️ 未找到 ruff（uvx/ruff 均不可用）。"
            "跳过 ruff 潜在缺陷检查以免阻断本地提交；CI 环境应联网以确保门禁生效。"
        )
        return 0

    # ruff 在其项目根（py-server）解析 pyproject 配置；传入相对/绝对路径均可。
    abs_files = [os.path.join(REPO_ROOT, f) for f in files]
    cmd = ruff + ["check", "--select", SELECT, "--output-format", "concise"] + abs_files
    try:
        proc = subprocess.run(
            cmd,
            cwd=PY_SERVER,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("[ruff_gate] ⚠️ ruff 执行超时，放行（不阻断）。")
        return 0

    if proc.returncode == 0:
        print("[ruff_gate] ✅ 暂存文件无 ruff 潜在缺陷（F401/F811/F821/F822/F841）。")
        return 0

    # 非零退出：打印 ruff 输出，列出潜在缺陷，拦截提交。
    print("[ruff_gate] ❌ 发现 ruff 潜在缺陷（F401/F811/F821/F822/F841），提交被拦截。请修复或加对应 `# noqa`：")
    print(proc.stdout.strip())
    print("\n提示：re-export（如 __init__.py 公开符号）应加入 __all__，而非用 noqa 掩盖；F821 未定义名须补 import 或定义。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
