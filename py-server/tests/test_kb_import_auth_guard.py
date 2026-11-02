# -*- coding: utf-8 -*-
"""知识库导入端点的权限结构守卫（2026-11-02 安全审计）。

背景：`POST /api/knowledge-base/import-pdf` 会把上传的 PDF 解析后写入**全站共享**
知识库，属共享写操作。审计发现它此前只要求登录（`get_current_user`），
⇒ 任意学生都能往共享库里写东西。已改为 `require_teacher`。

本测试用 AST 直接断言依赖项，不启动 FastAPI app（快、无 DB/网络依赖）。
变异检验：把实现改回 `get_current_user` → 本测试必须红。
"""
import ast
from pathlib import Path

KB_API = Path(__file__).resolve().parents[1] / "api" / "knowledge_base.py"


def _depends_names(func: ast.AST) -> list[str]:
    """收集函数参数默认值里 `Depends(<Name|Attr>)` 的被依赖名。"""
    out: list[str] = []
    defaults = list(func.args.defaults) + [d for d in func.args.kw_defaults if d is not None]
    for d in defaults:
        if not isinstance(d, ast.Call):
            continue
        if getattr(d.func, "id", None) != "Depends" or not d.args:
            continue
        arg = d.args[0]
        name = getattr(arg, "id", None) or getattr(arg, "attr", None)
        if name:
            out.append(name)
    return out


def _find_async_func(tree: ast.AST, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"未找到 async def {name}")


def test_import_pdf_uses_require_teacher():
    tree = ast.parse(KB_API.read_text(encoding="utf-8"))
    fn = _find_async_func(tree, "api_import_pdf")
    deps = _depends_names(fn)
    assert "require_teacher" in deps, (
        "import-pdf 写入共享知识库，必须要求教师/管理员权限；"
        f"实际依赖={deps}"
    )


def test_import_pdf_no_longer_accepts_plain_login():
    """反向断言：不得退回 get_current_user（防止有人「简化」回越权状态）。"""
    tree = ast.parse(KB_API.read_text(encoding="utf-8"))
    fn = _find_async_func(tree, "api_import_pdf")
    deps = _depends_names(fn)
    assert "get_current_user" not in deps, (
        "import-pdf 不得只要求登录（共享写必须 require_teacher）；"
        f"实际依赖={deps}"
    )
