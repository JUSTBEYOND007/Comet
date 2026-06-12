"""Agent 编排：方案B 双路径工具循环，产出统一事件流。

- 强模型（支持 function calling）：bind_tools + 流式工具循环，原生决定调用哪个工具。
- 弱模型：ToolOrchestrator（prompt 模拟 ReAct），解析 Action/Action Input 手动调工具。

两条路径都产出统一事件 dict：
  {"type": "tool_start", "tool", "query"} /
  {"type": "tool_result", "tool", "query", "status", "text", "stats", "latency_ms"} /
  {"type": "token", "text"} / {"type": "final", "text"}
引用由工具执行时写入外部传入的 citations 列表，编排结束后由调用方读取。

工具统计（命中数 / 实体数 / 网页数 等）由各工具写入 ctx.stats_holder[tool_key]，
本编排器在产 tool_result 事件时读取并附在事件上，前端 chip 副文动态绑定。
"""
import ast
import json
import re
import time
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI

from app.core.agent.prompt_renderer import render_agent_prompt
from app.core.logging import get_logger

logger = get_logger(__name__)

MAX_TOOL_ITERATIONS = 5
MAX_TOOL_RESULT_PREVIEW = 600


def _format_observation(observation: object) -> str:
    """把工具返回值格式化为人类与 LLM 都能读的文本。

    设计目标：
    - MCP 工具常返回 ``[{'type': 'text', 'text': '...'}]``（或其字符串形式），
      抽出 text 字段拼接，避免出现一坨 Python 字面量噪声。
    - 普通 dict / list 用 JSON 美化输出，保留结构感。
    - 字符串原样返回；若它本身是 Python 字面量字符串（容器），尝试 literal_eval 后递归格式化。
    - 任意对象优先取 ``text`` 属性（兼容 mcp.types.TextContent 等）。
    """
    # 字符串：先看是不是 Python 字面量序列化的形式（如 "[{'type': 'text', ...}]"）
    if isinstance(observation, str):
        text = observation.strip()
        if text and text[0] in "[{(" and text[-1] in "]})":
            try:
                parsed = ast.literal_eval(text)
                if not isinstance(parsed, str):
                    return _format_observation(parsed)
            except (ValueError, SyntaxError):
                pass
        return text

    # 列表：典型 MCP 多段内容；逐项抽 text，否则降级到 str
    if isinstance(observation, list):
        parts: list[str] = []
        for item in observation:
            if isinstance(item, dict):
                t = item.get("text") if isinstance(item.get("text"), str) else None
                if t is not None:
                    parts.append(t)
                    continue
            attr = getattr(item, "text", None)
            if isinstance(attr, str):
                parts.append(attr)
                continue
            try:
                parts.append(json.dumps(item, ensure_ascii=False, indent=2))
            except (TypeError, ValueError):
                parts.append(str(item))
        return "\n\n".join(p.strip() for p in parts if p)

    # 字典：优先 text 字段，否则 JSON 美化
    if isinstance(observation, dict):
        t = observation.get("text") if isinstance(observation.get("text"), str) else None
        if t is not None:
            return t
        try:
            return json.dumps(observation, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(observation)

    # 其他对象（如 mcp.types.TextContent）：尝试 text 属性
    attr = getattr(observation, "text", None)
    if isinstance(attr, str):
        return attr
    return str(observation)


def _truncate(text: str) -> str:
    """前端展示预览用：截断到 MAX_TOOL_RESULT_PREVIEW 长度。"""
    if len(text) <= MAX_TOOL_RESULT_PREVIEW:
        return text
    return text[:MAX_TOOL_RESULT_PREVIEW].rstrip() + "..."


async def run_function_calling(
    model: ChatOpenAI,
    tools: list[StructuredTool],
    messages: list,
    stats_holder: dict[str, dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """强模型路径：原生 function calling 流式工具循环。"""
    tool_map = {t.name: t for t in tools}
    model_with_tools = model.bind_tools(tools) if tools else model
    full_text = ""
    stats_holder = stats_holder if stats_holder is not None else {}

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
            yield {"type": "tool_start", "tool": name, "query": query}
            tool = tool_map.get(name)
            status = "success"
            t0 = time.monotonic()
            if tool is None:
                observation = f"未知工具：{name}"
                status = "error"
            else:
                try:
                    observation = await tool.ainvoke(args)
                except Exception as e:
                    observation = f"工具执行失败：{e}"
                    status = "error"
            latency_ms = int((time.monotonic() - t0) * 1000)
            stats = stats_holder.pop(name, {}) if stats_holder is not None else {}
            formatted = _format_observation(observation)
            yield {
                "type": "tool_result",
                "tool": name,
                "query": query,
                "status": status,
                "text": _truncate(formatted),
                "stats": stats,
                "latency_ms": latency_ms,
            }
            messages.append(
                ToolMessage(content=formatted, tool_call_id=tc.get("id", name))
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
    stats_holder: dict[str, dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """弱模型路径：prompt 模拟 ReAct，手动解析并调用工具。"""
    tool_map = {t.name: t for t in tools}
    sys = render_agent_prompt(
        "react.jinja2",
        tools=[{"name": t.name, "description": t.description} for t in tools],
        system_prompt=system_prompt,
    )
    convo: list = [SystemMessage(content=sys), *history, HumanMessage(content=user_text)]
    stats_holder = stats_holder if stats_holder is not None else {}

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
        yield {"type": "tool_start", "tool": tool_name, "query": query}

        tool = tool_map.get(tool_name)
        status = "success"
        t0 = time.monotonic()
        if tool is None:
            observation = f"未知工具：{tool_name}"
            status = "error"
        else:
            try:
                observation = await tool.ainvoke({"query": query})
            except Exception as e:
                observation = f"工具执行失败：{e}"
                status = "error"
        latency_ms = int((time.monotonic() - t0) * 1000)
        stats = stats_holder.pop(tool_name, {}) if stats_holder is not None else {}
        formatted = _format_observation(observation)
        yield {
            "type": "tool_result",
            "tool": tool_name,
            "query": query,
            "status": status,
            "text": _truncate(formatted),
            "stats": stats,
            "latency_ms": latency_ms,
        }
        # 把模型上一轮输出 + Observation 回灌
        convo.append(AIMessage(content=text))
        convo.append(HumanMessage(content=f"Observation: {formatted}"))

    yield {"type": "final", "text": "（多轮工具调用后仍未得到结论）"}


__all__ = ["run_function_calling", "run_react", "MAX_TOOL_ITERATIONS"]
