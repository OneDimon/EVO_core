# EVO-core — Project Map

> **Правило входа:** Прочитай этот файл ПЕРВЫМ при каждой сессии.
> Карта проекта, статус блоков, что сшито, что деплоить следующим.
> YMS-MMM ACTIVE | Архитектор: @OneDimon | v1.1

---

## Дерево проекта

```
evo-core/
├── PROJECT_MAP.md              ← ТЫ ЗДЕСЬ. Читать первым.
├── README.md
│
├── api/                        ← FastAPI эндпоинты (БЛОК 01)
│   ├── main.py                 ✅ готов
│   └── routes/
│       ├── handshake.py        ✅ POST /api/v1/handshake
│       ├── concierge.py        ✅ POST /api/v1/concierge
│       ├── query.py            ✅ POST /api/v1/query + Redis план
│       ├── step_done.py        ✅ POST /api/v1/step_done
│       ├── result.py           ✅ POST /api/v1/result
│       └── hook_reply.py       ✅ POST /api/v1/hook_reply
│
├── core/
│   ├── ai_router.py            ✅ Gemini→Flash→Ollama fallback
│   ├── librarian.py            ✅ поиск + Redis план + step_body
│   ├── archivist.py            ✅ Тип А/Б + confirmed_in + is_legacy
│   ├── concierge.py            🔴 Фаза 1
│   ├── verifier.py             🔴 Фаза 1 (YMS-MMM)
│   ├── obsidian.py             🔴 Фаза 1 (Тип А/Б расширенный)
│   └── sleep_mode.py           🔴 Фаза 1
│
├── db/
│   ├── models.py               ✅ SCLSymbol + все поля
│   ├── pg_client.py            ✅ find/insert/update/increment
│   ├── redis_client.py         ✅ кэш + план + очередь + RPS stats
│   └── migrations/
│       └── 001_init.sql        ✅ все таблицы + 9 индексов
│
├── shards/
│   ├── zstd_codec.py           ✅ compress/decompress + гиперлинки
│   └── shard_client.py         ✅ read/write + fallback зеркало
│
├── config/
│   ├── ai_router.json          ✅ Gemini/Ollama роутинг
│   ├── deployment.json         ✅ полный деплой конфиг
│   └── notifications.json      🔴 заполнить TG_BOT_TOKEN при деплое
│
├── prompts/
│   ├── flagship_system_prompt.txt    ✅ v3.0
│   └── local_model_instructions.txt  ✅ v1.0
│
├── scripts/
│   ├── bootstrap.py            ✅ 8 стартовых символов
│   ├── bootstrap_check.py      ✅ проверка готовности
│   └── deploy.sh               ✅ full|start|migrate|test|logs
│
├── tests/
│   ├── test_phase0.py          ✅ 9 тестов полного цикла
│   └── test_notation.py        ✅ гиперлинки + zstd + ID формат
│
├── .env.example                ✅
├── docker-compose.yml          ✅ postgres pgvector + redis + api
├── Dockerfile                  ✅
└── requirements.txt            ✅
```

---

## Статус блоков

| Блок | Файлы | Статус | Сшит с | Проверено |
|------|-------|--------|--------|-----------|
| **БЛОК 01** Core Engine | `api/`, `core/ai_router.py` | 🟡 Фаза 0 готов | 02✅ 03✅ 06🔴 | handshake→concierge→query→step→result→hook |
| **БЛОК 02** Language Library | `core/librarian.py`, `core/archivist.py`, `db/` | 🟡 Фаза 0 готов | 01✅ 03✅ 06🔴 | поиск + запись + confirmed_in |
| **БЛОК 03** Shard Storage | `shards/` | 🟢 Готов | 01✅ 02✅ | zstd + гиперлинки + fallback |
| **БЛОК 04** CLI Layer | — | 🔴 Фаза 2 | — | — |
| **БЛОК 05** MCP Server | — | 🔴 Фаза 2 | — | — |
| **БЛОК 06** YMS-MMM | `core/verifier.py` | 🔴 Фаза 1 | — | — |
| **БЛОК 07** Immune System | n8n воркфлоу | 🔴 Фаза 2 | — | — |
| **AI Router** | `core/ai_router.py` | 🟢 Готов | все | Gemini+Ollama |
| **Sleep Mode** | `core/sleep_mode.py` | 🔴 Фаза 1 | — | — |

**Статусы:** 🔴 Не начат / 🟡 В работе / 🟢 Готов / 🔵 Сшит и проверен

---

## Сшивка блоков (Фаза 0)

```
БЛОК 01 ──query──────→ БЛОК 02 (librarian.search)     ✅ сшит
БЛОК 01 ──step_done──→ БЛОК 02 (librarian.load_step)  ✅ сшит
БЛОК 02 ──shard_read─→ БЛОК 03 (shard_client.read)    ✅ сшит
БЛОК 02 ──write──────→ БЛОК 03 (shard_client.write)   ✅ сшит
БЛОК 01 ──result─────→ БЛОК 02 (archivist.archive)    ✅ сшит
БЛОК 01 ──all routes─→ AI Router (ai_router.*)         ✅ сшит
Redis    ←plan cache──  БЛОК 01 query                  ✅ сшит
Redis    ──plan read──→ БЛОК 01 step_done              ✅ сшит

БЛОК 01 ──verify─────→ БЛОК 06                        🔴 Фаза 1
БЛОК 06 ──webhook────→ БЛОК 07                        🔴 Фаза 2
```

---

## Порядок деплоя

### Фаза 0 — СЕЙЧАС (всё готово)

```bash
git clone https://github.com/OneDimon/EVO_core
cd EVO_core
cp .env.example .env
# Заполнить GEMINI_API_KEY в .env
./scripts/deploy.sh full
# Ожидаемый результат: Phase 0 Tests: 9/9 passed
```

Что проверяет:
- handshake → session_id + hmac_key
- concierge → context_accepted
- query → картридж (full/partial/gap)
- step_done → тело шага из Redis
- result workability=false → rejected
- result workability=true → verified + hook
- hook_reply → session_complete

### Фаза 1 (следующий этап после зелёных тестов Фазы 0)

```
Добавить:
+ core/verifier.py      (YMS-MMM полная проверка)
+ core/obsidian.py      (контур логики + граф)
+ core/sleep_mode.py    (режим СОН + уведомления)
+ config/notifications.json (TG_BOT_TOKEN)
Обновить:
~ api/routes/result.py  (подключить verifier вместо auto-verify)
~ BLOCK_06_ymm_verifier.md статус → 🟡
```

### Фаза 2

```
+ БЛОК 04 CLI Layer
+ БЛОК 05 MCP Server
+ БЛОК 07 n8n Immune System
```

---

## Ключевые правила (при каждом входе)

1. **Нотация** → `SCL_SYMBOLIC_NOTATION.md` — все ID символов по нотации
2. **Протокол библиотеки** → `SCL_FRACTAL_PROTOCOL.md`
3. **AI-вызовы** → только через `core/ai_router.py`
4. **Запись** → всегда асинхронно через `db/redis_client.enqueue_write`
5. **Legacy** → `is_legacy=True` + `superseded_by` — не удалять символы
6. **Хронология** → `evolved_from`, `evolution_note` неприкосновенны
7. **Workability** → флагман сам проверяет, отчитывается с флагом
8. **step_done** → каждый следующий шаг только после предыдущего

---

## При следующем входе — чеклист

```
□ Прочитал PROJECT_MAP.md
□ Проверил статус блоков в таблице
□ Проверил сшивку блоков
□ Открыл BLOCK_XX нужного блока — прочитал коннекторы
□ Обновил статус после завершения
```

---
*Обновлён: 2026-06-03 | v1.1 — Фаза 0 код готов, 5 багов исправлено*
