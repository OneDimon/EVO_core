# api/ — Core Engine (Блок 01)

**Перед правкой обязательно прочитать:** `../BLOCK_01_core_engine.md`,
`../api/middleware/security.py` целиком (HMAC/JWT/rate-limit — любой новый
роут проходит через это).

## Что здесь
- `main.py` — сборка приложения, регистрация роутов, `check_required_secrets()`
  вызывается при старте.
- `routes/handshake.py`, `concierge.py`, `query.py`, `step_done.py`,
  `result.py`, `hook_reply.py` — точки входа протокола (см. корневой
  `CLAUDE.md` → БЛОК 1 продукта в `.claude/CLAUDE.md` для формата запросов/ответов).
- `routes/admin.py` — admin UI API, требует `EVO_API_SECRET`.
- `routes/mcp.py` — транспорт для Блока 05.
- `routes/patch_callback.py` — вход для "реаниматора" (патчей от ядра).
- `middleware/security.py` — HMAC-верификация, JWT, rate limiting (Redis,
  fallback in-memory).

## Зависит от
`core/librarian.py`, `core/archivist.py`, `core/verifier.py`, `db/pg_client.py`,
`db/redis_client.py`.

## Границы
- `/admin` должен оставаться в `NO_AUTH_PATHS` для браузерного доступа без
  `X-API-Key` (см. git-историю — уже был баг с 403 вместо HTML).
- Не добавлять новый роут в обход `middleware/security.py`.
- Все ответы, содержащие `evo_signature` (HMAC) — подпись считать в одном
  месте, не дублировать логику подписи в разных роутах.
