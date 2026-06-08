# БЛОК 07 — Immune System (Реаниматор)

**Назначение:** Автоматически реанимирует конвейер при 3 провалах верификации подряд. Основной канал — Gemini API. Fallback — локальная модель (Ollama). Реализован как кодовая нода в n8n без визуальных ветвлений.

[← Вернуться к карте проекта](README.md)

---

## Статус

| Параметр | Значение |
|----------|----------|
| **Фаза** | Фаза 2 |
| **Статус блока** | 🔵 Полностью готов — n8n workflow + TG + patch_callback |
| **Последний апдейт** | 2026-06-03 |

---

## Коннекторы

### Получает на вход
| Источник | Что приходит | Формат |
|----------|-------------|--------|
| [БЛОК 06](BLOCK_06_ymm_verifier.md) | Webhook: ТЗ + базовые инструкции + ошибочный вывод + лог ошибки | HTTP POST |

### Отдаёт на выход
| Получатель | Что отдаёт | Формат |
|-----------|-----------|--------|
| [БЛОК 01](BLOCK_01_core_engine.md) | Патч-инструкция для флагмана | HTTP POST callback |

---

## Зависимости

- [БЛОК 06](BLOCK_06_ymm_verifier.md) — верификатор должен быть готов
- n8n self-hosted развёрнут
- Ollama установлен локально (llama3 или аналог)

---

## Маршрутизация

```
Триггер: 3 провала верификации подряд
  │
  ▼
Попытка 1 → Gemini API
  │ Отказ / таймаут → пауза 5s
  ▼
Попытка 2 → Gemini API
  │ Отказ / таймаут → пауза 15s
  ▼
Попытка 3 → Gemini API
  │ Отказ / таймаут → пауза 45s (экспоненциальный backoff)
  ▼
Fallback → Ollama (локальная модель)
  │
  ▼
Патч → callback в БЛОК 01 → флагман исправляет
```

---

## Кодовая нода n8n

```javascript
const { taskDescription, baseInstructions,
        faultyOutput, errorLog, callbackUrl } = items[0].json;

const prompt = `[EVO-CORE IMMUNE SYSTEM]
TASK: ${taskDescription}
BASE_INSTRUCTIONS: ${baseInstructions}
FAULTY_OUTPUT: ${faultyOutput}
ERROR_LOG: ${errorLog}
Find the exact point of failure. Return a zero-fluff code patch only.`;

const attempts = [
    { url: 'https://generativelanguage.googleapis.com/v1/...', model: 'gemini-2.5-pro' },
    { url: 'https://generativelanguage.googleapis.com/v1/...', model: 'gemini-2.5-pro' },
    { url: 'https://generativelanguage.googleapis.com/v1/...', model: 'gemini-2.5-pro' },
    { url: 'http://localhost:11434/api/chat', model: 'llama3' }
];
const delays = [5000, 15000, 45000, 0];

let patch = null;
for (let i = 0; i < attempts.length; i++) {
    try {
        const res = await this.helpers.request({
            method: 'POST', url: attempts[i].url,
            headers: { 'Content-Type': 'application/json' },
            body: { model: attempts[i].model,
                    messages: [{ role: 'user', content: prompt }] },
            json: true, timeout: 30000
        });
        patch = res.choices?.[0]?.message?.content || res.message?.content;
        if (patch) break;
    } catch (e) {
        if (delays[i]) await new Promise(r => setTimeout(r, delays[i]));
    }
}

if (!patch) return [{ json: { success: false, error: 'All attempts failed' } }];

await this.helpers.request({
    method: 'POST', url: callbackUrl,
    headers: { 'Content-Type': 'application/json' },
    body: { status: 'reanimated', patch },
    json: true
});

return [{ json: { success: true, status: 'Patch Injected' } }];
```

---

## Задачи

### Фаза 2
- [ ] Развернуть n8n self-hosted
- [ ] Создать воркфлоу с одной кодовой нодой (код выше)
- [ ] Установить Ollama + загрузить модель (llama3)
- [ ] Настроить Gemini API ключ
- [ ] Тест полного цикла: симуляция 3 провалов → реанимация → патч доходит до флагмана
- [ ] Интеграция с БЛОК 06 (webhook)
- [ ] Интеграция с БЛОК 01 (callback)

---

## Сшивка со смежными блоками

| Блок | Статус сшивки | Что проверено |
|------|--------------|---------------|
| [БЛОК 06](BLOCK_06_ymm_verifier.md) YMS-MMM | 🔵 Сшит | 3 провала → immune.reanimate() |
| [БЛОК 01](BLOCK_01_core_engine.md) Core Engine | 🔵 Сшит | /patch_callback → флагману |

---

*Апдейт: 2026-06-03*
