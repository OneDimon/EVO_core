# n8n — Деплой БЛОК 07 (Immune System)

## Быстрый старт

### 1. Запустить n8n
```bash
docker run -d --name evo_n8n \
  -p 5678:5678 \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=your_n8n_password \
  -e GEMINI_API_KEY=your_gemini_key \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  -e EVO_API_SECRET=your_evo_api_secret \
  -v n8n_data:/home/node/.n8n \
  n8nio/n8n
```

### 2. Импортировать воркфлоу
1. Открыть http://localhost:5678
2. Workflows → Import from File
3. Выбрать: `n8n/evo_immune_system_workflow.json`
4. Активировать воркфлоу (toggle ON)

### 3. Получить webhook URL
После активации n8n покажет URL вида:
```
http://localhost:5678/webhook/evo-reanimate
```

### 4. Прописать webhook URL в .env
```bash
N8N_WEBHOOK_URL=http://localhost:5678/webhook/evo-reanimate
```
Или через Admin API:
```bash
curl -X POST http://localhost:8000/api/v1/admin/config \
  -H "X-Admin-Token: YOUR_ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"key":"N8N_WEBHOOK_URL","value":"http://localhost:5678/webhook/evo-reanimate"}'
```

### 5. Проверить работу
```bash
curl -X POST http://localhost:5678/webhook/evo-reanimate \
  -H "Content-Type: application/json" \
  -d '{
    "taskDescription": "Тест реаниматора",
    "baseInstructions": "Авторизация ZennoPoster",
    "faultyOutput": "Ошибка: session expired",
    "errorLog": "YMS-MMM: 3 провала",
    "callbackUrl": "http://localhost:8000/api/v1/patch_callback",
    "sessionId": "test-session-001"
  }'
```

## Переменные окружения n8n

| Переменная | Описание |
|-----------|---------|
| `GEMINI_API_KEY` | Ключ Gemini (primary AI) |
| `OLLAMA_HOST` | Адрес Ollama (fallback) |
| `EVO_API_SECRET` | Секрет для callback в ядро |

## Логика воркфлоу

```
Webhook POST /evo-reanimate
        │
        ▼
Code Node (один, без ветвлений):
  1. Gemini 2.5 Pro attempt 1
  2. Gemini 2.5 Pro attempt 2 (пауза 5s)
  3. Gemini 2.0 Flash fallback (пауза 15s)
  4. Ollama local (пауза 45s)
  → Патч → POST callbackUrl
        │
        ▼
Response Node → 200 OK
```

## Обновление воркфлоя

При изменении логики реаниматора:
1. Отредактировать `n8n/evo_immune_system_workflow.json`
2. Импортировать заново в n8n (обновит существующий)
3. Пересохранить и активировать
