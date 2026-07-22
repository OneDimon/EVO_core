# EVO-core — Project Map

> **Правило входа:** Прочитай ПЕРВЫМ при каждой сессии.
> Карта, статус блоков, сшивка, безопасность, порядок деплоя.
> YMS-MMM ACTIVE | Архитектор: @OneDimon | v5.0

---

## Дерево проекта

```
evo-core/
├── PROJECT_MAP.md              ← ТЫ ЗДЕСЬ. Читать первым.
│
├── api/
│   ├── main.py                 ✅ v0.4 + Security + APScheduler + Admin UI route
│   ├── middleware/
│   │   ├── __init__.py         ✅
│   │   └── security.py         ✅ JWT + rate limiting + HMAC verify
│   └── routes/
│       ├── handshake.py        ✅ сессии в БД + строгий HMAC
│       ├── concierge.py        ✅ консьерж-диалог
│       ├── query.py            ✅ поиск + Redis план
│       ├── step_done.py        ✅ последовательное раскрытие
│       ├── result.py           ✅ YMS-MMM + Obsidian + Immune
│       ├── hook_reply.py       ✅ хук-допрос
│       ├── admin.py            ✅ конфиги + пользователи + audit log
│       ├── patch_callback.py   ✅ реаниматор callback
│       ├── mcp.py              ✅ JSON-RPC 2.0
│       └── tg_webhook.py       ✅ приём ответов Архитектора из ТГ
│
├── core/
│   ├── ai_router.py            ✅ Gemini→Flash→Ollama
│   ├── librarian.py            ✅ поиск + Redis план + step_body
│   ├── archivist.py            ✅ Тип А/Б + confirmed_in + legacy
│   ├── verifier.py             ✅ YMS-MMM полная верификация
│   ├── obsidian.py             ✅ Тип А/Б + лигатуры + граф
│   ├── immune_system.py        ✅ реаниматор БЛОК 07
│   ├── cli_layer.py            ✅ скелетонизатор БЛОК 04
│   ├── mcp_server.py           ✅ JSON-RPC БЛОК 05
│   ├── config_manager.py       ✅ шифрование + audit log
│   ├── sleep_mode.py           ✅ СОН + ТГ + APScheduler + задача 5
│   ├── crypto.py               ✅ AES шифрование
│   └── knowledge_collector.py  ✅ Канал 1 — автонаполнение в режиме СОН
├── site/
│   ├── index.html              ✅ Публичный сайт (Dark High-Tech + Three.js глобус)
│   ├── nginx.conf              ✅ Раздача статики + proxy /api, /mcp, /docs
│   └── mcp-manifest.json       ✅ Манифест для Anthropic MCP Registry
│
├── db/
│   ├── models.py               ✅ SCLSymbol полная схема
│   ├── pg_client.py            ✅ безопасный SQL
│   ├── redis_client.py         ✅ кэш + план + очередь + RPS
│   ├── users.py                ✅ пользователи + API ключи
│   └── migrations/
│       ├── 001_init.sql        ✅ scl_symbols + 9 индексов
│       ├── 002_config.sql      ✅ evo_config
│       ├── 003_users_security.sql ✅ users + sessions + audit + pgcrypto
│       └── 004_channel1_fields.sql ✅ source_url/rating/type/auto_collected
│
├── shards/
│   ├── zstd_codec.py           ✅ compress + гиперлинки новый формат
│   └── shard_client.py         ✅ path traversal защита + autopatch + 4 провайдера
│
├── n8n/
│   └── MIGRATED_TO_CODE.md     ℹ️  историческая заметка: Блок 07 — in-code, n8n не используется
│
├── config/
│   ├── ai_router.json          ✅ Gemini/Ollama роутинг
│   ├── deployment.json         ✅ деплой конфиг
│   └── notifications.json      ✅ TG + admin + protected zones
│
├── prompts/
│   ├── flagship_system_prompt.txt    ✅ v3.0
│   └── local_model_instructions.txt  ✅ v1.0
│
├── scripts/
│   ├── bootstrap.py            ✅ v2 реальные данные Gemini + fallback
│   ├── bootstrap_check.py      ✅
│   └── deploy.sh               ✅ check + gen-secrets + all migrations
│
├── tests/
│   ├── test_phase0.py          ✅ 9 тестов
│   ├── test_phase1.py          ✅ 9 тестов
│   └── test_full.py            ✅ 20 тестов полный стек
│
├── admin_ui.html               ✅ React Admin UI (config, shards, TG, audit)
├── .env.example                ✅ все секреты
├── docker-compose.yml          ✅
├── Dockerfile                  ✅
└── requirements.txt            ✅ + cryptography + apscheduler
```

---

## Статус всех блоков

| Блок | Файл | Статус | Сшит |
|------|------|--------|------|
| **01** Core Engine | api/ | 🔵 Полностью готов | 02✅ 03✅ 06✅ 07✅ 04✅ 05✅ |
| **02** Language Library | librarian+archivist+db/ | 🔵 Полностью готов | 01✅ 03✅ 06✅ |
| **03** Shard Storage | shards/ | 🔵 Полностью готов | 01✅ 02✅ |
| **04** CLI Layer | core/cli_layer.py | 🔵 Полностью готов | 01✅ |
| **05** MCP Server | core/mcp_server.py | 🔵 Полностью готов | 01✅ |
| **06** YMS-MMM+Obsidian | verifier+obsidian | 🔵 Полностью готов | 01✅ 02✅ 07✅ |
| **07** Immune System | core/immune_system.py (in-process) | 🔵 Полностью готов | 06✅ 01✅ |
| **AI Router** | core/ai_router.py | 🔵 Готов | все |
| **Config+Admin** | config_manager+admin+admin_ui | 🔵 Готов | все |
| **Sleep Mode** | core/sleep_mode.py | 🔵 Готов | APScheduler |
| **Канал 1** | core/knowledge_collector.py | 🔵 Готов | sleep_mode задача 5 → archivist → pg_client |
| **Security** | middleware/security.py + crypto | 🔵 Готов | все |

---

## Безопасность — все исправлено

| Уязвимость | Статус |
|-----------|--------|
| Слабые дефолты секретов | ✅ Исправлено |
| SQL f-string injection | ✅ Исправлено |
| Path traversal шарды | ✅ Исправлено |
| Sensitive plaintext в БД | ✅ AES шифрование |
| Нет rate limiting | ✅ 60 req/min |
| Нет auth на /api/v1/* | ✅ X-API-Key middleware |
| Нет audit log | ✅ evo_audit_log |
| Нет управления юзерами | ✅ db/users.py |
| Сессии не в БД | ✅ evo_sessions |

---

## Сшивка (все коннекторы)

```
01 ──query────────→ 02 librarian.search()              ✅
01 ──step_done────→ 02 librarian.load_step_body()      ✅
01 ──result───────→ 06 verifier.verify()               ✅
01 ──result───────→ 06 obsidian.process() [async]      ✅
01 ──result───────→ 07 immune.reanimate() [async]      ✅
01 ──/mcp─────────→ 05 mcp_server методы              ✅
02 ──read/write───→ 03 shard_client                    ✅
03 ──autopatch────→ 02 pg._attach_link() [auto]        ✅
06 ──Тип А/Б──────→ 02 archivist._type_a/_type_b       ✅
07 ──in-process────→ /api/v1/patch_callback             ✅
all ──ai──────────→ AI Router Gemini/Ollama            ✅
all ──config──────→ config_manager → evo_config [enc] ✅
security ─────────→ middleware → evo_users+sessions   ✅
tg ───────────────→ tg_webhook → apply_choice         ✅
sleep ──notify────→ ТГ Bot + admin                    ✅
sleep ──task5─────→ knowledge_collector.collect_and_fill ✅
kc ───archivist───→ _new_symbol(auto_collected=True)    ✅
kc ───pg_client───→ insert_symbol($21–$24 Канал 1)      ✅
```

---

## Быстрый старт

```bash
git clone https://github.com/OneDimon/EVO_core && cd EVO_core
cp .env.example .env

# 1. Генерация секретов
./scripts/deploy.sh gen-secrets >> .env

# 2. Заполнить GEMINI_API_KEY в .env

# 3. Проверка
./scripts/deploy.sh check

# 4. Запуск
./scripts/deploy.sh full

# 5. Создать admin пользователя
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "X-Admin-Token: $(grep EVO_API_SECRET .env|cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","plan":"pro"}'

# 6. Открыть Admin UI
open http://localhost:8000/admin

# 7. Настроить TG в Admin UI → внести TG_BOT_TOKEN + TG_ADMIN_CHAT_ID
# 8. Настроить шарды в Admin UI → SHARD_PROVIDER + токены
# 9. Тесты
EVO_ENV=development python tests/test_full.py  # 20 тестов
```

---

## Что осталось

| Задача | Приоритет | Описание |
|--------|-----------|---------|
| Публичный сайт evo-core.io | 🔵 Готов | `site/index.html` — деплой 🔴 |
| 3D-глобус знаний | 🔵 Готов | `site/index.html` Three.js — деплой 🔴 |
| MCP Registry публикация | 🟡 Манифест готов | `site/mcp-manifest.json` — нужен публичный HTTPS |
| Бесплатный период СТАРТ | 🔴 Высокий | Вирусный запуск |
| Google Drive OAuth2 | 🟡 Средний | Полный flow, сейчас базовый HTTP |
| Cloudflare R2 AWS Sig v4 | 🟡 Средний | Полная реализация |
| Граф знаний Admin UI | 🟢 Низкий | Three.js визуализация в Admin панели |
| Документация API | 🟢 Низкий | Swagger автогенерация готова (/docs) |

---

## Чеклист при каждом входе

```
□ Прочитал PROJECT_MAP.md
□ Проверил статус блоков и сшивку
□ Открыл BLOCK_XX нужного блока → коннекторы
□ Обновил статус после работы
```

---
*v7.0 | 2026-06-13 | +Канал 1 (knowledge_collector) + migration 004 + Фаза 3 (сайт) в работе.*
