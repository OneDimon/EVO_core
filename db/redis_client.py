"""Redis клиент: горячий кэш сессий + асинхронная очередь записи."""
import redis.asyncio as redis
import os, json

_redis = None

async def get_redis():
    global _redis
    if _redis is None:
        _redis = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    return _redis

EMBED_CACHE_TTL = 7 * 86400  # 7 дней — эмбеддинг детерминирован для одного
                              # текста на одной модели, не протухает по
                              # смыслу; TTL здесь только на случай смены
                              # модели эмбеддинга без явной инвалидации кэша


async def get_cached_embedding(normalized_text: str) -> list | None:
    """
    Глобальный (НЕ по сессии, в отличие от cache_symbol/cache_session_plan
    ниже) кэш векторов эмбеддинга по точному совпадению текста.

    Цель — не ускорить поиск в БД (HNSW и так быстрый), а пропустить сам
    оплачиваемый вызов ai_router.embed() для буквально повторяющихся
    запросов от РАЗНЫХ сессий/пользователей. Ответ по-прежнему ищется
    заново в scl_symbols при каждом обращении (find_symbols выполняется
    всегда) — устаревших результатов быть не может, кэшируется только
    сам вектор, не итоговая выдача.
    """
    import hashlib
    r = await get_redis()
    key = f"evo:embed_cache:{hashlib.sha256(normalized_text.encode()).hexdigest()}"
    raw = await r.get(key)
    return json.loads(raw) if raw else None


async def cache_embedding(normalized_text: str, vector: list):
    import hashlib
    r = await get_redis()
    key = f"evo:embed_cache:{hashlib.sha256(normalized_text.encode()).hexdigest()}"
    await r.setex(key, EMBED_CACHE_TTL, json.dumps(vector))


async def cache_symbol(session_id: str, symbol_id: str, data: dict, ttl: int = 3600):
    r = await get_redis()
    # fix: data приходит из find_symbols() — dict(asyncpg.Record), содержит
    # datetime-объекты (last_updated, last_tech_check, created_at). Обычный
    # json.dumps падает на них с TypeError — это роняло КАЖДЫЙ успешный
    # поиск в проде (find_symbols всегда возвращает хотя бы одну timestamp-
    # колонку). Найдено живым тестовым прогоном 2026-07-07.
    # default=str конвертирует datetime/Decimal/etc в строку для кэша —
    # это временный кэш для отображения, не источник истины, потеря
    # типизации здесь не критична.
    await r.setex(f"evo:session:{session_id}:sym:{symbol_id}", ttl,
                   json.dumps(data, default=str))

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

async def cache_candidate_ligature(session_id: str, ligature_id: str, ttl: int = 3600):
    """
    Сессия воспользовалась кандидатом на лигатуру (Сценарий Б — сборка по
    частям, ещё не подтверждена). Хранится, чтобы archivist.py::archive()
    смог утвердить именно её после подтверждения работоспособности —
    двухфазно: записан как кандидат сразу, утверждён (is_universal=TRUE)
    только после реального подтверждения, не раньше.
    """
    r = await get_redis()
    await r.setex(f"evo:session:{session_id}:candidate_ligature", ttl, ligature_id)

async def get_and_clear_candidate_ligature(session_id: str) -> str | None:
    """get+delete — утверждение кандидата происходит не более одного раза
    за сессию, даже если /result вызовут повторно."""
    r = await get_redis()
    key = f"evo:session:{session_id}:candidate_ligature"
    ligature_id = await r.get(key)
    if ligature_id:
        await r.delete(key)
        return ligature_id.decode() if isinstance(ligature_id, bytes) else ligature_id
    return None

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
