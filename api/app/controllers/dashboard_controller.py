"""仪表盘路由：每日回顾（概览统计等阶段8 补充）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.response import success
from app.db.postgres import get_session
from app.models.user_model import User
from app.services.daily_review_service import DailyReviewService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/daily-review")
async def daily_review(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """当日回顾（没有则现场生成）。"""
    data = await DailyReviewService(session).get_or_generate(user.id)
    return success(data)
