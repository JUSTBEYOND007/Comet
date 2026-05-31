"""仪表盘统计业务服务：聚合 PG / Neo4j 计数与分布，供首页与记忆统计展示。"""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.conversation_model import Conversation
from app.models.document_model import Document
from app.models.image_model import Image
from app.models.memory_model import Memory
from app.models.tag_model import Tag, document_tags

logger = get_logger(__name__)


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _count(self, model, user_id: uuid.UUID) -> int:
        total = await self.session.scalar(
            select(func.count()).select_from(model).where(model.user_id == user_id)
        )
        return int(total or 0)

    async def _entity_community_counts(self, user_id: str) -> tuple[int, int]:
        """从 Neo4j 取实体数与社区数。失败返回 0,0。"""
        try:
            from app.repositories.neo4j.community_repository import CommunityRepository
            from app.repositories.neo4j.memory_graph_repository import (
                MemoryGraphRepository,
            )

            entity_cnt = await MemoryGraphRepository().count_entities(user_id)
            communities = await CommunityRepository().list_communities(user_id)
            return entity_cnt, len(communities)
        except Exception as e:
            logger.warning("仪表盘取图谱计数失败: %s", e)
            return 0, 0

    async def overview(self, user_id: uuid.UUID) -> dict:
        """概览统计：各类计数 + 知识库标签分布 + 最近活动。"""
        doc_cnt = await self._count(Document, user_id)
        img_cnt = await self._count(Image, user_id)
        conv_cnt = await self._count(Conversation, user_id)
        entity_cnt, community_cnt = await self._entity_community_counts(str(user_id))

        # 标签分布（文档维度，取 top 10）
        tag_rows = await self.session.execute(
            select(Tag.name, func.count(document_tags.c.document_id))
            .join(document_tags, Tag.id == document_tags.c.tag_id)
            .where(Tag.user_id == user_id)
            .group_by(Tag.name)
            .order_by(func.count(document_tags.c.document_id).desc())
            .limit(10)
        )
        tag_distribution = [{"name": n, "value": c} for n, c in tag_rows.all()]

        # 最近活动：最近 5 个文档 + 最近 5 条主动记住
        recent_docs = await self.session.execute(
            select(Document.file_name, Document.created_at)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .limit(5)
        )
        recent = [
            {"type": "document", "title": name, "time": t.isoformat() if t else None}
            for name, t in recent_docs.all()
        ]

        return {
            "counts": {
                "documents": doc_cnt,
                "images": img_cnt,
                "conversations": conv_cnt,
                "entities": entity_cnt,
                "communities": community_cnt,
            },
            "tag_distribution": tag_distribution,
            "recent": recent,
        }

    async def memory_stats(self, user_id: uuid.UUID) -> dict:
        """记忆统计：近 14 天记忆新增趋势 + 社区分布。"""
        today = datetime.now().date()
        start = today - timedelta(days=13)

        # 近 14 天每天的 memories 新增数（来源不限）
        rows = await self.session.execute(
            select(
                func.date(Memory.created_at).label("d"),
                func.count().label("cnt"),
            )
            .where(Memory.user_id == user_id, Memory.created_at >= start)
            .group_by(func.date(Memory.created_at))
        )
        day_map = {str(r.d): r.cnt for r in rows.all()}
        trend = [
            {
                "date": (start + timedelta(days=i)).isoformat(),
                "count": int(day_map.get((start + timedelta(days=i)).isoformat(), 0)),
            }
            for i in range(14)
        ]

        # 社区分布（成员数）
        community_dist: list[dict] = []
        try:
            from app.repositories.neo4j.community_repository import CommunityRepository

            communities = await CommunityRepository().list_communities(str(user_id))
            community_dist = [
                {"name": c["name"], "value": c["member_count"]} for c in communities[:10]
            ]
        except Exception as e:
            logger.warning("仪表盘取社区分布失败: %s", e)

        return {"trend": trend, "community_distribution": community_dist}


__all__ = ["DashboardService"]
