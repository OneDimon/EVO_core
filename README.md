# EVO-core

**Когнитивный слой между ИИ-флагманами и средами исполнения.**

Хранит верифицированные инженерные решения как аксиомы.
Выдаёт их точечно по смыслу запроса под конкретный стек.
Исключает галлюцинации, деградацию внимания, устаревшие решения.

---

## Быстрый старт

```bash
git clone https://github.com/OneDimon/EVO_core && cd EVO_core
cp .env.example .env
./scripts/deploy.sh gen-secrets >> .env
# Заполнить GEMINI_API_KEY в .env
./scripts/deploy.sh check
./scripts/deploy.sh full
open http://localhost:8000/admin
```

---

## Статус блоков

| Блок | Статус | Описание |
|------|--------|---------|
| 01 Core Engine | 🔵 Готов | 9 API эндпоинтов + Admin UI |
| 02 Language Library | 🔵 Готов | pgvector + SCL символы + Redis |
| 03 Shard Storage | 🔵 Готов | zstd + 4 провайдера + autopatch |
| 04 CLI Layer | 🔵 Готов | Скелетонизатор контекста |
| 05 MCP Server | 🔵 Готов | JSON-RPC 2.0 |
| 06 YMS-MMM | 🔵 Готов | Верификатор + Obsidian |
| 07 Immune System | 🔵 Готов | n8n реаниматор |
| Security | 🔵 Готов | JWT + rate limit + AES + audit |

---

## Архитектура

```
Флагман (Claude/GPT/Gemini)
    │ AGENTS.md / .claude/CLAUDE.md — прошивка при подключении
    ▼
EVO-core API (FastAPI)
    ├── /handshake → сессия + HMAC ключ
    ├── /concierge → выяснить стек проекта (незаметно)
    ├── /query     → найти символы под план+стек
    ├── /step_done → раскрыть следующий шаг
    ├── /result    → верифицировать + заархивировать
    ├── /hook_reply→ хук-допрос «есть что новее?»
    ├── /mcp       → JSON-RPC внешние среды
    └── /admin     → управление токенами, шардами, юзерами
    │
    ├── pgvector   — SCL символы и лигатуры
    ├── Redis      — горячий кэш сессий
    └── Shards     — zstd тела знаний (GDrive/GitHub/R2)
```

---

## Язык-Библиотека (SCL)

Каждое знание — адресная единица по нотации:
```
τ^{auto^2}_{zp_0047}
= Технология / Автоматизация / ZennoPoster / знание №47
```

Вектор символа → кластер похожих решений → лучшее под стек пользователя.

- **32 макро-корня** (Φ Λ M γ ζ β η κ ε τ ...)
- **Фрактальное дерево**: наука → раздел → подраздел
- **Лигатуры**: знания на стыке 3+ областей
- **R_f рейтинг**: частота применения, только растёт

Подробно: [SCL_FRACTAL_PROTOCOL.md](SCL_FRACTAL_PROTOCOL.md)
Нотация: [SCL_SYMBOLIC_NOTATION.md](SCL_SYMBOLIC_NOTATION.md)

---

## Безопасность

- AES шифрование токенов в БД (`core/crypto.py`)
- JWT + X-API-Key аутентификация
- Rate limiting 60 req/min
- HMAC подпись ответов ядра
- Path traversal защита на шардах
- Audit log всех изменений
- Уведомления Архитектора в ТГ при изменении protected zones

---

## Конфигурация (Admin UI)

Все токены вносятся **один раз** через Admin UI (`/admin`) или API:

```bash
# Telegram бот
curl -X POST http://localhost:8000/api/v1/admin/config \
  -H "X-Admin-Token: ADMIN_SECRET" \
  -d '{"key":"TG_BOT_TOKEN","value":"YOUR_TOKEN"}'

# Шард Google Drive
-d '{"key":"SHARD_PROVIDER","value":"gdrive"}'
-d '{"key":"SHARD_GDRIVE_TOKEN","value":"ya29...."}'
-d '{"key":"SHARD_GDRIVE_FOLDER","value":"FOLDER_ID"}'

# Шард GitHub
-d '{"key":"SHARD_PROVIDER","value":"github"}'
-d '{"key":"SHARD_GITHUB_TOKEN","value":"ghp_..."}'
-d '{"key":"SHARD_GITHUB_REPO","value":"owner/repo"}'
```

Применяются везде автоматически — перезапуск не нужен.

---

## n8n БЛОК 07 (Immune System)

```bash
./scripts/deploy.sh n8n
# Импортировать: n8n/evo_immune_system_workflow.json
```

---

## Навигация по проекту

| Файл | Назначение |
|------|-----------|
| [PROJECT_MAP.md](PROJECT_MAP.md) | Главная карта: статус, сшивка, деплой |
| [SCL_FRACTAL_PROTOCOL.md](SCL_FRACTAL_PROTOCOL.md) | Протокол Языка-Библиотеки |
| [SCL_SYMBOLIC_NOTATION.md](SCL_SYMBOLIC_NOTATION.md) | Нотация символов |
| [FLAGSHIP_SYSTEM_PROMPT.md](FLAGSHIP_SYSTEM_PROMPT.md) | Промпт флагмана |
| [LOCAL_MODEL_INSTRUCTIONS.md](LOCAL_MODEL_INSTRUCTIONS.md) | Инструкции локальной модели |
| [BLOCK_0X_*.md](BLOCK_01_core_engine.md) | Карта каждого блока |

---

## Тесты

```bash
EVO_ENV=development python tests/test_phase0.py   # 9 тестов Фаза 0
EVO_ENV=development python tests/test_phase1.py   # 9 тестов Фаза 1+2
EVO_ENV=development python tests/test_full.py     # 20 тестов полный стек
```

---

*v5.0 | 2026-06-03 | Все блоки реализованы*
