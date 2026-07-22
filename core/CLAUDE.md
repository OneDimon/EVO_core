# core/ — Core Engine, Language Library, YMM Verifier, Immune System (Блоки 01/02/06/07)

**Перед правкой обязательно прочитать** карту нужного блока — не читать все
сразу:
- `librarian.py`, `ai_router.py` → `../BLOCK_02_language_library.md`
- `verifier.py` → `../BLOCK_06_ymm_verifier.md`
- `immune_system.py`, `sleep_mode.py` → `../BLOCK_07_immune_system.md`
- `cli_layer.py` → `../BLOCK_04_cli_layer.md`
- `mcp_server.py` → `../BLOCK_05_mcp_server.md`
- `archivist.py` → `../BLOCK_01_core_engine.md`

## Что здесь
| Файл | Роль |
|---|---|
| `ai_router.py` | Единственная точка вызова AI-провайдеров (Gemini/Ollama/OpenAI). Конфиг `config/ai_router.json`. Все AI-вызовы — только отсюда |
| `librarian.py` | Поиск символов: `similarity × log(R_f+2)` под план+стек |
| `archivist.py` | Сборка картриджа для флагмана |
| `verifier.py` | YMM-сверка выданного vs применённого, атомарный счётчик провалов (Redis INCR) |
| `immune_system.py` | Автовосстановление, реаниматор-патчи |
| `sleep_mode.py` | Фоновые задачи по расписанию (apscheduler) — дефрагментация шардов, тех-проверки устаревших символов |
| `cli_layer.py` | Скелетонизация контекста проекта перед отправкой флагману |
| `config_manager.py` | Чтение/запись `evo_config` в БД, шифрование через `crypto.py` |
| `crypto.py` | AES/Fernet-шифрование sensitive-полей. `SENSITIVE_KEYS` — обновлять при добавлении нового секрета |
| `knowledge_collector.py` | Сканер "белых зон" знаний (`_scan_knowledge_gaps`) |
| `signature.py` | Единая точка HMAC-подписи/верификации `evo_signature` протокола ядро↔флагман (`sign_response()`/`verify_request()`), ключ — `evo_sessions.hmac_key` (см. `db/sessions.py`) |
| `verifier.py`, `mcp_server.py` | см. выше |

## Правила
- Любой новый AI-вызов — через `ai_router.AIRouter`, не напрямую к SDK.
- CPU-bound (zstd/hashlib) внутри `async def` → `asyncio.to_thread`.
- Новый секрет в конфиге → добавить в `crypto.py::SENSITIVE_KEYS`.
- Для идентификаторов/кодов — сверяться с `SCL_FRACTAL_PROTOCOL.md` /
  `SCL_SYMBOLIC_NOTATION.md`, не изобретать параллельную таксономию.
- Любой новый роут протокола с `session_id` (по образцу `/query`, `/result`,
  `/concierge`, `/step_done`, `/hook_reply`, `/patch_callback`) — обязан
  верифицировать вход через `signature.verify_request()` и подписывать выход
  через `signature.sign_response()`. Не изобретать HMAC-логику на месте.
