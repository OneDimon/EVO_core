# EVO-core — Project Map

> **Правило входа:** Прочитай ПЕРВЫМ. Карта, статус, сшивка.
> YMS-MMM ACTIVE | Архитектор: @OneDimon | v3.0

---

## Дерево проекта

```
evo-core/
├── PROJECT_MAP.md          ← ТЫ ЗДЕСЬ
├── api/
│   ├── main.py             ✅ v0.3 + sleep scheduler
│   └── routes/
│       ├── handshake.py    ✅ /handshake
│       ├── concierge.py    ✅ /concierge
│       ├── query.py        ✅ /query + Redis план
│       ├── step_done.py    ✅ /step_done
│       ├── result.py       ✅ /result + verifier + obsidian + immune
│       ├── hook_reply.py   ✅ /hook_reply
│       ├── admin.py        ✅ /admin/* (токены, конфиги, шарды)
│       ├── patch_callback.py ✅ /patch_callback (реаниматор)
│       └── mcp.py          ✅ /mcp (JSON-RPC 2.0)
├── core/
│   ├── ai_router.py        ✅ Gemini→Flash→Ollama
│   ├── librarian.py        ✅ поиск + Redis план
│   ├── archivist.py        ✅ Тип А/Б + confirmed_in
│   ├── verifier.py         ✅ YMS-MMM
│   ├── obsidian.py         ✅ Тип А/Б + лигатуры + граф
│   ├── immune_system.py    ✅ реаниматор БЛОК 07
│   ├── cli_layer.py        ✅ скелетонизатор БЛОК 04
│   ├── mcp_server.py       ✅ JSON-RPC БЛОК 05
│   ├── config_manager.py   ✅ единый конфиг
│   └── sleep_mode.py       ✅ СОН + ТГ-уведомления
├── db/
│   ├── models.py / pg_client.py / redis_client.py  ✅
│   └── migrations/ 001_init.sql + 002_config.sql   ✅
├── shards/
│   ├── zstd_codec.py       ✅ compress + гиперлинки
│   └── shard_client.py     ✅ local|gdrive|github|r2 + autopatch
├── config/
│   ├── ai_router.json      ✅ Gemini/Ollama роутинг
│   └── deployment.json     ✅
├── prompts/
│   ├── flagship_system_prompt.txt    ✅ v3.0
│   └── local_model_instructions.txt  ✅ v1.0
├── scripts/ bootstrap.py + deploy.sh   ✅
├── tests/ test_phase0.py + test_phase1.py  ✅
└── docker-compose.yml / Dockerfile / .env.example  ✅
```

---

## Статус блоков

| Блок | Статус | Файл | Сшит с |
|------|--------|------|--------|
| **01** Core Engine | 🟢 Готов | api/ | 02✅ 03✅ 06✅ 07✅ |
| **02** Language Library | 🟢 Готов | librarian+archivist+db/ | 01✅ 03✅ 06✅ |
| **03** Shard Storage | 🟢 Готов | shards/ | 01✅ 02✅ |
| **04** CLI Layer | 🟢 Готов | core/cli_layer.py | 01✅ |
| **05** MCP Server | 🟢 Готов | core/mcp_server.py | 01✅ |
| **06** YMS-MMM+Obsidian | 🟢 Готов | verifier+obsidian | 01✅ 02✅ 07✅ |
| **07** Immune System | 🟢 Готов | core/immune_system.py | 06✅ 01✅ |
| **AI Router** | 🟢 Готов | core/ai_router.py | все |
| **Config+Admin** | 🟢 Готов | config_manager+admin.py | все |
| **Sleep Mode** | 🟢 Готов | core/sleep_mode.py | scheduled |

---

## Сшивка (все коннекторы)

```
01─query──────→ 02 librarian.search()              ✅
01─step_done──→ 02 librarian.load_step_body()      ✅
01─result─────→ 06 verifier.verify()               ✅
01─result─────→ 06 obsidian.process() [async]      ✅
01─result─────→ 07 immune.reanimate() [async]      ✅
01─archive────→ 02 archivist.archive() [async]     ✅
02─read───────→ 03 shard_client.read_cell()        ✅
02─write──────→ 03 shard_client.write_cell()       ✅
03─autopatch──→ 02 pg._attach_link() [auto]        ✅
06─Тип А/Б────→ 02 archivist._type_a/_type_b       ✅
06─лигатуры───→ 02 pg.insert_symbol()              ✅
all─ai────────→ AI Router → Gemini/Ollama          ✅
all─config────→ config_manager → Admin UI → БД    ✅
sleep─notify──→ ТГ Bot + /admin/notify             ✅
```

---

## Как запустить (все фазы)

```bash
git clone https://github.com/OneDimon/EVO_core
cd EVO_core
cp .env.example .env           # заполнить GEMINI_API_KEY
./scripts/deploy.sh full       # docker + migrate + bootstrap + тест Ф.0
python tests/test_phase1.py    # тест Ф.1+2 (нужен запущенный API)
```

## Токены и шарды — вносить через Admin API

```bash
# TG бот (уведомления Архитектора)
curl -X POST http://localhost:8000/api/v1/admin/config \
  -H "X-Admin-Token: $(grep EVO_API_SECRET .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"key":"TG_BOT_TOKEN","value":"YOUR_TOKEN"}'

# Шард Google Drive
-d '{"key":"SHARD_PROVIDER","value":"gdrive"}'
-d '{"key":"SHARD_GDRIVE_TOKEN","value":"ya29...."}'
-d '{"key":"SHARD_GDRIVE_FOLDER","value":"FOLDER_ID"}'

# Шард GitHub
-d '{"key":"SHARD_PROVIDER","value":"github"}'
-d '{"key":"SHARD_GITHUB_TOKEN","value":"ghp_..."}'
-d '{"key":"SHARD_GITHUB_REPO","value":"owner/repo"}'

# Тест подключения шарда
curl http://localhost:8000/api/v1/admin/shards/test \
  -H "X-Admin-Token: YOUR_ADMIN_SECRET"
```

Все значения → БД evo_config → применяются везде автоматически.

---

## Готово к тестированию

| Фаза | Тест | Покрывает |
|------|------|-----------|
| 0 | `python tests/test_phase0.py` | handshake→concierge→query→step→result→hook |
| 1+2 | `python tests/test_phase1.py` | Admin, YMS-MMM, Obsidian, MCP, CLI, Immune |

---

## Чеклист при входе

```
□ Прочитал PROJECT_MAP.md
□ Проверил статус блоков
□ Проверил сшивку
□ Обновил статус после работы
```

---
*v3.0 | 2026-06-03 | Все блоки реализованы. Готово к тестам.*
