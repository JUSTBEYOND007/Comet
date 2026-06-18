"""定时/主动任务业务服务：CRUD + 下次运行时间计算 + 立即运行一次。

调度本身由 Celery beat 每分钟心跳扫表触发（见 tasks/agent_task.py），本服务只管
任务的增删改查与 next_run_at 维护。
"""
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.logging import get_logger
from app.models.agent_task_model import (
    TRIGGER_DAILY,
    TRIGGER_INTERVAL,
    TRIGGER_WEEKLY,
    AgentTask,
)
from app.repositories.agent_task_repository import AgentTaskRepository
from app.schemas.agent_task_schema import AgentTaskUpsertRequest

logger = get_logger(__name__)

TZ = ZoneInfo("Asia/Shanghai")


def _parse_hhmm(text: str | None) -> tuple[int, int]:
    """解析 'HH:MM'，非法则回退 09:00。"""
    try:
        hh, mm = (text or "09:00").split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        pass
    return 9, 0


def compute_next_run(task: AgentTask, from_dt: datetime | None = None) -> datetime:
    """根据触发规则计算下次运行时间（Asia/Shanghai 时区感知）。"""
    now = from_dt or datetime.now(TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TZ)

    if task.trigger_type == TRIGGER_INTERVAL:
        hours = task.trigger_interval_hours or 24
        return now + timedelta(hours=hours)

    h, m = _parse_hhmm(task.trigger_time)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)

    if task.trigger_type == TRIGGER_WEEKLY:
        weekday = task.trigger_weekday if task.trigger_weekday is not None else 0
        days_ahead = (weekday - now.weekday()) % 7
        target = target + timedelta(days=days_ahead)
        if target <= now:
            target = target + timedelta(days=7)
        return target

    # daily
    if target <= now:
        target = target + timedelta(days=1)
    return target


class AgentTaskService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AgentTaskRepository(session)

    async def create(
        self, user_id: uuid.UUID, body: AgentTaskUpsertRequest
    ) -> AgentTask:
        self._validate(body)
        task = AgentTask(
            user_id=user_id,
            name=body.name.strip(),
            instruction=body.instruction.strip(),
            kb_ids=body.kb_ids or None,
            trigger_type=body.trigger_type,
            trigger_time=body.trigger_time,
            trigger_weekday=body.trigger_weekday,
            trigger_interval_hours=body.trigger_interval_hours,
            enabled=body.enabled,
        )
        task.next_run_at = compute_next_run(task) if body.enabled else None
        created = await self.repo.create(task)
        logger.info("创建定时任务: user=%s id=%s next=%s", user_id, created.id, created.next_run_at)
        return created

    async def update(
        self, user_id: uuid.UUID, task_id: uuid.UUID, body: AgentTaskUpsertRequest
    ) -> AgentTask:
        self._validate(body)
        task = await self._get_or_404(user_id, task_id)
        task.name = body.name.strip()
        task.instruction = body.instruction.strip()
        task.kb_ids = body.kb_ids or None
        task.trigger_type = body.trigger_type
        task.trigger_time = body.trigger_time
        task.trigger_weekday = body.trigger_weekday
        task.trigger_interval_hours = body.trigger_interval_hours
        task.enabled = body.enabled
        task.next_run_at = compute_next_run(task) if body.enabled else None
        return await self.repo.save(task)

    async def set_enabled(
        self, user_id: uuid.UUID, task_id: uuid.UUID, enabled: bool
    ) -> AgentTask:
        task = await self._get_or_404(user_id, task_id)
        task.enabled = enabled
        task.next_run_at = compute_next_run(task) if enabled else None
        return await self.repo.save(task)

    async def delete(self, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
        task = await self._get_or_404(user_id, task_id)
        await self.repo.delete(task)

    async def run_now(self, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
        """立即运行一次（派发 Celery 执行任务，不改 next_run_at）。"""
        await self._get_or_404(user_id, task_id)
        from app.tasks.agent_task import run_agent_task_task

        run_agent_task_task.delay(str(task_id))

    async def list_tasks(self, user_id: uuid.UUID) -> list[dict]:
        tasks = await self.repo.list_by_user(user_id)
        return [self.to_dict(t) for t in tasks]

    async def _get_or_404(
        self, user_id: uuid.UUID, task_id: uuid.UUID
    ) -> AgentTask:
        task = await self.repo.get(user_id, task_id)
        if not task:
            raise BizError("任务不存在", code=3060, status_code=404)
        return task

    @staticmethod
    def _validate(body: AgentTaskUpsertRequest) -> None:
        if body.trigger_type in (TRIGGER_DAILY, TRIGGER_WEEKLY) and not body.trigger_time:
            raise BizError("请设置触发时间（HH:MM）", code=3061)
        if body.trigger_type == TRIGGER_WEEKLY and body.trigger_weekday is None:
            raise BizError("请选择每周触发的星期", code=3062)
        if body.trigger_type == TRIGGER_INTERVAL and not body.trigger_interval_hours:
            raise BizError("请设置间隔小时数", code=3063)

    @staticmethod
    def to_dict(t: AgentTask) -> dict:
        return {
            "id": str(t.id),
            "name": t.name,
            "instruction": t.instruction,
            "kb_ids": t.kb_ids or [],
            "trigger_type": t.trigger_type,
            "trigger_time": t.trigger_time,
            "trigger_weekday": t.trigger_weekday,
            "trigger_interval_hours": t.trigger_interval_hours,
            "enabled": t.enabled,
            "last_run_at": t.last_run_at.isoformat() if t.last_run_at else None,
            "last_status": t.last_status or None,
            "next_run_at": t.next_run_at.isoformat() if t.next_run_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
