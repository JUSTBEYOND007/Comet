"""记忆图谱的 Cypher 语句集中管理。

写入统一用 UNWIND $rows + MERGE 批量幂等；按 id 业务键 MERGE，重复写入只更新属性。
节点标签与关系类型直接内联（Cypher 不支持参数化标签），值通过参数传入防注入。
"""

# ── 节点批量写入（MERGE by id，幂等） ──

DIALOGUE_SAVE = """
UNWIND $rows AS row
MERGE (n:Dialogue {id: row.id})
SET n.user_id = row.user_id,
    n.content = row.content,
    n.source = row.source,
    n.source_message_id = row.source_message_id,
    n.dialog_at = row.dialog_at,
    n.created_at = row.created_at
RETURN count(n) AS cnt
"""

CHUNK_SAVE = """
UNWIND $rows AS row
MERGE (n:Chunk {id: row.id})
SET n.user_id = row.user_id,
    n.dialog_id = row.dialog_id,
    n.content = row.content,
    n.speaker = row.speaker,
    n.sequence = row.sequence,
    n.created_at = row.created_at
WITH n, row
MATCH (d:Dialogue {id: row.dialog_id})
MERGE (d)-[:HAS_CHUNK]->(n)
RETURN count(n) AS cnt
"""

STATEMENT_SAVE = """
UNWIND $rows AS row
MERGE (n:Statement {id: row.id})
SET n.user_id = row.user_id,
    n.chunk_id = row.chunk_id,
    n.statement = row.statement,
    n.stmt_type = row.stmt_type,
    n.temporal_type = row.temporal_type,
    n.speaker = row.speaker,
    n.valid_at = row.valid_at,
    n.invalid_at = row.invalid_at,
    n.dialog_at = row.dialog_at,
    n.embedding = row.embedding,
    n.created_at = row.created_at
WITH n, row
MATCH (c:Chunk {id: row.chunk_id})
MERGE (c)-[:HAS_STATEMENT]->(n)
RETURN count(n) AS cnt
"""

# 实体：MERGE by id；description/aliases 增量合并由服务层在写入前算好
ENTITY_SAVE = """
UNWIND $rows AS row
MERGE (n:Entity {id: row.id})
SET n.user_id = row.user_id,
    n.name = row.name,
    n.type = row.type,
    n.description = row.description,
    n.aliases = row.aliases,
    n.name_embedding = row.name_embedding,
    n.community_id = row.community_id,
    n.created_at = coalesce(n.created_at, row.created_at)
RETURN count(n) AS cnt
"""

EVENT_SAVE = """
UNWIND $rows AS row
MERGE (n:Event {id: row.id})
SET n.user_id = row.user_id,
    n.title = row.title,
    n.description = row.description,
    n.event_time = row.event_time,
    n.embedding = row.embedding,
    n.created_at = row.created_at
RETURN count(n) AS cnt
"""

# ── 边批量写入 ──

MENTION_SAVE = """
UNWIND $rows AS row
MATCH (s:Statement {id: row.statement_id})
MATCH (e:Entity {id: row.entity_id})
MERGE (s)-[r:MENTIONS]->(e)
SET r.user_id = row.user_id,
    r.connect_strength = row.connect_strength,
    r.created_at = row.created_at
RETURN count(r) AS cnt
"""

RELATION_SAVE = """
UNWIND $rows AS row
MATCH (a:Entity {id: row.source_id})
MATCH (b:Entity {id: row.target_id})
MERGE (a)-[r:RELATION {predicate: row.predicate, target_id: row.target_id}]->(b)
SET r.id = row.id,
    r.user_id = row.user_id,
    r.predicate_surface = row.predicate_surface,
    r.source_text = row.source_text,
    r.statement_id = row.statement_id,
    r.value = row.value,
    r.valid_at = row.valid_at,
    r.invalid_at = row.invalid_at,
    r.created_at = row.created_at
RETURN count(r) AS cnt
"""

INVOLVES_SAVE = """
UNWIND $rows AS row
MATCH (ev:Event {id: row.event_id})
MATCH (e:Entity {id: row.entity_id})
MERGE (ev)-[r:INVOLVES]->(e)
SET r.user_id = row.user_id,
    r.role = row.role,
    r.created_at = row.created_at
RETURN count(r) AS cnt
"""

# ── 去重：取用户某实体类型下、已有同类实体（含 name_embedding，用于相似初筛） ──

ENTITY_LIST_BY_TYPE = """
MATCH (e:Entity {user_id: $user_id, type: $type})
RETURN e.id AS id, e.name AS name, e.type AS type,
       e.description AS description, e.aliases AS aliases,
       e.name_embedding AS name_embedding
"""

ENTITY_GET_BY_NAME = """
MATCH (e:Entity {user_id: $user_id, name: $name})
RETURN e.id AS id, e.name AS name, e.type AS type,
       e.description AS description, e.aliases AS aliases
LIMIT 1
"""

# ── 检索：实体向量召回（向量索引 KNN） ──

ENTITY_VECTOR_SEARCH = """
CALL db.index.vector.queryNodes('entity_embedding_index', $top_k, $vector)
YIELD node, score
WHERE node.user_id = $user_id
RETURN node.id AS id, node.name AS name, node.type AS type,
       node.description AS description, node.aliases AS aliases, score
"""

# ── 检索：实体全文召回（cjk 分词） ──

ENTITY_FULLTEXT_SEARCH = """
CALL db.index.fulltext.queryNodes('entity_fulltext', $query)
YIELD node, score
WHERE node.user_id = $user_id
RETURN node.id AS id, node.name AS name, node.type AS type,
       node.description AS description, node.aliases AS aliases, score
LIMIT $top_k
"""

# ── 检索：取实体的一跳邻居关系（图遍历上下文） ──

ENTITY_NEIGHBORS = """
MATCH (e:Entity {user_id: $user_id})
WHERE e.id IN $entity_ids
OPTIONAL MATCH (e)-[r:RELATION]->(o:Entity)
RETURN e.id AS entity_id, e.name AS entity_name,
       r.predicate AS predicate, r.source_text AS source_text,
       o.id AS object_id, o.name AS object_name, o.type AS object_type
"""

# ── 统计 / 删除（数据隔离） ──

ENTITY_COUNT = """
MATCH (e:Entity {user_id: $user_id})
RETURN count(e) AS cnt
"""

DELETE_USER_GRAPH = """
MATCH (n) WHERE n.user_id = $user_id DETACH DELETE n
"""
