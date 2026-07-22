# CLAUDE.md — инструкции для AI-агента, работающего с кодовой базой EVO-core

> Это инструкции для агента, который **правит код** в этом репозитории
> (Claude Code, Cursor и т.п.). Не путать с `.claude/CLAUDE.md` / `AGENTS.md` /
> `FLAGSHIP_SYSTEM_PROMPT.md` — это другое, см. раздел ниже.

## ⚠️ Карта документации репо (важно не перепутать)

| Файл | Что это на самом деле |
|---|---|
| **`CLAUDE.md`** (этот файл) | Инструкции для coding-агента: команды, стиль, границы, архитектура |
| `.claude/CLAUDE.md`, `AGENTS.md`, `FLAGSHIP_SYSTEM_PROMPT.md` | **Продуктовый системный промпт EVO-core** — протокол, который сам продукт встраивает во флагманскую AI-модель при подключении через API (handshake → concierge → query → result). Содержимое идентично во всех трёх файлах. Править их — значит менять поведение продукта, а не документацию для себя. Не трогать "чтобы обновить доку для агента" |
| `README.md`, `PROJECT_MAP.md` | Карта архитектуры, схема блоков 01-07 |
| `BLOCK_0X_*.md` (7 файлов) | Детальная карта каждого блока — читать перед правкой соответствующего блока |
| `AI_ONBOARDING.md` | Онбординг для новой сессии разработки |
| `AUDIT_*.md` (6 файлов) | История аудитов и закрытых багов — грепать перед правкой похожей логики |
| `SCL_FRACTAL_PROTOCOL.md`, `SCL_SYMBOLIC_NOTATION.md` | Канонический источник для таблиц соответствий/кодов (см. "Не трогать" ниже) |
| `essence.md` | Большой файл контекста ядра (248KB) — не грузить целиком без необходимости |

## Обзор проекта

EVO-core — когнитивный слой между AI-флагманами и средой исполнения: хранит
верифицированные инженерные решения ("SCL-символы") в pgvector с рейтинговой
системой и выдаёт их точечно под конкретный стек/план через REST API.
Стек: Python 3.12, FastAPI, asyncpg + pgvector, Redis, zstd-сжатие для
холодного хранения ("шарды" на local/gdrive/github/r2).

## Команды разработки

**Установка** (pip, без poetry/pyproject.toml):
```bash
pip install -r requirements.txt
```

**Первый запуск:**
```bash
cp .env.example .env
./scripts/deploy.sh gen-secrets >> .env   # сгенерировать HMAC/API/ENCRYPTION ключи, вставить вручную
./scripts/deploy.sh full                  # check env + start + migrate + bootstrap + test
```

**По шагам:**
```bash
docker-compose up -d postgres redis
docker-compose up -d api        # API на http://localhost:8000
```

**Миграции** — ⚠️ известный пробел на момент аудита: `./scripts/deploy.sh migrate`
явно накатывает только 001-003. Миграции 004-008 применяются автоматически
только при первом создании volume postgres (через docker-entrypoint-initdb.d).
На уже существующей БД катить вручную:
```bash
docker cp db/migrations/00N_name.sql evo_postgres:/tmp/
docker exec evo_postgres psql -U evo_user -d evo_core -f /tmp/00N_name.sql
```
Следующий свободный номер миграции — **009** (ещё не создана).

**Тесты** — НЕ pytest-раннер, отдельные скрипты (несмотря на pytest в requirements.txt):
```bash
python tests/test_notation.py                        # unit, офлайн
python tests/test_shard_roundtrip.py                  # unit, офлайн-совместимый
python tests/test_signature.py                        # unit, офлайн (HMAC evo_signature)
EVO_ENV=development python tests/test_phase0.py       # нужен запущенный API
EVO_ENV=development python tests/test_phase1.py       # нужен запущенный API
python tests/test_channel1_scan.py                    # нужен Postgres с миграциями
python tests/test_full.py                             # полный интеграционный прогон
```
Шорткаты: `./scripts/deploy.sh test` (= test_phase0.py), `test1` (= test_phase1.py).

**Линтер/форматтер:** не настроен (нет .flake8/ruff/pyproject в репо) — следовать
стилю файла, который редактируешь.

## Стиль и конвенции кода

- Docstring в начале каждого модуля `core/*`, `api/routes/*` — 1-3 строки: что
  делает + ключевой инвариант/правило.
- Комментарии `# fix: ...` / `# N<номер> fix: ...` рядом с исправлением бага —
  это память "почему так сделано", **не удалять** при рефакторинге, переносить
  вместе с кодом.
- Логирование через `log = logging.getLogger("evo.<module>")`, никогда `print()`.
- Все AI-вызовы — **только** через `core/ai_router.py::AIRouter`, никогда
  напрямую к Gemini/OpenAI/Ollama SDK из другого модуля.
- CPU-bound синхронные вызовы (zstd compress/decompress, hashlib) внутри
  `async def` — оборачивать в `asyncio.to_thread`, иначе блокируется весь
  event loop воркера под нагрузкой.
- Пути к конфигам резолвить относительно `Path(__file__).resolve().parent`,
  не полагаться на текущую рабочую директорию вызывающего кода.
- Новое секретное поле конфигурации → обязательно добавить в
  `core/crypto.py::SENSITIVE_KEYS` (иначе уйдёт в БД в открытом виде).
- Fallback-ветки на нераспознанные случаи логировать через `log.error`
  (не `log.debug`), если это не единичный edge-case — молчаливый fallback
  месяцами скрывал реальные баги в этом проекте.
- Для "таблиц соответствий" (коды, идентификаторы, ROOT_CODES и т.п.) —
  сначала grep по `SCL_FRACTAL_PROTOCOL.md` / `SCL_SYMBOLIC_NOTATION.md` /
  `LOCAL_MODEL_INSTRUCTIONS.md` на предмет уже существующей канонической
  версии. Никогда не придумывать свою таблицу заново.
- Тестируй поведение функции (импортируй и вызови), а не только формат
  итоговой строки регуляркой — здесь уже был баг, где мусор проходил
  проверку формата.

## Ограничения — "не трогать" без явного запроса

- `.env`, `server_data/config/credentials.json` — секреты. Никогда не
  коммитить, не выводить содержимое в чат/логи/примеры.
- `db/migrations/001_init.sql` … `008_fix_ivfflat_cleanup.sql` — уже
  применённые миграции задним числом не редактировать. Изменения схемы —
  через новую миграцию (009+).
- `.agents/`, `data/`, `skills-lock.json` — легаси-артефакты стороннего
  memory-плагина, гитигнорены, не восстанавливать.
- `AGENTS.md`, `.claude/CLAUDE.md`, `FLAGSHIP_SYSTEM_PROMPT.md` — продуктовый
  системный промпт ядра. Редактировать только по прямому запросу об изменении
  самого протокола EVO-core, не как "апдейт доки для агента".
- Значения из `core/crypto.py::SENSITIVE_KEYS` (GEMINI_API_KEY, TG_BOT_TOKEN,
  SHARD_*_TOKEN/KEY, EVO_HMAC_SECRET и т.д.) — никогда не хардкодить и не
  логировать; в `.env.example` — только имена полей без значений.
- `docker-compose.yml` — `--reload` намеренно не используется в prod-команде
  api (см. комментарий в файле); при изменении команды запуска сохранять
  `--workers` в проде, `--reload` только для локального override.

## Архитектура — что нужно знать при добавлении функционала

7 блоков (подробности → `BLOCK_0X_*.md`, обзорная схема → `README.md`):

1. **Core Engine** — `api/routes/*`, `core/archivist.py`, `core/verifier.py` —
   диспетчер: handshake → concierge → query → result.
2. **Language Library** — `core/librarian.py`, `db/pg_client.py` — pgvector-
   поиск символов, ранжирование `similarity × log(R_f+2)`.
3. **Shard Storage** — `shards/*` — zstd-сжатые ячейки на внешних провайдерах
   (local/gdrive/github/r2), переключаются через `SHARD_PROVIDER`.
4. **CLI Layer** — `core/cli_layer.py` — сжатие контекста проекта в сигнал
   перед отправкой флагману.
5. **MCP Server** — `core/mcp_server.py` — транспорт исполнения.
6. **YMM Verifier** — `core/verifier.py` — сверка выданного vs применённого,
   обновление рейтингов символов.
7. **Immune System** — `core/immune_system.py`, `core/sleep_mode.py` —
   фоновые задачи (см. `SLEEP_MODE.md`), самовосстановление. Реаниматор
   полностью в коде (Gemini→Flash→Ollama fallback через `core/ai_router.py`),
   без внешних сервисов — см. `BLOCK_07_immune_system.md` и
   `n8n/MIGRATED_TO_CODE.md` (историческое решение отказаться от n8n).

**Протокол подписи `evo_signature`** — реализован в `core/signature.py`
(единая точка подписи/верификации), подключён во все 5 протокольных
эндпоинтов сессии (`/concierge`, `/query`, `/result`, `/step_done`,
`/hook_reply`, `/patch_callback`): каждый запрос флагмана верифицируется,
каждый ответ ядра подписывается `session_key`, выданным при `/handshake`. В
`EVO_ENV=development` верификация входящих подписей пропускается (согласовано
с остальным `security.py`), но пропуск логируется явно, не тихо.

**Незакрытые пункты на момент этого аудита** (проверить актуальность перед
тем, как на них полагаться):
- Миграция 009 не создана — на момент аудита в коде нет ничего, что ждало бы
  новой схемы; создавать её без конкретной причины не нужно.
- `./scripts/deploy.sh migrate` покрывает все миграции 001-008 (исправлено),
  но по-прежнему требует, чтобы контейнер `evo_postgres` уже был поднят.

Перед правкой конкретного блока — прочитать его `BLOCK_0X_*.md` и раздел
"БЛОК 4.5 — Уроки из найденных багов" в `.claude/CLAUDE.md` (6 уроков из
реальных инцидентов проекта, применимы к любому блоку).
