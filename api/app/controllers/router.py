"""聚合所有路由，统一挂在 /api 前缀下。

后续各阶段在此注册：auth / model_config / document / image / tag /
conversation / chat / memory / search / favorite / dashboard / task。
"""
from fastapi import APIRouter

from app.controllers import (
    auth_controller,
    document_controller,
    file_controller,
    health_controller,
    image_controller,
    memory_controller,
    model_config_controller,
    tag_controller,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health_controller.router)
api_router.include_router(auth_controller.router)
api_router.include_router(model_config_controller.router)
api_router.include_router(document_controller.router)
api_router.include_router(image_controller.router)
api_router.include_router(tag_controller.router)
api_router.include_router(file_controller.router)
api_router.include_router(memory_controller.router)
