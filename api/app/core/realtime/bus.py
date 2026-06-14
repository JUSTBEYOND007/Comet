"""群聊实时事件总线 —— 基于 Redis 发布订阅（Pub/Sub）。

多人实时群聊里，任意成员发言或 AI 角色逐字回答，都通过 publish 把事件发到该群聊
会话的 Redis 频道；每个在场成员开一条 SSE 长连接订阅同一频道，从而实现「谁发消息
全员秒级可见」。复用现有 Redis（Celery broker），跨进程/多 worker 天然广播。

事件结构：{"event": "human_message" | "token" | ..., "data": {...}}

另提供「发言锁」：多个真人同时发言时，避免 AI 调度被重复触发（同一会话同一时刻
只允许一个 AI 回合在生成）。
"""
import json
from collections.abc import AsyncGenerator

from app.core.logging import get_logger
from app.db.redis import get_redis

logger = get_logger(__name__)

# 频道与锁的 key 前缀
_CHANNEL_PREFIX = "groupchat:"
_LOCK_PREFIX = "groupchat:lock:"
# AI 回合锁的最大持有时间（秒），防异常导致死锁
_LOCK_TTL = 120
# 订阅空闲心跳间隔（秒），保活长连接，避免反向代理空闲超时断开
_PING_INTERVAL = 25


def channel_for(conv_id: str) -> str:
    return f"{_CHANNEL_PREFIX}{conv_id}"


def _lock_key(conv_id: str) -> str:
    return f"{_LOCK_PREFIX}{conv_id}"


async def publish(conv_id: str, event: str, data: dict) -> None:
    """向群聊频道广播一个事件。失败只记日志，不阻断主流程。"""
    try:
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        await get_redis().publish(channel_for(conv_id), payload)
    except Exception as e:
        logger.warning("群聊事件广播失败: conv=%s event=%s err=%s", conv_id, event, e)


async def subscribe(conv_id: str) -> AsyncGenerator[dict, None]:
    """订阅群聊频道，持续产出 {"event":..., "data":...} 事件。

    空闲时（无新消息）周期性产出 {"event": "_ping"} 心跳，供上层发 SSE 注释保活，
    避免 nginx/反向代理对长时间无数据的连接做空闲超时断开。
    调用方负责在客户端断开时让本协程结束，finally 会清理订阅。
    """
    redis = get_redis()
    pubsub = redis.pubsub()
    channel = channel_for(conv_id)
    await pubsub.subscribe(channel)
    try:
        while True:
            try:
                raw = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=_PING_INTERVAL
                )
            except Exception as e:
                logger.warning("群聊订阅读取失败: conv=%s err=%s", conv_id, e)
                break
            if raw is None:
                # 超时未收到消息：吐心跳保活
                yield {"event": "_ping"}
                continue
            if raw.get("type") != "message":
                continue
            data = raw.get("data")
            if not data:
                continue
            try:
                yield json.loads(data)
            except (ValueError, TypeError) as e:
                logger.warning("群聊事件解析失败（跳过）: %s", e)
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception as e:
            logger.warning("群聊订阅清理失败: conv=%s err=%s", conv_id, e)


async def acquire_turn_lock(conv_id: str) -> bool:
    """尝试拿下某会话的 AI 回合锁（SET NX EX）。拿到返回 True。"""
    try:
        ok = await get_redis().set(_lock_key(conv_id), "1", nx=True, ex=_LOCK_TTL)
        return bool(ok)
    except Exception as e:
        logger.warning("获取群聊回合锁失败: conv=%s err=%s", conv_id, e)
        # 拿锁失败时保守放行（宁可偶发重复也不卡死对话）
        return True


async def release_turn_lock(conv_id: str) -> None:
    try:
        await get_redis().delete(_lock_key(conv_id))
    except Exception as e:
        logger.warning("释放群聊回合锁失败: conv=%s err=%s", conv_id, e)


# ── 在线状态（presence）：用有序集合存「user_id -> 最近心跳时间戳」，过期判离线 ──
_ONLINE_PREFIX = "groupchat:online:"
# 超过该秒数没有心跳即视为离线（心跳间隔 _PING_INTERVAL=25s，留足余量）
_ONLINE_TTL = 60


def _online_key(conv_id: str) -> str:
    return f"{_ONLINE_PREFIX}{conv_id}"


async def mark_online(conv_id: str, user_id: str) -> None:
    """标记某用户在该群在线（写入/刷新心跳时间戳）。"""
    import time

    try:
        await get_redis().zadd(_online_key(conv_id), {str(user_id): time.time()})
    except Exception as e:
        logger.warning("标记在线失败: conv=%s user=%s err=%s", conv_id, user_id, e)


async def mark_offline(conv_id: str, user_id: str) -> None:
    """移除某用户的在线标记。"""
    try:
        await get_redis().zrem(_online_key(conv_id), str(user_id))
    except Exception as e:
        logger.warning("标记离线失败: conv=%s user=%s err=%s", conv_id, user_id, e)


async def list_online(conv_id: str) -> set[str]:
    """返回该群当前在线的 user_id 集合（清理超时项后取剩余）。"""
    import time

    try:
        r = get_redis()
        cutoff = time.time() - _ONLINE_TTL
        await r.zremrangebyscore(_online_key(conv_id), 0, cutoff)
        members = await r.zrange(_online_key(conv_id), 0, -1)
        return {str(m) for m in members}
    except Exception as e:
        logger.warning("获取在线列表失败: conv=%s err=%s", conv_id, e)
        return set()
