"""知识库文档路由：上传/网页导入/列表/详情/状态/重试/删除/检索。"""
import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.schemas.document_schema import SearchRequest, UrlImportRequest
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["document"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    content = await file.read()
    service = DocumentService(session)
    doc = await service.upload(user.id, file.filename or "未命名", content)
    return success(await service.to_out_dict(doc), "上传成功，正在解析")


@router.post("/from-url")
async def import_from_url(
    body: UrlImportRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = DocumentService(session)
    doc = await service.import_url(user.id, body.url)
    return success(await service.to_out_dict(doc), "导入成功，正在解析")


@router.get("")
async def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = DocumentService(session)
    docs, total = await service.list_documents(user.id, page, page_size)
    items = [await service.to_out_dict(d) for d in docs]
    return success(
        {"total": total, "page": page, "page_size": page_size, "items": items}
    )


@router.get("/{doc_id}")
async def get_document(
    doc_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = DocumentService(session)
    doc = await service.get_detail(user.id, doc_id)
    return success(await service.to_out_dict(doc))


@router.get("/{doc_id}/status")
async def get_status(
    doc_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = DocumentService(session)
    doc = await service.get_detail(user.id, doc_id)
    return success(
        {"status": doc.status, "progress": doc.progress, "error_msg": doc.error_msg}
    )


@router.post("/{doc_id}/retry")
async def retry_document(
    doc_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    service = DocumentService(session)
    doc = await service.retry(user.id, doc_id)
    return success(await service.to_out_dict(doc), "已重新提交解析")


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await DocumentService(session).delete(user.id, doc_id)
    return success(message="删除成功")


@router.post("/search")
async def search_documents(
    body: SearchRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    hits = await DocumentService(session).search(
        user.id, body.query, body.top_k, body.tags
    )
    return success(hits)
