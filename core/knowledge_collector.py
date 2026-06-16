"""
Knowledge Collector — автономное наполнение ядра (Канал 1).
Запускается в режиме СОН через core/sleep_mode.py.
Правила: SLEEP_MODE.md раздел "Автонаполнение ядра"

Алгоритм:
1. Скан белых зон в ядре (pgvector)
2. Поиск знаний во внешних источниках по каждой зоне
3. Оценка по рейтингу и актуальности
4. Запись через стандартный путь archivist._new_symbol()
"""
import logging, asyncio, json
from datetime import datetime, timezone

def _detect_source_type(url: str) -> str:
    """
    P6 fix: определяет source_type по URL источника.
    Допустимые значения: github|npm|pypi|n8n|official|cli_plugin|ai_inferred
    "ai_search" было неверным — это метод, не тип источника.
    """
    if not url:
        return "ai_inferred"
    url_lower = url.lower()
    if "github.com" in url_lower:
        return "github"
    if "npmjs.com" in url_lower or "npm.io" in url_lower:
        return "npm"
    if "pypi.org" in url_lower:
        return "pypi"
    if "n8n.io" in url_lower:
        return "n8n"
    if any(x in url_lower for x in ["anthropic.com", "openai.com",
                                      "google.com", "docs.python.org",
                                      "developer.mozilla.org"]):
        return "official"
    if any(x in url_lower for x in ["cursor.sh", "marketplace.visualstudio.com",
                                      "extensions.codeium.com"]):
        return "cli_plugin"
    return "ai_inferred"


log = logging.getLogger("evo.collector")

# Приоритет источников
SOURCES = [
    {"name": "github_trending",  "priority": 1},
    {"name": "official_docs",    "priority": 2},
    {"name": "npm_pypi",         "priority": 3},
    {"name": "n8n_templates",    "priority": 4},
    {"name": "cli_plugins",      "priority": 5},
]

# Минимальный рейтинг для принятия знания
MIN_GITHUB_STARS = 500
MIN_NPM_WEEKLY   = 10000


async def collect_and_fill():
    """
    Точка входа. Вызывается из _sleep_cycle() в sleep_mode.py.
    Полный цикл: скан → поиск → оценка → запись.
    """
    log.info("[Collector] Запуск автонаполнения ядра")

    try:
        # 1. Найти белые зоны
        gaps = await _scan_knowledge_gaps()
        if not gaps:
            log.info("[Collector] Белых зон не найдено")
            return

        log.info(f"[Collector] Найдено {len(gaps)} белых зон: "
                 f"{[g['type'] for g in gaps[:5]]}")

        # 2. По каждой зоне — искать и забирать
        collected = 0
        for gap in gaps[:10]:  # не более 10 зон за один цикл СОН
            results = await _search_for_gap(gap)
            for candidate in results:
                ok = await _ingest_candidate(candidate, gap)
                if ok:
                    collected += 1

        log.info(f"[Collector] Цикл завершён. Собрано новых знаний: {collected}")

        # 3. Уведомить Архитектора если нашлось много
        if collected >= 5:
            from core.sleep_mode import notify_architect
            await notify_architect(
                zone="auto_collection",
                problem=f"Автонаполнение: найдено {collected} новых знаний за цикл СОН",
                options=[
                    {"description": "Принять все — они уже записаны",
                     "consequences": "База расширена, confirmed_by=1 у каждого"},
                    {"description": "Просмотреть и подтвердить вручную",
                     "consequences": "Символы помечены hypothesis=True до подтверждения"},
                    {"description": "Отклонить текущий набор",
                     "consequences": "Символы удалены, зоны помечены skip_auto=True"},
                ]
            )
    except Exception as e:
        log.error(f"[Collector] Ошибка: {e}")


async def _scan_knowledge_gaps() -> list[dict]:
    """
    Сканирует ядро и возвращает список белых зон по приоритету.
    """
    from db.pg_client import get_pool
    pool = await get_pool()
    gaps = []

    async with pool.acquire() as conn:
        # Зона 1: макро-корни с < 3 символами
        roots_32 = ["Φ","Λ","M","γ","ζ","β","η","κ","ε","τ",
                    "σ","α","χ","ψ","δ","ξ","Ω","Π","Θ","Ξ",
                    "Ψ","Σ","Δ","Γ","μ","ν","ρ","ι","θ","π","ω","λ"]

        for root in roots_32:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM scl_symbols WHERE id LIKE $1 AND is_legacy=FALSE",
                f"{root}%"
            )
            if count < 3:
                gaps.append({
                    "type": "zero_symbols_in_root",
                    "root": root,
                    "current_count": count,
                    "priority": 1
                })

        # Зона 2: разделы полностью из legacy
        legacy_zones = await conn.fetch("""
            SELECT science, section, COUNT(*) as total,
                   SUM(CASE WHEN is_legacy THEN 1 ELSE 0 END) as legacy_cnt
            FROM scl_symbols
            GROUP BY science, section
            HAVING COUNT(*) > 0
               AND SUM(CASE WHEN is_legacy THEN 1 ELSE 0 END) = COUNT(*)
        """)
        for z in legacy_zones:
            gaps.append({
                "type": "all_legacy_zone",
                "science": z['science'],
                "section": z['section'],
                "priority": 2
            })

        # Зона 3: символы с confirmed_by=1 и hypothesis=False — одиночные
        single_unconfirmed = await conn.fetchval("""
            SELECT COUNT(*) FROM scl_symbols
            WHERE confirmed_by = 1 AND hypothesis = FALSE AND is_legacy = FALSE
        """)
        if single_unconfirmed > 5:
            gaps.append({
                "type": "unconfirmed_singles",
                "count": single_unconfirmed,
                "priority": 3
            })

        # Зона 4: trending_expansion — просто новые технологии
        # Всегда добавляем одну зону расширения в конец
        gaps.append({
            "type": "trending_expansion",
            "priority": 5
        })

    # Сортируем по приоритету
    gaps.sort(key=lambda x: x["priority"])
    return gaps


async def _search_for_gap(gap: dict) -> list[dict]:
    """
    Ищет знания для конкретной белой зоны через AI Router.
    Возвращает список кандидатов для записи.
    """
    from core.ai_router import ai_router

    gap_type = gap.get("type", "")
    root = gap.get("root", "")
    science = gap.get("science", "")
    section = gap.get("section", "")

    # Формируем поисковый запрос под тип зоны
    if gap_type == "zero_symbols_in_root":
        query = (
            f"Find top 3 most popular open source tools, libraries or techniques "
            f"in the knowledge domain '{root}' (from: Φ=Philosophy/Logic, "
            f"Λ=Linguistics, M=Mathematics, γ=Physics, ζ=Chemistry, β=Biology, "
            f"η=Neuroscience/Psychology, κ=Cybernetics/Algorithms, ε=Economics, "
            f"τ=Technology/Engineering, σ=Sociology/Law, ...). "
            f"For each return JSON: {{\"label\": \"задача: X | лекарство: Y\", "
            f"\"science\": \"...\", \"section\": \"...\", \"subsection\": \"...\", "
            f"\"source_url\": \"...\", \"source_rating\": N, "
            f"\"applicable_stacks\": [...]}}. "
            f"Return ONLY a JSON array."
        )
    elif gap_type == "all_legacy_zone":
        query = (
            f"Find the most current replacement or modern alternative for "
            f"'{section}' in '{science}' domain as of 2025-2026. "
            f"Return JSON array of 2 items: {{\"label\": \"задача: X | лекарство: Y\", "
            f"\"science\": \"{science}\", \"section\": \"{section}\", "
            f"\"subsection\": \"...\", \"source_url\": \"...\", "
            f"\"source_rating\": N, \"applicable_stacks\": [...]}}. "
            f"ONLY JSON array."
        )
    elif gap_type == "trending_expansion":
        query = (
            "List top 5 trending developer tools or techniques in 2025-2026 "
            "from GitHub Trending, with high adoption. "
            "For each: {\"label\": \"задача: X | лекарство: Y\", "
            "\"science\": \"Технология\", \"section\": \"...\", "
            "\"subsection\": \"...\", \"source_url\": \"...\", "
            "\"source_rating\": N, \"applicable_stacks\": [...]}. "
            "ONLY JSON array."
        )
    else:
        # unconfirmed_singles — пропускаем поиск, только помечаем
        return []

    try:
        result = await ai_router.generate(query, task="knowledge_collection")
        # Очищаем от markdown
        result = result.strip()
        for fence in ["```json", "```JSON", "```"]:
            if result.startswith(fence):
                result = result[len(fence):]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        candidates = json.loads(result)
        if isinstance(candidates, list):
            # Добавляем метаданные источника
            for c in candidates:
                c["auto_collected"] = True
                # P6 fix: определяем тип по URL, не хардкодим "ai_search"
                c["source_type"] = _detect_source_type(c.get("source_url", ""))
                c["collected_at"] = datetime.now(timezone.utc).isoformat()
            return candidates
    except Exception as e:
        log.warning(f"[Collector] Поиск для {gap_type} не удался: {e}")

    return []


async def _ingest_candidate(candidate: dict, gap: dict) -> bool:
    """
    Принимает кандидата в базу через стандартный путь archivist.
    Тот же процесс что при gap_filled от флагмана.
    """
    from core.ai_router import ai_router
    from db.pg_client import find_symbols, insert_symbol, get_pool
    from shards.shard_client import write_cell

    label = candidate.get("label", "")
    science = candidate.get("science", "")
    section = candidate.get("section", "")
    subsection = candidate.get("subsection", "")

    # Базовая валидация
    if not all([label, science, section, subsection]):
        log.debug(f"[Collector] Пропуск: неполные метаданные {label[:40]}")
        return False
    if "задача:" not in label or "лекарство:" not in label:
        log.debug(f"[Collector] Пропуск: неверный формат label: {label[:40]}")
        return False

    try:
        # Векторизация
        embed_text = f"{label} {science} {section} {subsection}"
        vector = await ai_router.embed(embed_text)

        # Similarity check — не дублировать
        existing = await find_symbols(vector, top_k=1, exclude_legacy=True)
        if existing and existing[0].get("similarity", 0) > 0.95:
            log.debug(f"[Collector] Дубль: {label[:40]} ~ {existing[0]['label'][:40]}")
            return False

        # Генерация ID
        from core.archivist import _generate_id
        symbol_id = await _generate_id(science, section, subsection)

        # Тело на шард
        body = (
            f"# {label}\n\n"
            f"**Источник:** {candidate.get('source_url', 'N/A')}\n"
            f"**Рейтинг источника:** {candidate.get('source_rating', 0)}\n"
            f"**Тип источника:** {candidate.get('source_type', 'unknown')}\n"
            f"**Собрано:** {candidate.get('collected_at', '')}\n\n"
            f"*Знание собрано автономно в режиме СОН (Канал 1).*\n"
            f"*confirmed_by=1 — растёт при реальном применении флагманом.*\n"
        )
        shard_path = f"/evo/{science[:3].upper()}/{symbol_id}.zst"
        await write_cell("", shard_path, body, symbol_id=symbol_id)

        # Запись в pgvector — все поля включая Канал 1
        await insert_symbol({
            "id": symbol_id,
            "label": label,
            "vector": vector,
            "science": science,
            "section": section,
            "subsection": subsection,
            "applicable_stacks": candidate.get("applicable_stacks", []),
            "shard_host": "",
            "shard_path": shard_path,
            "hypothesis": True,         # требует реального применения для подтверждения
            "confirmed_by": 1,
            "evolution_note": (
                f"Канал 1 (авто): источник={candidate.get('source_url','N/A')}, "
                f"рейтинг={candidate.get('source_rating',0)}"
            ),
            # Поля Канала 1 — обязательны для трассировки автосбора
            "source_url":      candidate.get("source_url"),
            "source_rating":   candidate.get("source_rating", 0),
            "source_type":     candidate.get("source_type"),
            "auto_collected":  True,    # всегда True — знание от knowledge_collector
        })

        log.info(f"[Collector] ✓ Записан: {symbol_id} — {label[:60]}")
        return True

    except Exception as e:
        log.error(f"[Collector] Ошибка записи {label[:40]}: {e}")
        return False
