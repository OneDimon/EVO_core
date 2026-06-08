"""
Bootstrap v2 — реальное наполнение из GitHub Trending + Gemini.
Алгоритм:
1. Gemini анализирует топ востребованных тем из GitHub/npm/PyPI
2. По убыванию востребованности формирует символы
3. Сначала глобальные принципы, затем конкретные инструменты
4. Все символы проходят YMS-MMM упрощённый (consistency check)
Правила: SCL_FRACTAL_PROTOCOL.md, bootstrap протокол раздел 5
"""
import asyncio, sys, os, json, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("evo.bootstrap")

# ── Иерархия наполнения (от глобальных к частным) ───────────────────────────
# Уровень 1: Глобальные принципы (Философия, Логика, Математика)
# Уровень 2: Общие технические паттерны (Кибернетика, Алгоритмика)
# Уровень 3: Конкретные инструменты (τ^auto, τ^db, τ^infra)
# Уровень 4: Частные инструкции (ZennoPoster, n8n воркфлоу)

BOOTSTRAP_PROMPT = """
Ты заполняешь базу знаний EVO-core. Сгенерируй JSON массив из 40 символов знаний
по убыванию востребованности для разработчиков в 2025-2026 году.

СТРОГО соблюдай иерархию:
1. Сначала 5 глобальных принципов (логика, алгоритмы, паттерны)
2. Затем 10 общих технических паттернов (async, REST, микросервисы)
3. Затем 15 популярных инструментов (FastAPI, PostgreSQL, Redis, Docker, n8n)
4. Затем 10 частных решений (ZennoPoster, крипто-шлюзы, автоматизация)

Каждый символ: {"science":"X","section":"Y","subsection":"Z","label":"задача: [ЧТО РЕШИТЬ] | лекарство: [КАК РЕШИТЬ]","applicable_stacks":["list"]}

Возвращай ТОЛЬКО валидный JSON массив, без markdown, без пояснений.
"""

async def fetch_trending_topics() -> list[str]:
    """Получает реальные топ-темы через Gemini."""
    from core.ai_router import ai_router
    prompt = (
        "Перечисли 20 самых востребованных технологий/инструментов для backend-разработчиков "
        "в 2025-2026 году по данным GitHub Trending, Stack Overflow, npm. "
        "Только названия через запятую, без объяснений."
    )
    result = await ai_router.generate(prompt, task="bootstrap_topics")
    topics = [t.strip() for t in result.split(',') if t.strip()]
    log.info(f"[Bootstrap] Топ-темы: {topics[:10]}")
    return topics


async def generate_symbols_batch(topics: list[str]) -> list[dict]:
    """Генерирует символы через Gemini по реальным трендам."""
    from core.ai_router import ai_router
    topics_str = ", ".join(topics[:20])
    prompt = BOOTSTRAP_PROMPT + f"\n\nФокус на технологиях: {topics_str}"

    result = await ai_router.generate(prompt, task="bootstrap_symbols")
    # Очищаем от markdown
    result = result.strip()
    if result.startswith("```"):
        result = result.split("```")[1]
        if result.startswith("json"):
            result = result[4:]
    result = result.strip()

    try:
        symbols = json.loads(result)
        if isinstance(symbols, list):
            log.info(f"[Bootstrap] Gemini вернул {len(symbols)} символов")
            return symbols
    except json.JSONDecodeError as e:
        log.warning(f"[Bootstrap] JSON parse error: {e}, используем fallback")

    return []


async def get_fallback_symbols() -> list[dict]:
    """Статический fallback если Gemini недоступен."""
    return [
        {"science":"Философия","section":"Логика","subsection":"Верификация",
         "label":"задача: проверить истинность утверждения | лекарство: тройное независимое подтверждение",
         "applicable_stacks":[]},
        {"science":"Кибернетика","section":"Алгоритмика","subsection":"Поиск",
         "label":"задача: семантический поиск по смыслу | лекарство: cosine similarity + pgvector",
         "applicable_stacks":["postgresql","python"]},
        {"science":"Технология","section":"Веб","subsection":"FastAPI",
         "label":"задача: async REST API с валидацией | лекарство: FastAPI + Pydantic v2",
         "applicable_stacks":["python","fastapi"]},
        {"science":"Технология","section":"БД","subsection":"PostgreSQL",
         "label":"задача: connection pool для высокой нагрузки | лекарство: asyncpg pool min=2 max=20",
         "applicable_stacks":["python","postgresql"]},
        {"science":"Технология","section":"БД","subsection":"Redis",
         "label":"задача: горячий кэш с TTL | лекарство: redis.asyncio setex(key, ttl, value)",
         "applicable_stacks":["python","redis"]},
        {"science":"Технология","section":"Инфраструктура","subsection":"Docker",
         "label":"задача: контейнеризация с healthcheck | лекарство: docker-compose + depends_on condition",
         "applicable_stacks":["docker"]},
        {"science":"Технология","section":"Автоматизация","subsection":"n8n",
         "label":"задача: webhook триггер с обработкой JSON | лекарство: Webhook Node + Set Node + Code Node",
         "applicable_stacks":["n8n","nodejs"]},
        {"science":"Технология","section":"Автоматизация","subsection":"ZennoPoster",
         "label":"задача: авторизация через куки без пароля | лекарство: CookieManager + SaveCookies после входа",
         "applicable_stacks":["zennoposter"]},
        {"science":"Экономика","section":"Платежи","subsection":"Крипто",
         "label":"задача: приём крипто без KYC | лекарство: TON wallet direct + webhook подтверждение",
         "applicable_stacks":["ton","nodejs"]},
        {"science":"Технология","section":"ИИ","subsection":"Роутинг",
         "label":"задача: fallback между LLM провайдерами | лекарство: цепочка retry с exponential backoff",
         "applicable_stacks":["python","litellm"]},
        {"science":"Кибернетика","section":"Безопасность","subsection":"Auth",
         "label":"задача: API аутентификация без сессий | лекарство: JWT Bearer + проверка в middleware",
         "applicable_stacks":["python","fastapi"]},
        {"science":"Технология","section":"Компрессия","subsection":"zstd",
         "label":"задача: сжатие текстовых данных в памяти | лекарство: zstandard compress level=3 in-memory",
         "applicable_stacks":["python"]},
        {"science":"Математика","section":"Статистика","subsection":"Векторы",
         "label":"задача: найти похожие документы | лекарство: IVFFlat индекс + cosine_ops в pgvector",
         "applicable_stacks":["postgresql","python"]},
        {"science":"Технология","section":"Инфраструктура","subsection":"Nginx",
         "label":"задача: reverse proxy с rate limiting | лекарство: limit_req_zone + proxy_pass",
         "applicable_stacks":["nginx","docker"]},
        {"science":"Технология","section":"Мессенджеры","subsection":"Telegram",
         "label":"задача: Telegram бот с webhook | лекарство: setWebhook + secret_token верификация",
         "applicable_stacks":["python","telegram"]},
    ]


async def verify_symbol(sym: dict) -> bool:
    """Упрощённая YMS-MMM проверка символа перед записью."""
    required = ["science", "section", "subsection", "label"]
    for field in required:
        if not sym.get(field, "").strip():
            log.warning(f"[Bootstrap] Пропуск: нет поля {field} в {sym}")
            return False
    label = sym.get("label", "")
    if "задача:" not in label or "лекарство:" not in label:
        log.warning(f"[Bootstrap] Пропуск: неверный формат label: {label[:60]}")
        return False
    return True


async def bootstrap():
    from core.ai_router import ai_router
    from core.archivist import _generate_id
    from db.pg_client import insert_symbol, get_pool
    from shards.shard_client import write_cell

    print("=== EVO-core Bootstrap v2 (реальные данные) ===\n")
    pool = await get_pool()

    # Проверяем сколько уже есть
    async with pool.acquire() as conn:
        existing = await conn.fetchval("SELECT COUNT(*) FROM scl_symbols")

    if existing >= 15:
        print(f"✅ База уже содержит {existing} символов. Bootstrap не нужен.")
        print("   Для принудительного запуска: python scripts/bootstrap.py --force")
        if '--force' not in sys.argv:
            await pool.close()
            return

    print(f"Текущих символов: {existing}")

    # Шаг 1: Получить актуальные темы
    print("\n[1/4] Получаем топ-темы из Gemini...")
    try:
        topics = await fetch_trending_topics()
    except Exception as e:
        log.warning(f"Topics fetch failed: {e}, using defaults")
        topics = ["FastAPI", "PostgreSQL", "Redis", "Docker", "n8n", "Python", "Telegram"]

    # Шаг 2: Генерируем символы
    print(f"[2/4] Генерируем символы (топ темы: {', '.join(topics[:5])})...")
    try:
        symbols = await generate_symbols_batch(topics)
    except Exception as e:
        log.warning(f"Generation failed: {e}, using fallback")
        symbols = []

    if len(symbols) < 5:
        print(f"   Gemini вернул {len(symbols)} символов, дополняем fallback-набором")
        fallback = await get_fallback_symbols()
        # Добавляем только те которых нет
        existing_labels = {s.get('label','') for s in symbols}
        for fs in fallback:
            if fs['label'] not in existing_labels:
                symbols.append(fs)

    print(f"   Итого символов для записи: {len(symbols)}")

    # Шаг 3: Верификация и запись
    print("\n[3/4] Верификация и запись...")
    written = 0
    skipped = 0

    for i, sym_data in enumerate(symbols):
        # YMS-MMM упрощённая проверка
        if not await verify_symbol(sym_data):
            skipped += 1
            continue

        try:
            # Генерация ID по нотации SCL
            symbol_id = await _generate_id(
                sym_data['science'],
                sym_data['section'],
                sym_data['subsection']
            )

            # Векторизация
            embed_text = (f"{sym_data['label']} {sym_data['science']} "
                         f"{sym_data['section']} {sym_data['subsection']}")
            vector = await ai_router.embed(embed_text)

            # Запись тела на шард
            shard_path = f"/evo/{sym_data['science'][:3].upper()}/{symbol_id}.zst"
            await write_cell("", shard_path, sym_data['label'], symbol_id=symbol_id)

            # Запись в pgvector
            await insert_symbol({
                "id": symbol_id,
                "label": sym_data['label'],
                "vector": vector,
                "science": sym_data['science'],
                "section": sym_data['section'],
                "subsection": sym_data['subsection'],
                "applicable_stacks": sym_data.get('applicable_stacks', []),
                "shard_host": "",
                "shard_path": shard_path,
            })
            written += 1
            print(f"  ✓ [{written}] {symbol_id}: {sym_data['label'][:60]}")

        except Exception as e:
            log.error(f"[Bootstrap] Ошибка записи символа {i}: {e}")
            skipped += 1

    # Шаг 4: Итог
    print(f"\n[4/4] Итог:")
    print(f"  Записано: {written}")
    print(f"  Пропущено: {skipped}")

    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM scl_symbols")
    print(f"  Всего в базе: {total}")

    if total >= 8:
        print("\n✅ Bootstrap завершён. Система готова к работе.")
    else:
        print("\n⚠️  Мало символов. Запусти повторно или проверь GEMINI_API_KEY.")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(bootstrap())
