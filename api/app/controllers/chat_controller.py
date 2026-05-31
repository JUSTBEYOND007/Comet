"""对话路由：会话 CRUD + SSE 流式问答。"""
import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.core.storage import build_file_key, get_storage
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.chat_schema import (
    ChatStreamRequest,
    ConversationCreateRequest,
    ConversationRenameRequest,
)
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService

router = APIRouter(tags=["chat"])


# ── 会话管理 ──

@router.get("/conversations")
async def list_conversations(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ConversationService(session)
    items = await service.list_conversations(user.id)
    return success([service.to_out_dict(c) for c in items])


@router.post("/conversations")
async def create_conversation(
    body: ConversationCreateRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ConversationService(session)
    conv = await service.create(user.id, body.title)
    return success(service.to_out_dict(conv), "已创建")


@router.put("/conversations/{conv_id}")
async def rename_conversation(
    conv_id: uuid.UUID,
    body: ConversationRenameRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ConversationService(session)
    conv = await service.rename(user.id, conv_id, body.title)
    return success(service.to_out_dict(conv))


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await ConversationService(session).delete(user.id, conv_id)
    return success(message="删除成功")


@router.get("/conversations/{conv_id}/messages")
async def list_messages(
    conv_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ConversationService(session)
    return success(await service.list_messages(user.id, conv_id))


# ── 流式问答 ──

@router.post("/chat/stream")
async def chat_stream(
    body: ChatStreamRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = ChatService(session)
    return StreamingResponse(
        service.stream_chat(user.id, body),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/upload-image")
async def upload_chat_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """对话多模态：上传图片，返回 file_key（随消息一起发）与可访问 url。"""
    import uuid as _uuid
    from pathlib import Path

    content = await file.read()
    ext = Path(file.filename or "img.jpg").suffix.lower() or ".jpg"
    file_key = build_file_key(str(user.id), "chat", str(_uuid.uuid4()), ext)
    storage = get_storage()
    await storage.save(file_key, content)
    return success({"file_key": file_key, "url": storage.get_url(file_key)})
