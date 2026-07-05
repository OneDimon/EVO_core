# AUDIT_FULL_CYCLE_TRACE.md
## Полный проход по циклу запросов — найденные и закрытые баги

> Симуляция: handshake → concierge → query → step_done → result → verify →
> archive → hook_reply, с учётом параллельных/повторных вызовов.

---

## Пройденный цикл (подтверждено по коду)

```
1. handshake     → сессия + HMAC ключ (evo_flagship_sessions, migration 005)
2. concierge     → уточняющие вопросы через ai_router (task: concierge_questions)
3. query         → librarian.search → embed → find_symbols(is_universal=TRUE)
                   → HNSW-поиск (migration 006) → tech_check_required сигнал
4. step_done     → выдача шага N+1, decompress по требованию (read_cell)
5. result        → verifier.verify() → YMS-MMM чеклист → маршрутизация
6. archive       → advisory lock на бакет вектора → similarity check
                   (include_conditional=True) → Тип А/Б/новый
7. hook_reply    → обязательная проверка актуальности, last_tech_check сброс
8. immune_system → 3 провала → reanimate() → patch_callback
```

## Найденные и закрытые баги (эта сессия)

- [x] **`concierge.py`** — `task="concierge"` не совпадал с ключом
  `routing_rules["concierge_questions"]` — тот же паттерн что immune_patch
  (Урок 1 из AGENTS.md). Роутер брал дефолтную модель вместо оптимальной
  для быстрых уточняющих вопросов.

- [x] **`core/verifier.py`** — гонка счётчика провалов: `_increment_fail`
  (INCR) и `_fail_result` (отдельный `_get_fail_count` GET) были двумя
  независимыми Redis-вызовами. При двух параллельных провалах ОДНОЙ сессии
  (сетевой ретрай флагмана) оба вызова могли увидеть уже увеличенное другим
  значение, пропустив промежуточный `fix`-шаг и сразу решив `reanimate`.
  Исправлено: `INCR` теперь возвращает новое значение атомарно, передаётся
  напрямую в `_fail_result`, отдельный GET убран из потока.

- [x] **`api/routes/step_done.py`** — `next_step_requested=0` (или
  отрицательное значение) давало `next_idx=-1` → Python возвращает
  `plan[-1]` (ПОСЛЕДНИЙ шаг картриджа) вместо явной ошибки. Добавлена
  валидация нижней границы `next_step_requested >= 1`.

---

## Проверено и подтверждено безопасным (гонки НЕ найдены)

- `db/pg_client.py::insert_symbol` — `ON CONFLICT (id) DO NOTHING`, повторная
  вставка при двух одновременных попытках создать один и тот же символ
  просто тихо не срабатывает второй раз — безопасно, не роняет процесс.
- `core/immune_system.py::reanimate` — `setex` в Redis атомарен на уровне
  ключа, повторный вызов для той же сессии просто перезаписывает патч
  свежим — не мусорит, не падает.
- `core/archivist.py::_process_archive` — advisory lock (сессия 2026-06-19,
  AUDIT_SCALE_HARDENING.md S5) уже устраняет гонку почти-дублей при
  конкурентной архивации.

---

*Создан: 2026-06-19 | Архитектор: @OneDimon*
*YMS-MMM ACTIVE*
