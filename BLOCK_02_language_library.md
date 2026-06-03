# БЛОК 02 — Language Library (Язык-Библиотека)

**Назначение:** Хранит SCL-символы (семантические отпечатки скиллов) в PostgreSQL + pgvector. Отвечает за поиск по смыслу запроса, рейтинги символов и логику эволюции (перезапись / новый символ).

[← Вернуться к карте проекта](README.md)

---

## Статус

| Параметр | Значение |
|----------|----------|
| **Фаза** | Фаза 0 — первым в очереди |
| **Статус блока** | 🔴 Не начат |
| **Последний апдейт** | 2026-06-03 |

---

## Коннекторы

### Получает на вход
| Источник | Что приходит | Формат |
|----------|-------------|--------|
| [БЛОК 01](BLOCK_01_core_engine.md) | Запрос на поиск символов | `{vector: float[], top_k: int}` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Команда инкремента рейтинга | `{symbol_id: str}` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Новый или обновлённый SCL-символ | `SCLSymbol` |

### Отдаёт на выход
| Получатель | Что отдаёт | Формат |
|-----------|-----------|--------|
| [БЛОК 01](BLOCK_01_core_engine.md) | Список символов с similarity-скором | `list[SCLSymbol + score]` |
| [БЛОК 03](BLOCK_03_shard_storage.md) | shard_link из найденного символа | `ShardLink` |

---

## Зависимости

**Нет внешних зависимостей.** Этот блок первым поднимается в Фазе 0.

Требует только: PostgreSQL 16 + расширение pgvector установлены на сервере.

---

## Схема данных

### SCL-символ (Pydantic)

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ShardLink(BaseModel):
    host: str           # основной хост шарда
    path: str           # путь к zstd-файлу
    mirror: Optional[str] = None  # зеркало для fallback

class SCLSymbol(BaseModel):
    id: str             # формат: "SCL-XXXX-SECTION-TAG"
    label: str          # человекочитаемое описание
    vector: list[float] # эмбеддинг (размерность = модель эмбеддингов)

    # Фрактальная классификация
    science: str        # "Технические науки"
    section: str        # "Автоматизация"
    subsection: str     # "Парсинг игровых аккаунтов"

    # Рейтинги (только инкремент, никогда не сбрасываются)
    rating_frequency: int = 0
    rating_context: float = 0.0  # 0.0–1.0

    # Эволюция
    evolved_from: Optional[str] = None   # ID родительского символа
    evolution_note: Optional[str] = None # "Переход Python → Rust"
    last_updated: datetime

    # Хранилище
    shard_link: ShardLink

    # Внутренние ссылки
    hyperlinks: list[str] = []  # список SCL ID
```

### SQL-схема

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE scl_symbols (
    id                TEXT PRIMARY KEY,
    label             TEXT NOT NULL,
    vector            vector(1536),        -- размерность под модель эмбеддингов

    science           TEXT NOT NULL,
    section           TEXT NOT NULL,
    subsection        TEXT NOT NULL,

    rating_frequency  INTEGER DEFAULT 0,
    rating_context    FLOAT DEFAULT 0.0,

    evolved_from      TEXT REFERENCES scl_symbols(id),
    evolution_note    TEXT,
    last_updated      TIMESTAMPTZ DEFAULT NOW(),

    shard_host        TEXT NOT NULL,
    shard_path        TEXT NOT NULL,
    shard_mirror      TEXT,

    hyperlinks        TEXT[] DEFAULT '{}'
);

CREATE INDEX ON scl_symbols
USING ivfflat (vector vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX ON scl_symbols (science, section, subsection);
CREATE INDEX ON scl_symbols (rating_frequency DESC);
```

---

## Базовые операции

```python
# Поиск по смыслу
async def find_symbols(query_vector: list[float], top_k: int = 5):
    return await db.fetch("""
        SELECT *, 1 - (vector <=> $1::vector) AS similarity
        FROM scl_symbols
        ORDER BY vector <=> $1::vector
        LIMIT $2
    """, query_vector, top_k)

# Инкремент рейтинга (только +1, никогда не сбрасывается)
async def increment_rating(symbol_id: str):
    await db.execute("""
        UPDATE scl_symbols
        SET rating_frequency = rating_frequency + 1,
            last_updated = NOW()
        WHERE id = $1
    """, symbol_id)

# Перезапись тела (Тип А: символ тот же, тело скилла улучшилось)
async def overwrite_symbol(symbol_id: str, new_shard_path: str, note: str):
    await db.execute("""
        UPDATE scl_symbols
        SET shard_path = $2,
            evolution_note = $3,
            rating_frequency = rating_frequency + 1,
            last_updated = NOW()
        WHERE id = $1
    """, symbol_id, new_shard_path, note)

# Создание нового символа (Тип Б: новые инструменты/обстоятельства)
async def create_symbol(symbol: SCLSymbol):
    await db.execute("""
        INSERT INTO scl_symbols
        (id, label, vector, science, section, subsection,
         evolved_from, evolution_note, last_updated,
         shard_host, shard_path, shard_mirror, hyperlinks)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW(),$9,$10,$11,$12)
    """, symbol.id, symbol.label, symbol.vector,
        symbol.science, symbol.section, symbol.subsection,
        symbol.evolved_from, symbol.evolution_note,
        symbol.shard_link.host, symbol.shard_link.path,
        symbol.shard_link.mirror, symbol.hyperlinks)
```

---

## Пороги поиска

| Similarity | Сценарий | Действие ядра |
|-----------|----------|---------------|
| > 0.92 | Полное совпадение | Выдать лигатуру + гиперлинки |
| 0.70–0.92 | Частичное совпадение | Выдать набор символов + сообщение флагману |
| < 0.70 | Нет совпадения | Флагман ищет самостоятельно |

---

## Bootstrap (Фаза 0)

До запуска первых реальных сессий в базу вручную вносятся 20–30 символов — по ключевым областям проекта (n8n, ZennoPoster, CRM, крипто-шлюзы). Это позволяет сразу проверить работу поиска на реальных запросах.

Скрипт bootstrap: `scripts/bootstrap_symbols.py`

---

## Задачи

### Фаза 0
- [ ] Развернуть PostgreSQL 16 на сервере
- [ ] Установить расширение pgvector
- [ ] Применить SQL-схему (`migrations/001_init.sql`)
- [ ] Реализовать Pydantic-модели `SCLSymbol`, `ShardLink`
- [ ] Реализовать функции `find_symbols`, `increment_rating`, `overwrite_symbol`, `create_symbol`
- [ ] Написать скрипт `bootstrap_symbols.py` (загрузка первых 20–30 символов)
- [ ] Написать тесты: поиск возвращает корректные символы по тестовым векторам
- [ ] Интеграционный тест с БЛОК 01: ядро получает список символов корректно

---

## Сшивка со смежными блоками

| Блок | Статус сшивки | Что проверено |
|------|--------------|---------------|
| [БЛОК 01](BLOCK_01_core_engine.md) Core Engine | 🔴 Не сшит | — |
| [БЛОК 03](BLOCK_03_shard_storage.md) Shard Storage | 🔴 Не сшит | — |

---

*Апдейт: 2026-06-03*
