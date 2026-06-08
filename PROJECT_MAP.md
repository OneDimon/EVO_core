# EVO-core — Project Map

> **Правило входа:** Прочитай ПЕРВЫМ при каждой сессии.
> Карта, статус блоков, сшивка, безопасность, что деплоить.
> YMS-MMM ACTIVE | Архитектор: @OneDimon | v4.0

---

## Дерево проекта

```
evo-core/
├── PROJECT_MAP.md              ← ТЫ ЗДЕСЬ. Читать первым.
│
├── api/
│   ├── main.py                 ✅ v0.3 + SecurityMiddleware + sleep scheduler
│   ├── middleware/
│   │   └── security.py         ✅ JWT auth + rate limiting + HMAC verify
│   └── routes/
│       ├── handshake.py        ✅ сессии в БД + строгий HMAC
│       ├── concierge.py        ✅ консьерж-диалог
│       ├── query.py            ✅ поиск + Redis план
│       ├── step_done.py        ✅ последовательное раскрытие
│       ├── result.py           ✅ YMS-MMM + Obsidian + Immune
│       ├── hook_reply.py       ✅ хук-допрос
│       ├── admin.py            ✅ конфиги + пользователи + audit log
│       ├── patch_callback.py   ✅ реаниматор callback
│       └── mcp.py              ✅ JSON-RPC 2.0
│
├── core/
│   ├── ai_router.py            ✅ Gemini→Flash→Ollama fallback
│   ├── librarian.py            ✅ поиск + Redis план
│   ├── archivist.py            ✅ Тип А/Б + confirmed_in + legacy
│   ├── verifier.py             ✅ YMS-MMM полная верификация
│   ├── obsidian.py             ✅ Тип А/Б + лигатуры + граф
│   ├── immune_system.py        ✅ реаниматор БЛОК 07
│   ├── cli_layer.py            ✅ скелетонизатор БЛОК 04
│   ├── mcp_server.py           ✅ JSON-RPC БЛОК 05
│   ├── config_manager.py       ✅ шифрование + audit log
│   ├── sleep_mode.py           ✅ СОН + ТГ-уведомления
│   └── crypto.py               ✅ AES шифрование sensitive данных
│
├── db/
│   ├── models.py               ✅ SCLSymbol полная схема
│   ├── pg_client.py            ✅ безопасный SQL (нет f-string injection)
│   ├── redis_client.py         ✅ кэш + план + очередь
│   ├── users.py                ✅ пользователи + API ключи
│   └── migrations/
│       ├── 001_init.sql        ✅ scl_symbols + 9 индексов
│       ├── 002_config.sql      ✅ evo_config
│       └── 003_users_security.sql ✅ users + sessions + audit + pgcrypto
│
├── shards/
│   ├── zstd_codec.py           ✅ compress + гиперлинки
│   └── shard_client.py         ✅ path traversal защита + autopatch
│
├── config/
│   ├── ai_router.json          ✅
│   └── deployment.json         ✅
│
├── prompts/
│   ├── flagship_system_prompt.txt    ✅ v3.0
│   └── local_model_instructions.txt  ✅ v1.0
│
├── scripts/
│   ├── bootstrap.py            ✅
│   ├── bootstrap_check.py      ✅
│   └── deploy.sh               ✅ check + gen-secrets + migrate 003
│
├── tests/
│   ├── test_phase0.py          ✅ 9 тестов
│   └── test_phase1.py          ✅ 9 тестов
│
├── .env.example                ✅ все секреты с пояснениями
├── docker-compose.yml          ✅
├── Dockerfile                  ✅
└── requirements.txt            ✅ + cryptography + apscheduler
```

---

## Статус блоков (все готовы)

| Блок | Файл | Статус | Сшит |
|------|------|--------|------|
| 01 Core Engine | api/ | 🟢 | 02✅ 03✅ 06✅ 07✅ |
| 02 Language Library | librarian+archivist+db/ | 🟢 | 01✅ 03✅ 06✅ |
| 03 Shard Storage | shards/ | 🟢 | 01✅ 02✅ |
| 04 CLI Layer | core/cli_layer.py | 🟢 | 01✅ |
| 05 MCP Server | core/mcp_server.py | 🟢 | 01✅ |
| 06 YMS-MMM+Obsidian | verifier+obsidian | 🟢 | 01✅ 02✅ 07✅ |
| 07 Immune System | core/immune_system.py | 🟢 | 06✅ 01✅ |
| AI Router | core/ai_router.py | 🟢 | все |
| Config+Admin | config_manager+admin | 🟢 | все |
| Sleep Mode | core/sleep_mode.py | 🟢 | scheduled |
| Security | middleware/security.py | 🟢 | все |

---

## Безопасность — статус

| Уязвимость | Статус | Файл |
|-----------|--------|------|
| Слабые дефолты секретов | ✅ Исправлено | handshake.py, admin.py |
| SQL f-string injection | ✅ Исправлено | pg_client.py |
| Path traversal в шардах | ✅ Исправлено | shard_client.py |
| Sensitive данные plaintext | ✅ Исправлено | crypto.py + config_manager.py |
| Нет rate limiting | ✅ Добавлено | middleware/security.py |
| Нет auth на /api/v1/* | ✅ Добавлено | middleware/security.py |
| Нет audit log | ✅ Добавлено | evo_audit_log + admin.py |
| Нет управления юзерами | ✅ Добавлено | db/users.py + admin.py |
| Сессии не хранятся в БД | ✅ Исправлено | handshake.py + evo_sessions |

---

## Сшивка (все коннекторы)

```
01 ──query────────→ 02 librarian.search()              ✅
01 ──step_done────→ 02 librarian.load_step_body()      ✅
01 ──result───────→ 06 verifier.verify()               ✅
01 ──result───────→ 06 obsidian.process() [async]      ✅
01 ──result───────→ 07 immune.reanimate() [async]      ✅
02 ──read/write───→ 03 shard_client                    ✅
03 ──autopatch────→ 02 pg._attach_link()               ✅
06 ──Тип А/Б──────→ 02 archivist._type_a/_type_b       ✅
all ──ai──────────→ AI Router Gemini/Ollama            ✅
all ──config──────→ config_manager → evo_config(enc)   ✅
security ─────────→ middleware → evo_users + evo_sessions ✅
sleep ──notify────→ ТГ Bot + admin /notify             ✅
```

---

## Быстрый старт

```bash
git clone https://github.com/OneDimon/EVO_core && cd EVO_core
cp .env.example .env

# Шаг 1: Сгенерировать секреты
./scripts/deploy.sh gen-secrets >> .env

# Шаг 2: Заполнить GEMINI_API_KEY в .env

# Шаг 3: Проверить .env
./scripts/deploy.sh check

# Шаг 4: Запустить всё
./scripts/deploy.sh full

# Шаг 5: Создать первого пользователя
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "X-Admin-Token: $(grep EVO_API_SECRET .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","plan":"pro"}'
# Получишь api_key_full — сохрани, он понадобится для запросов

# Шаг 6: Внести токены
curl -X POST http://localhost:8000/api/v1/admin/config \
  -H "X-Admin-Token: YOUR_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"key":"TG_BOT_TOKEN","value":"YOUR_TOKEN"}'

# Шаг 7: Тесты
EVO_ENV=development python tests/test_phase0.py
EVO_ENV=development python tests/test_phase1.py
```

---

## Что осталось (приоритеты)

| # | Задача | Приоритет | Почему |
|---|--------|-----------|--------|
| 1 | Admin UI frontend (React) | 🔴 Высокий | Сейчас только curl, нужна панель |
| 2 | n8n воркфлоу БЛОК 07 | 🔴 Высокий | Реаниматор описан, не задеплоен |
| 3 | Bootstrap из реальных данных | 🟡 Средний | Сейчас заглушки |
| 4 | Google Drive OAuth2 flow | 🟡 Средний | Базовый HTTP, нужен полный flow |
| 5 | ТГ webhook (приём ответа 1/2/3) | 🟡 Средний | Сейчас только отправка |
| 6 | Cloudflare R2 AWS Sig v4 | 🟡 Средний | Заглушка |
| 7 | Граф знаний Three.js | 🟢 Низкий | Dashboard визуализация |
| 8 | APScheduler для Sleep Mode | 🟢 Низкий | Сейчас asyncio loop |
| 9 | Документация API (Swagger) | 🟢 Низкий | Автогенерация из FastAPI |

---

## Чеклист при каждом входе

```
□ Прочитал PROJECT_MAP.md
□ Проверил статус блоков и безопасности
□ Открыл BLOCK_XX нужного блока → коннекторы
□ Обновил статус после работы
```

---
*v4.0 | 2026-06-03 | Все блоки + безопасность реализованы*
