"""每日回顾业务服务：汇总当日新增对话/记忆/文档，LLM 生成简报。

双触发：用户打开仪表盘时按需生成（当天没有则现生成）；Celery beat 每日定时批量生成。
"""
import uuid
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.conversation_model import ROLE_USER, Conversation, Message
from app.models.daily_review_model import DailyReview
from app.models.document_model import Document
from app.models.memory_model import MEMORY_SOURCE_MANUAL, Memory

logger = get_logger(__name__)

_PROMPT = """你是用户的个人助理。请根据下面今天的活动数据，用中文写一段简短的「今日回顾」，
像朋友一样自然、温暖，2-4 句话，可用 Markdown。不要罗列数字，要提炼今天聊了什么、记住了什么、学了什么。

今日数据：
- 新对话消息（用户提问）：{messages}
- 新记住的内容：{memories}
- 新增文档：{documents}

如果今天几乎没有活动，就回应一句轻松的鼓励。"""


class DailyReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _day_range(self, day: date) -> tuple[datetime, datetime]:
        start = datetime.combine(day, time.min)
        end = datetime.combine(day, time.max)
        return start, end

    async def _collect(self, user_id: uuid.UUID, day: date) -> dict:
        """收集当日新增的对话提问 / 主动记住 / 文档。"""
        start, end = await self._day_range(day)

        # 用户提问消息（关联本人会话）
        msg_rows = await self.session.execute(
            select(Message.content)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(
                Conversation.user_id == user_id,
                Message.role == ROLE_USER,
                Message.created_at >= start,
                Message.created_at <= end,
            )
            .limit(30)
        )
        messages = [r[0] for r in msg_rows.all()]

        mem_rows = await self.session.execute(
            select(Memory.raw_text).where(
                Memory.user_id == user_id,
                Memory.source == MEMORY_SOURCE_MANUAL,
                Memory.created_at >= start,
                Memory.created_at <= end,
            )
        )
        memories = [r[0] for r in mem_rows.all()]

        doc_rows = await self.session.execute(
            select(Document.file_name).where(
                Document.user_id == user_id,
                Document.created_at >= start,
                Document.created_at <= end,
            )
        )
        documents = [r[0] for r in doc_rows.all()]

        return {"messages": messages, "memories": memories, "documents": documents}

    async def _generate_content(
        self, user_id: uuid.UUID, data: dict
    ) -> str:
        """调用对话模型生成简报；无模型或失败则用规则兜底。"""
        from app.core.llm.resolver import get_optional_client_for_type

        total = len(data["messages"]) + len(data["memories"]) + len(data["documents"])
        if total == 0:
            return "今天还没有新动态，休息一下也很好 🌿"

        client = await get_optional_client_for_type(self.session, user_id, "chat")
        if not client:
            return (
                f"今天有 {len(data['messages'])} 次提问、"
                f"记住了 {len(data['memories'])} 件事、"
                f"新增了 {len(data['documents'])} 份文档。"
            )
        prompt = _PROMPT.format(
            messages="；".join(data["messages"][:20]) or "（无）",
            memories="；".join(data["memories"]) or "（无）",
            documents="、".join(data["documents"]) or "（无）",
        )
        try:
            return await client.chat(
                [{"role": "user", "content": prompt}], temperature=0.6, max_tokens=400
            )
        except Exception as e:
            logger.warning("每日回顾生成失败，用兜底文案: %s", e)
            return (
                f"今天有 {len(data['messages'])} 次提问、"
                f"记住了 {len(data['memories'])} 件事、"
                f"新增了 {len(data['documents'])} 份文档。"
            )

    async def get_or_generate(self, user_id: uuid.UUID, day: date | None = None) -> dict:
        """取当天回顾，没有则现场生成并落库。"""
        day = day or date.today()
        existing = await self.session.scalar(
            select(DailyReview).where(
                DailyReview.user_id == user_id, DailyReview.review_date == day
            )
        )
        if existing:
            return self.to_out_dict(existing)

        data = await self._collect(user_id, day)
        content = await self._generate_content(user_id, data)
        stats = {
            "messages": len(data["messages"]),
            "memories": len(data["memories"]),
            "documents": len(data["documents"]),
        }
        review = DailyReview(
            user_id=user_id, review_date=day, content=content, stats=stats
        )
        self.session.add(review)
        await self.session.commit()
        await self.session.refresh(review)
        return self.to_out_dict(review)

    @staticmethod
    def to_out_dict(review: DailyReview) -> dict:
        return {
            "date": review.review_date.isoformat(),
            "content": review.content,
            "stats": review.stats,
            "created_at": review.created_at.isoformat() if review.created_at else None,
        }


__all__ = ["DailyReviewService"]
