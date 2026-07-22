# Immune System (Блок 07) — почему здесь больше нет n8n

## Что было

Изначально план (см. `IMPLEMENTATION_PLAN.md` §5.2) предполагал реаниматор
как отдельный n8n-воркфлоу: `evo_immune_system_workflow.json` — одна кодовая
нода на JS, повторяющая цепочку Gemini (3 попытки с backoff) → Ollama
fallback → HTTP callback в ядро.

## Что оказалось в реальности при аудите (2026-07-22)

Реальный код (`api/routes/result.py` → `core/immune_system.py::reanimate()`
→ `core/ai_router.py::AIRouter._call_with_fallback`) **никогда не вызывал
n8n**. Вся цепочка fallback (primary Gemini → gemini-flash → Ollama local,
retry с backoff 5/15/45с) уже реализована в `core/ai_router.py` и
используется реаниматором напрямую, в одном процессе с FastAPI-приложением.
n8n-воркфлоу был отдельным, никогда не подключённым к реальному пути
исполнения куском инфраструктуры — параллельная нереализованная копия уже
существующей логики.

## Решение

n8n-воркфлоу и инструкция по его деплою удалены (`README_n8n.md`,
`evo_immune_system_workflow.json`). Блок 07 — полностью в коде:

- `core/immune_system.py::reanimate()` — генерация патча
- `core/immune_system.py::patch_callback()` — выдача патча флагману
  (три явных статуса: `reanimated` / `failed` / `pending`, см. докстринг
  в файле — раньше отказ всех AI-провайдеров тихо терялся в fire-and-forget
  таске, теперь явно сохраняется в Redis и различим для флагмана)
- `core/ai_router.py` — сама fallback-цепочка (config: `config/ai_router.json`)
- `api/routes/result.py`, `api/routes/patch_callback.py` — HTTP-обвязка

Плюсы: меньше движущихся частей в проде (не нужен ни отдельный контейнер,
ни импорт воркфлоу руками через UI, ни второй набор креды для Gemini/Ollama),
вся логика тестируется и версионируется как обычный Python-код.

Если в будущем понадобится визуальный воркфлоу-слой (например для
непрограммистских правок логики реаниматора) — это осознанное решение
завести n8n заново, а не автоматическое "было и осталось". См. также
`BLOCK_07_immune_system.md`.
