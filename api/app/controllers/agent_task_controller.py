"""定时/主动任务路由：任务 CRUD + 启停 + 立即运行。"""
import uuid

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.agent_task_schema import AgentTaskUpsertRequest
from app.services.agent_task_service import AgentTaskService

router = APIRouter(prefix="/agent-tasks", tags=["agent-tasks"])


@router.get("")
async def list_tasks(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return success(await AgentTaskService(session).list_tasks(user.id))


@router.post("")
async def create_task(
    body: AgentTaskUpsertRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    task = await AgentTaskService(session).create(user.id, body)
    return success(AgentTaskService.to_dict(task), "已创建")


@router.put("/{task_id}")
async def update_task(
    task_id: uuid.UUID,
    body: AgentTaskUpsertRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    task = await AgentTaskService(session).update(user.id, task_id, body)
    return success(AgentTaskService.to_dict(task), "已保存")


@router.patch("/{task_id}/enabled")
async def set_enabled(
    task_id: uuid.UUID,
    enabled: bool = Body(..., embed=True),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    task = await AgentTaskService(session).set_enabled(user.id, task_id, enabled)
    return success(AgentTaskService.to_dict(task))


@router.post("/{task_id}/run")
async def run_now(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await AgentTaskService(session).run_now(user.id, task_id)
    return success(message="已触发运行，稍后在深度研究里查看报告")


@router.delete("/{task_id}")
async def delete_task(
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await AgentTaskService(session).delete(user.id, task_id)
    return success(message="已删除")
