# SLEEP_MODE.md — Протокол «Сон» ядра EVO-core

> **Назначение:** Автоматическое окно внутренней работы в часы минимальной нагрузки.
> Версия: 1.0 | 2026-06-03 | YMS-MMM ACTIVE

---

## Принцип

Ядро анализирует статистику обращений за последние 3–7 дней,
выявляет час наименьшей нагрузки и выделяет его для внутренних процессов.

Все внутренние задачи выполняются через AI-коннектор (`config/ai_router.json`).

---

## Алгоритм определения окна сна

```python
# Каждые сутки в 23:00 — планировщик пересчитывает окно
async def calculate_sleep_window(days: int = 7) -> tuple[int, int]:
    """
    Анализирует RPS по часам за последние N дней.
    Возвращает (час_начала, час_конца) с минимальной нагрузкой.
    """
    hourly_avg = await redis.get_hourly_rps_stats(days=days)
    min_hour = min(hourly_avg, key=hourly_avg.get)
    return (min_hour, min_hour + 1)
    # Результат сохраняется в Redis: "evo:sleep_window"
```

---

## Триггер входа в сон

```
Условия для входа в режим СОН (все должны выполняться):
  ✓ Текущий час = запланированное окно сна
  ✓ Текущий RPS < 10% от среднего за последние 7 дней
  ✓ Нет активных сессий пользователей
  ✓ Нет незавершённых задач в очереди записи (Redis Queue пуста)
```

---

## Задачи в режиме СОН

Выполняются через AI Router. Приоритет задач:

```
1. ФОНОВАЯ АССИМИЛЯЦИЯ (из SCL_FRACTAL_PROTOCOL раздел 18)
   - Поиск потенциальных лигатур (similarity > 0.85, confirmed_by >= 2)
   - Проверка гипотез (hypothesis: true, давность > 7 дней)
   - Апдейт весов графа знаний

2. ГРАФ ЗНАНИЙ
   - Пересчёт весов узлов по актуальным R_f
   - Поиск изолированных узлов
   - Генерация статистики (топ-10 символов, областей)

3. ПРОВЕРКА ЦЕЛОСТНОСТИ
   - Сверка: все символы в pgvector имеют ячейку на шарде
   - Сверка: все is_legacy символы имеют корректный superseded_by
   - Сверка: все confirmed_by >= 3 имеют соответствующую лигатуру

4. КРИТИЧЕСКИЕ ИЗМЕНЕНИЯ → УВЕДОМЛЕНИЕ (см. ниже)
```

---

## Прерывание сна

```python
# Мониторинг каждые 30 секунд во время сна
async def sleep_watchdog():
    while in_sleep_mode:
        current_rps = await get_current_rps()
        baseline_rps = await get_baseline_rps(days=7)

        if current_rps > baseline_rps * 0.90:  # нагрузка > 90% от базовой
            await interrupt_sleep()
            await notify_sleep_interrupted(current_rps)
            break

        await asyncio.sleep(30)

async def interrupt_sleep():
    """Немедленно останавливает фоновые задачи, переходит в активный режим."""
    await background_tasks.cancel_all()
    await set_mode("active")
    log.info("СОН прерван — ядро вышло на работу")
```

---

## Система уведомлений (критические изменения)

Запрет на редактирование критически важных участков без подтверждения Архитектора.

### Что требует подтверждения

```python
PROTECTED_AREAS = [
    "scl_symbols",           # таблица символов в pgvector
    "config/ai_router.json", # роутинг моделей
    "config/deployment.json",# деплой конфиг
    "prompts/",              # системные промпты
    "SCL_FRACTAL_PROTOCOL",  # протокол библиотеки
    "LOCAL_MODEL_INSTRUCTIONS", # инструкции локальной модели
    "migrations/",           # миграции БД
]
```

При обнаружении необходимости изменения в защищённой зоне:

### Формат уведомления

```
🔔 EVO-core: Требуется подтверждение

📌 Зона: config/ai_router.json
⚠️ Проблема: Gemini API вернул 404 на endpoint v1beta — endpoint изменился

Варианты решения:
1️⃣ Обновить endpoint на v1 (рекомендуется)
   Последствия: быстрое исправление, обратно совместимо
2️⃣ Переключить primary на gemini_flash
   Последствия: снижение качества верификации до восстановления
3️⃣ Переключить на Ollama local до выяснения
   Последствия: офлайн-режим, нет внешних данных

Ответь: 1, 2 или 3
```

Уведомление отправляется **одновременно**:
- В Telegram-бот (токен: `TG_BOT_TOKEN` из env)
- В админку сайта (`/admin/notifications`)

### Применение после ответа

```python
async def handle_architect_response(choice: int, context: dict):
    """
    Получает ответ Архитектора через ТГ или админку.
    Применяет выбранное решение. Отчитывается в оба канала.
    """
    solution = context['options'][choice - 1]
    await apply_solution(solution)
    await report_to_telegram(f"✅ Применено: {solution['description']}")
    await report_to_admin(f"✅ Применено: {solution['description']}")
```

### Конфиг уведомлений (заполнить при деплое)

```json
// config/notifications.json
{
  "telegram": {
    "bot_token_env": "TG_BOT_TOKEN",
    "admin_chat_id_env": "TG_ADMIN_CHAT_ID",
    "enabled": true
  },
  "admin_panel": {
    "endpoint": "/admin/api/notifications",
    "enabled": true
  },
  "protected_zones": [
    "scl_symbols", "config/", "prompts/",
    "SCL_FRACTAL_PROTOCOL.md", "LOCAL_MODEL_INSTRUCTIONS.md",
    "migrations/"
  ]
}
```

---

*Версия: 1.0 | 2026-06-03 | Архитектор: @OneDimon*
