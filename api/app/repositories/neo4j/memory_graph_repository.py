"""记忆图谱仓储：封装 Neo4j 的节点/边写入与检索。

写入用单写事务批量 MERGE，保证一次萃取的图数据原子落库、幂等可重试。
只做数据存取，业务编排在 service / 萃取流水线里完成。
"""
from datetime import datetime
from typing import Any

from app.core.memory.graph_models import (
    ChunkNode,
    DialogueNode,
    EntityNode,
    EventNode,
    InvolvesEdge,
    MentionEdge,
    RelationEdge,
    StatementNode,
)
from app.core.logging import get_logger
from app.db.neo4j import get_driver
from app.repositories.neo4j import cypher_queries as cq

logger = get_logger(__name__)


def _dt(value: datetime | None) -> str | None:
    """datetime → ISO 字符串（Neo4j 存字符串，避免时区/驱动类型差异）。"""
    return value.isoformat() if isinstance(value, datetime) else value


class MemoryGraphRepository:
    """记忆图谱数据访问层。"""

    def __init__(self):
        self._driver = get_driver()

    # ── 序列化：节点/边 → Cypher 参数行 ──

    @staticmethod
    def _dialogue_row(n: DialogueNode) -> dict[str, Any]:
        return {
            "id": n.id,
            "user_id": n.user_id,
            "content": n.content,
            "source": n.source,
            "source_message_id": n.source_message_id,
            "dialog_at": _dt(n.dialog_at),
            "created_at": _dt(n.created_at),
        }

    @staticmethod
    def _chunk_row(n: ChunkNode) -> dict[str, Any]:
        return {
            "id": n.id,
            "user_id": n.user_id,
            "dialog_id": n.dialog_id,
            "content": n.content,
            "speaker": n.speaker,
            "sequence": n.sequence,
            "created_at": _dt(n.created_at),
        }

    @staticmethod
    def _statement_row(n: StatementNode) -> dict[str, Any]:
        return {
            "id": n.id,
            "user_id": n.user_id,
            "chunk_id": n.chunk_id,
            "statement": n.statement,
            "stmt_type": n.stmt_type,
            "temporal_type": n.temporal_type,
            "speaker": n.speaker,
            "valid_at": _dt(n.valid_at),
            "invalid_at": _dt(n.invalid_at),
            "dialog_at": _dt(n.dialog_at),
            "embedding": n.embedding,
            "created_at": _dt(n.created_at),
        }

    @staticmethod
    def _entity_row(n: EntityNode) -> dict[str, Any]:
        return {
            "id": n.id,
            "user_id": n.user_id,
            "name": n.name,
            "type": n.type,
            "description": n.description,
            "aliases": n.aliases,
            "name_embedding": n.name_embedding,
            "community_id": n.community_id,
            "created_at": _dt(n.created_at),
        }

    @staticmethod
    def _event_row(n: EventNode) -> dict[str, Any]:
        return {
            "id": n.id,
            "user_id": n.user_id,
            "title": n.title,
            "description": n.description,
            "event_time": _dt(n.event_time),
            "embedding": n.embedding,
            "created_at": _dt(n.created_at),
        }

    @staticmethod
    def _mention_row(e: MentionEdge) -> dict[str, Any]:
        return {
            "user_id": e.user_id,
            "statement_id": e.statement_id,
            "entity_id": e.entity_id,
            "connect_strength": e.connect_strength,
            "created_at": _dt(e.created_at),
        }

    @staticmethod
    def _relation_row(e: RelationEdge) -> dict[str, Any]:
        return {
            "id": e.id,
            "user_id": e.user_id,
            "source_id": e.source_id,
            "target_id": e.target_id,
            "predicate": e.predicate,
            "predicate_surface": e.predicate_surface,
            "source_text": e.source_text,
            "statement_id": e.statement_id,
            "value": e.value,
            "valid_at": _dt(e.valid_at),
            "invalid_at": _dt(e.invalid_at),
            "created_at": _dt(e.created_at),
        }

    @staticmethod
    def _involves_row(e: InvolvesEdge) -> dict[str, Any]:
        return {
            "user_id": e.user_id,
            "event_id": e.event_id,
            "entity_id": e.entity_id,
            "role": e.role,
            "created_at": _dt(e.created_at),
        }

    # ── 批量写入：一次萃取的全部图数据，单写事务原子落库 ──

    async def save_graph(
        self,
        *,
        dialogues: list[DialogueNode],
        chunks: list[ChunkNode],
        statements: list[StatementNode],
        entities: list[EntityNode],
        events: list[EventNode],
        mentions: list[MentionEdge],
        relations: list[RelationEdge],
        involves: list[InvolvesEdge],
    ) -> None:
        """按依赖顺序在单事务内写入：节点先于其关系。"""

        async def _txn(tx):
            if dialogues:
                await tx.run(cq.DIALOGUE_SAVE, rows=[self._dialogue_row(n) for n in dialogues])
            if chunks:
                await tx.run(cq.CHUNK_SAVE, rows=[self._chunk_row(n) for n in chunks])
            if statements:
                await tx.run(cq.STATEMENT_SAVE, rows=[self._statement_row(n) for n in statements])
            if entities:
                await tx.run(cq.ENTITY_SAVE, rows=[self._entity_row(n) for n in entities])
            if events:
                await tx.run(cq.EVENT_SAVE, rows=[self._event_row(n) for n in events])
            if mentions:
                await tx.run(cq.MENTION_SAVE, rows=[self._mention_row(e) for e in mentions])
            if relations:
                await tx.run(cq.RELATION_SAVE, rows=[self._relation_row(e) for e in relations])
            if involves:
                await tx.run(cq.INVOLVES_SAVE, rows=[self._involves_row(e) for e in involves])

        async with self._driver.session() as session:
            await session.execute_write(_txn)
        logger.info(
            "记忆图谱写入: dialogue=%d chunk=%d statement=%d entity=%d event=%d "
            "mention=%d relation=%d involves=%d",
            len(dialogues), len(chunks), len(statements), len(entities),
            len(events), len(mentions), len(relations), len(involves),
        )

    # ── 去重支持：取用户已有同类实体 ──

    async def list_entities_by_type(self, user_id: str, type_: str) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(
                cq.ENTITY_LIST_BY_TYPE, user_id=user_id, type=type_
            )
            return [dict(record) async for record in result]

    async def get_entity_by_name(self, user_id: str, name: str) -> dict[str, Any] | None:
        async with self._driver.session() as session:
            result = await session.run(
                cq.ENTITY_GET_BY_NAME, user_id=user_id, name=name
            )
            record = await result.single()
            return dict(record) if record else None

    # ── 检索：向量 / 全文 / 邻居遍历 ──

    async def search_entities_by_vector(
        self, user_id: str, vector: list[float], top_k: int
    ) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(
                cq.ENTITY_VECTOR_SEARCH, user_id=user_id, vector=vector, top_k=top_k
            )
            return [dict(record) async for record in result]

    async def search_entities_by_fulltext(
        self, user_id: str, query: str, top_k: int
    ) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(
                cq.ENTITY_FULLTEXT_SEARCH, user_id=user_id, query=query, top_k=top_k
            )
            return [dict(record) async for record in result]

    async def get_entity_neighbors(
        self, user_id: str, entity_ids: list[str]
    ) -> list[dict[str, Any]]:
        async with self._driver.session() as session:
            result = await session.run(
                cq.ENTITY_NEIGHBORS, user_id=user_id, entity_ids=entity_ids
            )
            return [dict(record) async for record in result]

    async def count_entities(self, user_id: str) -> int:
        async with self._driver.session() as session:
            result = await session.run(cq.ENTITY_COUNT, user_id=user_id)
            record = await result.single()
            return record["cnt"] if record else 0

    async def list_all_entities(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户全部实体（含一跳出边关系），供画像视图。"""
        async with self._driver.session() as session:
            result = await session.run(cq.ENTITY_LIST_ALL, user_id=user_id)
            return [dict(record) async for record in result]

    async def entity_type_counts(self, user_id: str) -> list[dict[str, Any]]:
        """每种实体类型的数量。"""
        async with self._driver.session() as session:
            result = await session.run(cq.ENTITY_TYPE_COUNTS, user_id=user_id)
            return [dict(record) async for record in result]

    async def delete_entity(self, user_id: str, entity_id: str) -> None:
        """删除单个实体（连带其关系）。"""
        async with self._driver.session() as session:
            await session.run(cq.DELETE_ENTITY, user_id=user_id, entity_id=entity_id)

    async def delete_user_graph(self, user_id: str) -> None:
        """删除某用户的全部图数据（数据隔离 / 重置用）。"""
        async with self._driver.session() as session:
            await session.run(cq.DELETE_USER_GRAPH, user_id=user_id)
