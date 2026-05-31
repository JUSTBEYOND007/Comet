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

# ── 画像视图：列出用户全部实体（含每个实体的一跳出边关系，供卡片展示） ──

ENTITY_LIST_ALL = """
MATCH (e:Entity {user_id: $user_id})
OPTIONAL MATCH (e)-[r:RELATION]->(o:Entity)
WITH e, collect({predicate: r.predicate, object_name: o.name, object_type: o.type}) AS rels
RETURN e.id AS id, e.name AS name, e.type AS type,
       e.description AS description, e.aliases AS aliases,
       e.created_at AS created_at,
       [rel IN rels WHERE rel.predicate IS NOT NULL] AS relations
ORDER BY e.created_at DESC
"""

# ── 统计：每种实体类型的数量 ──

ENTITY_TYPE_COUNTS = """
MATCH (e:Entity {user_id: $user_id})
RETURN e.type AS type, count(e) AS cnt
ORDER BY cnt DESC
"""

# ── 删除单个实体（连带其关系） ──

DELETE_ENTITY = """
MATCH (e:Entity {user_id: $user_id, id: $entity_id})
DETACH DELETE e
"""

# ── 社区聚类（阶段7）──

# 取用户全部实体的 id + name_embedding（全量聚类初始化用）
ENTITY_IDS_WITH_EMBEDDING = """
MATCH (e:Entity {user_id: $user_id})
RETURN e.id AS id, e.name_embedding AS name_embedding, e.community_id AS community_id
"""

# 取一批实体的邻居（含邻居的 community_id + name_embedding，供加权投票）
ENTITY_NEIGHBORS_FOR_VOTE = """
MATCH (e:Entity {user_id: $user_id})
WHERE e.id IN $entity_ids
MATCH (e)-[:RELATION]-(nb:Entity {user_id: $user_id})
RETURN e.id AS entity_id, nb.id AS id,
       nb.community_id AS community_id, nb.name_embedding AS name_embedding
"""

# upsert 社区节点
COMMUNITY_UPSERT = """
MERGE (c:Community {id: $community_id, user_id: $user_id})
ON CREATE SET c.created_at = $created_at, c.member_count = 0,
              c.name = $community_id, c.summary = ''
RETURN c.id AS id
"""

# 把实体归到社区（写 community_id 属性 + IN_COMMUNITY 边）
ENTITY_ASSIGN_COMMUNITY = """
MATCH (e:Entity {user_id: $user_id, id: $entity_id})
SET e.community_id = $community_id
WITH e
MATCH (c:Community {user_id: $user_id, id: $community_id})
OPTIONAL MATCH (e)-[old:IN_COMMUNITY]->(:Community)
DELETE old
MERGE (e)-[:IN_COMMUNITY]->(c)
"""

# 刷新社区成员数
COMMUNITY_REFRESH_COUNT = """
MATCH (c:Community {user_id: $user_id, id: $community_id})
OPTIONAL MATCH (e:Entity {user_id: $user_id, community_id: $community_id})
WITH c, count(e) AS cnt
SET c.member_count = cnt
RETURN cnt
"""

# 取社区成员（含 name_embedding，供合并计算 + 元数据）
COMMUNITY_MEMBERS = """
MATCH (e:Entity {user_id: $user_id, community_id: $community_id})
RETURN e.id AS id, e.name AS name, e.type AS type,
       e.description AS description, e.aliases AS aliases,
       e.name_embedding AS name_embedding
"""

# 社区内实体间关系（供 LLM 生成摘要）
COMMUNITY_RELATIONSHIPS = """
MATCH (a:Entity {user_id: $user_id, community_id: $community_id})
      -[r:RELATION]->(b:Entity {user_id: $user_id, community_id: $community_id})
RETURN a.name AS subject, r.predicate AS predicate, b.name AS object
LIMIT 50
"""

# 写社区元数据
COMMUNITY_UPDATE_META = """
MATCH (c:Community {user_id: $user_id, id: $community_id})
SET c.name = $name, c.summary = $summary
RETURN c.id AS id
"""

# 社区列表（成员数倒序）
COMMUNITY_LIST = """
MATCH (c:Community {user_id: $user_id})
WHERE c.member_count > 0
RETURN c.id AS id, c.name AS name, c.summary AS summary,
       c.member_count AS member_count
ORDER BY c.member_count DESC
"""

# 用户是否已有社区（判断全量 or 增量）
COMMUNITY_EXISTS = """
MATCH (c:Community {user_id: $user_id})
RETURN count(c) AS cnt
"""

# 清掉成员数为 0 的空社区
COMMUNITY_PRUNE_EMPTY = """
MATCH (c:Community {user_id: $user_id})
WHERE c.member_count = 0 OR c.member_count IS NULL
DETACH DELETE c
"""

# ── 重复实体清理（同 user_id + name + type 视为重复，合并到保留节点）──

# 找出重复实体组：返回每组 [ids...]（按 created_at 升序，第一个作保留方）
DUPLICATE_ENTITY_GROUPS = """
MATCH (e:Entity {user_id: $user_id})
WITH e ORDER BY e.created_at ASC
WITH toLower(trim(e.name)) AS key, e.type AS type,
     collect(e.id) AS ids,
     collect(e.aliases) AS aliases_list,
     collect(e.description) AS descs,
     collect(e.name) AS names
WHERE size(ids) > 1
RETURN ids, aliases_list, descs, names
"""

# 把重复节点的 MENTIONS 入边接到保留节点
DEDUP_REDIRECT_MENTIONS = """
MATCH (keeper:Entity {user_id: $user_id, id: $keeper_id})
MATCH (s:Statement)-[r:MENTIONS]->(dup:Entity {user_id: $user_id})
WHERE dup.id IN $dup_ids
MERGE (s)-[:MENTIONS]->(keeper)
"""

# 把重复节点的 INVOLVES 入边接到保留节点
DEDUP_REDIRECT_INVOLVES = """
MATCH (keeper:Entity {user_id: $user_id, id: $keeper_id})
MATCH (ev:Event)-[r:INVOLVES]->(dup:Entity {user_id: $user_id})
WHERE dup.id IN $dup_ids
MERGE (ev)-[:INVOLVES]->(keeper)
"""

# 重复节点的 RELATION 出边接到保留节点（跳过指向保留节点自身的自环）
DEDUP_REDIRECT_RELATION_OUT = """
MATCH (keeper:Entity {user_id: $user_id, id: $keeper_id})
MATCH (dup:Entity {user_id: $user_id})-[r:RELATION]->(o:Entity)
WHERE dup.id IN $dup_ids AND o.id <> $keeper_id
MERGE (keeper)-[nr:RELATION {predicate: r.predicate, target_id: o.id}]->(o)
ON CREATE SET nr.id = r.id, nr.user_id = r.user_id,
    nr.predicate_surface = r.predicate_surface, nr.source_text = r.source_text,
    nr.statement_id = r.statement_id, nr.value = r.value,
    nr.valid_at = r.valid_at, nr.invalid_at = r.invalid_at, nr.created_at = r.created_at
"""

# 重复节点的 RELATION 入边接到保留节点（target_id 改为保留节点；跳过自环）
DEDUP_REDIRECT_RELATION_IN = """
MATCH (keeper:Entity {user_id: $user_id, id: $keeper_id})
MATCH (s:Entity)-[r:RELATION]->(dup:Entity {user_id: $user_id})
WHERE dup.id IN $dup_ids AND s.id <> $keeper_id
MERGE (s)-[nr:RELATION {predicate: r.predicate, target_id: $keeper_id}]->(keeper)
ON CREATE SET nr.id = r.id, nr.user_id = r.user_id,
    nr.predicate_surface = r.predicate_surface, nr.source_text = r.source_text,
    nr.statement_id = r.statement_id, nr.value = r.value,
    nr.valid_at = r.valid_at, nr.invalid_at = r.invalid_at, nr.created_at = r.created_at
"""

# 合并别名/描述并删除重复节点（连带其残留边）
DEDUP_UPDATE_KEEPER = """
MATCH (keeper:Entity {user_id: $user_id, id: $keeper_id})
SET keeper.aliases = $aliases, keeper.description = $description
"""

DEDUP_DELETE_DUPS = """
MATCH (dup:Entity {user_id: $user_id})
WHERE dup.id IN $dup_ids
DETACH DELETE dup
"""

# ── 统计 / 删除（数据隔离） ──

ENTITY_COUNT = """
MATCH (e:Entity {user_id: $user_id})
RETURN count(e) AS cnt
"""

DELETE_USER_GRAPH = """
MATCH (n) WHERE n.user_id = $user_id DETACH DELETE n
"""

# ── 知识图谱可视化（阶段8）──

# 全量图：所有实体节点（含类型/社区/描述）
GRAPH_NODES = """
MATCH (e:Entity {user_id: $user_id})
RETURN e.id AS id, e.name AS name, e.type AS type,
       e.description AS description, e.community_id AS community_id
"""

# 全量图：实体间 RELATION 边
GRAPH_EDGES = """
MATCH (a:Entity {user_id: $user_id})-[r:RELATION]->(b:Entity {user_id: $user_id})
RETURN a.id AS source, b.id AS target,
       r.predicate AS predicate, r.predicate_surface AS predicate_surface
"""

# 单实体一跳子图：中心实体 + 邻居 + 它们之间的关系边
ENTITY_SUBGRAPH_NODES = """
MATCH (c:Entity {user_id: $user_id, id: $entity_id})
OPTIONAL MATCH (c)-[:RELATION]-(nb:Entity {user_id: $user_id})
WITH collect(DISTINCT c) + collect(DISTINCT nb) AS ns
UNWIND ns AS e
RETURN DISTINCT e.id AS id, e.name AS name, e.type AS type,
       e.description AS description, e.community_id AS community_id
"""

ENTITY_SUBGRAPH_EDGES = """
MATCH (c:Entity {user_id: $user_id, id: $entity_id})
MATCH (c)-[r:RELATION]-(nb:Entity {user_id: $user_id})
WITH startNode(r) AS s, endNode(r) AS t, r
RETURN s.id AS source, t.id AS target,
       r.predicate AS predicate, r.predicate_surface AS predicate_surface
"""

# 事件时间线：Event 节点 + 参与实体（按 event_time 倒序，未填时间的排后）
EVENT_TIMELINE = """
MATCH (ev:Event {user_id: $user_id})
OPTIONAL MATCH (ev)-[:INVOLVES]->(e:Entity {user_id: $user_id})
WITH ev, collect({id: e.id, name: e.name, type: e.type}) AS parts
RETURN ev.id AS id, ev.title AS title, ev.description AS description,
       ev.event_time AS event_time, ev.created_at AS created_at,
       [p IN parts WHERE p.id IS NOT NULL] AS participants
ORDER BY coalesce(ev.event_time, ev.created_at) DESC
"""
