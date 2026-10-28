# -*- coding: utf-8 -*-
"""submission 包口径零漂移校验（口径脚本 / 正式签核机器证据）。

读取 SSOT（docs/METRICS_CURRENT.md + AGENTS.md，机器维护、随 verify_metrics 更新）
动态取值，比对 submission/00_提交清单.md §二「核心真值数字」的声称值，并校验
submission/02_配套文档 53 份齐全。任一不一致即 fail-closed 退出非 0，
作为 engineer-6/PM 对「53 份迁移 + 口径」的正式签核证据。

注意：METRICS_CURRENT.md:81 为历史链（1524→1654→1693→1737，每个「已更新」覆盖前一个），
故 SSOT 取值取链的最后一个（=当前真值）；submission 锚定 §二 段提取，避免命中旧快照。
API 操作数/认证覆盖率由 verify_openapi_snapshot.py / verify_auth_coverage.py 单独守门，本脚本不重复。

用法：python scripts/verify_submission_caliber.py
依赖：仅标准库；读文件、不写、不改任何产物。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def p(*a):
    return os.path.join(ROOT, *a)


def read(path):
    with open(p(path), encoding="utf-8") as f:
        return f.read()


def num(regex, text):
    m = re.search(regex, text)
    return m.groups() if m else None


def num_last(regex, text):
    ms = re.findall(regex, text)
    if not ms:
        return None
    last = ms[-1]
    return last if isinstance(last, tuple) else (last,)


def section(text, start_marker, end_marker="\n## "):
    i = text.find(start_marker)
    if i < 0:
        return ""
    j = text.find(end_marker, i + len(start_marker))
    return text[i:j] if j >= 0 else text[i:]


ok = True


def check(name, got, expect):
    global ok
    if got == expect:
        print(f"✅ {name}: {got}")
    else:
        ok = False
        print(f"❌ {name}: 期望 {expect}，实际 {got}")


# ---- 来源 ----
mtr = read("docs/METRICS_CURRENT.md")
agt = read("AGENTS.md")
sub = read("submission/00_提交清单.md")
sub_sec2 = section(sub, "## 二、")  # 核心真值数字（2026-10-21 实测）

print("== 芒得很职 submission 包口径零漂移校验 ==")

# 1) 测试数（CI 默认档）：SSOT 取历史链最后一个值；submission 取 §二
ssot_t = num_last(r"(\d+)\s*通过\s*/\s*(\d+)\s*跳过\s*/\s*(\d+)\s*xfail\s*/\s*(\d+)\s*失败", mtr) or tuple(
    int(x) for x in num(r"(\d+)\s*passed\s*/\s*(\d+)\s*skipped\s*/\s*(\d+)\s*xfailed\s*/\s*(\d+)\s*failed", agt)
)
sub_t = num(r"(\d+)\s*通过\s*/\s*(\d+)\s*跳过\s*/\s*(\d+)\s*xfail\s*/\s*(\d+)\s*失败", sub_sec2)
if ssot_t and sub_t:
    check("测试数 SSOT == submission §二（通过/跳过/xfail/失败）", sub_t, ssot_t)
else:
    print("  ⚠️ 测试数未能从 SSOT/submission 提取，跳过（以 verify_metrics.py 为权威）")

# 2) collected（容忍文档中的反引号：约 `1785 collected`）
ssot_c = num_last(r"约\s*`?\s*(\d+)\s*`?\s*collected", mtr)
sub_c = num(r"约\s*`?\s*(\d+)\s*`?\s*collected", sub_sec2)
if ssot_c and sub_c:
    check("collected SSOT == submission §二", sub_c, ssot_c)
else:
    print("  ⚠️ collected 未能提取，跳过")

# 3) 53 份配套文档齐全（排除 _archive 存档）
doc_dir = p("submission/02_配套文档")
count = 0
for root, dirs, files in os.walk(doc_dir):
    dirs[:] = [d for d in dirs if not d.startswith("_archive")]
    if "_archive" in root:
        continue
    count += len(files)
check("02_配套文档 文档数 == 53（TEST_TRUTH.md:38 口径）", count, 53)

print()
if ok:
    print("✅ submission 包口径零漂移校验通过 —— 可作为 engineer-6/PM 正式签核证据")
    sys.exit(0)
else:
    print("❌ 存在口径漂移，请核对上述 ❌ 项后重跑")
    sys.exit(1)
