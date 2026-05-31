"""问答业务服务：SSE 流式对话（方案B 工具编排）。

流程：加载默认对话模型 + Agent 配置 → 构建工具（知识库/记忆/联网，按开关）
→ 强模型走原生 function calling / 弱模型走 ReAct → 流式产出 token/工具标记/引用
→ 落库 user/assistant 消息（assistant 带引用与工具调用元信息）
→ 回答后异步派发记忆萃取（对话自动萃取）。
"""
import json
import uuid
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.orchestrator import run_function_calling, run_react
from app.core.agent.tools import (
    build_knowledge_tool,
    build_memory_tool,
    build_web_search_tool,
)
from app.core.llm.chat_model import (
    build_chat_model,
    build_default_chat_model,
    get_default_config_for_type,
    supports_function_call,
)
from app.core.logging import get_logger
from app.core.security import decrypt_secret
from app.core.storage import get_storage
from app.models.agent_config_model import AgentConfig
from app.models.conversation_model import (
    ROLE_ASSISTANT,
    ROLE_USER,
    Conversation,
    Message,
)
from app.repositories.agent_config_repository import AgentConfigRepository
from app.repositories.conversation_repository import (
    ConversationRepository,
    MessageRepository,
)
from app.repositories.model_config_repository import ModelConfigRepository
from app.schemas.chat_schema import ChatStreamRequest

logger = get_logger(__name__)

MAX_HISTORY_TURNS = 10


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conv_repo = ConversationRepository(session)
        self.msg_repo = MessageRepository(session)
        self.agent_repo = AgentConfigRepository(session)

    async def _ensure_conversation(
        self, user_id: uuid.UUID, body: ChatStreamRequest
    ) -> Conversation:
        if body.conversation_id:
            conv = await self.conv_repo.get(user_id, body.conversation_id)
            if conv:
                return conv
        title = body.message.strip()[:20] or "新对话"
        return await self.conv_repo.create(Conversation(user_id=user_id, title=title))

    async def _history_messages(self, conv_id: uuid.UUID) -> list:
        """历史消息转 LangChain 消息（不含 system 与当前问题）。"""
        out: list = []
        history = await self.msg_repo.recent_history(conv_id, MAX_HISTORY_TURNS)
        for m in history:
            if m.role == ROLE_USER:
                out.append(HumanMessage(content=m.content))
            elif m.role == ROLE_ASSISTANT:
                out.append(AIMessage(content=m.content))
        return out

    async def _get_websearch_config(self, user_id: uuid.UUID):
        """取用户默认 websearch 配置（provider + 解密 key）；无则返回 None。"""
        configs = await ModelConfigRepository(self.session).list_by_user(
            user_id, "websearch"
        )
        if not configs:
            return None
        cfg = next((c for c in configs if c.is_default), configs[0])
        return cfg.provider, decrypt_secret(cfg.api_key_encrypted)

    async def _build_tools(
        self,
        user_id: uuid.UUID,
        agent: AgentConfig | None,
        body: ChatStreamRequest,
        citations: list[dict],
    ) -> list:
        """按 agent 默认开关 + 本轮覆盖，构建启用的工具列表。"""

        def enabled(override: bool | None, default: bool) -> bool:
            return default if override is None else override

        a_know = agent.enable_knowledge if agent else True
        a_mem = agent.enable_memory if agent else True
        a_web = agent.enable_web_search if agent else False

        embed_holder: dict = {}
        tools: list = []
        if enabled(body.enable_knowledge, a_know):
            tools.append(
                build_knowledge_tool(self.session, user_id, citations, embed_holder)
            )
        if enabled(body.enable_memory, a_mem):
            tools.append(build_memory_tool(self.session, user_id, embed_holder))
        if enabled(body.enable_web_search, a_web):
            ws = await self._get_websearch_config(user_id)
            if ws:
                provider, key = ws
                tools.append(build_web_search_tool(provider, key))
        return tools

    async def stream_chat(
        self, user_id: uuid.UUID, body: ChatStreamRequest
    ) -> AsyncGenerator[str, None]:
        user_text = body.message.strip()
        try:
            conv = await self._ensure_conversation(user_id, body)
        except Exception as e:
            yield _sse("error", {"message": str(e)})
            return

        yield _sse("meta", {"conversation_id": str(conv.id), "title": conv.title})
        await self.msg_repo.add(
            Message(conversation_id=conv.id, role=ROLE_USER, content=user_text)
        )

        try:
            agent = await self.agent_repo.get_by_user(user_id)
            temperature = agent.temperature if agent else 0.7
            model, config = await build_default_chat_model(
                self.session, user_id, temperature=temperature, streaming=True
            )
            system_prompt = (agent.system_prompt.strip() if agent else "") or ""
            citations: list[dict] = []
            tools = await self._build_tools(user_id, agent, body, citations)
            history = await self._history_messages(conv.id)
        except Exception as e:
            yield _sse("error", {"message": str(e)})
            return

        full_text = ""
        tool_calls: list[dict] = []
        try:
            if body.image_keys:
                # 多模态输入：用多模态模型看图回答（不走工具编排）
                async for token in self._stream_multimodal(
                    user_id, system_prompt, history, user_text, body.image_keys
                ):
                    full_text += token
                    yield _sse("token", {"text": token})
            elif not tools:
                # 无工具：纯流式
                lc_messages: list = []
                if system_prompt:
                    lc_messages.append(SystemMessage(content=system_prompt))
                lc_messages.extend(history)
                lc_messages.append(HumanMessage(content=user_text))
                async for chunk in model.astream(lc_messages):
                    if chunk.content:
                        full_text += chunk.content
                        yield _sse("token", {"text": chunk.content})
            elif supports_function_call(config):
                # 强模型：原生 function calling
                lc_messages = []
                if system_prompt:
                    lc_messages.append(SystemMessage(content=system_prompt))
                lc_messages.extend(history)
                lc_messages.append(HumanMessage(content=user_text))
                async for ev in run_function_calling(model, tools, lc_messages):
                    full_text, tool_calls = await self._emit(
                        ev, full_text, tool_calls
                    )
                    out = self._event_to_sse(ev)
                    if out:
                        yield out
            else:
                # 弱模型：ReAct
                async for ev in run_react(model, tools, user_text, history, system_prompt):
                    full_text, tool_calls = await self._emit(
                        ev, full_text, tool_calls
                    )
                    out = self._event_to_sse(ev)
                    if out:
                        yield out
        except Exception as e:
            logger.error("问答生成失败: %s", e, exc_info=True)
            yield _sse("error", {"message": f"生成失败：{e}"})
            return

        # 引用事件
        if citations:
            yield _sse("citation", {"citations": citations})

        # 存 assistant 消息（带引用 + 工具调用元信息）
        assistant_msg = await self.msg_repo.add(
            Message(
                conversation_id=conv.id,
                role=ROLE_ASSISTANT,
                content=full_text,
                meta_data={"citations": citations, "tool_calls": tool_calls},
            )
        )
        await self.conv_repo.touch(conv.id)

        # 回答后异步萃取记忆（对话自动萃取，不阻塞用户：仅落库+派发，萃取在 worker）
        await self._dispatch_memory(user_id, user_text)

        yield _sse(
            "done",
            {"conversation_id": str(conv.id), "message_id": str(assistant_msg.id)},
        )

    @staticmethod
    async def _emit(
        ev: dict, full_text: str, tool_calls: list[dict]
    ) -> tuple[str, list[dict]]:
        """累积文本与工具调用记录。"""
        if ev["type"] == "token":
            full_text += ev["text"]
        elif ev["type"] == "tool_call":
            tool_calls.append({"tool": ev["tool"], "query": ev.get("query", "")})
        elif ev["type"] == "final" and not full_text:
            full_text = ev["text"]
        return full_text, tool_calls

    @staticmethod
    def _event_to_sse(ev: dict) -> str | None:
        """编排事件 → SSE。final 不单独发（token 已累积）。"""
        if ev["type"] == "token":
            return _sse("token", {"text": ev["text"]})
        if ev["type"] == "tool_call":
            return _sse("tool_call", {"tool": ev["tool"], "query": ev.get("query", "")})
        return None

    async def _stream_multimodal(
        self,
        user_id: uuid.UUID,
        system_prompt: str,
        history: list,
        user_text: str,
        image_keys: list[str],
    ):
        """多模态流式：读图转 base64，用多模态模型看图答。逐 token 产出。"""
        import base64

        from langchain_core.messages import HumanMessage, SystemMessage

        config = await get_default_config_for_type(
            self.session, user_id, "multimodal", "多模态"
        )
        model = build_chat_model(config, temperature=0.7, streaming=True)

        storage = get_storage()
        content_parts: list[dict] = [{"type": "text", "text": user_text}]
        for key in image_keys[:4]:  # 单轮最多 4 张
            try:
                raw = await storage.get(key)
                b64 = base64.b64encode(raw).decode()
                mime = "image/png" if key.lower().endswith(".png") else "image/jpeg"
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
            except Exception as e:
                logger.warning("读取对话图片失败（跳过）: %s", e)

        messages: list = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.extend(history)
        messages.append(HumanMessage(content=content_parts))

        async for chunk in model.astream(messages):
            if chunk.content:
                text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                yield text

    async def _dispatch_memory(self, user_id: uuid.UUID, user_text: str) -> None:
        """把本轮用户表达落 memories(source=auto) 并派发萃取任务。失败不影响问答。"""
        try:
            from app.models.memory_model import MEMORY_SOURCE_AUTO, Memory
            from app.tasks.memory import extract_memory_task

            memory = Memory(
                user_id=user_id, raw_text=user_text, source=MEMORY_SOURCE_AUTO
            )
            self.session.add(memory)
            await self.session.commit()
            await self.session.refresh(memory)
            extract_memory_task.delay(str(memory.id))
        except Exception as e:
            logger.warning("对话记忆萃取派发失败（忽略）: %s", e)


__all__ = ["ChatService"]
