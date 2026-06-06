# EVO-core — Project Map

> **Правило входа:** Прочитай этот файл ПЕРВЫМ при каждой сессии.
> Карта проекта, статус блоков, сшивка, что деплоить следующим.
> YMS-MMM ACTIVE | Архитектор: @OneDimon | v2.0

---

## Дерево проекта

```
evo-core/
├── PROJECT_MAP.md              ← ТЫ ЗДЕСЬ. Читать первым.
│
├── api/
│   ├── main.py                 ✅ v0.2 + startup init
│   └── routes/
│       ├── handshake.py        ✅ POST /api/v1/handshake
│       ├── concierge.py        ✅ POST /api/v1/concierge
│       ├── query.py            ✅ POST /api/v1/query + Redis план
│       ├── step_done.py        ✅ POST /api/v1/step_done
│       ├── result.py           ✅ POST /api/v1/result + verifier + obsidian
│       ├── hook_reply.py       ✅ POST /api/v1/hook_reply
│       └── admin.py            ✅ Admin API — токены/конфиги/шарды
│
├── core/
│   ├── ai_router.py            ✅ Gemini→Flash→Ollama fallback
│   ├── librarian.py            ✅ поиск + Redis план + step_body
│   ├── archivist.py            ✅ Тип А/Б + confirmed_in + legacy
│   ├── verifier.py             ✅ YMS-MMM полная верификация
│   ├── obsidian.py             ✅ Тип А/Б + лигатуры + граф
│   ├── config_manager.py       ✅ единый конфиг из БД + Admin UI
│   ├── sleep_mode.py           ✅ СОН + фон + ТГ-уведомления
│   └── concierge.py            🔴 Фаза 2 (детальная логика вопросов)
│
├── db/
│   ├── models.py               ✅ SCLSymbol + все поля
│   ├── pg_client.py            ✅ CRUD + векторный поиск
│   ├── redis_client.py         ✅ кэш + план + очередь + RPS
│   └── migrations/
│       ├── 001_init.sql        ✅ scl_symbols + 9 индексов
│       └── 002_config.sql      ✅ evo_config + начальные значения
│
├── shards/
│   ├── zstd_codec.py           ✅ compress/decompress + гиперлинки
│   └── shard_client.py         ✅ local|gdrive|github|r2 + autopatch
│
├── config/
│   ├── ai_router.json          ✅
│   ├── deployment.json         ✅
│   └── notifications.json      → заполняется через Admin UI
│
├── prompts/
│   ├── flagship_system_prompt.txt    ✅ v3.0
│   └── local_model_instructions.txt  ✅ v1.0
│
├── scripts/
│   ├── bootstrap.py            ✅
│   ├── bootstrap_check.py      ✅
│   └── deploy.sh               ✅
│
├── tests/
│   ├── test_phase0.py          ✅ 9 тестов
│   └── test_notation.py        ✅ 3 теста
│
├── .env.example / docker-compose.yml / Dockerfile / requirements.txt  ✅
```

---

## Статус блоков

| Блок | Статус | Реализовано | Сшивка |
|------|--------|-------------|--------|
| **01** Core Engine | 🟡 Ф.0+1 | 6 эндпоинтов + Admin API | 02✅ 03✅ 06✅ |
| **02** Language Library | 🟡 Ф.0+1 | librarian + archivist + pg + redis | 01✅ 03✅ 06✅ |
| **03** Shard Storage | 🟢 Готов | local+gdrive+github+r2 + autopatch | 01✅ 02✅ |
| **04** CLI Layer | 🔴 Ф.2 | — | — |
| **05** MCP Server | 🔴 Ф.2 | — | — |
| **06** YMS-MMM+Obsidian | 🟢 Готов | verifier + obsidian + лигатуры | 01✅ 02✅ 07⚠ |
| **07** Immune System | 🔴 Ф.2 | заглушка reanimate | — |
| **AI Router** | 🟢 Готов | Gemini+Flash+Ollama | все |
| **Config+Admin** | 🟢 Готов | config_manager + Admin API | все |
| **Sleep Mode** | 🟢 Готов | СОН + фон + ТГ + Arch.notify | 01 06 |

---

## Сшивка блоков

```
01 ──query────────→ 02 librarian.search()              ✅
01 ──step_done────→ 02 librarian.load_step_body()      ✅
01 ──result───────→ 06 verifier.verify()               ✅
01 ──result───────→ 06 obsidian.process() [async]      ✅
01 ──archive──────→ 02 archivist.archive() [async]     ✅
02 ──read/write───→ 03 shard_client.*                  ✅
03 ──autopatch────→ 02 pg_client._attach_link()        ✅
06 ──Тип А/Б──────→ 02 archivist._type_a/_type_b       ✅
06 ──лигатуры─────→ 02 pg_client.insert_symbol()       ✅
all ──ai calls────→ AI Router (config/ai_router.json)  ✅
all ──config──────→ config_manager (Admin UI → БД)     ✅
sleep ──notify────→ ТГ Bot + Admin /notify             ✅
01 ──reanimate─→ 07 webhook                            ⚠ Ф.2
04 CLI ───────→ 01 /api/v1/query                       ⚠ Ф.2
05 MCP ───────→ 01 /api/v1/*                           ⚠ Ф.2
```

---

## Где вносить токены (ОДИН РАЗ — применяется везде)

Все токены и конфиги вносятся через **Admin API**:

```bash
# Telegram бот
curl -X POST http://localhost:8000/api/v1/admin/config \
  -H "X-Admin-Token: your_admin_secret" \
  -H "Content-Type: application/json" \
  -d '{"key":"TG_BOT_TOKEN","value":"your_token"}'

curl -X POST http://localhost:8000/api/v1/admin/config \
  -d '{"key":"TG_ADMIN_CHAT_ID","value":"your_chat_id"}'

# Шард Google Drive
curl -X POST http://localhost:8000/api/v1/admin/config \
  -d '{"key":"SHARD_PROVIDER","value":"gdrive"}'
curl -X POST http://localhost:8000/api/v1/admin/config \
  -d '{"key":"SHARD_GDRIVE_TOKEN","value":"ya29...."}'
curl -X POST http://localhost:8000/api/v1/admin/config \
  -d '{"key":"SHARD_GDRIVE_FOLDER","value":"folder_id"}'

# Шард GitHub
curl -X POST http://localhost:8000/api/v1/admin/config \
  -d '{"key":"SHARD_PROVIDER","value":"github"}'
curl -X POST http://localhost:8000/api/v1/admin/config \
  -d '{"key":"SHARD_GITHUB_TOKEN","value":"ghp_..."}'
curl -X POST http://localhost:8000/api/v1/admin/config \
  -d '{"key":"SHARD_GITHUB_REPO","value":"owner/shard-repo"}'

# Тест подключения шарда
curl http://localhost:8000/api/v1/admin/shards/test \
  -H "X-Admin-Token: your_admin_secret"
```

Все значения сохраняются в БД (evo_config) и читаются везде автоматически через `config_manager.get(key)`. Перезапуск не нужен.

---

## Готово к тестированию

### Фаза 0+1 — READY

```bash
git clone https://github.com/OneDimon/EVO_core && cd EVO_core
cp .env.example .env          # заполнить GEMINI_API_KEY
./scripts/deploy.sh full      # docker + migrate + bootstrap + test
# Ожидается: Phase 0 Tests: 9/9 passed
```

После запуска — внести токены через Admin API (выше).

### Что проверяется в тестах Фазы 0:
1. handshake → session_id
2. concierge → context_accepted
3. query → картридж (full/partial/gap)
4. step_done → тело шага N+1
5. result workability=false → rejected
6. result workability=true → verified + YMS-MMM + Obsidian async
7. hook_reply → session_complete

### Фаза 2 (следующий этап)

```
+ БЛОК 04 CLI Layer    (core/cli_layer.py + LiteLLM proxy)
+ БЛОК 05 MCP Server   (core/mcp_server.py + StreamableHTTP)
+ БЛОК 07 Immune System (n8n workflow + webhook /api/v1/patch_callback)
+ Sleep scheduler      (APScheduler в startup)
+ Admin UI frontend    (React dashboard)
```

---

## Чеклист при каждом входе

```
□ Прочитал PROJECT_MAP.md
□ Проверил статус и сшивку блоков
□ Открыл BLOCK_XX нужного блока → коннекторы + зависимости
□ Обновил статус после завершения работы
□ Проверил что autopatch shard_link работает после write_cell
```

---
*v2.0 | 2026-06-03 | Фаза 0+1 реализована | 9 файлов Фазы 1 загружены*
