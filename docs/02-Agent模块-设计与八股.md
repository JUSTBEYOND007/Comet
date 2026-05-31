# Agent 模块 — 设计与面试八股

> 结合 Comet 智能问答模块的真实实现，讲解 Agent / 工具调用 / ReAct / 流式 等面试高频点。
> 对应代码：`api/app/core/agent/`（orchestrator/tools/web_search/prompts）+ `api/app/services/chat_service.py` + `api/app/core/llm/chat_model.py`

---

## 一、模块在做什么

把「知识库检索、记忆检索、联网搜索」三种能力封装成 LLM 可调用的**工具（Tool）**，让大模型在回答用户问题时**自主决定**调用哪个/哪些工具、调几次，最后综合工具结果生成答案，整个过程通过 **SSE 流式**实时推给前端，并展示工具调用标记与引用来源。

一次问答的完整链路：

```
用户提问
  → 加载用户默认对话模型 + Agent 配置（system prompt / 温度 / 工具开关）
  → 按开关构建工具集（知识库 / 记忆 / 联网）
  → 判断模型能力：
       强模型（支持 function calling） → 原生工具调用循环
       弱模型 → ReAct 提示词模拟，手动解析 Action
  → 流式产出 token / 工具调用标记 / 引用
  → 落库 user/assistant 消息
  → 回答后异步派发记忆萃取
```

---

## 二、核心设计：方案B 双路径

**问题**：不同模型对 function calling 的支持参差不齐。强模型（GPT-4o、DeepSeek 等）支持 OpenAI 原生 function calling；一些弱模型 / 老模型不支持。

**方案**：双路径，按模型 `capability` 标记分流（`supports_function_call`）。

### 路径一：强模型 — 原生 function calling

```python
# core/agent/orchestrator.py - run_function_calling
model_with_tools = model.bind_tools(tools)
for _ in range(MAX_TOOL_ITERATIONS):       # 最多 5 轮
    async for chunk in model_with_tools.astream(messages):
        yield {"type": "token", "text": ...}    # 边生成边推送
    tool_calls = gathered.tool_calls
    if not tool_calls:
        yield {"type": "final", ...}; return    # 无工具调用 = 最终答案
    # 有工具调用：执行 → ToolMessage 回灌 → 继续循环
    for tc in tool_calls:
        observation = await tool.ainvoke(tc["args"])
        messages.append(ToolMessage(content=observation, tool_call_id=tc["id"]))
```

要点：
- `bind_tools` 把工具的 name/description/参数 schema 以 OpenAI tools 格式传给模型；
- 模型返回 `tool_calls` 时执行工具，把结果包成 `ToolMessage` 回灌进对话历史，再次调用模型；
- 循环直到模型不再要求调工具（即给出最终回答），或达到最大迭代 `MAX_TOOL_ITERATIONS=5`（防死循环）。

### 路径二：弱模型 — ReAct 提示词模拟

```python
# core/agent/orchestrator.py - run_react
# 用 jinja2 prompt 告诉模型可用工具 + ReAct 格式
# 模型输出形如：
#   Thought: 我需要查知识库
#   Action: knowledge_search
#   Action Input: 用户的简历
# 用正则解析出 Action / Action Input，手动调工具，把 Observation 回灌
```

要点：
- 用提示词约束模型按 `Thought / Action / Action Input / Observation / Final Answer` 格式输出；
- 后端用正则解析 `Action` 和 `Action Input`，手动执行对应工具；
- 把模型输出 + `Observation: ...` 追加进对话再调模型，循环到出现 `Final Answer`。

> 两条路径产出**统一事件流** `{type: token/tool_call/final}`，上层 chat_service 不关心走了哪条路径，便于维护。

---

## 三、工具是怎么定义的

```python
# core/agent/tools.py
StructuredTool.from_function(
    coroutine=_run,                # 异步执行函数
    name="knowledge_search",
    description="从用户的个人知识库（文档、图片）中检索相关内容。当问题涉及用户上传的资料时使用。",
    args_schema=_QueryInput,       # pydantic 定义参数（query: str）
)
```

三个工具：
- `knowledge_search`：内部调 RAG 的 `hybrid_search`，并把命中来源收集到共享的 `citations` 列表（用于回答后展示引用）。
- `memory_search`：内部调记忆图谱的 `search_memory`，返回实体+关系拼成的上下文。
- `web_search`：调联网搜索（百度千帆 / tavily）。

**关键设计**：工具用闭包捕获 `session`、`user_id`、共享的 `citations` 收集器。`description` 写清「什么场景用」，这是模型选对工具的关键——description 就是给模型看的工具说明书。

---

## 四、SSE 流式输出

**为什么用 SSE 而不是 WebSocket**：问答是「服务端单向持续推送」场景，SSE（Server-Sent Events）基于 HTTP，比 WebSocket 轻量，浏览器原生支持自动重连，足够用。

事件类型（`chat_service._sse`）：

| event | 含义 |
|-------|------|
| `meta` | 会话 id、标题 |
| `token` | 流式文本片段 |
| `tool_call` | 工具调用标记（前端显示「🔍 知识库」标签） |
| `citation` | 引用来源列表 |
| `done` | 结束（带 message_id） |
| `error` | 错误信息 |

后端用 async generator 逐段 `yield`，FastAPI 用 `StreamingResponse` 以 `text/event-stream` 返回。前端用 `fetch` + `ReadableStream` 解析 SSE（不用 EventSource 是因为要带 POST body 和 Authorization 头）。

---

## 五、多轮对话 & 记忆闭环

- **多轮上下文**：每次取最近 N 轮（`MAX_HISTORY_TURNS=10`）历史消息，转成 LangChain 的 HumanMessage/AIMessage 拼进对话。
- **记忆闭环**：回答完成后异步派发记忆萃取任务（`_dispatch_memory`），把用户本轮表达落 memories(source=auto) 并交给 worker 萃取——对话越多，记忆图谱越丰富，下次问答记忆工具能召回的就越多。这是「知识库 + 记忆」双飞轮。

---

## 六、多模态

对话可传图：读图转 base64，用多模态模型（`type=multimodal`）的 `astream` 看图回答（单轮最多 4 张）。多模态走单独分支，不走工具编排（看图问答一般不需要再查知识库）。

---

## 七、面试问答（八股）

**Q1：什么是 Agent？和直接调 LLM 有什么区别？**
Agent 是让 LLM 具备「使用工具 + 多步推理」能力的范式。直接调 LLM 只能用它训练时的知识一次性作答；Agent 让 LLM 能根据问题自主决定调用外部工具（检索、计算、联网等），拿到结果后再推理，可多轮迭代，从而回答它本身不知道、或需要实时/私有数据的问题。本项目里 Agent 能查用户私有知识库、查用户记忆、联网，这些都是模型本身没有的信息。

**Q2：function calling 的原理？**
模型在训练时学会了「按结构化格式请求调用函数」。调用方把可用函数的名字、描述、参数 JSON Schema 一起传给模型，模型判断需要调用时，返回结构化的 `tool_calls`（函数名 + 参数）。调用方实际执行函数，把结果回传给模型，模型据此继续生成。本质是模型负责「决策调什么、传什么参数」，执行由外部代码完成。

**Q3：ReAct 是什么？为什么需要它？**
ReAct = Reasoning + Acting，让模型按「思考(Thought) → 行动(Action) → 观察(Observation)」循环解决问题的提示词范式。对不支持原生 function calling 的模型，用 ReAct 提示词约束输出格式，后端解析出 Action 手动调工具，实现降级兼容。本项目强模型走原生 function calling、弱模型走 ReAct。

**Q4：怎么防止 Agent 无限循环调工具？**
设最大迭代次数（`MAX_TOOL_ITERATIONS=5`），超过就用现有内容兜底返回。另外每轮把工具结果回灌后让模型重新判断，正常情况下拿到足够信息模型就会停止调工具直接作答。

**Q5：工具描述（description）为什么重要？**
description 是模型选择工具的唯一依据。写得含糊模型会选错或不选。本项目每个工具 description 都明确写了「什么场景用」（如记忆工具写「当问题涉及'我'的个人信息时使用」），引导模型正确路由。

**Q6：流式输出怎么实现的？SSE vs WebSocket？**
后端用 async generator 逐 token yield，配合 FastAPI 的 StreamingResponse 以 text/event-stream 返回；LangChain 的 `astream` 提供逐 chunk 的流式接口。选 SSE 是因为问答是服务端单向推送，SSE 基于 HTTP 更轻量、原生支持；WebSocket 是全双工，适合双向实时交互（聊天室、协同编辑），这里用不上。

**Q7：多轮对话上下文怎么管理？会不会超 token？**
取最近 N 轮历史拼进 prompt（滑动窗口）。超长可进一步做历史摘要压缩。本项目个人场景对话不长，固定 10 轮够用。

**Q8：引用（citation）怎么做的？**
工具执行检索时，把命中的来源（doc 名、source_id、score）写进一个贯穿本次问答的共享 citations 列表；回答结束后通过 citation 事件一次性下发，前端渲染成引用卡片，并存进 assistant 消息的 meta_data 做持久化。

**Q9：为什么不用 LangGraph？**
LangGraph 适合复杂的有状态多智能体编排（分支、循环、人工介入等）。本项目就是「单 Agent + 工具循环」，用 LangChain 的 bind_tools + 手写循环已经够清晰可控，引入 LangGraph 反而增加复杂度。技术选型要匹配实际复杂度，避免过度设计。

**Q10：温度（temperature）参数的作用？**
控制输出随机性。低温（0~0.3）更确定、适合事实问答和工具决策；高温（0.7+）更发散、适合创意。本项目对话默认 0.7（可由 Agent 配置调），萃取/分类等需要稳定结构化输出的场景用低温（0.1~0.2）。

---

## 八、常见追问（进阶）

**Q1：function calling 和 ReAct 本质区别？各自优劣？**
function calling 是模型「原生能力」，调用结构化、稳定、解析可靠，但依赖模型支持；ReAct 是「提示词技巧」，任何能跟随指令的模型都能用，但要靠正则解析模型的自然语言输出，脆弱（模型不按格式输出就崩）。本项目优先 function calling，ReAct 仅作弱模型降级。

**Q2：工具调用循环里，工具结果怎么传回模型？**
function calling 路径：把工具结果包成 `ToolMessage`（带对应的 tool_call_id）追加进 messages，再次调用模型——模型看到工具结果后继续推理。ReAct 路径：把 `Observation: <结果>` 作为新的 user 消息追加。两者都是「把结果回灌进对话上下文」。

**Q3：多个工具能并行调用吗？**
OpenAI function calling 支持一次返回多个 tool_calls（并行工具调用）。本项目 `run_function_calling` 里遍历执行 gathered 的所有 tool_calls 再统一回灌。是否真并行执行取决于实现，这里是顺序 await（个人场景够用，要提速可改 asyncio.gather）。

**Q4：流式输出时工具调用怎么和文本 token 区分？**
模型流式输出时，普通内容在 chunk.content（推 token 事件），工具调用信息在 chunk 累积后的 tool_calls 字段。本项目边 astream 边 yield token，流结束后检查 gathered.tool_calls 决定是否还要调工具。

**Q5：如果模型一直不调用工具、凭空乱答怎么办？**
靠 prompt 引导（system prompt 说明有哪些工具、什么时候该用）+ 工具 description 写清场景。但模型最终是否调用不可强制。可加策略：检测到答案可能需要私有数据却没调工具时提示。本项目信任模型决策 + description 引导。

**Q6：SSE 断线了怎么办？**
SSE 原生支持断线自动重连（EventSource）。但本项目用 fetch + ReadableStream（为了带 POST body 和 token），需自己处理。当前简单实现：断线则本轮失败，用户重发。生产可加断点续传（记录已发 token 偏移）。

**Q7：会话历史无限增长怎么办？**
当前取最近 10 轮滑动窗口。更优方案：超过阈值时用 LLM 对早期历史做摘要压缩（summary memory），保留摘要 + 最近几轮原文，兼顾上下文完整性和 token 成本。

**Q8：怎么评估 Agent 回答质量？**
①工具是否选对（人工标注 case 看路由准确率）；②答案是否有引用支撑（RAG 可溯源）；③端到端人工评测。生产可引入 LLM-as-judge 自动打分或用户反馈（赞/踩）。
