"""统一导入所有 ORM 模型，确保 SQLAlchemy metadata 完整。

任何模块导入 app.models 即可让全部表与外键关系正确注册，
避免在 Celery worker 等场景因模型未全部加载导致外键解析失败。
"""
from app.models.document_model import Document
from app.models.image_model import Image
from app.models.memory_model import Memory
from app.models.model_config_model import ModelConfig
from app.models.tag_model import Tag, document_tags, image_tags
from app.models.user_model import User

__all__ = [
    "Document",
    "Image",
    "Memory",
    "ModelConfig",
    "Tag",
    "document_tags",
    "image_tags",
    "User",
]
