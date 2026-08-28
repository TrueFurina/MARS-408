# ============================================================
# API — 管理员创建用户（/api/admin/users）— 需管理员权限
# ------------------------------------------------------------
# 缺口修复：现有注册端点 /api/auth/register 默认 role=student，
# 仅有种子 admin；没有任何通道能创建 teacher 角色账户，导致
# shared.auth.require_teacher 形同只对 admin 生效。
# 本路由是创建 teacher（及 student/admin）账户的唯一通道，
# 整路由受 require_admin 保护（管理员登录后才能调用）。
# ============================================================

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from shared.auth import require_admin
from db.user_store import create_user

logger = logging.getLogger("netlearn.admin_users_api")

# 允许创建的角色集合，须与 db/user_store.py 中 users.role 的取值一致
VALID_ROLES = ("student", "teacher", "admin")

# 整路由需 admin 权限：未携带有效 admin Token 一律 403
router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin)],
)


class CreateUserRequest(BaseModel):
    """创建用户请求体。

    role 默认 "student"，也可传 "teacher"/"admin"。
    角色合法性校验在端点内完成（非法返回 400）。
    """

    username: str
    password: str
    display_name: str = ""
    role: str = "student"


@router.post("")
async def create_user_endpoint(req: CreateUserRequest) -> dict:
    """创建用户（含 teacher 角色）；仅限 admin 调用。

    - role 非法 -> 400
    - 用户名已存在 -> 409
    - 其他参数校验失败（空用户名/密码、密码过短） -> 400
    - 成功返回用户信息（绝不返回 password_hash / salt）
    """
    # 角色合法性校验
    if req.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail="role 必须是 'student'、'teacher' 或 'admin' 之一",
        )

    try:
        user = create_user(
            username=req.username,
            password=req.password,
            display_name=req.display_name,
            role=req.role,
        )
    except ValueError as exc:
        # create_user 在用户名已存在时抛 "用户名已存在"，映射为 409
        msg = str(exc)
        if "已存在" in msg or "exist" in msg.lower():
            raise HTTPException(status_code=409, detail=msg)
        # 其余校验失败（空用户名/密码、密码过短等）映射为 400
        raise HTTPException(status_code=400, detail=msg)

    # 不返回 password_hash / salt，仅返回安全字段
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "created_at": user["created_at"],
    }


@router.get("/list")
async def list_users_endpoint(admin: dict = Depends(require_admin)) -> dict:
    """列出全部用户（精简字段：id/username/display_name/role）；仅限 admin。

    注：GET /api/admin/users 已由 api/admin.py 提供（含学习统计），
    此处提供精简版列表并置于 /list 子路径，避免与既有路由冲突。
    """
    from db.user_store import list_all_users

    users = list_all_users()
    return {
        "users": [
            {
                "id": u["id"],
                "username": u["username"],
                "display_name": u["display_name"],
                "role": u["role"],
            }
            for u in users
        ]
    }
