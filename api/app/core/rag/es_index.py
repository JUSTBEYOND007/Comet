"""Elasticsearch 索引定义与初始化。

统一索引 comet_chunks（个人版数据量小，单索引 + user_id 过滤足够）。
向量维度固定 1024（通义 text-embedding-v3）。
"""
from app.config import settings
from app.core.logging import get_logger
from app.db.elastic import get_es

logger = get_logger(__name__)

CHUNKS_INDEX = "comet_chunks"
VECTOR_DIMS = settings.embedding_dims

# 父子分块：child 用于向量召回，parent 提供更大上下文
CHUNK_TYPE_CHILD = "child"
CHUNK_TYPE_PARENT = "parent"
CHUNK_TYPE_IMAGE = "image_desc"

_MAPPING = {
    "mappings": {
        "properties": {
            "user_id": {"type": "keyword"},
            "source_type": {"type": "keyword"},  # document | image
            "source_id": {"type": "keyword"},  # documents.id / images.id
            "doc_name": {"type": "keyword"},
            "chunk_id": {"type": "keyword"},
            "chunk_type": {"type": "keyword"},  # child | parent | image_desc
            "parent_id": {"type": "keyword"},  # child 指向其 parent chunk_id
            # content 用 IK 中文分词：写入 ik_max_word（细粒度），查询 ik_smart（粗粒度）
            "content": {
                "type": "text",
                "analyzer": "ik_max_word",
                "search_analyzer": "ik_smart",
            },
            "tags": {"type": "keyword"},
            "vector": {
                "type": "dense_vector",
                "dims": VECTOR_DIMS,
                "index": True,
                "similarity": "cosine",
            },
            "created_at": {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}


async def ensure_index() -> None:
    """确保 comet_chunks 索引存在，不存在则创建。应用启动时调用。"""
    es = get_es()
    exists = await es.indices.exists(index=CHUNKS_INDEX)
    if not exists:
        await es.indices.create(index=CHUNKS_INDEX, body=_MAPPING)
        logger.info("创建 ES 索引: %s", CHUNKS_INDEX)
    else:
        logger.info("ES 索引已存在: %s", CHUNKS_INDEX)


__all__ = [
    "CHUNKS_INDEX",
    "VECTOR_DIMS",
    "CHUNK_TYPE_CHILD",
    "CHUNK_TYPE_PARENT",
    "CHUNK_TYPE_IMAGE",
    "ensure_index",
]
