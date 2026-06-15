# AUDIT_BEFORE_DEPLOY.md
# Доработка перед переходом к: Деплой на VPS (Фаза 3, пункт 1)

> **Текущий активный пункт плана:** `IMPLEMENTATION_PLAN.md` → ФАЗА 3 →
> `[ ] Деплой на VPS (домен, SSL, .env, bootstrap.py)`
>
> **Правило для любого ИИ:**
> Перед началом следующего пункта плана — проверь этот файл.
> Все пункты ниже должны быть отмечены `[x]` прежде чем переходить к деплою.
> При выполнении пункта — ставь `[x]` прямо здесь (не переписывая файл, только меняя `[ ]` на `[x]`).
> Если появляется новый план/подплан — сразу создавай аналогичный AUDIT-файл рядом.

---

## 🔴 КРИТИЧЕСКИЕ — ломают работу при деплое

### P1 — `db/pg_client.py::find_symbols` — SQL через f-string (уязвимость)
- [ ] **Файл:** `db/pg_client.py`
- [ ] **Проблема:** Вектор вставляется в SQL строку через `.replace(...)` минуя параметризацию asyncpg.
  Хрупко: безопасно только пока `vec_str` содержит цифры/запятые. Нарушает принцип защиты по умолчанию.
- [ ] **Правка:** Переписать `find_symbols` — передавать вектор как `$1::vector` параметр asyncpg.
- [ ] **Влияет на:** `core/librarian.py` (вызывает `find_symbols`), все поисковые запросы.
- [ ] **Проверить после правки:** `tests/test_phase0.py` — тест поиска по маячкам.

### P2 — `core/sleep_mode.py::_find_ligature_candidates` — инвертированная логика
- [ ] **Файл:** `core/sleep_mode.py`
- [ ] **Проблема:** Код помечает `hypothesis=TRUE` символы с `confirmed_by >= 2` —
  то есть *хорошие* подтверждённые символы. По SCL (раздел 6) `hypothesis=True` = непроверенное знание.
  Логика инвертирована: хорошие символы переводятся в статус "под вопросом".
- [ ] **Правка:** Убрать UPDATE `hypothesis=TRUE`. Только логировать кандидатов на лигатуру.
  Лигатура создаётся в `obsidian.py` при `confirmed_by >= 3` — не здесь.
- [ ] **Влияет на:** `SCL_FRACTAL_PROTOCOL.md` раздел 6, `core/obsidian.py`.

### P3 — `core/archivist.py::_process_archive` — дублирование `applied_stack`
- [ ] **Файл:** `core/archivist.py`
- [ ] **Проблема:** `_type_b(similar[0], output, applied_stack, applied_stack, vector, original_tz)` —
  `new_stack` и `applied_stack` передаются одинаково. `new_stack` = стек нового применения,
  `applied_stack` = стек исходного картриджа. Разница теряется, эволюция стека не фиксируется.
- [ ] **Правка:** Передавать `new_stack=applied_stack` (текущий), `applied_stack=parent["applicable_stacks"]`
  (из родительского символа). Проверить сигнатуру `_type_b`.
- [ ] **Влияет на:** `core/obsidian.py::_archive_delta` — та же ошибка (P7 ниже).

### P4 — `db/migrations` — нет таблицы `evo_sessions`
- [ ] **Файл:** `db/migrations/002_config.sql` (или новый `005_sessions.sql`)
- [ ] **Проблема:** `api/routes/handshake.py` пишет в `evo_sessions`, но таблица не создаётся
  ни в одной миграции. При деплое `handshake` упадёт с `relation "evo_sessions" does not exist`.
- [ ] **Правка:** Добавить `CREATE TABLE IF NOT EXISTS evo_sessions` в миграцию.
  Схема: `session_id TEXT PK, flagship TEXT, created_at TIMESTAMPTZ, hmac_key TEXT, meta JSONB`.
- [ ] **Влияет на:** `api/routes/handshake.py`, `api/middleware/security.py` (верификация сессий).
- [ ] **Проверить после правки:** `docker-compose up` → `curl /api/v1/handshake` без ошибки.

### P5 — `core/knowledge_collector.py` — `source_type` всегда `"ai_search"`
- [ ] **Файл:** `core/knowledge_collector.py`
- [ ] **Проблема:** `c["source_type"] = "ai_search"` — это метод поиска, не тип источника.
  По спецификации (`SLEEP_MODE.md`, `SCL_FRACTAL_PROTOCOL.md` раздел 19):
  `source_type` должен быть `github|npm|pypi|n8n|official|cli_plugin`.
  Фильтрация и аналитика по `source_type` в Admin UI/запросах сломаются.
- [ ] **Правка:** Определять `source_type` по содержимому `gap_type` или URL источника:
  `"github.com" → "github"`, `"npmjs.com" → "npm"`, `"pypi.org" → "pypi"` и т.д.
  Дефолт при неизвестном — `"ai_inferred"` (добавить в допустимые значения в `SCL_FRACTAL_PROTOCOL.md`).
- [ ] **Влияет на:** `db/models.py` (добавить `"ai_inferred"` в комментарий допустимых значений),
  `SCL_FRACTAL_PROTOCOL.md` раздел 19, Admin UI фильтры.

### P6 — `IMPLEMENTATION_PLAN.md` — дублированные `[ ]` из Фазы 0 (строки 92-100)
- [ ] **Файл:** `IMPLEMENTATION_PLAN.md`
- [ ] **Проблема:** Строки 92-100 содержат незакрытые `[ ]` пункты Фазы 0 которые уже выполнены
  (PostgreSQL развёрнут, SCL-символ реализован и т.д.). Это создаёт ложную картину о статусе проекта.
- [ ] **Правка:** Проставить `[x]` на строках 92-100 (дублированный блок Фазы 0 внутри текста).
- [ ] **Влияет на:** Любой ИИ читающий план видит незакрытые задачи и может начать их "выполнять" повторно.

---

## 🟡 ЛОГИЧЕСКИЕ НЕСТЫКОВКИ — работает, но неправильно

### P7 — `core/ai_router.py::embed` — не семантический эмбеддинг
- [ ] **Файл:** `core/ai_router.py`
- [ ] **Проблема:** `embed()` просит LLM вернуть "JSON array of 768 floats" через текстовый промпт.
  LLM не генерирует семантические векторы — возвращает псевдослучайный массив.
  Поиск по `pgvector` с такими векторами семантически бессмысленен.
- [ ] **Правка (варианты):**
  A) Gemini `embedContent` API (`models/embedding-001`, dim=768) — рекомендуется (primary уже Gemini)
  B) `sentence-transformers` локально в docker-контейнере (`all-MiniLM-L6-v2`, dim=384 — нужно изменить pgvector dim)
  C) OpenAI `text-embedding-3-small` (dim=1536 — нужно изменить dim)
  Вариант A наименее инвазивен — Gemini уже в стеке.
- [ ] **Влияет на:** `db/migrations/001_init.sql` (dim в vector), `core/librarian.py`, весь поиск.

### P8 — `core/obsidian.py::_archive_delta` — та же ошибка стека что P3
- [ ] **Файл:** `core/obsidian.py`
- [ ] **Проблема:** `_type_b(parent_dict, output, applied_stack, applied_stack, ...)` — см. P3.
- [ ] **Правка:** Исправить одновременно с P3.
- [ ] **Влияет на:** `core/archivist.py`.

### P9 — `api/routes/result.py` — `original_tz` не обязательное поле
- [ ] **Файл:** `api/routes/result.py`
- [ ] **Проблема:** `original_tz=req.original_tz or req.result[:200]` —
  если флагман не передал ТЗ, верификатор сравнивает результат с самим собой. Всегда пройдёт.
- [ ] **Правка:** Сделать `original_tz` обязательным полем Pydantic-схемы запроса.
  Или: логировать WARNING и отклонять с 422 если не передано.
- [ ] **Влияет на:** `FLAGSHIP_SYSTEM_PROMPT.md` (добавить требование передавать `original_tz`).

### P10 — `api/middleware/security.py` — rate limiter in-memory не работает при 4 воркерах
- [ ] **Файл:** `api/middleware/security.py`
- [ ] **Проблема:** `_rate_store = {}` — in-memory словарь. `docker-compose.yml` запускает
  `uvicorn --workers 4`. Каждый воркер имеет свой `_rate_store`. Rate limiting не работает.
- [ ] **Правка:** Перенести rate limiting в Redis: `r.incr(key)` + `r.expire(key, 60)`.
  Redis уже в стеке (`db/redis_client.py`).
- [ ] **Влияет на:** `config/deployment.json`, `docker-compose.yml` (зависимость api от redis уже есть).

### P11 — `site/index.html` — кнопка "Получить ключ" не подключена к API
- [ ] **Файл:** `site/index.html` + новый `api/routes/register.py`
- [ ] **Проблема:** `// TODO: POST /api/v1/register` — эндпоинт не существует.
  При деплое кнопка не работает: пользователь не получает ключ.
- [ ] **Правка:** Создать `api/routes/register.py` → `POST /api/v1/register` →
  принять email → создать запись в `users` → вернуть API-ключ.
  Подключить в `site/index.html` через `fetch('/api/v1/register', ...)`.
- [ ] **Влияет на:** `api/main.py` (подключить роут), `db/users.py`, `site/nginx.conf` (уже проксирует /api/).

### P12 — `config/ai_router.json` — нет routing rule для `knowledge_collection`
- [ ] **Файл:** `config/ai_router.json`
- [ ] **Проблема:** `knowledge_collector.py` вызывает `ai_router.generate(query, task="knowledge_collection")`,
  но в `routing_rules` этот task отсутствует. Роутер упадёт на дефолт или выбросит KeyError.
- [ ] **Правка:** Добавить `"knowledge_collection": "primary"` в `routing_rules`.
- [ ] **Влияет на:** `core/knowledge_collector.py`, `core/ai_router.py`.

---

## 🟢 ДОКУМЕНТАЛЬНЫЕ — не ломают, но создают путаницу

### P13 — `db/migrations/001_init.sql` — нет индекса на `evo_notifications(status)`
- [ ] **Файл:** `db/migrations/001_init.sql` или `005_sessions.sql`
- [ ] **Проблема:** `notify_architect` делает `SELECT WHERE status='pending'` без индекса.
  При росте уведомлений — seq scan.
- [ ] **Правка:** `CREATE INDEX IF NOT EXISTS evo_notif_status_idx ON evo_notifications(status)`.

### P14 — `shards/shard_client.py::_r2_write/_r2_read` — нет AWS Sig v4
- [ ] **Файл:** `shards/shard_client.py`
- [ ] **Проблема:** R2 требует AWS Signature v4. Без неё все запросы → 403.
  В коде нет даже предупреждения — тихая ошибка при деплое с R2.
- [ ] **Правка:** Добавить `raise NotImplementedError("R2 требует AWS Sig v4 — см. PROJECT_MAP.md")`.
  Или реализовать Sig v4 через `aws4auth` / вручную.

### P15 — `core/archivist.py::_generate_id` — `science[:2]` для не-ASCII корней
- [ ] **Файл:** `core/archivist.py`
- [ ] **Проблема:** `science[:2]` для корня "Технология" даст "Те" вместо нотационного символа.
  Нотация в `SCL_SYMBOLIC_NOTATION.md` предполагает греческие/латинские префиксы из 32 корней.
- [ ] **Правка:** Добавить маппинг 32 корней → 2-символьные коды в `core/archivist.py`
  и `SCL_SYMBOLIC_NOTATION.md`.

---

## ПРАВИЛА (для любого ИИ работающего с этим репо)

```
1. Перед началом любого пункта плана — прочитай этот файл.
2. Выполнил пункт → поставь [x] здесь (только замена [ ] на [x], не переписывать).
3. Появился новый план/подплан → создай AUDIT_BEFORE_*.md рядом с планом.
4. Перед правкой кода → сначала опиши Архитектору что меняешь и варианты.
5. После правки → проброс изменений до конца (все связанные файлы).
6. После проброса → финальный аудит связки (проверка реальных строк в файлах).
```

---

*Создан: 2026-06-13 | Архитектор: @OneDimon*
*Текущий пункт плана: ФАЗА 3 → Деплой на VPS*
*YMS-MMM ACTIVE*
