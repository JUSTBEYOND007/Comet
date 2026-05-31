"""Agent 配置请求/响应 schema。"""
from pydantic import BaseModel, Field


class AgentConfigUpdate(BaseModel):
    """更新 Agent 配置（全部可选，传啥改啥）。"""

    system_prompt: str | None = Field(default=None, max_length=4000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    enable_knowledge: bool | None = None
    enable_memory: bool | None = None
    enable_web_search: bool | None = None
