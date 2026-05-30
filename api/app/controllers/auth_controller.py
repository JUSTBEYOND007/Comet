"""鉴权路由：注册 / 登录 / 刷新 / 退出 / 当前用户 / 改密。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.auth_schema import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    user = await AuthService(session).register(body.username, body.password)
    return success(UserOut.model_validate(user).model_dump(mode="json"), "注册成功")


@router.post("/login")
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    service = AuthService(session)
    user = await service.authenticate(body.username, body.password)
    access, refresh = service.issue_tokens(user)
    return success(
        TokenPair(access_token=access, refresh_token=refresh).model_dump(), "登录成功"
    )


@router.post("/refresh")
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    access, refresh_token = await AuthService(session).refresh(body.refresh_token)
    return success(
        TokenPair(access_token=access, refresh_token=refresh_token).model_dump()
    )


@router.post("/logout")
async def logout(_: User = Depends(get_current_user)):
    # 无状态 JWT：登出由前端清除 token 实现，这里仅作语义端点
    return success(message="已退出登录")


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return success(UserOut.model_validate(user).model_dump(mode="json"))


@router.put("/password")
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await AuthService(session).change_password(
        user, body.old_password, body.new_password
    )
    return success(message="密码修改成功")
