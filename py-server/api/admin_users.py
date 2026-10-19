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
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.auth import require_admin
from shared.audit import log_event
# 走模块对象（属性访问时解析）而非静态 from-import：
# db.user_store 存在 PEP 562 动态转发，静态绑定会让后续 monkeypatch 静默失效
from db import user_store
from services.user_service import create_user

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


def _client_ip(request: Request) -> str:
    """取客户端 IP（沿用 api/config_routes.py 的写法，unknown 兜底不抛异常）"""
    return request.client.host if request and request.client else "unknown"


@router.delete("/{username}")
async def delete_user_endpoint(username: str, request: Request,
                              admin: dict = Depends(require_admin)) -> dict:
    """删除用户及其全部关联数据（级联）；仅限 admin，且禁止删除自己。

    为什么现在才加：此前评估「造删除端点」收益为零风险不为零，
    判断前提是「没有需要删的对象」。该前提已不成立——权限矩阵
    探测时误用写端点，在线上留下了垃圾账号（其中一个是 role=admin
    的弱密码探测账号，本身就是安全面扩大），而当时没有任何通道
    能移除它、也没有改密通道能先废掉它。

    护栏（缺一不可）：
      1. 整路由 require_admin（与其他 admin 端点同口径）；
      2. 禁止删除调用者自己——否则管理员一次手滑就锁死整站；
      3. 不存在则 404（不静默成功，避免误以为删掉了）。
    """
    target = (username or "").strip()
    if not target:
        raise HTTPException(status_code=400, detail="username 不能为空")

    # ⚠️ 契约：get_current_user 只产出 {"user_id", "role"}，**不含 username**
    #（shared/auth.py:134）。所以「禁止删自己」必须落到 user_id 上比较——
    # 若照直觉写 admin.get("username") == target，恒为 None == target ⇒ False，
    # 护栏永远不触发，管理员一次手滑就能把自己删掉、锁死整站。
    actor_id = str(admin.get("user_id", ""))
    victim = user_store.get_user_by_username(target)
    if victim and str(victim.get("id", "")) == actor_id:
        log_event("admin_delete_user", user_id=actor_id, ip=_client_ip(request),
                  result="blocked", detail=f"拒绝自删除 username={target}")
        raise HTTPException(status_code=403, detail="不能删除当前登录的管理员自己")

    if not user_store.delete_user(target):
        log_event("admin_delete_user", user_id=actor_id, ip=_client_ip(request),
                  result="failure", detail=f"username={target} 不存在")
        raise HTTPException(status_code=404, detail="用户不存在")

    log_event("admin_delete_user", user_id=actor_id, ip=_client_ip(request),
              result="success", detail=f"username={target}")
    return {"deleted": True, "username": target}


@router.get("/list")
async def list_users_endpoint(admin: dict = Depends(require_admin)) -> dict:
    """列出全部用户（精简字段：id/username/display_name/role）；仅限 admin。

    注：GET /api/admin/users 已由 api/admin.py 提供（含学习统计），
    此处提供精简版列表并置于 /list 子路径，避免与既有路由冲突。
    """
    from services.user_service import list_all_users

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
