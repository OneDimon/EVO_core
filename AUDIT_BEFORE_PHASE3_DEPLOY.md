# AUDIT_BEFORE_PHASE3_DEPLOY.md
## Доработка перед переходом к: **Деплой на VPS** (Фаза 3, пункт 1)
### Второй аудит — найдено после исправления P1-P16

> **Текущий пункт плана:** ФАЗА 3 → `[ ] Деплой на VPS`
> Все пункты ниже закрыть `[x]` перед деплоем.
> **Прогресс 2026-06-18:** ВСЕ N1-N15 закрыты ✅. Проект готов к деплою.
> **Правило:** выполнил → поставь [x] здесь. Не переписывать файл целиком.

---

## 🔴 КРИТИЧЕСКИЕ — ломают работу при деплое

### N1 — Конфликт `evo_sessions` в миграциях 003 и 005

- [ ] **Файлы:** `db/migrations/003_users_security.sql`, `db/migrations/005_sessions.sql`, `api/routes/handshake.py`
- [ ] **Проблема:**
  `003_users_security.sql` уже создаёт `evo_sessions(user_id UUID REFERENCES evo_users)` — пользовательские сессии.
  `005_sessions.sql` создаёт `evo_sessions(flagship_id TEXT, hmac_key TEXT)` — HMAC-сессии флагмана.
  Одно имя, разные схемы. При деплое — конфликт или потеря данных.
- [ ] **Правка:**
  Переименовать в `005_sessions.sql`: `evo_sessions` → `evo_flagship_sessions`.
  В `handshake.py`: `INSERT INTO evo_sessions` → `INSERT INTO evo_flagship_sessions`.
- [ ] **Влияет на:** `api/routes/handshake.py`, `api/middleware/security.py` (если читает сессии).

---

### N2 — `obsidian.py:_archive_delta` — `NameError: 'r'` при Тип Б

- [ ] **Файл:** `core/obsidian.py`
- [ ] **Проблема:**
  ```python
  if delta_type == "A":
      from core.ai_router import ai_router as r  # импорт только здесь
      vector = await r.embed(output[:400])
      ...
  else:
      from core.archivist import _type_b
      vector = await r.embed(output[:400])       # r не определён! → NameError
  ```
  При любом `delta_type == "B"` — `NameError`. Архивация Тип Б никогда не работает.
- [ ] **Правка:**
  ```python
  from core.ai_router import ai_router as r  # вынести ДО if/else
  vector = await r.embed(output[:400])       # вычислить один раз
  if delta_type == "A":
      from core.archivist import _type_a
      await _type_a(parent_dict, output, applied_stack, vector)
  else:
      from core.archivist import _type_b
      parent_stacks = parent_dict.get("applicable_stacks", [])
      await _type_b(parent_dict, output, applied_stack, parent_stacks, vector, original_tz)
  ```
- [ ] **Влияет на:** `core/archivist.py`, весь путь archiving Тип Б.

---

### N3 — `db/users.py:create_user` — `ON CONFLICT DO UPDATE` перезаписывает ключ

- [ ] **Файл:** `db/users.py`
- [ ] **Проблема:**
  ```python
  INSERT INTO evo_users (email, api_key, plan)
  VALUES ($1, $2, $3)
  ON CONFLICT (email) DO UPDATE SET plan=$3
  RETURNING id, email, api_key, plan, created_at
  ```
  При существующем email — `DO UPDATE SET plan=$3` обновляет план,
  но `RETURNING api_key` вернёт **новый** `$2`, не существующий в БД ключ.
  Пользователь получит ключ которого нет в базе → 403 при всех запросах.
- [ ] **Правка:**
  ```python
  ON CONFLICT (email) DO UPDATE SET plan=EXCLUDED.plan
  RETURNING id, email, api_key, plan, created_at
  -- api_key НЕ меняется — вернётся существующий
  ```
  Или: при конфликте — отдельный SELECT для получения существующего ключа.
- [ ] **Влияет на:** `api/routes/register.py` (использует `create_user`).

---

### N4 — Двойная запись плана в Redis (`query.py` + `librarian.py`)

- [ ] **Файлы:** `core/librarian.py`, `api/routes/query.py`
- [ ] **Проблема:**
  `librarian.py::search` вызывает `asyncio.create_task(cache_session_plan(...))`.
  `query.py::query` тоже вызывает `asyncio.create_task(cache_session_plan(...))`.
  Два `create_task` с одинаковым `session_id` → race condition + двойная запись.
  Второй `create_task` в `query.py` может перезаписать уже закешированный план.
- [ ] **Правка:**
  Убрать `asyncio.create_task(cache_session_plan(...))` из `librarian.py::search`.
  Оставить только в `query.py::query` где есть полный контроль над данными.
- [ ] **Влияет на:** `api/routes/step_done.py` (читает план из Redis).

---

### N5 — `archivist.py:ROOT_CODES` — коллизии кодов (одинаковые коды для разных корней)

- [ ] **Файл:** `core/archivist.py`
- [ ] **Проблема:**
  `"Философия": "Ph"` и `"Физика": "Ph"` → одинаковый префикс ID.
  `"Архитектура": "Ar"` и `"Искусство": "Ar"` → одинаковый префикс ID.
  Символы из разных макро-корней получат одинаковый prefix → нарушение уникальности нотации.
- [ ] **Правка:**
  ```python
  "Философия": "Fl",   # было "Ph"
  "Физика":    "Fx",   # было "Ph" (конфликт)
  "Искусство": "Is",   # было "Ar" (конфликт с Архитектурой)
  ```
- [ ] **Влияет на:** `_generate_id`, уникальность `scl_symbols.id`.

---

## 🟡 ЛОГИЧЕСКИЕ

### N6 — `hook_reply.py` — обновление по хуку не попадает в базу

- [ ] **Файл:** `api/routes/hook_reply.py`
- [ ] **Проблема:**
  При `has_update=True` возвращается `"update_recorded"` но `archivist` не вызывается.
  `update_description` теряется — обновление в базу знаний не попадает.
- [ ] **Правка:**
  ```python
  if req.has_update and req.update_description:
      from core.archivist import archive
      import asyncio
      asyncio.create_task(archive(
          session_id=req.session_id,
          output=req.update_description,
          solution_quality="gap_filled",
          deviations="",
          applied_stack=[],
          original_tz=f"hook update: {req.update_description[:100]}",
          context={}
      ))
  ```
- [ ] **Влияет на:** `core/archivist.py`, цикл дообучения ядра.

---

### N7 — `knowledge_collector.py` — вариант "отклонить" в уведомлении не работает

- [ ] **Файл:** `core/sleep_mode.py:apply_architect_choice`
- [ ] **Проблема:**
  Уведомление предлагает вариант 3 "Отклонить — символы удалены",
  но `apply_architect_choice` только пишет `status='applied'` в `evo_notifications`.
  Реального удаления символов нет.
- [ ] **Правка:** при `choice == 3`:
  ```python
  await conn.execute("""
      DELETE FROM scl_symbols
      WHERE auto_collected = TRUE AND hypothesis = TRUE
        AND last_updated > NOW() - INTERVAL '3 hours'
  """)
  ```
- [ ] **Влияет на:** `core/knowledge_collector.py`, `db/migrations/004_channel1_fields.sql`.

---

### N8 — `main.py:health` — возвращает `"phase": "2"` вместо `"4"`

- [ ] **Файл:** `api/main.py`
- [ ] **Правка:** `"phase": "2"` → `"phase": "4"`.
- [ ] **Влияет на:** мониторинг, `/health` эндпоинт.

---

### N9 — `pg_client.py:update_symbol_type_a` — optimistic lock молча не применяется

- [ ] **Файл:** `db/pg_client.py`
- [ ] **Проблема:**
  ```sql
  WHERE id = $1 AND version_ts = (SELECT version_ts ...)
  ```
  При concurrent update — WHERE не совпадёт, UPDATE молча применит 0 строк.
  Нет проверки `rowcount` — потеря обновления без ошибки.
- [ ] **Правка:**
  ```python
  result = await conn.execute("UPDATE scl_symbols SET ... WHERE id=$1 AND version_ts=...", ...)
  if result == "UPDATE 0":
      log.warning(f"[Archivist] Тип А: concurrent update detected для {symbol_id}")
  ```

---

### N10 — `sleep_mode.py` — watchdog не останавливает текущие задачи

- [ ] **Файл:** `core/sleep_mode.py`
- [ ] **Проблема:**
  `sleep_watchdog` устанавливает `_sleep_active = False` при нагрузке,
  но задачи в `_sleep_cycle` не проверяют флаг между шагами.
  Текущая задача доработает полностью даже если нагрузка критическая.
- [ ] **Правка:** в `_sleep_cycle` добавить проверку после каждой задачи (уже есть `if not _sleep_active: break` — но `break` только в цикле `for`, не прерывает текущую задачу).
  Добавить `_sleep_active` проверку внутри длинных задач (`_auto_fill_knowledge`).

---

### N11 — `ai_router.py:_call` — нет `raise_for_status()` для Gemini и OpenAI

- [ ] **Файл:** `core/ai_router.py`
- [ ] **Проблема:**
  При 429/500 от провайдера — парсинг JSON падает с `KeyError` вместо
  понятной ошибки, что ломает fallback-логику (`except Exception` ловит но логирует неправильно).
- [ ] **Правка:** добавить `resp.raise_for_status()` после каждого `await client.post(...)`.

---

### N12 — `knowledge_collector.py:_scan_knowledge_gaps` — поиск по `id LIKE root%` некорректен

- [ ] **Файл:** `core/knowledge_collector.py`
- [ ] **Проблема:**
  ```python
  roots_32 = ["Φ","Λ","M","γ","ζ"...]
  count = await conn.fetchval(
      "SELECT COUNT(*) FROM scl_symbols WHERE id LIKE $1 AND is_legacy=FALSE",
      f"{root}%"
  )
  ```
  Символы хранятся с ID типа `Tc^{new}_{new_0001}` (ROOT_CODES, латинские коды).
  Поиск по греческому символу `τ%` всегда вернёт 0 → все 32 корня = "белые зоны" каждый цикл.
- [ ] **Правка:** искать по полю `science`:
  ```python
  from core.archivist import ROOT_CODES
  ROOT_TO_SCIENCE = {v: k for k, v in ROOT_CODES.items()}
  science_name = ROOT_TO_SCIENCE.get(root, root)
  count = await conn.fetchval(
      "SELECT COUNT(*) FROM scl_symbols WHERE science=$1 AND is_legacy=FALSE",
      science_name
  )
  ```
  Или хранить `science` как русское название и искать напрямую по нему.
- [ ] **Влияет на:** весь цикл автонаполнения Канала 1.

---

## 🟢 ДОКУМЕНТАЛЬНЫЕ

### N13 — `main.py` — docstring файла `"v0.3 — Фаза 2"` устарел
- [ ] **Файл:** `api/main.py`
- [ ] **Правка:** обновить до `"v0.4.0 — Фаза 3/4"`.

### N14 — MCP роут `/api/v1/mcp` vs `/mcp` в манифесте и nginx
- [ ] **Файлы:** `site/mcp-manifest.json`, `site/nginx.conf`
- [ ] **Проблема:** роут в FastAPI регистрируется как `/api/v1/mcp` (prefix + `/mcp`),
  а в манифесте и nginx указан `/mcp`.
- [ ] **Правка (вариант А — рекомендуется):** изменить prefix для mcp роутера на `""` в `main.py`.
  **Вариант Б:** обновить манифест и nginx на `/api/v1/mcp`.

### N15 — `ai_router.json` routing rule `"immune_system_patch"` vs код `"immune_patch"`
- [ ] **Файлы:** `config/ai_router.json`, `core/immune_system.py`
- [ ] **Проблема:** `immune_system.py` вызывает `task="immune_patch"`,
  в `routing_rules` ключ `"immune_system_patch"`. Имена не совпадают.
- [ ] **Правка:** унифицировать в `"immune_patch"` везде.

---

## СВОДНАЯ ТАБЛИЦА

| # | Приоритет | Файл(ы) | Статус |
|---|-----------|---------|--------|
| N1 | 🔴 | `005_sessions.sql`, `handshake.py` | [x] ✓ 2026-06-18 |
| N2 | 🔴 | `core/obsidian.py` | [x] ✓ 2026-06-18 |
| N3 | 🔴 | `db/users.py` | [x] ✓ 2026-06-18 |
| N4 | 🔴 | `core/librarian.py`, `api/routes/query.py` | [x] ✓ 2026-06-18 |
| N5 | 🔴 | `core/archivist.py` | [x] ✓ 2026-06-18 Fx/Fl/Is |
| N6 | 🟡 | `api/routes/hook_reply.py` | [x] ✓ 2026-06-18 |
| N7 | 🟡 | `core/sleep_mode.py` | [x] ✓ 2026-06-18 |
| N8 | 🟡 | `api/main.py` | [x] ✓ 2026-06-18 |
| N9 | 🟡 | `db/pg_client.py` | [x] ✓ 2026-06-18 |
| N10 | 🟡 | `core/sleep_mode.py` | [x] ✓ 2026-06-18 Task cancel |
| N11 | 🟡 | `core/ai_router.py` | [x] ✓ 2026-06-18 x3 провайдера |
| N12 | 🟡 | `core/knowledge_collector.py` | [x] ✓ 2026-06-18 КРИТИЧНО |
| N13 | 🟢 | `api/main.py` | [x] ✓ 2026-06-18 (вместе с N8) |
| N14 | 🟢 | `site/mcp-manifest.json`, `site/nginx.conf` | [x] ✓ 2026-06-18 |
| N15 | 🟢 | `config/ai_router.json`, `core/immune_system.py` | [x] ✓ 2026-06-18 |

---

*Создан: 2026-06-17 | Архитектор: @OneDimon*
*Текущий пункт плана: ФАЗА 3 → Деплой на VPS*
*YMS-MMM ACTIVE*
