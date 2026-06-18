"""研究写作：分章节撰写（带引用）+ 全文汇总 TL;DR / 核心要点。"""
from collections.abc import AsyncGenerator

from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.agent.research.models import PlanSection, Source
from app.core.agent.research.prompt_renderer import render_research_prompt
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)


def _char_bigrams(text: str) -> set[str]:
    text = "".join(ch for ch in (text or "").lower() if ch.isalnum())
    return {text[i : i + 2] for i in range(len(text) - 1)} if len(text) >= 2 else set()


def pick_sources_for_section(
    section: PlanSection, sources: list[Source], limit: int
) -> list[Source]:
    """为某章节挑选最相关的来源（字符 2-gram 重叠打分），不足则按原序补足。

    保证每个章节都有资料可引用；打分只是排序，不会丢弃全部来源。
    """
    if not sources:
        return []
    key = _char_bigrams(f"{section.heading} {section.points}")
    if not key:
        return sources[:limit]
    scored = []
    for s in sources:
        sig = _char_bigrams(f"{s.title} {s.content[:500]}")
        overlap = len(key & sig)
        scored.append((overlap, s))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored[:limit]]


def _source_payload(sources: list[Source]) -> list[dict]:
    return [
        {"index": s.index, "title": s.title, "content": s.content} for s in sources
    ]


async def write_section_stream(
    model: ChatOpenAI,
    report_title: str,
    section: PlanSection,
    sources: list[Source],
) -> AsyncGenerator[str, None]:
    """流式撰写一个章节，逐 token 产出。失败时产出占位说明（不中断整篇）。"""
    picked = pick_sources_for_section(
        section, sources, settings.research_section_context_sources
    )
    prompt = render_research_prompt(
        "write_section.jinja2",
        report_title=report_title,
        heading=section.heading,
        points=section.points,
        sources=_source_payload(picked),
    )
    got = False
    try:
        async for chunk in model.astream(prompt):
            if chunk.content:
                text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                if text:
                    got = True
                    yield text
    except Exception as e:
        logger.warning("章节撰写失败: heading=%s err=%s", section.heading, e)
        if not got:
            yield f"（本章节生成失败：{e}）"


async def summarize(model: ChatOpenAI, report_title: str, body: str) -> dict:
    """汇总：从正文提炼 TL;DR + 核心要点。失败返回空结构（不阻断落库）。"""
    prompt = render_research_prompt(
        "summarize.jinja2", report_title=report_title, body=body[:12000]
    )
    try:
        resp = await model.ainvoke(prompt)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as e:
        logger.warning("研究汇总 LLM 调用失败: %s", e)
        return {"tldr": "", "key_points": []}

    data = parse_json_object(text) or {}
    tldr = (data.get("tldr") or "").strip()
    key_points = [
        p.strip() for p in (data.get("key_points") or []) if isinstance(p, str) and p.strip()
    ]
    return {"tldr": tldr, "key_points": key_points}


__all__ = ["pick_sources_for_section", "write_section_stream", "summarize"]
