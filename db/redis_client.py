"""Redis клиент: горячий кэш сессий + асинхронная очередь записи."""
import redis.asyncio as redis
import os, json

_redis = None

async def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return _redis

async def cache_symbol(session_id: str, symbol_id: str, data: dict, ttl: int = 3600):
    r = await get_redis()
    await r.setex(f"evo:session:{session_id}:sym:{symbol_id}", ttl, json.dumps(data))

async def get_cached_symbol(session_id: str, symbol_id: str) -> dict | None:
    r = await get_redis()
    raw = await r.get(f"evo:session:{session_id}:sym:{symbol_id}")
    return json.loads(raw) if raw else None

async def cache_session_plan(session_id: str, plan: list[dict], ttl: int = 3600):
    r = await get_redis()
    await r.setex(f"evo:session:{session_id}:plan", ttl, json.dumps(plan))

async def get_session_plan(session_id: str) -> list | None:
    r = await get_redis()
    raw = await r.get(f"evo:session:{session_id}:plan")
    return json.loads(raw) if raw else None

async def flush_session(session_id: str):
    """Схлопывание сессии — физическое удаление из Redis."""
    r = await get_redis()
    keys = await r.keys(f"evo:session:{session_id}:*")
    if keys:
        await r.delete(*keys)

async def enqueue_write(data: dict):
    """Асинхронная очередь записи — пользователь не ждёт."""
    r = await get_redis()
    await r.lpush("evo:write_queue", json.dumps(data))

async def record_rps(rps: float, session_cnt: int):
    """Статистика нагрузки для режима СОН."""
    r = await get_redis()
    import time
    hour_key = f"evo:rps:{int(time.time() // 3600)}"
    await r.hset(hour_key, mapping={"rps": rps, "sessions": session_cnt})
    await r.expire(hour_key, 86400 * 7)  # 7 дней
