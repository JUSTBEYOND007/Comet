"""定时/主动任务 Celery 任务：

- heartbeat：每分钟扫 agent_tasks 找到期的，派发执行 + 立即推进 next_run_at（防重复触发）。
- run_agent_task：跑深度研究引擎，产出报告（research_reports，task_id 关联），回写任务状态。

与其他 beat 任务一致：任务级独立引擎（NullPool）+ 独立事件循环（asyncio.run）。
"""
import asyncio
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401  确保 ORM 模型注册
from app.celery_app import celery_app
from app.core.agent.research.engine import run_research
from app.core.logging import get_logger
from app.db.postgres import create_task_engine
from app.models.agent_task_model import (
    TASK_RUN_DONE,
    TASK_RUN_FAILED,
    TASK_RUN_RUNNING,
)
from app.models.research_report_model import (
    RESEARCH_STATUS_DONE,
    RESEARCH_STATUS_FAILED,
    RESEARCH_STATUS_PENDING,
    ResearchReport,
)
from app.repositories.agent_task_repository import AgentTaskRepository
from app.repositories.research_report_repository import ResearchReportRepository
from app.services.agent_task_service import compute_next_run

logger = get_logger(__name__)


# ── 每分钟心跳：扫到期任务 → 派发 + 推进 next_run_at ──

async def _heartbeat() -> int:
    engine_db = create_task_engine()
    sm = async_sessionmaker(engine_db, expire_on_commit=False, class_=AsyncSession)
    dispatched = 0
    try:
        async with sm() as session:
            repo = AgentTaskRepository(session)
            due = await repo.list_due()
            for task in due:
                # 先把 next_run_at 推进到下次，避免本轮未跑完下一分钟重复触发
                try:
                    task.next_run_at = compute_next_run(task)
                    await repo.save(task)
                except Exception as e:
                    logger.warning("推进任务下次运行时间失败: id=%s err=%s", task.id, e)
                    continue
                run_agent_task_task.delay(str(task.id))
                dispatched += 1
    finally:
        await engine_db.dispose()
    if dispatched:
        logger.info("定时任务心跳：派发 %d 个到期任务", dispatched)
    return dispatched


@celery_app.task(name="app.tasks.agent_task.heartbeat")
def heartbeat_task() -> int:
    """每分钟调度心跳的 Celery 任务入口。"""
    return asyncio.run(_heartbeat())


# ── 执行一次研究任务 ──

async def _run_task(task_id: str) -> None:
    tid = uuid.UUID(task_id)
    engine_db = create_task_engine()
    sm = async_sessionmaker(engine_db, expire_on_commit=False, class_=AsyncSession)
    try:
        async with sm() as session:
            task_repo = AgentTaskRepository(session)
            task = await task_repo.get_by_id(tid)
            if not task:
                logger.warning("定时任务执行：任务不存在 %s", tid)
                return

            # 建报告行（task_id 关联），标任务运行中
            report = await ResearchReportRepository(session).create(
                ResearchReport(
                    user_id=task.user_id,
                    topic=task.instruction,
                    status=RESEARCH_STATUS_PENDING,
                    task_id=task.id,
                )
            )
            task.last_status = TASK_RUN_RUNNING
            await task_repo.save(task)

            kb_ids = [str(k) for k in (task.kb_ids or [])] or None
            ok = await _execute_research(
                session, report.id, task.user_id, task.instruction, kb_ids
            )

            # 回写任务最近运行状态/时间
            task.last_run_at = datetime.now()
            task.last_status = TASK_RUN_DONE if ok else TASK_RUN_FAILED
            await task_repo.save(task)
            logger.info("定时任务执行完成: id=%s ok=%s", tid, ok)
    finally:
        await engine_db.dispose()


async def _execute_research(
    session: AsyncSession,
    report_id: uuid.UUID,
    user_id: uuid.UUID,
    topic: str,
    kb_ids: list[str] | None,
) -> bool:
    """消费研究引擎事件并把最终报告落库（无 SSE/bus，后台直跑）。"""
    repo = ResearchReportRepository(session)
    final_md: str | None = None
    final_sources: list = []
    final_title: str | None = None
    outline: dict | None = None
    partial = ""
    try:
        async for ev in run_research(session, user_id, topic, kb_ids):
            etype = ev.get("type")
            if etype == "plan":
                outline = {
                    "title": ev.get("title", ""),
                    "sections": ev.get("sections", []),
                    "queries": ev.get("queries", []),
                }
                final_title = ev.get("title")
            elif etype == "section_start":
                partial += f"\n\n## {ev.get('heading', '')}\n\n"
            elif etype == "token":
                partial += ev.get("text", "")
            elif etype == "report":
                final_md = ev.get("markdown", "")
                final_sources = ev.get("sources", [])
                final_title = ev.get("title", final_title)
            elif etype == "error":
                raise RuntimeError(ev.get("message", "研究失败"))
        if final_md is None:
            raise RuntimeError("研究未产出报告")
        report = await repo.get_by_id(report_id)
        if report:
            report.title = (final_title or topic)[:255]
            report.report_md = final_md
            report.sources = final_sources
            report.outline = outline
            report.status = RESEARCH_STATUS_DONE
            report.error_msg = None
            await repo.save(report)
        return True
    except Exception as e:
        logger.error("定时研究执行失败: report=%s err=%s", report_id, e, exc_info=True)
        report = await repo.get_by_id(report_id)
        if report:
            report.status = RESEARCH_STATUS_FAILED
            report.error_msg = str(e)[:2000]
            if partial.strip():
                report.report_md = partial
            report.outline = outline
            await repo.save(report)
        return False


@celery_app.task(name="app.tasks.agent_task.run")
def run_agent_task_task(task_id: str) -> str:
    """执行一次定时研究任务的 Celery 入口。"""
    asyncio.run(_run_task(task_id))
    return task_id
