"""萃取流水线的中间数据模型（LLM 结构化输出 + 流水线传递）。

仅在萃取过程内部使用，最终转换成 graph_models 的节点/边写入 Neo4j。
"""
from pydantic import BaseModel, ConfigDict, Field


# ── 陈述抽取 ──

class ExtractedStatement(BaseModel):
    """从文本切出的原子陈述句。"""

    model_config = ConfigDict(extra="ignore")
    statement: str
    statement_type: str = "FACT"  # FACT | OPINION | PREDICTION | SUGGESTION
    temporal_type: str = "STATIC"  # STATIC | DYNAMIC | ATEMPORAL
    has_unsolved_reference: bool = False


class StatementExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    statements: list[ExtractedStatement] = Field(default_factory=list)


# ── 三元组抽取 ──

class ExtractedEvent(BaseModel):
    """LLM 抽出的事件（一次性发生、有时间的经历）。"""

    model_config = ConfigDict(extra="ignore")
    title: str  # 事件标题，如「完成项目上线」
    description: str = ""  # 事件描述
    event_time: str | None = None  # ISO 时间 或 NULL
    participants: list[str] = Field(default_factory=list)  # 涉及实体名（关联到已抽实体）


class ExtractedEntity(BaseModel):
    """LLM 抽出的实体（chunk 内局部 idx 用于关联 triplet）。"""

    model_config = ConfigDict(extra="ignore")
    entity_idx: int
    name: str
    type: str
    description: str = ""


class ExtractedTriplet(BaseModel):
    """LLM 抽出的三元组。"""

    model_config = ConfigDict(extra="ignore")
    subject_name: str
    subject_id: int
    predicate: str
    predicate_surface: str = ""
    object_name: str
    object_id: int
    value: str | None = None
    valid_at: str | None = None
    invalid_at: str | None = None


class TripletExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entities: list[ExtractedEntity] = Field(default_factory=list)
    triplets: list[ExtractedTriplet] = Field(default_factory=list)
    events: list[ExtractedEvent] = Field(default_factory=list)


# ── 实体去重判定 ──

class DedupDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    same_entity: bool = False
    canonical_idx: int = 0
    confidence: float = 0.0
    reason: str = ""


__all__ = [
    "ExtractedStatement",
    "StatementExtractionResult",
    "ExtractedEvent",
    "ExtractedEntity",
    "ExtractedTriplet",
    "TripletExtractionResult",
    "DedupDecision",
]
