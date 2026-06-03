# БЛОК 02 — Language Library (Язык-Библиотека)

**Назначение:** Когнитивная матрица ядра EVO-core. Хранит SCL-символы и лигатуры — адресные единицы любого верифицированного знания. Не только технические скиллы: любое знание прошедшее YMS-MMM записывается сюда по единому протоколу фрактального дерева.

[← Карта проекта](README.md) | [→ Протокол формирования](SCL_FRACTAL_PROTOCOL.md)

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
| [БЛОК 01](BLOCK_01_core_engine.md) | Запрос на поиск символов по запросу пользователя | `SearchRequest {vector, top_k}` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Новое верифицированное знание для записи | `SCLSymbol` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Команда инкремента рейтинга после вызова | `{id: str}` |

### Отдаёт на выход
| Получатель | Что отдаёт | Формат |
|-----------|-----------|--------|
| [БЛОК 01](BLOCK_01_core_engine.md) | Список символов с similarity-скором | `list[SCLSymbol + score]` |
| [БЛОК 03](BLOCK_03_shard_storage.md) | shard_link из найденного символа | `ShardLink` |

---

## Зависимости

Нет внешних зависимостей. Этот блок первым поднимается в Фазе 0.
Требуется: PostgreSQL 16 + расширение pgvector на сервере.

---

## Что такое SCL-символ

SCL (Symbolic Connection Ligature) — адресная единица знания. Адрес строится по системе нотации:

```
[БАЗОВЫЙ_СИМВОЛ]^[надстрочный]_[подстрочный]_[номер]
```

Пример: `τ^auto_zp_0047` — технология / автоматизация / ZennoPoster / знание №47

Сам символ является вектором в pgvector. Поиск идёт по микро-маячкам в метаданных (science, section, subsection, label) — не по тексту тела знания. Тело хранится в zstd на шарде, в библиотеке только адрес и метаданные.

Подробная система нотации, 32 базовых корня и алгоритм автоматического формирования фракталов: → **[SCL_FRACTAL_PROTOCOL.md](SCL_FRACTAL_PROTOCOL.md)**

---

## Схема данных

### Python / Pydantic

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ShardLink(BaseModel):
    host: str
    path: str
    mirror: Optional[str] = None

class SCLSymbol(BaseModel):
    # Идентификатор по нотации: τ^auto_zp_0047
    id: str
    label: str
    vector: list[float]          # эмбеддинг от (label + science + section + subsection)

    # Фрактальная классификация
    science: str                 # "Технология"
    section: str                 # "Автоматизация"
    subsection: str              # "ZennoPoster"

    # Рейтинг — только инкрементируется, никогда не сбрасывается
    rating_frequency: int = 0
    confirmed_by: int = 1        # сколько смежных областей подтвердили знание

    # Эволюция — неприкосновенна, удаление = Критическая Ошибка YMS-MMM
    evolved_from: Optional[str] = None
    evolution_note: Optional[str] = None
    last_updated: datetime

    # Хранилище тела знания
    shard_link: ShardLink

    # Внутренние ссылки (гиперлинки вшитые в тело на шарде)
    hyperlinks: list[str] = []
```

### SQL / PostgreSQL + pgvector

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE scl_symbols (
    -- Идентификатор по нотации (τ^auto_zp_0047)
    id                TEXT PRIMARY KEY,
    label             TEXT NOT NULL,
    vector            vector(1536),        -- размерность под модель эмбеддингов

    -- Фрактальная классификация
    science           TEXT NOT NULL,
    section           TEXT NOT NULL,
    subsection        TEXT NOT NULL,

    -- Рейтинг (только инкремент)
    rating_frequency  INTEGER DEFAULT 0,
    confirmed_by      INTEGER DEFAULT 1,

    -- Эволюция (защищена YMS-MMM)
    evolved_from      TEXT REFERENCES scl_symbols(id),
    evolution_note    TEXT,
    last_updated      TIMESTAMPTZ DEFAULT NOW(),

    -- Хранилище
    shard_host        TEXT NOT NULL,
    shard_path        TEXT NOT NULL,
    shard_mirror      TEXT,

    -- Ссылки на связанные символы
    hyperlinks        TEXT[] DEFAULT '{}'
);

-- Поиск по вектору (cosine similarity)
CREATE INDEX ON scl_symbols
USING ivfflat (vector vector_cosine_ops)
WITH (lists = 100);

-- Поиск по классификации
CREATE INDEX ON scl_symbols (science, section, subsection);

-- Топ по рейтингу (горячие символы)
CREATE INDEX ON scl_symbols (rating_frequency DESC);
```

---

## Базовые операции

```python
# Поиск по смыслу запроса
async def find_symbols(query_vector: list[float], top_k: int = 5):
    return await db.fetch("""
        SELECT *, 1 - (vector <=> $1::vector) AS similarity
        FROM scl_symbols
        ORDER BY vector <=> $1::vector
        LIMIT $2
    """, query_vector, top_k)

# Инкремент рейтинга при каждом вызове (только +1, никогда не сбрасывается)
async def increment_rating(symbol_id: str):
    await db.execute("""
        UPDATE scl_symbols
        SET rating_frequency = rating_frequency + 1,
            last_updated = NOW()
        WHERE id = $1
    """, symbol_id)

# Перезапись тела (Тип А — знание то же, но улучшено)
# Рейтинг накапливается, тело на шарде заменяется, эволюция фиксируется
async def overwrite_symbol(symbol_id: str, new_shard_path: str, evolution_note: str):
    await db.execute("""
        UPDATE scl_symbols
        SET shard_path = $2,
            evolution_note = $3,
            rating_frequency = rating_frequency + 1,
            last_updated = NOW()
        WHERE id = $1
    """, symbol_id, new_shard_path, evolution_note)

# Создание нового символа (Тип Б — новые обстоятельства/инструменты)
async def create_symbol(symbol: SCLSymbol):
    await db.execute("""
        INSERT INTO scl_symbols
        (id, label, vector, science, section, subsection,
         confirmed_by, evolved_from, evolution_note, last_updated,
         shard_host, shard_path, shard_mirror, hyperlinks)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW(),$10,$11,$12,$13)
    """, symbol.id, symbol.label, symbol.vector,
        symbol.science, symbol.section, symbol.subsection,
        symbol.confirmed_by, symbol.evolved_from, symbol.evolution_note,
        symbol.shard_link.host, symbol.shard_link.path,
        symbol.shard_link.mirror, symbol.hyperlinks)
```

---

## Пороги поиска

| Similarity | Сценарий | Действие ядра |
|-----------|----------|---------------|
| > 0.92 | Полное совпадение | Выдать символ/лигатуру + параллельно подтянуть гиперлинки |
| 0.70–0.92 | Частичное совпадение | Выдать набор смежных символов + сообщение флагману: «точного решения нет, вот ближайшее» |
| < 0.70 | Нет совпадения | Флагман ищет решение самостоятельно в песочнице, результат записывается в библиотеку |

---

## Bootstrap (Фаза 0)

До запуска первых сессий вручную вносятся 20–30 символов по ключевым областям проекта. Это позволяет сразу проверить работу поиска на реальных запросах.

Приоритет для bootstrap:
- `τ^auto_zp_*` — ZennoPoster (ключевой инструмент)
- `τ^auto_n8n_*` — n8n воркфлоу
- `ε^pay_crypto_*` — крипто-шлюзы
- `τ^db_pg_*` — PostgreSQL паттерны
- `Φ^logic_*` — базовые логические правила (фундамент верификации)

Скрипт: `scripts/bootstrap_symbols.py`

---

## Задачи

### Фаза 0
- [ ] Развернуть PostgreSQL 16 на сервере
- [ ] Установить расширение pgvector
- [ ] Применить SQL-схему (`migrations/001_init.sql`)
- [ ] Реализовать Pydantic-модели `SCLSymbol`, `ShardLink`
- [ ] Реализовать операции `find_symbols`, `increment_rating`, `overwrite_symbol`, `create_symbol`
- [ ] Написать `bootstrap_symbols.py` (20–30 символов вручную)
- [ ] Написать тест: поиск возвращает правильные символы по тестовым векторам
- [ ] Интеграционный тест с БЛОК 01

### Фаза 1
- [ ] Реализовать автоматическое определение макро-корня по тексту
- [ ] Реализовать проверку на дублирование (similarity check перед записью)
- [ ] Реализовать алгоритм определения: Тип А (перезапись) vs Тип Б (новый символ)
- [ ] Реализовать автоматическую генерацию `evolution_note`
- [ ] Реализовать хук-допрос флагмана («...или есть что-то ещё новее?»)
- [ ] Поддержка лигатур (создание и поиск по комбинированным символам)

---

## Сшивка со смежными блоками

| Блок | Статус сшивки | Что проверено |
|------|--------------|---------------|
| [БЛОК 01](BLOCK_01_core_engine.md) Core Engine | 🔴 Не сшит | — |
| [БЛОК 03](BLOCK_03_shard_storage.md) Shard Storage | 🔴 Не сшит | — |

---

*Апдейт: 2026-06-03*
