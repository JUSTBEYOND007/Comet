"""Agent 工具工厂：把知识库检索 / 记忆检索 / 联网搜索包成 LangChain 工具。

每次问答构建一组工具（闭包捕获 session/user_id + 共享的引用收集器）。
工具内部调用阶段3 的 hybrid_search、阶段4 的 search_memory、联网搜索 web_search。
"""
import uuid

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.memory.retrieval.searcher import format_memory_context, search_memory

logger = get_logger(__name__)


class _QueryInput(BaseModel):
    query: str = Field(..., description="检索的问题或关键词")


# 工具名常量（前端工具调用标记按此映射图标）
TOOL_KNOWLEDGE = "knowledge_search"
TOOL_MEMORY = "memory_search"
TOOL_WEB = "web_search"


def build_knowledge_tool(
    session: AsyncSession,
    user_id: uuid.UUID,
    citations: list[dict],
    embed_client_holder: dict,
) -> StructuredTool:
    """知识库检索工具：检索文档/图片片段并收集引用。"""

    async def _run(query: str) -> str:
        from app.core.rag.search import hybrid_search

        hits = await hybrid_search(session, user_id, query, top_k=5)
        if not hits:
            return "知识库中没有检索到相关内容。"
        seen = {c["source_id"] for c in citations}
        parts: list[str] = []
        for h in hits:
            parts.append(h["content"])
            sid = h.get("source_id")
            if sid and sid not in seen:
                seen.add(sid)
                citations.append({
                    "source_id": sid,
                    "source_type": h.get("source_type"),
                    "doc_name": h.get("doc_name"),
                    "score": h.get("score"),
                })
        return "检索到以下知识库内容：\n\n" + "\n\n".join(parts)

    return StructuredTool.from_function(
        coroutine=_run,
        name=TOOL_KNOWLEDGE,
        description="从用户的个人知识库（文档、图片）中检索相关内容。当问题涉及用户上传的资料、文档、笔记时使用。",
        args_schema=_QueryInput,
    )


def build_memory_tool(
    session: AsyncSession, user_id: uuid.UUID, embed_client_holder: dict
) -> StructuredTool:
    """记忆检索工具：从记忆图谱召回相关实体与关系。"""

    async def _run(query: str) -> str:
        embed_client = embed_client_holder.get("embedding")
        if embed_client is None:
            from app.core.llm.resolver import get_client_for_type

            embed_client = await get_client_for_type(session, user_id, "embedding")
            embed_client_holder["embedding"] = embed_client
        results = await search_memory(
            embed_client=embed_client, user_id=user_id, query=query, top_k=10
        )
        if not results:
            return "没有检索到相关记忆。"
        return "检索到以下用户记忆：\n\n" + format_memory_context(results)

    return StructuredTool.from_function(
        coroutine=_run,
        name=TOOL_MEMORY,
        description="检索关于用户本人的长期记忆（画像、偏好、关系、经历等）。当问题涉及'我'的个人信息时使用。",
        args_schema=_QueryInput,
    )


def build_web_search_tool(provider: str, api_key: str) -> StructuredTool:
    """联网搜索工具：从互联网获取实时信息。"""

    async def _run(query: str) -> str:
        from app.core.agent.web_search import web_search

        try:
            result = await web_search(provider, api_key, query, top_k=10)
            return f"联网搜索到以下信息：\n\n{result}" if result else "联网搜索没有返回结果。"
        except Exception as e:
            logger.warning("联网搜索失败: %s", e)
            return f"联网搜索失败：{e}"

    return StructuredTool.from_function(
        coroutine=_run,
        name=TOOL_WEB,
        description="从互联网搜索最新信息。当问题需要实时信息、最新新闻、或知识库/记忆中没有的网络资料时使用。",
        args_schema=_QueryInput,
    )


__all__ = [
    "TOOL_KNOWLEDGE",
    "TOOL_MEMORY",
    "TOOL_WEB",
    "build_knowledge_tool",
    "build_memory_tool",
    "build_web_search_tool",
]
