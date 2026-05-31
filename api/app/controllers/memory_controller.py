"""记忆路由：主动记住 / 列表 / 详情 / 删除。

检索接口在第③步随记忆检索一起加入。
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.memory_schema import MemorySearchRequest, RememberRequest
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["memory"])


@router.post("/remember")
async def remember(
    body: RememberRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MemoryService(session)
    memory = await service.remember(user.id, body.text)
    return success(service.to_out_dict(memory), "已提交，正在萃取记忆")


@router.post("/search")
async def search_memory(
    body: MemorySearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    hits = await MemoryService(session).search(user.id, body.query, body.top_k)
    return success(hits)


@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """画像视图：系统记住的实体（按类型分组）+ 类型计数。"""
    data = await MemoryService(session).get_profile(user.id)
    return success(data)


@router.delete("/entity/{entity_id}")
async def delete_entity(
    entity_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """删除单个记忆实体（连带其关系）。"""
    await MemoryService(session).delete_entity(user.id, entity_id)
    return success(message="删除成功")


@router.get("")
async def list_memories(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MemoryService(session)
    items, total = await service.list_memories(user.id, page, page_size)
    return success(
        {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [service.to_out_dict(m) for m in items],
        }
    )


@router.get("/{memory_id}")
async def get_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = MemoryService(session)
    memory = await service.get_detail(user.id, memory_id)
    return success(service.to_out_dict(memory))


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await MemoryService(session).delete(user.id, memory_id)
    return success(message="删除成功")
