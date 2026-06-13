# EVO-core — Онбординг для ИИ-разработчика

> **Читай этот файл первым.** Он даёт полную картину за 5 минут.
> После него читай только то что нужно для конкретной задачи.
> Версия: 1.0 | 2026-06-13 | Архитектор: @OneDimon | YMS-MMM ACTIVE

---

## ЧТО ТАКОЕ EVO-CORE (одна строка)

**Когнитивный слой между ИИ-флагманами и средами исполнения:**
хранит верифицированные инженерные решения как аксиомы,
выдаёт их точечно по смыслу запроса, исключает галлюцинации
и деградацию внимания при длинных проектах.

---

## КАК РАБОТАЕТ (шаг за шагом)

```
[ Пользователь ставит задачу ]
         │
         ▼
[ CLI-прослойка (Cursor / Claude Code / VS Code / MCP) ]
  Скелетонизирует контекст: ~1300 токенов вместо ~44000
         │
         ▼
[ КОНСЬЕРЖ /api/v1/concierge ]
  Задаёт флагману 3 вопроса: что делаем / стек / ограничения
  Сохраняет: detected_stack[], constraints[], project_type
         │
         ▼
[ БИБЛИОТЕКАРЬ /api/v1/query ]
  Векторизует (запрос + план флагмана)
  Ищет в pgvector: similarity × log(R_f + 2), top_k=5-10
  Три сценария:
    А — есть лигатура → выдать картридж
    Б — есть символы → собрать лигатуру на месте → выдать
    В — пусто → директива флагману искать самому
         │
         ▼
[ ФЛАГМАН РАБОТАЕТ ]
  Получает картридж → выполняет шаги → докладывает /api/v1/result
  После каждого шага → /api/v1/step_done → следующий шаг раскрывается
         │
         ▼
[ ВЕРИФИКАТОР YMS-MMM /api/v1/result ]
  Проверяет: 100% ТЗ, синтаксис, артефакты, хронология, workability
  ideal     → R_f+=1, запись, хук-допрос
  adapted   → Тип А/Б через obsidian, запись
  gap_filled → новый символ с нуля, запись
  fail×3    → n8n → Gemini → Ollama fallback → патч → флагману
         │
         ▼
[ АРХИВАРИУС (async) ]
  similarity check > 0.95 → Тип А (перезапись + legacy)
  similarity 0.75–0.95   → Тип Б (новый + evolved_from)
  < 0.75                 → новый независимый символ
  zstd в памяти → шард + pgvector
  хук-допрос: «есть что-то новее?»
         │
         ▼
[ ПОЛЬЗОВАТЕЛЬ ПОЛУЧАЕТ ОТВЕТ ]
  Ядро работало незаметно. Флагман выглядит умнее обычного.
```

---

## РЕЖИМ СОН (автономная работа)

В часы минимальной нагрузки ядро само наполняет базу знаний (Канал 1):

```
23:00 — пересчёт окна сна (час с min RPS за 7 дней)
  │
  ▼ Если RPS < 10% базового + нет сессий + очередь пуста
  │
  ▼ ЗАДАЧА 1: фоновая ассимиляция (поиск потенциальных лигатур)
  ▼ ЗАДАЧА 2: пересчёт графа знаний (R_f → веса узлов)
  ▼ ЗАДАЧА 3: проверка целостности (pgvector ↔ шарды ↔ лигатуры)
  ▼ ЗАДАЧА 4: уведомления Архитектора (protected zones)
  ▼ ЗАДАЧА 5: КАНАЛ 1 — knowledge_collector.collect_and_fill()
     └─ скан белых зон → поиск GitHub/npm/PyPI → оценка → запись
  │
  ▼ При нагрузке > 90% базового — немедленное прерывание
```

---

## КАРТА ФАЙЛОВ ПРОЕКТА

### Документация (читай в этом порядке)

| Файл | Что это | Когда читать |
|------|---------|--------------|
| `AI_ONBOARDING.md` | **Этот файл** — вход в проект | Первым делом |
| `PROJECT_MAP.md` | Карта всех файлов + статусы + сшивки | Перед любой правкой |
| `IMPLEMENTATION_PLAN.md` | Полный план v3.0 — что сделано, что осталось | Перед началом работы |
| `AGENTS.md` / `.claude/CLAUDE.md` | Правила для ИИ-агентов в этом репо | Автозагрузка в Claude Code |
| `FLAGSHIP_SYSTEM_PROMPT.md` | Промпт флагмана (вшивается через MCP/CLI) | При настройке флагмана |
| `LOCAL_MODEL_INSTRUCTIONS.md` | Промпт локальной модели ядра — 6 ролей | При настройке ядра |
| `SCL_FRACTAL_PROTOCOL.md` | Протокол Языка-Библиотеки — 19 разделов | При работе с символами |
| `SCL_SYMBOLIC_NOTATION.md` | Нотация символов | При создании символов |
| `SLEEP_MODE.md` | Протокол режима СОН | При работе с sleep/Канал 1 |
| `README.md` | Публичное описание + статус блоков | Обзор |

### Код — API (точки входа)

| Файл | Эндпоинт | Роль |
|------|----------|------|
| `api/routes/handshake.py` | `POST /api/v1/handshake` | Рукопожатие флагмана + HMAC |
| `api/routes/concierge.py` | `POST /api/v1/concierge` | Консьерж — интервью стека |
| `api/routes/query.py` | `POST /api/v1/query` | Поиск картриджа |
| `api/routes/step_done.py` | `POST /api/v1/step_done` | Шаг выполнен → следующий |
| `api/routes/result.py` | `POST /api/v1/result` | YMS-MMM верификация |
| `api/routes/hook_reply.py` | `POST /api/v1/hook_reply` | Ответ на хук-допрос |
| `api/routes/patch_callback.py` | `POST /api/v1/patch_callback` | Патч от n8n реаниматора |
| `api/routes/mcp.py` | `POST /mcp` | MCP JSON-RPC 2.0 |
| `api/routes/admin.py` | `/admin/*` | Управление ключами, шардами |
| `api/routes/tg_webhook.py` | `/tg/webhook` | Ответы Архитектора из Telegram |

### Код — Ядро (бизнес-логика)

| Файл | Что делает | Связан с |
|------|-----------|---------|
| `core/librarian.py` | Поиск и сборка картриджа | `db/pg_client.py`, `shards/` |
| `core/verifier.py` | YMS-MMM проверка результата | `core/obsidian.py`, `core/ai_router.py` |
| `core/obsidian.py` | Контур Тип А/Б + лигатуры | `core/archivist.py` |
| `core/archivist.py` | Запись символов → шарды + pgvector | `db/pg_client.py`, `shards/` |
| `core/sleep_mode.py` | Планировщик СОН + 5 задач | `core/knowledge_collector.py` |
| `core/knowledge_collector.py` | Канал 1: белые зоны → внешние источники | `core/archivist.py` |
| `core/immune_system.py` | n8n реаниматор + fallback | `config/ai_router.json` |
| `core/mcp_server.py` | MCP JSON-RPC сервер | `api/routes/mcp.py` |
| `core/cli_layer.py` | Скелетонизатор + detect_stack | `core/librarian.py` |
| `core/crypto.py` | AES шифрование токенов в БД | `db/users.py` |
| `core/ai_router.py` | Единая точка вызова всех ИИ-моделей | `config/ai_router.json` |

### Код — БД и шарды

| Файл | Что делает |
|------|-----------|
| `db/models.py` | Pydantic-модель SCLSymbol (все поля) |
| `db/pg_client.py` | INSERT/SELECT в pgvector + PostgreSQL |
| `db/redis_client.py` | Очередь записи + горячий кэш сессий |
| `db/users.py` | Пользователи + API-ключи + ротация |
| `shards/shard_client.py` | Чтение/запись zstd-шардов + path traversal защита |
| `shards/zstd_codec.py` | Compress/decompress в памяти (без файлов на диске) |
| `db/migrations/001_init.sql` | Основная схема scl_symbols + pgvector |
| `db/migrations/002_config.sql` | evo_config таблица |
| `db/migrations/003_users_security.sql` | users + sessions + audit_log + pgcrypto |
| `db/migrations/004_channel1_fields.sql` | ALTER TABLE: source_url/rating/type/auto_collected |

### Конфиги

| Файл | Содержит |
|------|---------|
| `config/ai_router.json` | Primary/fallback модели + backoff 5s/15s/45s |
| `config/deployment.json` | Хосты шардов, Redis, PG, порты |
| `config/notifications.json` | Telegram + admin webhook + protected zones |
| `n8n/evo_immune_system_workflow.json` | n8n workflow реаниматора |
| `docker-compose.yml` | Полный стек: PG+pgvector, Redis, API, n8n |

---

## ТЕКУЩИЙ СТАТУС БЛОКОВ

| Блок | Файлы | Статус |
|------|-------|--------|
| БД + pgvector | `db/` + `migrations/001-004` | ✅ Готов к деплою |
| SCL Symbol | `db/models.py` | ✅ Все поля включая Канал 1 |
| API конвейер | `api/routes/` (9 эндпоинтов) | ✅ Готов |
| Библиотекарь | `core/librarian.py` | ✅ Готов |
| YMS-MMM | `core/verifier.py` | ✅ Готов |
| Obsidian | `core/obsidian.py` | ✅ Готов |
| Архивариус | `core/archivist.py` + поля Канала 1 | ✅ Готов |
| Иммунная система | `core/immune_system.py` + n8n | ✅ Готов |
| MCP сервер | `core/mcp_server.py` | ✅ Готов |
| CLI скелетонизатор | `core/cli_layer.py` | ✅ Готов |
| Безопасность | `api/middleware/security.py` + `core/crypto.py` | ✅ Готов |
| Admin UI | `admin_ui.html` | ✅ Готов |
| Telegram webhook | `api/routes/tg_webhook.py` | ✅ Готов |
| Режим СОН | `core/sleep_mode.py` (5 задач) | ✅ Готов |
| Канал 1 | `core/knowledge_collector.py` | ✅ Готов, сшит с archivist |
| Тесты | `tests/test_phase0,1,full.py` | ✅ 38 тестов |
| **Публичный сайт** | — | 🔴 Не начат |
| **3D-глобус** | — | 🔴 Не начат |
| **MCP Registry** | — | 🔴 Не начат |
| **Деплой prod** | — | 🟡 docker-compose готов, не развёрнут |

---

## ЧТО ОСТАЛОСЬ (Фаза 3)

### 1. Публичный сайт evo-core.io

```
Стиль: Dark High-Tech, кибер-минимализм
Разделы:
  / (Hero)          — одна строка что это + CTA "Получить ключ"
  /how-it-works     — анимированная схема конвейера
  /dashboard        — 3D-глобус знаний + статистика ядра
  /pricing          — бесплатный период → $15/мес → Enterprise
  /docs             — документация API (Swagger уже есть на /docs)

Технологии: Next.js + Three.js (3D-глобус) + Tailwind
Глобус: каждый узел = символ в pgvector, пульсация = R_f, GeoIP пользователей
```

### 2. Публикация в Anthropic MCP Registry

```
Что нужно:
  - manifest.json (name, description, tools, auth)
  - Документация для install (уже есть /docs)
  - Endpoint: Streamable HTTP JSON-RPC 2.0 (core/mcp_server.py — готов)
  - Публичный HTTPS (нужен деплой)
```

### 3. Деплой production

```
docker-compose up -d (готов)
Нужно:
  - Домен evo-core.io → VPS
  - SSL (Let's Encrypt)
  - Заполнить .env (TG_BOT_TOKEN, DB_PASSWORD, SECRET_KEY, AES_KEY)
  - Запустить bootstrap.py (первичное наполнение ядра)
  - Проверить /health
```

### 4. Бесплатный период СТАРТ 🚀

```
Месяцы 0-2: бесплатно, без ограничений
  → Ядро дообучается на реальных задачах пользователей
  → Канал 1 автоматически заполняет белые зоны
  → Вирусное распространение через MCP Registry + GitHub
```

---

## ПРАВИЛА ДЛЯ ИИ-РАЗРАБОТЧИКА (обязательны)

```
1. ВСЕГДА читай реальный файл перед правкой — не предполагай
2. НИКОГДА не переписывай файл целиком — только patch/append
3. При противоречии в документах — предложи варианты Архитектору
4. Любое изменение проброси до конца (нож через весь проект):
   код → тесты → документация → IMPLEMENTATION_PLAN → README
5. Минимизируй контекст — читай только нужные файлы через GitHub API
6. PROTECTED ZONES (изменять только с подтверждения Архитектора):
   scl_symbols, config/, prompts/, SCL_FRACTAL_PROTOCOL.md,
   LOCAL_MODEL_INSTRUCTIONS.md, migrations/
7. Версии файлов обновляй при каждом коммите
8. После любой правки — финальная сверка целостности связки
```

---

## ПОРЯДОК ЗАПУСКА (для деплоя)

```bash
# 1. Переменные окружения
cp .env.example .env
# Заполнить: DB_PASSWORD, SECRET_KEY, AES_KEY,
#            TG_BOT_TOKEN, TG_ADMIN_CHAT_ID,
#            GEMINI_API_KEY (primary AI router)

# 2. Запуск стека
docker-compose up -d

# 3. Проверка БД (4 миграции применятся автоматически)
docker-compose logs postgres | grep "database system is ready"

# 4. Bootstrap — первичное наполнение ядра
docker-compose exec api python scripts/bootstrap.py

# 5. Проверка готовности
curl http://localhost:8000/health
curl http://localhost:8000/docs  # Swagger UI

# 6. Проверка тестов
docker-compose exec api pytest tests/ -v

# 7. Первый флагман
# В Claude Code / Cursor — открыть репо. AGENTS.md загрузится автоматически.
# Или: вшить FLAGSHIP_SYSTEM_PROMPT.md в системный промпт флагмана вручную.
```

---

## СХЕМА СШИВОК (критические точки)

```
Канал 1 (полная цепочка):
sleep_mode._sleep_cycle()
  └→ _auto_fill_knowledge()
       └→ knowledge_collector.collect_and_fill()
            └→ archivist._new_symbol(
                 source_url, source_rating,
                 source_type, auto_collected=True
               )
                 └→ pg_client.insert_symbol({
                      ...,
                      "source_url": ...,     # $21
                      "source_rating": ...,  # $22
                      "source_type": ...,    # $23
                      "auto_collected": True # $24
                    })
                      └→ pgvector + shards

Верификация (полная цепочка):
/api/v1/result
  └→ verifier.verify()
       └→ obsidian.process() [Тип А/Б]
            └→ archivist._type_a() или _type_b() или _new_symbol()
                 └→ pg_client.insert_symbol()
                      └→ shard_client.write_cell() [zstd в памяти]

Иммунная система (при 3 провалах):
verifier.fail×3
  └→ immune_system.activate()
       └→ n8n webhook → Gemini (primary)
            └→ fallback: Ollama local
                 └→ /api/v1/patch_callback → флагману
```

---

*Версия: 1.0 | 2026-06-13 | Архитектор: @OneDimon*
*YMS-MMM ACTIVE*
*Этот файл — единственная точка входа для любого ИИ, начинающего работу с репо.*
