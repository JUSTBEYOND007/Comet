"""研究规划：用 LLM 把一句话主题拆成报告标题 + 章节提纲 + 多角度子查询。"""
from datetime import date

from langchain_openai import ChatOpenAI

from app.config import settings
from app.core.agent.research.models import PlanSection, ResearchPlan
from app.core.agent.research.prompt_renderer import render_research_prompt
from app.core.logging import get_logger
from app.core.memory.json_utils import parse_json_object

logger = get_logger(__name__)

MIN_SECTIONS = 3
MIN_QUERIES = 3


def _fallback_plan(topic: str) -> ResearchPlan:
    """规划失败兜底：单章节 + 用主题本身作查询，保证流程不中断。"""
    return ResearchPlan(
        title=topic[:30] or "研究报告",
        sections=[PlanSection(heading="综合分析", points="围绕主题综合检索资料并归纳")],
        queries=[topic],
    )


async def make_plan(model: ChatOpenAI, topic: str) -> ResearchPlan:
    """生成研究计划；任何异常或解析失败都降级到兜底计划。"""
    topic = (topic or "").strip()
    if not topic:
        return _fallback_plan("研究报告")

    prompt = render_research_prompt(
        "plan.jinja2",
        topic=topic,
        today=date.today().isoformat(),
        min_sections=MIN_SECTIONS,
        max_sections=settings.research_max_sections,
        min_queries=MIN_QUERIES,
        max_queries=settings.research_max_queries,
    )
    try:
        resp = await model.ainvoke(prompt)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
    except Exception as e:
        logger.warning("研究规划 LLM 调用失败，用兜底计划: %s", e)
        return _fallback_plan(topic)

    data = parse_json_object(text)
    if not data:
        logger.warning("研究规划解析失败，用兜底计划")
        return _fallback_plan(topic)

    title = (data.get("title") or topic)[:60].strip() or topic[:30]

    sections: list[PlanSection] = []
    for item in data.get("sections") or []:
        if not isinstance(item, dict):
            continue
        heading = (item.get("heading") or "").strip()
        if not heading:
            continue
        sections.append(
            PlanSection(heading=heading[:60], points=(item.get("points") or "").strip())
        )
    sections = sections[: settings.research_max_sections]
    if not sections:
        sections = [PlanSection(heading="综合分析", points="围绕主题综合检索资料并归纳")]

    queries: list[str] = []
    for q in data.get("queries") or []:
        if isinstance(q, str) and q.strip():
            queries.append(q.strip())
    # 去重保序
    seen: set[str] = set()
    queries = [q for q in queries if not (q in seen or seen.add(q))]
    queries = queries[: settings.research_max_queries]
    if not queries:
        queries = [topic]

    return ResearchPlan(title=title, sections=sections, queries=queries)


__all__ = ["make_plan"]
