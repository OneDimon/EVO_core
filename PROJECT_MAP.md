# EVO-core — Project Map

> **Правило входа:** Прочитай этот файл ПЕРВЫМ. Здесь вся карта проекта,
> статус каждого блока, что сшито, что нужно деплоить следующим.
> YMS-MMM ACTIVE | Архитектор: @OneDimon

---

## Дерево проекта

```
evo-core/
├── PROJECT_MAP.md          ← ТЫ ЗДЕСЬ. Читать первым.
├── README.md               ← Краткое описание для GitHub
│
├── api/                    ← FastAPI эндпоинты (БЛОК 01)
│   ├── main.py             ← Точка входа FastAPI
│   ├── routes/
│   │   ├── handshake.py    ← POST /api/v1/handshake
│   │   ├── concierge.py    ← POST /api/v1/concierge
│   │   ├── query.py        ← POST /api/v1/query
│   │   ├── step_done.py    ← POST /api/v1/step_done
│   │   ├── result.py       ← POST /api/v1/result
│   │   └── hook_reply.py   ← POST /api/v1/hook_reply
│   └── middleware/
│       └── hmac_auth.py    ← HMAC верификация ответов
│
├── core/                   ← Ядро логики
│   ├── ai_router.py        ← AI коннектор (Gemini/Ollama/любая)
│   ├── librarian.py        ← Библиотекарь: поиск символов (БЛОК 02)
│   ├── archivist.py        ← Архивариус: запись символов (БЛОК 02)
│   ├── concierge.py        ← Консьерж: выяснение стека (БЛОК 01)
│   ├── cartridge.py        ← Сборка картриджа под план+стек
│   ├── verifier.py         ← YMS-MMM верификатор (БЛОК 06)
│   ├── obsidian.py         ← Контур Obsidian: Тип А/Б (БЛОК 06)
│   └── sleep_mode.py       ← Режим СОН (SLEEP_MODE.md)
│
├── db/                     ← База данных (БЛОК 02)
│   ├── models.py           ← Pydantic модели SCLSymbol
│   ├── pg_client.py        ← PostgreSQL + pgvector клиент
│   ├── redis_client.py     ← Redis горячий кэш + очередь
│   └── migrations/
│       └── 001_init.sql    ← Первая миграция: scl_symbols таблица
│
├── shards/                 ← Работа с шардами (БЛОК 03)
│   ├── shard_client.py     ← Чтение/запись на шарды
│   └── zstd_codec.py       ← zstd на лету в памяти
│
├── config/
│   ├── ai_router.json      ← Роутинг моделей (уже в репо)
│   ├── deployment.json     ← Деплой конфиг (уже в репо)
│   └── notifications.json  ← ТГ-бот + админка (заполнить при деплое)
│
├── prompts/
│   ├── flagship_system_prompt.txt   ← Промпт флагмана
│   └── local_model_instructions.txt ← Инструкции локальной модели
│
├── scripts/
│   ├── bootstrap.py        ← Первичное наполнение через Gemini
│   ├── bootstrap_check.py  ← Проверка готовности базы
│   └── deploy.sh           ← Деплой скрипт
│
├── tests/
│   ├── test_phase0.py      ← Тесты Фазы 0: запрос→поиск→выдача
│   └── test_notation.py    ← Тесты нотации SCL символов
│
├── .env.example            ← Переменные окружения (заполнить)
├── docker-compose.yml      ← PostgreSQL + Redis + API
├── Dockerfile              ← Образ API сервера
└── requirements.txt        ← Python зависимости
```

---

## Статус блоков

| Блок | Файлы | Статус | Сшит с |
|------|-------|--------|--------|
| БЛОК 01 Core Engine | `api/`, `core/concierge.py`, `core/cartridge.py` | 🔴 Не начат | 02, 03, 06 |
| БЛОК 02 Language Library | `core/librarian.py`, `core/archivist.py`, `db/` | 🔴 Не начат | 01, 03, 06 |
| БЛОК 03 Shard Storage | `shards/` | 🔴 Не начат | 01, 02 |
| БЛОК 04 CLI Layer | — | 🔴 Фаза 2 | 01, 05 |
| БЛОК 05 MCP Server | — | 🔴 Фаза 2 | 01, 04 |
| БЛОК 06 YMS-MMM | `core/verifier.py`, `core/obsidian.py` | 🔴 Фаза 1 | 01, 02, 07 |
| БЛОК 07 Immune System | n8n воркфлоу | 🔴 Фаза 2 | 06, 01 |
| AI Router | `core/ai_router.py` | 🔴 Не начат | все |
| Sleep Mode | `core/sleep_mode.py` | 🔴 Фаза 1 | 01 |

**Статусы:** 🔴 Не начат / 🟡 В работе / 🟢 Готов / 🔵 Сшит и проверен

---

## Порядок деплоя

### Фаза 0 — Минимальное рабочее ядро (СЕЙЧАС)
```
1. docker-compose up (PostgreSQL + Redis)
2. python scripts/deploy.sh migrate
3. python scripts/bootstrap.py --check
4. uvicorn api.main:app
5. python tests/test_phase0.py
```

Что проверяет Фаза 0:
- Запрос флагмана → консьерж → поиск символа → декомпрессия → выдача
- Нотация символов: создание, расшифровка, кластер
- Запись нового символа в pgvector + шард

### Фаза 1 — Полный конвейер
```
После зелёных тестов Фазы 0:
+ core/verifier.py (YMS-MMM)
+ core/obsidian.py (Тип А/Б)
+ core/sleep_mode.py (СОН)
```

### Фаза 2 — Транспорт
```
+ БЛОК 04 CLI Layer
+ БЛОК 05 MCP Server
+ БЛОК 07 Immune System (n8n)
```

---

## Ключевые правила (читать при каждом входе)

1. **Нотация символов** → `SCL_SYMBOLIC_NOTATION.md` — святая святых
2. **Протокол библиотеки** → `SCL_FRACTAL_PROTOCOL.md`
3. **Промпт флагмана** → `FLAGSHIP_SYSTEM_PROMPT.md`
4. **Инструкции локальной модели** → `LOCAL_MODEL_INSTRUCTIONS.md`
5. **AI Router** → `config/ai_router.json` — все AI-вызовы только через него
6. **Запись** → миллисекунды, асинхронно, пользователь не ждёт
7. **Legacy** → `is_legacy: true` + `superseded_by`, не удалять
8. **Хронология** → `evolved_from`, `evolution_note` неприкосновенны

---

## При следующем входе — чеклист

```
□ Прочитал PROJECT_MAP.md
□ Проверил статус блоков в таблице выше
□ Открыл BLOCK_XX нужного блока — прочитал коннекторы и зависимости
□ Проверил сшивку в таблице блока
□ Обновил статус после завершения работы
```

---
*Обновлён: 2026-06-03 | v1.0*
