# AUDIT_BEFORE_DEPLOY.md
## Доработка перед переходом к: **Деплой на VPS** (ФАЗА 3, пункт 1)

> **Текущий активный пункт плана:**
> `IMPLEMENTATION_PLAN.md` → ФАЗА 3 → `[ ] Деплой на VPS (домен, SSL, .env, bootstrap.py)`
>
> **Читай этот файл первым перед любой правкой или деплоем.**
> Все пункты ниже должны быть закрыты `[x]` прежде чем переходить к деплою.

---

## ⚙️ ПРАВИЛА (обязательны для любого ИИ в этом репо)

```
ПРАВИЛО 1 — АУДИТ-ФАЙЛ:
  Перед началом любого пункта плана → прочитай этот файл полностью.
  Все [ ] должны стать [x] прежде чем переходить к следующему пункту плана.

ПРАВИЛО 2 — ГАЛОЧКИ:
  Выполнил пункт → поставь [x] прямо здесь.
  Только замена [ ] на [x] — файл не переписывать целиком.
  Формат: [ ] → [x] + добавить строку "  ✓ Выполнено: {дата} {краткое описание}"

ПРАВИЛО 3 — НОВЫЙ ПЛАН:
  Появился новый план/подплан → сразу создать AUDIT_BEFORE_{НАЗВАНИЕ}.md рядом.
  Структура такая же как этот файл.

ПРАВИЛО 4 — ПЕРЕД ПРАВКОЙ КОДА:
  Сначала описать Архитектору: что меняешь, в каких файлах, варианты решения.
  Приступать только после подтверждения.

ПРАВИЛО 5 — ПРОБРОС ДО КОНЦА:
  После любой правки кода → пробросить изменения во все связанные файлы
  (модели, миграции, документация, IMPLEMENTATION_PLAN, README, AI_ONBOARDING).

ПРАВИЛО 6 — ФИНАЛЬНЫЙ АУДИТ:
  После проброса → проверить реальное содержимое всех затронутых файлов.
  Не считать задачу закрытой пока аудит не показал ✅.
```

---

## 🔴 КРИТИЧЕСКИЕ — ломают работу при деплое

### P1 — `db/pg_client.py::find_symbols` — SQL через f-string (уязвимость инъекции)

- [x] **Файл:** `db/pg_client.py`
- [x] **Проблема:**
  ```python
  # Текущий код (уязвимо):
  sql = sql_template.replace("${vec_str}", f"'{vec_str}'")
  await conn.fetch(sql)
  ```
  Вектор вставляется в SQL строку напрямую, минуя параметризацию asyncpg.
  Безопасно только пока `vec_str` содержит цифры и запятые — но это хрупко.
  Нарушает принцип защиты по умолчанию. При любом изменении валидации — открытая инъекция.
- [x] **Правка:**
  ```python
  # Правильно — вектор как параметр:
  await conn.fetch(
      "SELECT ... FROM scl_symbols ORDER BY vector <=> $1::vector LIMIT $2",
      f"[{vec_str}]", top_k
  )
  ```
- [x] **Влияет на:** `core/librarian.py` (вызывает `find_symbols`), весь поиск символов.
- [x] **Проверить после правки:** `tests/test_phase0.py` — тест поиска по маячкам.

---

### P2 — `core/sleep_mode.py::_find_ligature_candidates` — инвертированная логика hypothesis

- [x] **Файл:** `core/sleep_mode.py`
- [x] **Проблема:**
  ```python
  # Текущий код (неверно):
  await conn.execute(
      "UPDATE scl_symbols SET hypothesis=TRUE WHERE confirmed_by >= 2"
  )
  ```
  Код помечает `hypothesis=TRUE` символы с `confirmed_by >= 2` — то есть *хорошие*,
  дважды подтверждённые символы. По `SCL_FRACTAL_PROTOCOL.md` раздел 6:
  `hypothesis=True` = знание непроверенное, под вопросом.
  Логика инвертирована: лучшие символы переводятся в статус "сомнительных".
  Лигатура создаётся в `obsidian.py` при `confirmed_by >= 3` — не здесь.
- [x] **Правка:**
  ```python
  # Правильно — только логировать кандидатов, не трогать hypothesis:
  candidates = await conn.fetch(
      "SELECT id, label, confirmed_by FROM scl_symbols "
      "WHERE confirmed_by >= 2 AND hypothesis = FALSE "
      "ORDER BY confirmed_by DESC LIMIT 20"
  )
  log.info(f"[Sleep] Кандидаты на лигатуру: {len(candidates)} символов")
  # obsidian.py создаст лигатуру когда confirmed_by достигнет 3
  ```
- [x] **Влияет на:** `SCL_FRACTAL_PROTOCOL.md` раздел 6, `core/obsidian.py`, целостность базы знаний.

---

### P3 — `core/archivist.py::_process_archive` — дублирование `applied_stack`

- [x] **Файл:** `core/archivist.py`
- [x] **Проблема:**
  ```python
  # Текущий код (неверно — оба аргумента одинаковы):
  await _type_b(similar[0], output, applied_stack, applied_stack, vector, original_tz)
  #                                  ^ new_stack    ^ applied_stack  — одно и то же!
  ```
  Сигнатура: `_type_b(parent, new_output, new_stack, applied_stack, vector, original_tz)`
  — `new_stack` = стек *нового* применения (текущий запрос)
  — `applied_stack` = стек *родительского* символа (из `parent["applicable_stacks"]`)
  Разница теряется. Эволюция стека в символе не фиксируется корректно.
- [x] **Правка:**
  ```python
  # Правильно:
  parent_stacks = similar[0].get("applicable_stacks", [])
  await _type_b(similar[0], output, applied_stack, parent_stacks, vector, original_tz)
  ```
- [x] **Влияет на:** `core/obsidian.py::_archive_delta` — та же ошибка (см. P8).
  После правки проверить оба файла одновременно.

---

### P4 — `api/routes/handshake.py` + `api/middleware/security.py` — HMAC bytes/str несоответствие

- [x] **Файл:** `api/routes/handshake.py`, `api/middleware/security.py`
- [ ] **Проблема:**
  ```python
  # handshake.py — генерирует ключ как строку:
  session_key = hmac.new(secret.encode(), session_id.encode(), hashlib.sha256).hexdigest()
  # session_key — это str (hex)

  # security.py — verify_incoming_hmac использует session_key:
  expected = hmac.new(session_key, msg.encode(), hashlib.sha256).hexdigest()
  # hmac.new ожидает key как bytes, но session_key — str → TypeError при верификации
  ```
  При каждом запросе после handshake верификация HMAC падает с `TypeError`.
- [x] **Правка:**
  ```python
  # security.py — явно кодировать ключ:
  expected = hmac.new(session_key.encode(), msg.encode(), hashlib.sha256).hexdigest()
  ```
  Проверить консистентность во всех местах где используется `session_key`.
- [x] **Влияет на:** Всю цепочку аутентификации после handshake: `query`, `result`, `step_done`.

---

### P5 — `db/migrations` — нет таблицы `evo_sessions`

- [x] **Файл:** Новая миграция `db/migrations/005_sessions.sql`
- [ ] **Проблема:**
  `api/routes/handshake.py` пишет в таблицу `evo_sessions`:
  ```python
  await conn.execute(
      "INSERT INTO evo_sessions (session_id, flagship, hmac_key, created_at) VALUES ..."
  )
  ```
  Таблица `evo_sessions` отсутствует во всех 4 миграциях (`001`–`004`).
  При деплое первый же запрос к `handshake` упадёт:
  `asyncpg.exceptions.UndefinedTableError: relation "evo_sessions" does not exist`
- [ ] **Правка:** Создать `db/migrations/005_sessions.sql`:
  ```sql
  CREATE TABLE IF NOT EXISTS evo_sessions (
      session_id   TEXT PRIMARY KEY,
      flagship     TEXT NOT NULL,
      hmac_key     TEXT NOT NULL,
      created_at   TIMESTAMPTZ DEFAULT NOW(),
      last_active  TIMESTAMPTZ DEFAULT NOW(),
      meta         JSONB DEFAULT '{}'
  );
  CREATE INDEX IF NOT EXISTS evo_sessions_created_idx
      ON evo_sessions (created_at);
  -- TTL-очистка: сессии старше 24ч (запускать через pg_cron или sleep_mode)
  ```
- [x] **Влияет на:** `docker-compose.yml` (добавить `005_sessions.sql` в init),
  `AI_ONBOARDING.md` (порядок запуска), `IMPLEMENTATION_PLAN.md`.

---

### P6 — `core/knowledge_collector.py` — `source_type` всегда `"ai_search"`, не тип источника

- [x] **Файл:** `core/knowledge_collector.py`
- [x] **Проблема:**
  ```python
  # Текущий код (неверно):
  c["source_type"] = "ai_search"  # это метод поиска, не тип источника
  ```
  По спецификации (`SLEEP_MODE.md`, `SCL_FRACTAL_PROTOCOL.md` раздел 19):
  `source_type` = `github|npm|pypi|n8n|official|cli_plugin`
  `"ai_search"` — не тип источника. Admin UI фильтры по `source_type` вернут пустые результаты.
- [ ] **Правка:**
  ```python
  def _detect_source_type(url: str) -> str:
      if not url:
          return "ai_inferred"
      if "github.com" in url:
          return "github"
      if "npmjs.com" in url or "npm.io" in url:
          return "npm"
      if "pypi.org" in url:
          return "pypi"
      if "n8n.io" in url:
          return "n8n"
      if any(x in url for x in ["anthropic.com","openai.com","google.com"]):
          return "official"
      return "ai_inferred"

  c["source_type"] = _detect_source_type(c.get("source_url", ""))
  ```
- [x] **Влияет на:** `db/models.py` (добавить `"ai_inferred"` в комментарий допустимых значений),
  `SCL_FRACTAL_PROTOCOL.md` раздел 19 (добавить `ai_inferred` в список допустимых типов),
  `SLEEP_MODE.md` раздел "Метаданные источника".

---

## 🟡 ЛОГИЧЕСКИЕ НЕСТЫКОВКИ — работает, но неправильно

### P7 — `core/ai_router.py::embed` — не семантический эмбеддинг

- [x] **Файл:** `core/ai_router.py`
- [x] **Проблема:**
  ```python
  # Текущий код — просит LLM вернуть массив через текст:
  result = await self._call_with_fallback(
      f"Return ONLY a JSON array of 768 floats representing semantic embedding of: {text}",
      task="vectorization"
  )
  ```
  LLM не генерирует семантические векторы через текстовый промпт.
  Возвращает псевдослучайный или детерминированный массив — не смысловой вектор.
  Поиск по `pgvector` (`<=>` cosine distance) с такими векторами семантически бессмысленен.
- [ ] **Варианты правки (на выбор Архитектора):**
  ```
  A) Gemini embedContent API — РЕКОМЕНДУЕТСЯ (Gemini уже primary в ai_router.json):
     POST https://generativelanguage.googleapis.com/v1beta/models/embedding-001:embedContent
     dim=768 — совпадает с текущей схемой БД. Минимально инвазивно.

  B) sentence-transformers локально в docker:
     model: all-MiniLM-L6-v2, dim=384
     Требует: изменить dim в 001_init.sql + пересоздать pgvector индекс

  C) OpenAI text-embedding-3-small:
     dim=1536 — требует изменить dim в БД
  ```
  Вариант A — наименее инвазивен, Gemini уже в стеке.
- [x] **Влияет на:** `db/migrations/001_init.sql` (dim), `core/librarian.py`, весь поиск.

---

### P8 — `core/obsidian.py::_archive_delta` — та же ошибка стека что P3

- [x] **Файл:** `core/obsidian.py`
- [x] **Проблема:**
  ```python
  # Та же ошибка что в archivist.py (P3):
  await _type_b(parent_dict, output, applied_stack, applied_stack, vector, original_tz)
  ```
- [ ] **Правка:** Исправить одновременно с P3:
  ```python
  parent_stacks = parent_dict.get("applicable_stacks", [])
  await _type_b(parent_dict, output, applied_stack, parent_stacks, vector, original_tz)
  ```
- [x] **Влияет на:** `core/archivist.py` — исправлять P3 и P8 в одном коммите.

---

### P9 — `api/routes/result.py` — `original_tz` не обязательное поле

- [x] **Файл:** `api/routes/result.py`, `api/models/` (Pydantic схема запроса)
- [x] **Проблема:**
  ```python
  # Текущий код — тихий fallback:
  original_tz = req.original_tz or req.result[:200]
  ```
  Если флагман не передал `original_tz` — YMS-MMM верифицирует вывод против самого себя.
  Верификация всегда пройдёт. Любой мусор запишется в базу как "ideal".
- [ ] **Правка (вариант А — рекомендуется):**
  ```python
  # Сделать обязательным в Pydantic схеме:
  class ResultRequest(BaseModel):
      original_tz: str  # убрать Optional, убрать default
      result: str
      ...
  ```
  **Вариант Б** — логировать WARNING и возвращать 422 если `original_tz` пустой.
- [x] **Влияет на:** `FLAGSHIP_SYSTEM_PROMPT.md` — добавить требование всегда передавать `original_tz`.
  `AGENTS.md` / `.claude/CLAUDE.md` — синхронизировать.

---

### P10 — `api/middleware/security.py` — rate limiter in-memory не работает при 4 воркерах

- [x] **Файл:** `api/middleware/security.py`
- [x] **Проблема:**
  ```python
  # Текущий код:
  _rate_store: dict = {}  # in-memory — не работает при --workers 4
  ```
  `docker-compose.yml` запускает `uvicorn --workers 4`.
  Каждый воркер имеет свой `_rate_store` — rate limiting не работает совсем.
- [ ] **Правка:**
  ```python
  # Через Redis (уже в стеке):
  async def check_rate_limit(api_key: str) -> bool:
      r = await get_redis()
      key = f"evo:rate:{api_key}"
      count = await r.incr(key)
      if count == 1:
          await r.expire(key, 60)  # окно 60 секунд
      return count <= 60           # 60 req/min
  ```
- [x] **Влияет на:** `db/redis_client.py` (функция `get_redis` уже есть), `docker-compose.yml`.

---

### P11 — `site/index.html` + отсутствует `api/routes/register.py`

- [x] **Файл:** `site/index.html`, новый `api/routes/register.py`, `api/main.py`
- [ ] **Проблема:**
  ```javascript
  // Текущий код в site/index.html:
  // TODO: POST /api/v1/register email → выдать ключ
  ```
  Эндпоинт `/api/v1/register` не существует. При деплое кнопка "Получить ключ" не работает.
  Пользователь вводит email → ничего не происходит.
- [ ] **Правка:** Создать `api/routes/register.py`:
  ```python
  @router.post("/api/v1/register")
  async def register(email: str):
      # 1. Валидация email
      # 2. Создать запись в db/users.py → вернуть api_key
      # 3. Опционально: отправить на email (через TG или SMTP)
      user = await create_user(email=email, plan="free")
      return {"api_key": user.api_key, "plan": "free", "expires": None}
  ```
  Подключить в `site/index.html`:
  ```javascript
  const res = await fetch('/api/v1/register', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email})
  });
  ```
- [x] **Влияет на:** `api/main.py` (подключить роут), `db/users.py`, `site/nginx.conf` (уже проксирует `/api/`).

---

### P12 — `config/ai_router.json` — нет task `knowledge_collection` в routing_rules

- [x] **Файл:** `config/ai_router.json`
- [x] **Проблема:**
  `core/knowledge_collector.py` вызывает:
  ```python
  result = await ai_router.generate(query, task="knowledge_collection")
  ```
  В `routing_rules` этот task отсутствует.
  Роутер упадёт на дефолт primary или выбросит `KeyError` в зависимости от реализации.
- [ ] **Правка:** Добавить в `routing_rules`:
  ```json
  "knowledge_collection": "primary"
  ```
- [x] **Влияет на:** `core/knowledge_collector.py`, `core/ai_router.py::_get_model_for_task`.

---

## 🟢 ДОКУМЕНТАЛЬНЫЕ — не ломают, но создают путаницу

### P13 — `db/migrations/001_init.sql` — нет индекса на `evo_notifications(status)`

- [x] **Файл:** `db/migrations/001_init.sql` или `005_sessions.sql`
- [x] **Проблема:** `notify_architect` делает `SELECT WHERE status='pending'` без индекса.
  При росте уведомлений — полный seq scan.
- [ ] **Правка:**
  ```sql
  CREATE INDEX IF NOT EXISTS evo_notif_status_idx
      ON evo_notifications (status)
      WHERE status = 'pending';
  ```

---

### P14 — `shards/shard_client.py::_r2_write/_r2_read` — нет AWS Sig v4, тихая ошибка

- [x] **Файл:** `shards/shard_client.py`
- [x] **Проблема:**
  ```python
  # Текущий код — запрос без аутентификации:
  await c.put(f"https://{account}.r2.cloudflarestorage.com/{bucket}{path}", content=data)
  ```
  R2 требует AWS Signature v4. Без неё все запросы → 403 Forbidden.
  В `PROJECT_MAP.md` это отмечено как "нужна реализация", но в коде нет даже предупреждения.
  При деплое с R2 — тихая ошибка, шарды не записываются.
- [ ] **Правка (минимальная — заглушка с предупреждением):**
  ```python
  async def _r2_write(self, path: str, data: bytes) -> bool:
      raise NotImplementedError(
          "R2 требует AWS Signature v4. "
          "Реализовать через httpx + aws4auth или вручную. "
          "См. PROJECT_MAP.md раздел 'Что осталось'."
      )
  ```
  Полная реализация Sig v4 — отдельная задача.

---

### P15 — `README.md` — ссылка на IMPL PLAN указывает `v3.0`, файл уже `v3.1`

- [x] **Файл:** `README.md`
- [x] **Проблема:** Навигационная таблица содержит `v3.0` вместо актуального `v3.1`.
- [ ] **Правка:** Заменить `v3.0` → `v3.1` в строке навигации IMPLEMENTATION_PLAN.

---

### P16 — `core/archivist.py::_generate_id` — `science[:2]` для не-ASCII корней

- [x] **Файл:** `core/archivist.py`, `SCL_SYMBOLIC_NOTATION.md`
- [ ] **Проблема:**
  ```python
  sym = science[:2]  # "Технология" → "Те" вместо нотационного символа
  ```
  Нотация в `SCL_SYMBOLIC_NOTATION.md`: `τ^{auto^2}_{zp_0047}` — предполагает
  2-символьные латинские/греческие коды из 32 корней.
  При русских названиях макро-корней ID будет нечитаем и несовместим с нотацией.
- [ ] **Правка:** Добавить маппинг 32 корней → 2-символьные коды:
  ```python
  ROOT_CODES = {
      "Технология": "Tc", "Математика": "Mt", "Физика": "Ph",
      "Химия": "Ch", "Биология": "Bi", "Информатика": "Cs",
      # ... все 32 корня
  }
  sym = ROOT_CODES.get(science, science[:2].upper())
  ```
  Синхронизировать с `SCL_SYMBOLIC_NOTATION.md`.

---

## СВОДНАЯ ТАБЛИЦА

| # | Приоритет | Файл(ы) | Статус |
|---|-----------|---------|--------|
| P1 | 🔴 | `db/pg_client.py` | [x] ✓ 2026-06-13 |
| P2 | 🔴 | `core/sleep_mode.py` | [x] ✓ 2026-06-13 |
| P3 | 🔴 | `core/archivist.py` | [x] ✓ 2026-06-13 |
| P4 | 🔴 | `api/routes/handshake.py`, `api/middleware/security.py` | [x] ✓ Код был корректен |
| P5 | 🔴 | `db/migrations/005_sessions.sql`, `docker-compose.yml` | [x] ✓ 2026-06-13 |
| P6 | 🔴 | `core/knowledge_collector.py` | [x] ✓ 2026-06-13 |
| P7 | 🟡 | `core/ai_router.py` | [x] ✓ 2026-06-13 Gemini embedContent |
| P8 | 🟡 | `core/obsidian.py` | [x] ✓ 2026-06-13 |
| P9 | 🟡 | `api/routes/result.py` | [x] ✓ 2026-06-13 |
| P10 | 🟡 | `api/middleware/security.py` | [x] ✓ 2026-06-13 Redis rate limit |
| P11 | 🟡 | `site/index.html`, `api/routes/register.py`, `api/main.py` | [x] ✓ 2026-06-13 |
| P12 | 🟡 | `config/ai_router.json` | [x] ✓ 2026-06-13 |
| P13 | 🟢 | `db/migrations/001_init.sql` | [x] ✓ 2026-06-13 |
| P14 | 🟢 | `shards/shard_client.py` | [x] ✓ 2026-06-13 NotImplementedError |
| P15 | 🟢 | `README.md` | [x] ✓ Уже была v3.1 |
| P16 | 🟢 | `core/archivist.py`, `SCL_SYMBOLIC_NOTATION.md` | [x] ✓ 2026-06-13 ROOT_CODES |

---

*Создан: 2026-06-13 | Архитектор: @OneDimon*
*Текущий пункт плана: ФАЗА 3 → Деплой на VPS*
*YMS-MMM ACTIVE*
