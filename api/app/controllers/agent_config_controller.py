"""Agent 配置路由：获取 / 更新用户的 Agent 个性化配置。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.agent_config_schema import AgentConfigUpdate
from app.services.agent_config_service import AgentConfigService

router = APIRouter(prefix="/agent-config", tags=["agent"])


@router.get("")
async def get_agent_config(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = AgentConfigService(session)
    config = await service.get_or_create(user.id)
    return success(service.to_out_dict(config))


@router.put("")
async def update_agent_config(
    body: AgentConfigUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = AgentConfigService(session)
    config = await service.update(user.id, body)
    return success(service.to_out_dict(config), "已保存")
