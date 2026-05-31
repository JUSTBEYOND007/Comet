"""Agent 配置业务服务：取/更新用户的 Agent 个性化配置（每用户一条，懒创建）。"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_config_model import AgentConfig
from app.repositories.agent_config_repository import AgentConfigRepository
from app.schemas.agent_config_schema import AgentConfigUpdate


class AgentConfigService:
    def __init__(self, session: AsyncSession):
        self.repo = AgentConfigRepository(session)

    async def get_or_create(self, user_id: uuid.UUID) -> AgentConfig:
        config = await self.repo.get_by_user(user_id)
        if config is None:
            config = await self.repo.create(AgentConfig(user_id=user_id))
        return config

    async def update(
        self, user_id: uuid.UUID, body: AgentConfigUpdate
    ) -> AgentConfig:
        config = await self.get_or_create(user_id)
        if body.system_prompt is not None:
            config.system_prompt = body.system_prompt
        if body.temperature is not None:
            config.temperature = body.temperature
        if body.enable_knowledge is not None:
            config.enable_knowledge = body.enable_knowledge
        if body.enable_memory is not None:
            config.enable_memory = body.enable_memory
        if body.enable_web_search is not None:
            config.enable_web_search = body.enable_web_search
        return await self.repo.save(config)

    @staticmethod
    def to_out_dict(config: AgentConfig) -> dict:
        return {
            "system_prompt": config.system_prompt,
            "temperature": config.temperature,
            "enable_knowledge": config.enable_knowledge,
            "enable_memory": config.enable_memory,
            "enable_web_search": config.enable_web_search,
        }
