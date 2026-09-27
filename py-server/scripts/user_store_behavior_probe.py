# ============================================================
# py-server/scripts/user_store_behavior_probe.py
# db.user_store 的行为探针 —— 供「M-4 ② 拆域」做差分校验。
#
# 为什么不用符号 repr 快照（seed/ 那次的做法）有效：
#   这里绝大多数符号是**函数**，`repr(func)` 含内存地址，搬运后必然不同，
#   会淹没真正的差异。函数要证的是「行为不变」，不是「对象同一」。
#
# 做法：指向一个临时 DB（NETLEARN_USER_DB），跑一段固定的调用序列，
# 把每一步的返回值 JSON 化输出；动态时间戳统一归一为 "<TS>"。
# 拆分前跑一次存为基线，拆分后再跑一次逐键比对。
#
# 用法：
#   cd py-server && python scripts/user_store_behavior_probe.py <输出.json>
# ============================================================

import json
import os
import re
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))  # py-server 根

_TMP = tempfile.mkdtemp(prefix="userstore_probe_")
os.environ["NETLEARN_USER_DB"] = os.path.join(_TMP, "probe_users.db")  # db.core 启动时读取

import db.user_store as us  # noqa: E402

_TS_FIELDS = (
    "created_at", "updated_at", "timestamp", "last_wrong_at", "first_wrong_at",
    "next_review_at", "submitted_at", "deadline",
)

import re as _re

_UID_RE = _re.compile(r"^u_[0-9a-f]{16}$")

steps: "dict[str, object]" = {}
# 先占位：create_user 是第一步，它的 _clean 会引用 _UID（归一时比较），
# 若等到赋值那行才定义，第一步就会 NameError。
_UID = ""


def _clean(value):
    """JSON 化 + 动态值归一（时间戳、随机用户 id）。

    ⚠️ 用户 id 是 create_user 现场生成的随机串（u_<hex>），每次运行都不同；
    它还会出现在 created_by / owner_user_id / user_id 等派生字段里，
    不归一的话差分会被这些噪声淹没（实测 6 处假差异全由此而来）。
    """
    if isinstance(value, str):
        # 按形态归一（u_<16 hex>）：比"等于 _UID"更通用 —— 能覆盖 admin 等
        # 其它用户的 id，也不依赖 _UID 的赋值时机（create_user 那步它还为空）。
        if _UID_RE.match(value):
            return "<UID>"
        return value
    if isinstance(value, dict):
        return {k: ("<TS>" if k in _TS_FIELDS else _clean(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def record(name, fn):
    try:
        result = fn()
        steps[name] = {"ok": True, "value": _clean(result)}
    except Exception as e:  # noqa: BLE001
        steps[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _first_task_id():
    """取每日计划里的第一个 task_id（供 update_daily_plan_task 使用）。

    定义在 record 调用之前：record 会**立即**执行 fn()，放在后面会 NameError。
    """
    plan = steps.get("get_or_create_daily_plan", {}).get("value") or {}
    tasks = plan.get("tasks") or []
    return tasks[0].get("task_id") if tasks else None


# ── 账户域 ──
# 先真实创建并取 id：不能从 steps[...]["value"] 取 —— 那里已被 _clean 归一成 "<UID>"，
# 拿它去查库必然返回 None（实测踩过）。
_USER = us.create_user("probe_u1", "Passw0rd!23", "Probe User")
_UID = _USER["id"]
record("create_user", lambda: _USER)
record("authenticate_ok", lambda: us.authenticate("probe_u1", "Passw0rd!23"))
record("authenticate_bad_pwd", lambda: us.authenticate("probe_u1", "wrong-password"))
record("get_user_by_id", lambda: {k: v for k, v in us.get_user_by_id(_UID).items() if k != "password_hash"})
record("get_user_by_username", lambda: us.get_user_by_username("probe_u1") is not None)
record("ensure_admin", lambda: us.ensure_admin("probe_admin", "AdminPassw0rd!23"))
record("set_password", lambda: us.set_password("probe_u1", "NewPassw0rd!23"))
record("authenticate_after_set_password", lambda: us.authenticate("probe_u1", "NewPassw0rd!23") is not None)

# ── 画像域（本次拆出的目标）──
record("save_profile", lambda: us.save_profile(_UID, {"dim": {"konwledge": 0.4}, "note": "probe"}))
record("get_profile", lambda: us.get_profile(_UID))
record("append_quiz_history", lambda: us.append_quiz_history(
    _UID, [{"subject": "ds", "correct": 1, "difficulty": "easy"}]))
record("get_quiz_history", lambda: us.get_quiz_history(_UID))
# 注意：save_conversations 取的是 c["id"]（不是 conv_id）
record("save_conversations", lambda: us.save_conversations(_UID, [{"id": "c1", "title": "t", "messages": []}]))
record("get_conversations", lambda: us.get_conversations(_UID))
record("save_profile_snapshot", lambda: isinstance(us.save_profile_snapshot(_UID, {"dim": {"a": 1}}), int))
record("get_profile_snapshots", lambda: us.get_profile_snapshots(_UID, limit=5))
# 关键：list_all_users 内部回调 get_profile —— 拆域后最容易断的一条链
record("list_all_users", lambda: us.list_all_users())
record("get_platform_stats", lambda: us.get_platform_stats())

# ── 错题 / 复习域 ──
record("add_wrong_question", lambda: us.add_wrong_question(
    _UID, {"id": "q1", "text": "probe?"}, "B", error_type="concept"))
_WID = steps["add_wrong_question"]["value"]["id"] if steps["add_wrong_question"]["ok"] else None
record("get_wrong_question_owner", lambda: us.get_wrong_question_owner(_WID))
record("get_wrong_question", lambda: us.get_wrong_question(_WID))
record("get_error_profile", lambda: us.get_error_profile(_UID))
record("record_review", lambda: us.record_review(_WID, recalled_correct=True) is not None)
record("get_due_reviews", lambda: len(us.get_due_reviews(_UID)))
record("list_wrong_questions", lambda: us.list_wrong_questions(_UID))
record("get_wrong_question_stats", lambda: us.get_wrong_question_stats(_UID))
record("mark_wrong_question_mastered", lambda: us.mark_wrong_question_mastered(_WID, _UID, True))
record("delete_wrong_question", lambda: us.delete_wrong_question(_WID, _UID))

# ── 每日计划域 ──
record("get_or_create_daily_plan", lambda: us.get_or_create_daily_plan(_UID))
_PID = steps["get_or_create_daily_plan"]["value"]["id"] if steps["get_or_create_daily_plan"]["ok"] else None
record("update_daily_plan_task", lambda: us.update_daily_plan_task(_PID, _UID, _first_task_id(), True))
record("list_daily_plans", lambda: us.list_daily_plans(_UID))
record("reset_daily_plan", lambda: us.reset_daily_plan(_PID, _UID) is not None)


def _first_task_id():
    plan = steps.get("get_or_create_daily_plan", {}).get("value") or {}
    tasks = plan.get("tasks") or []
    return tasks[0].get("task_id") if tasks else None


# ── 学习资源域 ──
record("register_learning_resource", lambda: us.register_learning_resource(
    _UID, "reading_material", "probe title", {"body": "x"}))
_RID = steps["register_learning_resource"]["value"]["id"] if steps["register_learning_resource"]["ok"] else None
record("get_learning_resource", lambda: us.get_learning_resource(_RID))
record("list_learning_resources", lambda: us.list_learning_resources(_UID))
record("delete_learning_resource", lambda: us.delete_learning_resource(_RID, _UID))

# ── 作业域 ──
record("create_assignment", lambda: us.create_assignment(
    "probe assignment", [], subject="ds", chapter="ch1", created_by=_UID))
record("list_assignments", lambda: us.list_assignments(limit=5))
_AID = steps["create_assignment"]["value"]["id"] if steps["create_assignment"]["ok"] else None
record("get_assignment", lambda: us.get_assignment(_AID))
record("submit_assignment", lambda: us.submit_assignment(_AID, _UID, [{"q": 1, "a": "A"}], 88.0))
record("get_submission", lambda: us.get_submission(_AID, _UID))

# ── 常量 ──
record("constants", lambda: {
    "PBKDF2_ITERATIONS": us.PBKDF2_ITERATIONS,
    "MIN_PASSWORD_LENGTH": us.MIN_PASSWORD_LENGTH,
    "public_symbols": sorted(n for n in dir(us) if not n.startswith("_")),
})

out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "user_store_baseline_probe.json")
payload = json.dumps(steps, ensure_ascii=False, indent=1, sort_keys=True)
# 兜底：再抹一次任何残留的绝对时间戳形态（YYYY-MM-DD HH:MM:SS）
payload = re.sub(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "<TS>", payload)
with open(out, "w", encoding="utf-8") as f:
    f.write(payload)

shutil.rmtree(_TMP, ignore_errors=True)
failed = [k for k, v in steps.items() if not v["ok"]]
print(f"steps={len(steps)} failed={len(failed)} -> {out}")
if failed:
    print("  failed steps:", failed)
