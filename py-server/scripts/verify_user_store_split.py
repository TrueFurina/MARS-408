# ============================================================
# py-server/scripts/verify_user_store_split.py
# 架构评审 M-4 ②（db/user_store.py 画像域拆出 db/profile_store.py）的可机验守门脚本。
#
# 为什么是「行为差分」而不是「符号 repr 快照」：
#   user_store 的符号绝大多数是**函数**，repr(func) 含内存地址，搬运后必然不同，
#   会把真差异淹掉。函数要证的是「行为不变」——于是用固定调用序列 + 临时 DB，
#   把每一步的返回值 JSON 化，与拆分前冻结的基线逐键对账（时间戳归一为 <TS>）。
#
# 另查三件只看代码看不出来的事：
#   1) 委托是否动态（patch profile_store 后 user_store 是否跟随）
#   2) 有无循环依赖（profile_store 能否脱离 user_store 单独导入）
#   3) user_store 的公共符号集合是否与拆分前完全一致
#
# 运行：cd py-server && python scripts/verify_user_store_split.py
# 退出码：0 = 全部通过，1 = 存在失败
# ============================================================

import json
import os
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

_BASELINE = os.path.join(_HERE, "user_store_baseline_probe.json")
_PROBE = os.path.join(_HERE, "user_store_behavior_probe.py")

ok = True


def check(label, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {label} {extra}")


def main():
    with open(_BASELINE, "r", encoding="utf-8") as f:
        base = json.load(f)

    # ── 1) 行为差分：跑同一序列，逐键对账 ──
    tmp_out = os.path.join(tempfile.gettempdir(), "user_store_probe_current.json")
    subprocess.run([sys.executable, _PROBE, tmp_out], cwd=_ROOT, check=True)
    with open(tmp_out, "r", encoding="utf-8") as f:
        now = json.load(f)
    os.remove(tmp_out)

    check("探针步数与基线一致", set(base) == set(now),
          f"base={len(base)} now={len(now)}")
    diffs = []
    for k in sorted(set(base) & set(now)):
        if base[k] != now[k]:
            diffs.append(k)
    check("每一步的返回值/错误与基线完全一致", not diffs, diffs[:6])

    failures = [k for k, v in now.items() if not v.get("ok")]
    check("探针自身无失败步骤", not failures, failures[:5])

    # ── 2) 委托是动态的（不是快照）──
    import db.profile_store as ps
    import db.user_store as us
    check("user_store.get_profile 指向 profile_store.get_profile",
          us.get_profile is ps.get_profile)
    check("三个高频画像符号均动态穿透",
          us.save_profile is ps.save_profile and us.get_quiz_history is ps.get_quiz_history
          and us.get_profile_snapshots is ps.get_profile_snapshots)

    _orig = ps.get_profile
    _sentinel = lambda uid: {"sentinel": True}  # noqa: E731
    ps.get_profile = _sentinel
    check("patch profile_store 后 user_store 跟随（非快照）", us.get_profile is _sentinel)
    ps.get_profile = _orig
    check("还原后恢复", us.get_profile is _orig)

    # ── 3) 无循环依赖：profile_store 可独立导入 ──
    code = (
        "import sys; sys.path.insert(0, r'%s'); import db.profile_store as p; "
        "print('USER_STORE_LOADED' if 'db.user_store' in sys.modules else 'CLEAN')" % _ROOT
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=_ROOT)
    check("profile_store 可独立导入且不拉起 user_store（无循环）",
          "CLEAN" in proc.stdout, proc.stdout.strip()[:40])

    # ── 4) 公共符号集合与拆分前一致 ──
    baseline_syms = base["constants"]["value"]["public_symbols"]
    current_syms = sorted(n for n in dir(us) if not n.startswith("_"))
    check("user_store 公共符号集合与拆分前一致", baseline_syms == current_syms,
          f"多出={sorted(set(current_syms) - set(baseline_syms))} 缺失={sorted(set(baseline_syms) - set(current_syms))}")

    # ── 5) 画像域四张表由 profile_store 负责建（独立可用）──
    tmp_db = tempfile.mkdtemp(prefix="profile_store_standalone_")
    env = dict(os.environ, NETLEARN_USER_DB=os.path.join(tmp_db, "standalone.db"))
    code2 = (
        "import sys; sys.path.insert(0, r'%s'); import db.profile_store as p;"
        "p.save_profile('u1', {'a': 1}); print(p.get_profile('u1'))" % _ROOT
    )
    proc2 = subprocess.run([sys.executable, "-c", code2], capture_output=True, text=True,
                           cwd=_ROOT, env=env)
    check("profile_store 单独使用即可建表并读写（幂等建表生效）",
          "'a': 1" in proc2.stdout, (proc2.stdout or proc2.stderr).strip()[:80])

    print("\nRESULT:", "ALL PASS" if ok else "HAS FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
