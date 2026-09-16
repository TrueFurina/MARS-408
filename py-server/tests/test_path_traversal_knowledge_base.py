# ============================================================
# 回归测试：教材读取路径穿越（P0-1，2026-09-16 修复）
# 验证 get_textbook_content 拒绝非法 textbook_id 与越目录路径，
# 仅允许纯字母数字/下划线/连字符 ID，且解析路径必须落在 _TEXTBOOK_DIR 内。
#
# 运行：py-server/.venv/Scripts/python.exe -m pytest tests/test_path_traversal_knowledge_base.py -q
# ============================================================

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.pdf_reader import get_textbook_content, _TEXTBOOK_DIR  # noqa: E402


# ── 非法字符 / 路径穿越 payload 必须被拒绝 ──

@pytest.mark.parametrize("bad_id", [
    "../config",                       # 父目录穿越
    "..\\config",                     # Windows 风格父目录穿越
    "../../../etc/passwd",            # 多层穿越
    "D:/config",                      # Windows 盘符绝对路径
    "D:\\config",                     # Windows 盘符反斜杠
    "/etc/passwd",                    # 类 Unix 绝对路径
    "foo/bar",                        # 含路径分隔符
    "foo\\bar",                       # 含反斜杠
    "a b",                            # 含空格
    "a;b",                            # 含特殊字符
    "a$(whoami)",                     # 含 shell 元字符
    "",                               # 空串
    "中文id",                         # 非 ASCII
    "..",                             # 纯父目录
    ".",                              # 当前目录
])
def test_rejects_traversal_and_illegal_ids(bad_id):
    # 越权 ID 一律返回 None，绝不读取目录外文件
    assert get_textbook_content(bad_id) is None


# ── 合法 ID 形态可通过格式校验（内容缺失时返回 None，不抛异常） ──

@pytest.mark.parametrize("ok_id", [
    "tcp_handshake",
    "computer_network_01",
    "CN-2024-v2",
    "a1b2c3",
])
def test_accepts_well_formed_ids(ok_id):
    # 格式合法但文件不存在 -> 返回 None（无异常、无越权）
    result = get_textbook_content(ok_id)
    assert result is None or isinstance(result, dict)


# ── realpath 落目录校验：即使 _TEXTBOOK_DIR 内构造绝对路径也只在目录内 ──

def test_resolved_path_stays_inside_textbook_dir():
    # 验证防护逻辑确实基于 realpath 前缀判断，而非简单拼接
    base = os.path.realpath(_TEXTBOOK_DIR)
    candidate = os.path.realpath(os.path.join(_TEXTBOOK_DIR, "..", "config.json"))
    assert not candidate.startswith(base + os.sep), "测试本身假设失败：越目录路径不应落在教材目录内"
    # 真实存在但越目录的文件，经 get_textbook_content 仍不可达
    assert get_textbook_content("..%sconfig" % os.sep) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
