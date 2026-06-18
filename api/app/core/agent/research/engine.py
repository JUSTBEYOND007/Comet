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

from app.core.agent.research.models import (
    SOURCE_KB,
    SOURCE_MCP,
    SOURCE_WEB,
    Source,
)
from app.core.agent.research.planner import make_plan
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

_SOURCE_KIND_CN = {SOURCE_WEB: "网页", SOURCE_KB: "知识库", SOURCE_MCP: "工具"}

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


async def run_research(
    session: AsyncSession,
    user_id: uuid.UUID,
    topic: str,
    kb_ids: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    """执行一次深度研究，逐步产出事件。内部各步降级处理，尽量产出报告。"""
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

    # ── 1. 规划 ──
    yield {"type": "status", "phase": "planning", "detail": "正在规划研究提纲与检索策略…"}
    plan = await make_plan(model, topic)
    yield {
        "type": "plan",
        "title": plan.title,
        "sections": [{"heading": s.heading, "points": s.points} for s in plan.sections],
        "queries": plan.queries,
    }

    # ── 2. 检索（四源）──
    yield {
        "type": "status",
        "phase": "searching",
        "detail": f"正在围绕 {len(plan.queries)} 个角度检索并抓取资料…",
    }
    ws = await get_websearch_config(session, user_id)

    # 用队列把检索内部的细粒度进度（搜索/抓取/命中/调用工具）实时透出
    queue: asyncio.Queue = asyncio.Queue()

    async def _emit(ev: dict) -> None:
        await queue.put(ev)

    async def _gather_all() -> list[Source]:
        collected: list[Source] = []
        if ws:
            provider, api_key = ws
            try:
                collected += await gather_web_sources(
                    provider, api_key, plan.queries, emit=_emit
                )
            except Exception as e:
                logger.warning("研究联网检索整体失败（继续）: %s", e)
        try:
            collected += await gather_kb_sources(
                session, user_id, plan.queries, kb_ids, emit=_emit
            )
        except Exception as e:
            logger.warning("研究知识库检索整体失败（继续）: %s", e)
        try:
            collected += await gather_mcp_sources(
                session, user_id, topic, model, supports_fc, emit=_emit
            )
        except Exception as e:
            logger.warning("研究 MCP 增强整体失败（继续）: %s", e)
        return collected

    gather_task = asyncio.create_task(_gather_all())
    # 边检索边把进度事件吐给前端，直到检索任务结束
    while True:
        if gather_task.done() and queue.empty():
            break
        try:
            ev = await asyncio.wait_for(queue.get(), timeout=0.5)
            yield ev
        except (TimeoutError, asyncio.TimeoutError):
            continue
    sources = await gather_task

    sources = assign_indices(sources)
    counts = {k: 0 for k in _SOURCE_KIND_CN}
    for s in sources:
        counts[s.type] = counts.get(s.type, 0) + 1
    detail = "、".join(
        f"{_SOURCE_KIND_CN[k]} {v}" for k, v in counts.items() if v
    ) or "未获取到外部资料"
    yield {
        "type": "status",
        "phase": "searching_done",
        "detail": f"已收集来源：{detail}",
    }
    yield {"type": "sources", "sources": _source_brief(sources)}

    # ── 3. 分章节写作 ──
    written: list[tuple[str, str]] = []
    for i, section in enumerate(plan.sections, 1):
        yield {
            "type": "status",
            "phase": "writing",
            "detail": f"正在撰写第 {i}/{len(plan.sections)} 节：{section.heading}",
        }
        yield {"type": "section_start", "heading": section.heading}
        buf: list[str] = []
        async for tok in write_section_stream(model, plan.title, section, sources):
            buf.append(tok)
            yield {"type": "token", "text": tok}
        content = "".join(buf).strip() or "（本章节暂无内容）"
        written.append((section.heading, content))
        yield {"type": "section_done", "heading": section.heading}

    # ── 4. 汇总 ──
    yield {"type": "status", "phase": "summarizing", "detail": "正在提炼摘要与核心要点…"}
    body = "\n\n".join(f"## {h}\n{c}" for h, c in written)
    summary = await summarize(model, plan.title, body)

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
