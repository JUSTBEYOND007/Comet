"""标签数据访问层。"""
import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tag_model import Tag, document_tags


class TagRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, user_id: uuid.UUID, name: str) -> Tag:
        stmt = select(Tag).where(Tag.user_id == user_id, Tag.name == name)
        tag = (await self.session.execute(stmt)).scalar_one_or_none()
        if tag:
            return tag
        tag = Tag(user_id=user_id, name=name)
        self.session.add(tag)
        await self.session.commit()
        await self.session.refresh(tag)
        return tag

    async def list_by_user(self, user_id: uuid.UUID) -> list[Tag]:
        stmt = select(Tag).where(Tag.user_id == user_id).order_by(Tag.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get(self, user_id: uuid.UUID, tag_id: uuid.UUID) -> Tag | None:
        stmt = select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def count_documents(self, tag_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(document_tags.c.tag_id == tag_id)
        return int(await self.session.scalar(stmt) or 0)

    async def set_document_tags(
        self, document_id: uuid.UUID, tag_ids: list[uuid.UUID]
    ) -> None:
        await self.session.execute(
            delete(document_tags).where(document_tags.c.document_id == document_id)
        )
        for tid in tag_ids:
            await self.session.execute(
                document_tags.insert().values(document_id=document_id, tag_id=tid)
            )
        await self.session.commit()

    async def get_document_tag_names(self, document_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Tag.name)
            .join(document_tags, Tag.id == document_tags.c.tag_id)
            .where(document_tags.c.document_id == document_id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def save(self, tag: Tag) -> Tag:
        await self.session.commit()
        await self.session.refresh(tag)
        return tag

    async def delete_tag(self, tag: Tag) -> None:
        await self.session.delete(tag)
        await self.session.commit()
