"""记忆图谱混合检索：实体向量召回 + 全文召回 → 融合 → 邻居关系遍历。

强制 user_id 过滤做数据隔离。命中实体后取其一跳关系，拼成「实体 + 关联事实」上下文。
"""
import uuid

from app.core.llm.client import LLMClient
from app.core.logging import get_logger
from app.repositories.neo4j.memory_graph_repository import MemoryGraphRepository

logger = get_logger(__name__)

# 融合权重（与知识库检索保持一致口径：向量为主，全文为辅）
_VECTOR_WEIGHT = 0.6
_FULLTEXT_WEIGHT = 0.4


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


async def search_memory(
    *,
    embed_client: LLMClient,
    user_id: uuid.UUID,
    query: str,
    top_k: int = 10,
    recall_size: int = 20,
) -> list[dict]:
    """记忆检索：返回 top_k 个相关实体，每个带其一跳关系（关联事实）。

    结果结构：{id, name, type, description, aliases, score, relations:[{predicate, object_name, source_text}]}
    """
    repo = MemoryGraphRepository()
    uid = str(user_id)

    # 1. 向量召回
    vec_hits: dict[str, dict] = {}
    vec_scores: dict[str, float] = {}
    try:
        query_vector = await embed_client.embed_one(query)
        rows = await repo.search_entities_by_vector(uid, query_vector, recall_size)
        for r in rows:
            vec_hits[r["id"]] = r
            vec_scores[r["id"]] = float(r.get("score", 0.0))
    except Exception as e:
        logger.warning("记忆向量召回失败（降级仅全文）: %s", e)

    # 2. 全文召回（cjk 分词）
    ft_hits: dict[str, dict] = {}
    ft_scores: dict[str, float] = {}
    try:
        rows = await repo.search_entities_by_fulltext(uid, query, recall_size)
        for r in rows:
            ft_hits[r["id"]] = r
            ft_scores[r["id"]] = float(r.get("score", 0.0))
    except Exception as e:
        logger.warning("记忆全文召回失败: %s", e)

    if not vec_hits and not ft_hits:
        return []

    # 3. 归一化 + 加权融合
    all_hits = {**ft_hits, **vec_hits}
    vec_n = _normalize(vec_scores)
    ft_n = _normalize(ft_scores)
    fused: dict[str, float] = {}
    for eid in all_hits:
        fused[eid] = _VECTOR_WEIGHT * vec_n.get(eid, 0.0) + _FULLTEXT_WEIGHT * ft_n.get(eid, 0.0)

    ranked = sorted(fused.items(), key=lambda x: x[1], reverse=True)[:top_k]
    top_ids = [eid for eid, _ in ranked]

    # 4. 一跳邻居关系遍历，拼上下文
    neighbor_rows = await repo.get_entity_neighbors(uid, top_ids)
    relations_by_entity: dict[str, list[dict]] = {eid: [] for eid in top_ids}
    for row in neighbor_rows:
        eid = row.get("entity_id")
        if eid in relations_by_entity and row.get("predicate"):
            relations_by_entity[eid].append({
                "predicate": row.get("predicate"),
                "object_name": row.get("object_name"),
                "object_type": row.get("object_type"),
                "source_text": row.get("source_text"),
            })

    results: list[dict] = []
    for eid, score in ranked:
        src = all_hits[eid]
        results.append({
            "id": eid,
            "name": src.get("name"),
            "type": src.get("type"),
            "description": src.get("description"),
            "aliases": src.get("aliases") or [],
            "score": round(score, 4),
            "relations": relations_by_entity.get(eid, []),
        })
    return results


def format_memory_context(results: list[dict]) -> str:
    """把检索结果拼成给 LLM 的记忆上下文文本（供问答 Agent 记忆工具复用）。"""
    if not results:
        return ""
    lines: list[str] = []
    for r in results:
        head = f"- {r['name']}（{r['type']}）：{r.get('description') or ''}".rstrip("：")
        lines.append(head)
        for rel in r.get("relations", []):
            obj = rel.get("object_name") or ""
            lines.append(f"    · {r['name']} {rel['predicate']} {obj}")
    return "\n".join(lines)


__all__ = ["search_memory", "format_memory_context"]
