# ============================================================
# _mutate_verify_r8 — 变异验证：证明本轮新增的回归护栏真能杀死缺陷
#
# 原则（项目硬教训）：测试全绿 ≠ 测试有效。写完关键测试必须**故意改回错误行为**，
# 确认测试转为 FAIL（KILLED），再恢复确认 PASS（RESTORED）。杀不死变异体的测试是摆设。
#
# 用法：NO_PROXY=127.0.0.1 .venv/Scripts/python.exe ../scripts/_mutate_verify_r8.py
# 安全：每个变异体执行前备份原文件，无论成败都在 finally 中恢复。
# ============================================================

import shutil
import subprocess
import sys
from pathlib import Path

PY_SERVER = Path(__file__).resolve().parent.parent / "py-server"
PY = PY_SERVER / ".venv" / "Scripts" / "python.exe"

# (名称, 目标文件, 原文, 变异后, 期望被杀死的测试)
MUTANTS = [
    (
        "M1 影子策略漏传 batch_episodes（复现本轮真实事故）",
        "engines/review_shadow_probe.py",
        "batch_episodes = max(1, min(48, int(ppo_episodes) // 10))",
        "batch_episodes = 48",
        "tests/test_mappo_budget_audit.py::test_build_shadow_policy_is_not_starved_by_default",
    ),
    (
        "M2 n_updates 上报错误值（预算不可审计）",
        "engines/review_policy.py",
        '"batch_episodes": int(batch_episodes), "n_updates": n_updates,',
        '"batch_episodes": int(batch_episodes), "n_updates": episodes,',
        "tests/test_mappo_budget_audit.py::test_train_ppo_reports_effective_budget",
    ),
    (
        "M3 成本项权重压倒 gate 项（奖励与验收口径错位）",
        "engines/review_policy.py",
        'REWARD_W = {"gate": 0.4, "precision": 0.35, "cost": 0.15, "discipline": 0.10}',
        'REWARD_W = {"gate": 0.4, "precision": 0.35, "cost": 5.0, "discipline": 0.10}',
        "tests/test_mappo_budget_audit.py::test_review_reward_aligned_with_acceptance_metric",
    ),
    (
        "M4 删除确定性回报字段（improved 重新变成会骗人的指标）",
        "engines/review_policy.py",
        '"improved_deterministic": det_after > det_before,',
        '"improved_deterministic_FOO": det_after > det_before,',
        "tests/test_mappo_budget_audit.py::test_train_ppo_reports_deterministic_improvement",
    ),
]


def run_test(test_id: str):
    """返回 (是否通过, 汇总行)。"""
    r = subprocess.run(
        [str(PY), "-m", "pytest", test_id, "-q", "--timeout=300",
         "-p", "no:cacheprovider",
         "--basetemp", str(PY_SERVER / ".pytest_tmp" / "mut")],
        cwd=str(PY_SERVER), capture_output=True,
        # Windows 控制台在 GBK 代码页下会输出非 UTF-8 字节（实测 0xcf），
        # 用 text=True 会让 harness 自身崩在解码上 —— 这里显式宽松解码，
        # 避免"工具崩了"被误读成"测试失败"。
        encoding="utf-8", errors="replace",
        env={"NO_PROXY": "127.0.0.1", "PATH": str(PY.parent), "SYSTEMROOT": "C:\\Windows"})
    out = (r.stdout or "") + (r.stderr or "")
    # 以 pytest 汇总行为准（不依赖退出码：项目已知 PowerShell 下退出码会污染）
    tail = [ln for ln in out.strip().splitlines() if ln.strip()]
    summary = tail[-1] if tail else "(无输出)"
    passed = (" passed" in summary) and ("failed" not in summary)
    return passed, summary


def main():
    results = []
    for name, rel, old, new, test_id in MUTANTS:
        f = PY_SERVER / rel
        backup = f.with_suffix(f.suffix + ".mutbak")
        src = f.read_text(encoding="utf-8")
        if old not in src:
            print(f"[{name}] SKIP: 未找到待变异片段（源码已变，请更新变异体定义）")
            results.append((name, "SKIP", ""))
            continue
        shutil.copy2(f, backup)
        try:
            f.write_text(src.replace(old, new, 1), encoding="utf-8")
            ok, summary = run_test(test_id)
            status = "SURVIVED ⚠️" if ok else "KILLED ✅"
            print(f"[{name}] {status}  ({summary})")
            results.append((name, status, summary))
        finally:
            shutil.copy2(backup, f)          # 恢复
            backup.unlink()

    # 恢复后必须全绿
    ok, summary = run_test("tests/test_mappo_budget_audit.py")
    print(f"\n[恢复后自检] {'PASS ✅' if ok else 'FAIL ❌'}  ({summary})")
    print("\n================= 变异验证汇总 =================")
    killed = sum(1 for _, s, _ in results if s.startswith("KILLED"))
    total = sum(1 for _, s, _ in results if s != "SKIP")
    for n, s, _ in results:
        print(f"  {s:<12} {n}")
    print(f"\n  杀死 {killed}/{total} 个变异体"
          f"{'（全部有效）' if killed == total and total else '（存在存活变异体，测试为摆设）'}")
    return 0 if (killed == total and total and ok) else 1


if __name__ == "__main__":
    sys.exit(main())
