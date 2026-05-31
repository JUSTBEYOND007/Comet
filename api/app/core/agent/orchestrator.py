"""Agent 编排：方案B 双路径工具循环，产出统一事件流。

- 强模型（支持 function calling）：bind_tools + 流式工具循环，原生决定调用哪个工具。
- 弱模型：ToolOrchestrator（prompt 模拟 ReAct），解析 Action/Action Input 手动调工具。

两条路径都产出统一事件 dict：
  {"type": "tool_call", "tool", "query"} / {"type": "token", "text"} / {"type": "final", "text"}
引用由工具执行时写入外部传入的 citations 列表，编排结束后由调用方读取。
"""
import re
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI

from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_TOOL_ITERATIONS = 5


async def run_function_calling(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    messages: list,
) -> AsyncGenerator[dict, None]:
    """强模型路径：原生 function calling 流式工具循环。"""
    tool_map = {t.name: t for t in tools}
    model_with_tools = model.bind_tools(tools) if tools else model
    full_text = ""

    for _ in range(MAX_TOOL_ITERATIONS):
        gathered = None
        async for chunk in model_with_tools.astream(messages):
            if chunk.content:
                text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                full_text += text
                yield {"type": "token", "text": text}
            gathered = chunk if gathered is None else gathered + chunk

        tool_calls = getattr(gathered, "tool_calls", None) or []
        if not tool_calls:
            # 无工具调用 → 已是最终回答
            yield {"type": "final", "text": full_text}
            return

        # 有工具调用：执行后把结果回灌，继续循环
        messages.append(gathered)
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args", {}) or {}
            query = args.get("query", "")
            yield {"type": "tool_call", "tool": name, "query": query}
            tool = tool_map.get(name)
            if tool is None:
                observation = f"未知工具：{name}"
            else:
                try:
                    observation = await tool.ainvoke(args)
                except Exception as e:
                    observation = f"工具执行失败：{e}"
            messages.append(
                ToolMessage(content=str(observation), tool_call_id=tc.get("id", name))
            )

    # 达到最大迭代仍未收敛：用现有内容兜底
    yield {"type": "final", "text": full_text or "（未能生成回答）"}


_ACTION_RE = re.compile(r"Action\s*:\s*(.+)")
_ACTION_INPUT_RE = re.compile(r"Action\s*Input\s*:\s*(.+)")
_FINAL_RE = re.compile(r"Final\s*Answer\s*:\s*(.*)", re.DOTALL)


async def run_react(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    user_text: str,
    history: list,
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    """弱模型路径：prompt 模拟 ReAct，手动解析并调用工具。"""
    tool_map = {t.name: t for t in tools}
    sys = render_agent_prompt(
        "react.jinja2",
        tools=[{"name": t.name, "description": t.description} for t in tools],
        system_prompt=system_prompt,
    )
    convo: list = [SystemMessage(content=sys), *history, HumanMessage(content=user_text)]

    for _ in range(MAX_TOOL_ITERATIONS):
        resp = await model.ainvoke(convo)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)

        final_match = _FINAL_RE.search(text)
        if final_match:
            answer = final_match.group(1).strip()
            yield {"type": "token", "text": answer}
            yield {"type": "final", "text": answer}
            return

        action_match = _ACTION_RE.search(text)
        input_match = _ACTION_INPUT_RE.search(text)
        if not action_match:
            # 没有 Action 也没有 Final，把整段当回答兜底
            yield {"type": "token", "text": text}
            yield {"type": "final", "text": text}
            return

        tool_name = action_match.group(1).strip().splitlines()[0].strip()
        query = (input_match.group(1).strip().splitlines()[0].strip() if input_match else user_text)
        yield {"type": "tool_call", "tool": tool_name, "query": query}

        tool = tool_map.get(tool_name)
        if tool is None:
            observation = f"未知工具：{tool_name}"
        else:
            try:
                observation = await tool.ainvoke({"query": query})
            except Exception as e:
                observation = f"工具执行失败：{e}"
        # 把模型上一轮输出 + Observation 回灌
        convo.append(AIMessage(content=text))
        convo.append(HumanMessage(content=f"Observation: {observation}"))

    yield {"type": "final", "text": "（多轮工具调用后仍未得到结论）"}


__all__ = ["run_function_calling", "run_react", "MAX_TOOL_ITERATIONS"]
