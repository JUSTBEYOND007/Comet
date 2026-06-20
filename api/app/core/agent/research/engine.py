"""研究编排：串起 规划 → 检索（四源）→ 分章节写作 → 汇总，产出统一事件流。

本模块是**纯异步生成器**，与传输层解耦：
- 在线发起：由 research_service 在后台任务里消费，事件经 Redis bus 广播给前端（可断线续传）。
- 定时任务（②）：将来由 Celery worker 直接消费同一引擎，无需 bus。

产出事件（dict）：
  {"type": "status", "phase": str, "detail": str}
  {"type": "plan", "title": str, "sections": [...], "queries": [...]}
  {"type": "sources", "sources": [{index,type,title,url}]}
  {"type": "section_start", "heading": str}
  {"type": "token", "text": str}
  {"type": "section_done", "heading": str}
  {"type": "report", "title": str, "markdown": str, "sources": [...]}
  {"type": "error", "message": str}
"""
import asyncio
import re
import uuid
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.agent.research.curator import curate_outline
from app.core.agent.research.distiller import distill_sources
from app.core.agent.research.models import (
    Learning,
    Source,
)
from app.core.agent.research.planner import make_plan
from app.core.agent.research.reflector import find_gap_queries
from app.core.agent.research.retriever import (
    assign_indices,
    gather_kb_sources,
    gather_mcp_sources,
    gather_web_sources,
    get_websearch_config,
)
from app.core.agent.research.writer import summarize, write_section_stream
from app.core.logging import get_logger

logger = get_logger(__name__)

_CITATION_RE = re.compile(r"\[来源\s*(\d+)\]")


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    try:
        return urlparse(url).netloc or ""
    except Exception:  # noqa: BLE001
        return ""


def _linkify_citations(text: str, sources: list[Source]) -> str:
    """把正文里的 [来源N] 角标替换为带说明的可点链接。

    - 有网址的来源：渲染为 [N]，链接 title 写明「来源标题 · 域名」，悬停即可预知跳转目标。
    - 无网址的来源（知识库/工具）：保留为 [N]，title 标注其名称与类型。
    """
    meta = {s.index: s for s in sources}

    def _repl(m: re.Match) -> str:
        idx = int(m.group(1))
        s = meta.get(idx)
        if s is None:
            return f"\\[{idx}\\]"
        # markdown link title 用双引号包裹，标题里的双引号转单引号避免截断
        title = (s.title or "").replace('"', "'").strip()
        # 角标文字用的短标题（截断，避免正文过长）
        short = title[:16] + "…" if len(title) > 16 else title
        if s.url:
            dom = _domain(s.url)
            hint = f"{title} · {dom}" if dom else title
            # 链接文字直接带上来源标题，手机端无需悬停也能看懂跳转目标
            label = f"{idx} · {short}" if short else (dom or str(idx))
            return f'[\\[{label}\\]]({s.url} "{hint}")'
        # 无网址（知识库/工具）：标注来源名称，文末「参考来源」可查
        label = f"{idx} · {short}" if short else str(idx)
        return f"\\[{label}\\]"

    return _CITATION_RE.sub(_repl, text)


def _source_brief(sources: list[Source]) -> list[dict]:
    """给前端的来源简要（不含正文，避免事件过大）。"""
    return [
        {"index": s.index, "type": s.type, "title": s.title, "url": s.url}
        for s in sources
    ]


def _build_markdown(
    title: str,
    summary: dict,
    sections: list[tuple[str, str]],
    sources: list[Source],
) -> str:
    """拼装最终报告 Markdown：标题 / TL;DR / 核心要点 / 各章节 / 参考来源。

    正文里的 [来源N] 角标会被替换为指向来源网址的可点链接（无网址的保留为 [N]）。
    """
    lines: list[str] = [f"# {title}", ""]
    tldr = (summary.get("tldr") or "").strip()
    if tldr:
        lines += [f"> {_linkify_citations(tldr, sources)}", ""]
    key_points = summary.get("key_points") or []
    if key_points:
        lines += ["## 核心要点", ""]
        lines += [f"- {_linkify_citations(p, sources)}" for p in key_points]
        lines.append("")
    for heading, content in sections:
        lines += [
            f"## {heading}",
            "",
            _linkify_citations(content.strip(), sources),
            "",
        ]
    if sources:
        lines += ["## 参考来源", ""]
        lines += [f"{s.index}. {s.cite_label()}" for s in sources]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


async def _pump(holder: dict, make_task) -> AsyncGenerator[dict, None]:
    """跑一个会上报进度的异步任务：边产出 progress 事件边执行，结果存进 holder['result']。

    make_task(emit) 是一个接收 emit 回调、返回结果的协程工厂。
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def _emit(ev: dict) -> None:
        await queue.put(ev)

    async def _runner() -> None:
        try:
            holder["result"] = await make_task(_emit)
        finally:
            await queue.put(None)  # 哨兵：通知 drain 结束

    task = asyncio.create_task(_runner())
    while True:
        ev = await queue.get()
        if ev is None:
            break
        yield ev
    await task


async def run_research(
    session: AsyncSession,
    user_id: uuid.UUID,
    topic: str,
    kb_ids: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    """执行一次深度研究（v2：规划→检索→逐源提炼→反思补搜→大纲整理→分节写作→汇总）。

    内部各步降级处理，尽量产出报告；引擎为纯异步生成器，与传输层解耦。
    """
    from app.core.llm.chat_model import (
        build_default_chat_model,
        supports_function_call,
    )

    topic = (topic or "").strip()
    try:
        model, config = await build_default_chat_model(
            session, user_id, temperature=0.4, streaming=True
        )
    except Exception as e:
        yield {"type": "error", "message": str(e)}
        return
    supports_fc = supports_function_call(config)
    ws = await get_websearch_config(session, user_id)

    # ── 1. 规划（多视角子问题）──
    yield {"type": "status", "phase": "planning", "detail": "正在规划研究提纲与多视角检索策略…"}
    plan = await make_plan(model, topic)
    headings = [s.heading for s in plan.sections]
    yield {
        "type": "plan",
        "title": plan.title,
        "sections": [{"heading": s.heading, "points": s.points} for s in plan.sections],
        "queries": plan.queries,
    }

    # ── 检索辅助（一轮：四源并行 + 续编引用号）──
    async def _retrieve(emit, queries: list[str], start_index: int) -> list[Source]:
        collected: list[Source] = []
        if ws:
            provider, api_key = ws
            try:
                collected += await gather_web_sources(provider, api_key, queries, emit=emit)
            except Exception as e:
                logger.warning("研究联网检索整体失败（继续）: %s", e)
        try:
            collected += await gather_kb_sources(session, user_id, queries, kb_ids, emit=emit)
        except Exception as e:
            logger.warning("研究知识库检索整体失败（继续）: %s", e)
        try:
            collected += await gather_mcp_sources(
                session, user_id, topic, model, supports_fc, emit=emit
            )
        except Exception as e:
            logger.warning("研究 MCP 增强整体失败（继续）: %s", e)
        return assign_indices(collected, start=start_index)

    # ── 2. 检索（第一轮）──
    yield {
        "type": "status",
        "phase": "searching",
        "detail": f"正在围绕 {len(plan.queries)} 个角度检索并抓取资料…",
    }
    h1: dict = {}
    async for ev in _pump(h1, lambda emit: _retrieve(emit, plan.queries, 1)):
        yield ev
    sources: list[Source] = h1.get("result") or []
    yield {"type": "sources", "sources": _source_brief(sources)}

    # ── 3. 逐源提炼（v2 核心：原始资料 → 带来源号的要点）──
    yield {
        "type": "status",
        "phase": "distilling",
        "detail": f"正在从 {len(sources)} 个来源提炼关键要点…",
    }
    h2: dict = {}
    async for ev in _pump(
        h2, lambda emit: distill_sources(model, topic, headings, sources, emit=emit)
    ):
        yield ev
    learnings: list[Learning] = h2.get("result") or []

    # ── 4. 反思补搜（找缺口 → 补一轮检索+提炼，可配关闭）──
    if settings.research_reflection_rounds > 0 and learnings:
        yield {"type": "status", "phase": "reflecting", "detail": "正在评估信息缺口…"}
        gap_queries = await find_gap_queries(model, topic, plan.sections, learnings)
        if gap_queries:
            yield {
                "type": "status",
                "phase": "reflecting",
                "detail": f"补充检索 {len(gap_queries)} 个缺口角度…",
            }
            h3: dict = {}
            async for ev in _pump(
                h3, lambda emit: _retrieve(emit, gap_queries, len(sources) + 1)
            ):
                yield ev
            extra_sources: list[Source] = h3.get("result") or []
            if extra_sources:
                sources += extra_sources
                yield {"type": "sources", "sources": _source_brief(sources)}
                h4: dict = {}
                async for ev in _pump(
                    h4,
                    lambda emit: distill_sources(
                        model, topic, headings, extra_sources, emit=emit
                    ),
                ):
                    yield ev
                learnings += h4.get("result") or []

    # 全局要点截断（按相关度），并赋全局编号供大纲整理引用
    learnings.sort(key=lambda x: x.relevance, reverse=True)
    learnings = learnings[: settings.research_max_learnings]

    # ── 5. 大纲整理（要点 → 每节核心论点 + 证据分配）──
    yield {"type": "status", "phase": "curating", "detail": "正在整理大纲、分配论据…"}
    curated = await curate_outline(model, topic, plan.sections, learnings)

    # ── 6. 分章节写作（吃分配的要点 + 前文摘要避免重复）──
    written: list[tuple[str, str]] = []
    prev_summaries: list[str] = []
    total = len(curated)
    for i, sec in enumerate(curated, 1):
        sec_learnings = [
            learnings[lid - 1] for lid in sec.learning_ids if 1 <= lid <= len(learnings)
        ]
        yield {
            "type": "status",
            "phase": "writing",
            "detail": f"正在撰写第 {i}/{total} 节：{sec.heading}",
        }
        yield {"type": "section_start", "heading": sec.heading}
        buf: list[str] = []
        async for tok in write_section_stream(
            model, plan.title, sec.heading, sec.thesis, sec_learnings, prev_summaries
        ):
            buf.append(tok)
            yield {"type": "token", "text": tok}
        content = "".join(buf).strip() or "（本章节暂无内容）"
        written.append((sec.heading, content))
        prev_summaries.append(f"{sec.heading}：{sec.thesis or '（见正文）'}")
        yield {"type": "section_done", "heading": sec.heading}

    # ── 7. 汇总 ──
    yield {"type": "status", "phase": "summarizing", "detail": "正在提炼摘要与核心要点…"}
    body = "\n\n".join(f"## {h}\n{c}" for h, c in written)
    summary = await summarize(model, plan.title, body)

    # ── 8. 拼装 + 引用映射 ──
    markdown = _build_markdown(plan.title, summary, written, sources)
    yield {
        "type": "report",
        "title": plan.title,
        "markdown": markdown,
        "sources": [
            {"index": s.index, "type": s.type, "title": s.title, "url": s.url}
            for s in sources
        ],
    }


__all__ = ["run_research"]
