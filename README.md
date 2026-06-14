# EVO-core

**Когнитивный слой между ИИ-флагманами и средами исполнения.**

Хранит верифицированные инженерные решения как аксиомы.
Выдаёт их точечно по смыслу запроса под конкретный стек.
Исключает галлюцинации, деградацию внимания, устаревшие решения.

> **Правило входа в любую сессию:** прочитай этот файл первым.
> Найди свой блок, открой его карту, проверь статус сшивки со смежными блоками.
> Работай только внутри своего блока.
> Апдейти статус сшивки в обоих файлах сразу после проверки.

---

## Карта проекта

```
[ ЗАПРОС ПОЛЬЗОВАТЕЛЯ ]
        │
        ▼
┌───────────────┐
│  БЛОК 04      │  CLI-скелетонизатор
│  CLI Layer    │  Сжимает контекст до сигнала
└──────┬────────┘
       │
       ▼
┌───────────────┐
│  БЛОК 01      │  Ядро — главный диспетчер
│  Core Engine  │  Принимает запрос, управляет конвейером
└──────┬────────┘
       │
    ┌──┴──────────────────────────────┐
    │                                 │
    ▼                                 ▼
┌────────────┐                 ┌─────────────┐
│  БЛОК 02   │                 │  БЛОК 03    │
│  Language  │                 │  Shard      │
│  Library   │                 │  Storage    │
│ pgvector + │                 │ zstd-файлы  │
│ SCL-символы│                 │ на шардах   │
└──────┬─────┘                 └──────┬──────┘
       │                              │
       └──────────────┬───────────────┘
                      │
                      ▼
             ┌─────────────────┐
             │    БЛОК 01      │
             │  Сборщик        │
             │  картриджа      │
             │  → Флагман      │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │    БЛОК 06      │
             │  YMS-MMM        │
             │  Верификатор    │
             └────────┬────────┘
                      │
           ┌──────────┴──────────┐
           ▼                     ▼
    ┌─────────────┐      ┌──────────────┐
    │   БЛОК 07   │      │   БЛОК 05    │
    │  Иммунная   │      │  MCP-сервер  │
    │  система    │      │  Транспорт   │
    │ n8n+Gemini  │      │  исполнения  │
    └─────────────┘      └──────────────┘
```

---

## Блоки — быстрый обзор

| # | Блок | Что делает | Карта | Смежные |
|---|------|------------|-------|---------|
| 01 | **Core Engine** | Главный диспетчер. Принимает запрос, управляет конвейером от плана флагмана до выдачи картриджа | [→ карта](BLOCK_01_core_engine.md) | 02, 03, 06 |
| 02 | **Language Library** | Язык-Библиотека. SCL-символы в pgvector. Поиск по маячкам, рейтинги, эволюция символов | [→ карта](BLOCK_02_language_library.md) | 01, 03 |
| 03 | **Shard Storage** | Холодное хранилище. zstd-сжатые инструкции на бесплатных шардах с зеркалированием | [→ карта](BLOCK_03_shard_storage.md) | 01, 02 |
| 04 | **CLI Layer** | Скелетонизатор контекста. Сжимает файлы проекта до сигнала перед отправкой флагману | [→ карта](BLOCK_04_cli_layer.md) | 01, 05 |
| 05 | **MCP Server** | Транспорт исполнения. JSON-RPC шлюз для физических действий во внешних средах | [→ карта](BLOCK_05_mcp_server.md) | 01, 04 |
| 06 | **YMS-MMM** | Верификатор. Перехватывает вывод флагмана, проверяет 100% соответствие ТЗ | [→ карта](BLOCK_06_ymm_verifier.md) | 01, 07 |
| 07 | **Immune System** | Реаниматор. n8n + Gemini (fallback: Ollama). Активируется при 3 провалах верификации | [→ карта](BLOCK_07_immune_system.md) | 06, 01 |
| 00 | **README / Nav** | Этот файл. Карта всего проекта | — | все |

---

## Текущий статус блоков

| Блок | Статус | Фаза | Реализация |
|------|--------|------|-----------|
| 01 Core Engine | 🔵 Сшит и проверен | Все фазы | `api/` + `core/` |
| 02 Language Library | 🔵 Сшит и проверен | Фаза 0+1 | `core/librarian.py` + `core/archivist.py` + `db/` |
| 03 Shard Storage | 🔵 Сшит и проверен | Фаза 0 | `shards/` |
| 04 CLI Layer | 🔵 Сшит и проверен | Фаза 2 | `core/cli_layer.py` |
| 05 MCP Server | 🔵 Сшит и проверен | Фаза 2 | `core/mcp_server.py` |
| 06 YMS-MMM | 🔵 Сшит и проверен | Фаза 1 | `core/verifier.py` + `core/obsidian.py` |
| 07 Immune System | 🔵 Сшит и проверен | Фаза 2 | `core/immune_system.py` + `n8n/` |
| Канал 1 (СОН) | 🔵 Сшит и проверен | Фаза 4 | `core/knowledge_collector.py` + `core/sleep_mode.py` |
| Безопасность | 🔵 Сшит и проверен | Фаза 4 | `api/middleware/security.py` + `core/crypto.py` + `db/users.py` |
| Публичный сайт | 🟡 Готов, нужен деплой | Фаза 3 | `site/index.html` (Dark High-Tech + Three.js глобус) |
| nginx + docker | 🟡 Готов, нужен деплой | Фаза 3 | `site/nginx.conf` + `docker-compose.yml` site-сервис |
| MCP Registry | 🟡 Манифест готов | Фаза 3 | `site/mcp-manifest.json` — нужен публичный HTTPS |

**Статусы:** 🔴 Не начат / 🟡 В работе / 🟢 Готов / 🔵 Сшит и проверен

---

## Порядок реализации (выполнено)

### Фаза 0 — Минимальное рабочее ядро ✅
```
БЛОК 02 → БЛОК 03 → БЛОК 01 (минимум)
```
- БЛОК 02: PostgreSQL + pgvector + SCL-схема + bootstrap символов
- БЛОК 03: zstd compress/decompress + шарды + autopatch shard_link
- БЛОК 01: HTTP-эндпоинты handshake/concierge/query/step_done

### Фаза 1 — Полный конвейер ✅
- БЛОК 06: YMS-MMM верификатор + контур Obsidian (Тип А/Б + лигатуры)
- БЛОК 01: интервью флагмана + сборщик картриджа + архиватор

### Фаза 2 — Транспорт + Иммунная система ✅
- БЛОК 04: CLI-скелетонизатор + detect_stack
- БЛОК 05: MCP-сервер JSON-RPC 2.0
- БЛОК 07: n8n + Gemini + Ollama fallback + patch_callback

### Безопасность ✅
- AES шифрование токенов в БД
- JWT + X-API-Key аутентификация + rate limiting
- HMAC подпись ответов ядра
- Path traversal защита на шардах
- Audit log, управление пользователями

### Фаза 4 — Безопасность + Автонаполнение ✅
- `core/knowledge_collector.py` — Канал 1 автонаполнение в режиме СОН
- `core/archivist.py::_new_symbol` — поля source_url/rating/type/auto_collected
- `db/pg_client.py::insert_symbol` — INSERT с полями Канала 1 ($21–$24)
- `db/migrations/004_channel1_fields.sql` — ALTER TABLE для existing БД
- `docker-compose.yml` — migration 004 в init-последовательности

### Фаза 3 — Сайт + Запуск 🟡 В РАБОТЕ
- [x] Публичный сайт `evo-core.io` — `site/index.html` Dark High-Tech + Three.js глобус
- [x] 3D-глобус знаний — Two.js в `site/index.html` (узлы=символы, пульсация=R_f)
- [x] nginx конфиг `site/nginx.conf` + docker-compose site сервис
- [x] MCP Registry манифест `site/mcp-manifest.json`
- [ ] Деплой на VPS (домен evo-core.io + SSL + .env + bootstrap.py)
- [ ] Регистрация в Anthropic MCP Registry (нужен публичный HTTPS)
- [ ] Бесплатный период СТАРТ 🚀

---

## Два канала наполнения ядра знаниями

```
КАНАЛ 1 — Автономный (режим СОН):
  Ядро само сканирует GitHub/маркетплейсы/документацию
  Находит знания отсутствующие в базе (белые зоны)
  Забирает, верифицирует через YMS-MMM, записывает
  → см. SLEEP_MODE.md раздел "Автонаполнение"

КАНАЛ 2 — Через флагмана (рабочий режим):
  Флагман решает задачу → result workability=true
  Ядро забирает решение → YMS-MMM → Obsidian → запись
  → см. SCL_FRACTAL_PROTOCOL.md раздел 10-14
```

---

## Правила апдейта статусов

1. Закончил задачу в блоке → обнови `## Статус` в файле этого блока
2. Сшил два блока и проверил → обнови `## Сшивка` в **обоих** файлах
3. Никогда не меняй статус на 🔵 без реальной функциональной проверки
4. Дата последнего апдейта — в каждом файле блока

---

## Быстрый старт

```bash
git clone https://github.com/OneDimon/EVO_core && cd EVO_core
cp .env.example .env
./scripts/deploy.sh gen-secrets >> .env
# Заполнить GEMINI_API_KEY в .env
./scripts/deploy.sh check
./scripts/deploy.sh full

# Создать admin пользователя
curl -X POST http://localhost:8000/api/v1/admin/users \
  -H "X-Admin-Token: $(grep EVO_API_SECRET .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","plan":"pro"}'

# Admin UI
open http://localhost:8000/admin

# n8n БЛОК 07
./scripts/deploy.sh n8n
```

---

## Тесты

```bash
EVO_ENV=development python tests/test_phase0.py   # 9 тестов Фаза 0
EVO_ENV=development python tests/test_phase1.py   # 9 тестов Фаза 1+2
EVO_ENV=development python tests/test_full.py     # 20 тестов полный стек
```

---

## Навигация по ключевым документам

| Файл | Назначение |
|------|-----------|
| [PROJECT_MAP.md](PROJECT_MAP.md) | Главная карта: дерево файлов, сшивка, деплой |
| [SCL_FRACTAL_PROTOCOL.md](SCL_FRACTAL_PROTOCOL.md) | Протокол Языка-Библиотеки (32 корня, лигатуры, алгоритмы) |
| [SCL_SYMBOLIC_NOTATION.md](SCL_SYMBOLIC_NOTATION.md) | Нотация символов — святая святых |
| [FLAGSHIP_SYSTEM_PROMPT.md](FLAGSHIP_SYSTEM_PROMPT.md) | Системный промпт флагмана |
| [LOCAL_MODEL_INSTRUCTIONS.md](LOCAL_MODEL_INSTRUCTIONS.md) | Инструкции локальной модели-хранителя |
| [SLEEP_MODE.md](SLEEP_MODE.md) | Режим СОН: фоновая работа + автонаполнение |
| [AI_ONBOARDING.md](AI_ONBOARDING.md) | **Читай первым** — карта проекта, схема, статусы, деплой |
| [site/index.html](site/index.html) | Публичный сайт Dark High-Tech + Three.js глобус знаний |
| [site/mcp-manifest.json](site/mcp-manifest.json) | Манифест для Anthropic MCP Registry |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Полный технический план v3.1 (Фазы 0–4 ✅, Фаза 3 сайт 🟡 деплой 🔴) |

---

*Версия: 3.1 | 2026-06-13 | Архитектор: @OneDimon*
*Фазы 0–4 выполнены. Фаза 3: сайт+глобус+MCP манифест ✅, деплой 🔴*
*YMS-MMM ACTIVE*
