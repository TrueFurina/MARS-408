# ============================================================
# 诚实口径扫描器（honesty_scan）红线拦截单元测试
#
# 覆盖：
#   - 归一化变体（下降了/下降了/约/开销/提升了 等）
#   - 跨行拆分（红线被换行切断）
#   - 正常文案不误报
#   - 归档/记忆/规则目录豁免（红线作为「已证伪记录」被引用不判违规）
#
# 无网络 / 无 git 依赖，纯正则。本文件已被 honesty_scan 的
# _REDLINE_SKIP_FILES 豁免（故意以红线字符串作为测试夹具）。
# ============================================================

import sys
from pathlib import Path

import pytest

# honesty_scan.py 在仓库根 scripts/pre-commit/ 下，加入路径后导入
_SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "pre-commit"
sys.path.insert(0, str(_SCRIPT_DIR))

import honesty_scan  # noqa: E402


# ────────────────────────────────────────────────────────────
# 红线变体必须被拦截
# ────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("text,label", [
    ("检索成本降低45%", "canonical"),
    ("检索成本降低了45%", "了变体"),
    ("检索成本下降了45%", "下降变体"),
    ("检索成本约降45%", "约变体"),
    ("检索成本降低 45%", "空格"),
    ("检索开销降低45%", "开销变体"),
    ("成本降低45%", "成本变体"),
    ("GOMARL提升了15%", "提升了变体"),
    ("GOMARL升15%", "GOMARL原样"),
    ("仅需500条标注样本", "500条"),
    ("检索成本\n降低45%", "跨行拆分"),
])
def test_redline_caught(text, label):
    hits = honesty_scan.scan_text(text, "demo.vue")
    assert hits, f"红线变体未被拦截: {label} -> {text!r}"


# ────────────────────────────────────────────────────────────
# 正常文案不得误报
# ────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "我们做了成本优化工作",
    "检索成本是一个重要指标",
    "GOMARL 是一种多智能体架构",
    "本次检索成本上升明显",  # 上升非「降」，且未带 45%
])
def test_no_false_positive(text):
    hits = honesty_scan.scan_text(text, "demo.vue")
    assert hits == [], f"正常文案被误报: {text!r} -> {hits}"


# ────────────────────────────────────────────────────────────
# 豁免目录：红线作为「已证伪记录」被引用，不应判违规
# ────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_archive_dir_exempt():
    hits = honesty_scan.scan_text("已把「检索成本降低45%」列为禁止项", "deliverables/x.md")
    assert hits == []


@pytest.mark.unit
def test_workbuddy_dir_exempt():
    hits = honesty_scan.scan_text("红线「成本降低45%」已在审计中记录", ".workbuddy/memory/foo.md")
    assert hits == []


@pytest.mark.unit
def test_precommit_dir_exempt():
    # 规则定义目录自身承载红线正则字面量，豁免
    hits = honesty_scan.scan_text("检索成本降低45%", "scripts/pre-commit/honesty_scan.py")
    assert hits == []
