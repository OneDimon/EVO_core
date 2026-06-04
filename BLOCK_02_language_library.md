# БЛОК 02 — Language Library (Язык-Библиотека)

**Назначение:** Когнитивная матрица ядра EVO-core. Хранит SCL-символы и лигатуры —
адресные единицы любого верифицированного знания. Любое знание прошедшее YMS-MMM
записывается по единому протоколу фрактального дерева.

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
| [БЛОК 01](BLOCK_01_core_engine.md) | Запрос на поиск символов | `SearchRequest {vector, top_k, stack?}` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Новое верифицированное знание | `SCLSymbol` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Инкремент рейтинга | `{id: str}` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Запрос по стеку пользователя | `StackQuery {stack[], project_context}` |

### Отдаёт на выход
| Получатель | Что отдаёт | Формат |
|-----------|-----------|--------|
| [БЛОК 01](BLOCK_01_core_engine.md) | Символы с similarity + R_f | `list[SCLSymbol + score]` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Набор символов под стек | `list[SCLSymbol]` |
| [БЛОК 03](BLOCK_03_shard_storage.md) | shard_link из найденного символа | `ShardLink` |

---

## Зависимости

Нет внешних зависимостей. Первым поднимается в Фазе 0.
Требуется: PostgreSQL 16 + pgvector на сервере.

---

## Ключевые принципы

**Метаданные символа — статичны.** Они описывают суть знания как пункт оглавления.
Позиция символа в плане определяется динамически при каждой сессии на основе
соответствия шагам плана флагмана. В метаданных самого символа позиция не хранится.

**Выдаётся решение с наивысшим R_f.** При поиске ядро выдаёт флагману символ
с максимальным частотным рейтингом среди подходящих. Флагман сам решает как применять.

**Legacy = набор символов/лигатур.** При перезаписи (Тип А) рядом с основным решением
сохраняется набор альтернативных проверенных символов — для случаев когда пользователь
использует другой стек и не может применить основное решение. Не отдельный файл —
ссылки на существующие символы в `legacy_symbols[]`.

**Bootstrap через Gemini.** Первичное наполнение ядра выполняет Gemini автоматически
из открытых источников по убыванию востребованности. Сначала логика процессов,
затем конкретные инструкции. Сначала глобальные общие, затем частные.

---

## Схема данных

### Python / Pydantic

```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ShardLink(BaseModel):
    host: str
    path: str                    # актуальное решение
    mirror: Optional[str] = None

class SCLSymbol(BaseModel):
    # Адрес по нотации: τ^auto_zp_0047
    id: str
    label: str
    vector: list[float]          # эмбеддинг от (label + science + section + subsection)
                                 # генерируется подключённой моделью автоматически

    # Фрактальная классификация (статичны, неизменяемы после создания)
    science: str                 # "Технология"
    section: str                 # "Автоматизация"
    subsection: str              # "ZennoPoster"

    # Рейтинги
    rating_frequency: int = 0    # R_f — только инкрементируется, никогда не сбрасывается
    confirmed_by: int = 1        # сколько смежных областей подтвердили знание

    # Эволюция — неприкосновенна
    evolved_from: Optional[str] = None
    evolution_note: Optional[str] = None
    last_updated: datetime

    # Хранилище тела знания
    shard_link: ShardLink

    # Альтернативные решения (набор ID символов под другие стеки)
    # Не файлы — ссылки на существующие символы в библиотеке
    legacy_symbols: list[str] = []

    # Применимые стеки (для поиска по стеку пользователя)
    applicable_stacks: list[str] = []

    # Гиперлинки — только для уточняющих деталей конкретного проекта
    hyperlinks: list[str] = []
```

### SQL / PostgreSQL + pgvector

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE scl_symbols (
    id                TEXT PRIMARY KEY,       -- τ^auto_zp_0047
    label             TEXT NOT NULL,
    vector            vector(1536),           -- размерность под подключённую модель

    -- Фрактальная классификация (статична после создания)
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

    -- Альтернативные решения (набор ID символов, не файлы)
    legacy_symbols    TEXT[] DEFAULT '{}',

    -- Применимые стеки
    applicable_stacks TEXT[] DEFAULT '{}',

    -- Гиперлинки (уточняющие детали проекта)
    hyperlinks        TEXT[] DEFAULT '{}',

    -- Версионирование для optimistic locking при конкурентной записи
    version_ts        TIMESTAMPTZ DEFAULT NOW()
);

-- Поиск по вектору (cosine similarity)
CREATE INDEX ON scl_symbols
USING ivfflat (vector vector_cosine_ops) WITH (lists = 100);

-- Поиск по классификации
CREATE INDEX ON scl_symbols (science, section, subsection);

-- Топ по рейтингу (горячие символы первыми)
CREATE INDEX ON scl_symbols (rating_frequency DESC);

-- Поиск по стеку
CREATE INDEX ON scl_symbols USING gin (applicable_stacks);
```

---

## Базовые операции

```python
# Поиск — выдаёт символы отсортированные по similarity × R_f
async def find_symbols(query_vector: list[float], top_k: int = 5):
    return await db.fetch("""
        SELECT *,
               1 - (vector <=> $1::vector) AS similarity,
               (1 - (vector <=> $1::vector)) * log(rating_frequency + 2) AS score
        FROM scl_symbols
        ORDER BY score DESC
        LIMIT $2
    """, query_vector, top_k)

# Поиск под конкретный стек пользователя
async def find_by_stack(query_vector: list[float], user_stack: list[str], top_k: int = 5):
    return await db.fetch("""
        SELECT *,
               1 - (vector <=> $1::vector) AS similarity
        FROM scl_symbols
        WHERE applicable_stacks && $2::text[]
        ORDER BY (1 - (vector <=> $1::vector)) * log(rating_frequency + 2) DESC
        LIMIT $3
    """, query_vector, user_stack, top_k)

# Инкремент рейтинга
async def increment_rating(symbol_id: str):
    await db.execute("""
        UPDATE scl_symbols
        SET rating_frequency = rating_frequency + 1,
            last_updated = NOW()
        WHERE id = $1
    """, symbol_id)

# Тип А — перезапись с сохранением legacy как ссылки на старый символ
async def overwrite_symbol(symbol_id: str, new_shard_path: str,
                            evolution_note: str, old_symbol_id: str):
    await db.execute("""
        UPDATE scl_symbols
        SET shard_path = $2,
            evolution_note = $3,
            legacy_symbols = array_append(legacy_symbols, $4),
            rating_frequency = rating_frequency + 1,
            version_ts = NOW(),
            last_updated = NOW()
        WHERE id = $1
        AND version_ts = (SELECT version_ts FROM scl_symbols WHERE id = $1)
    """, symbol_id, new_shard_path, evolution_note, old_symbol_id)
    # Если 0 строк обновлено — conflict, retry через очередь

# Тип Б — создание нового символа
async def create_symbol(symbol: SCLSymbol):
    await db.execute("""
        INSERT INTO scl_symbols
        (id, label, vector, science, section, subsection,
         confirmed_by, evolved_from, evolution_note, last_updated,
         shard_host, shard_path, shard_mirror,
         legacy_symbols, applicable_stacks, hyperlinks, version_ts)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW(),$10,$11,$12,$13,$14,$15,NOW())
    """, symbol.id, symbol.label, symbol.vector,
        symbol.science, symbol.section, symbol.subsection,
        symbol.confirmed_by, symbol.evolved_from, symbol.evolution_note,
        symbol.shard_link.host, symbol.shard_link.path, symbol.shard_link.mirror,
        symbol.legacy_symbols, symbol.applicable_stacks, symbol.hyperlinks)
```

---

## Пороги поиска

| Similarity | Сценарий | Действие |
|-----------|----------|----------|
| > 0.92 | Полное совпадение | Выдать символ с наивысшим R_f |
| 0.70–0.92 | Частичное | Набор смежных + `stack_query: true` |
| < 0.70 | Нет совпадения | `cartridge_empty` — поиск внешний |

---

## Bootstrap (первичное наполнение)

**Кто:** Gemini (бесплатный, щедрые лимиты)
**Источники:** GitHub Trending, Stack Overflow, npm, PyPI, n8n Templates

**Порядок наполнения:**
1. Оценить востребованность скиллов по открытым источникам
2. Наполнять по убыванию востребованности
3. Иерархия: глобальные общие → технические паттерны → инструменты → частные инструкции
4. Сначала логика процесса (почему так работает), затем инструкции (как делать)

**Критерий готовности к продакшну:**
- Минимум 3 символа в каждом из 32 корневых разделов
- Минимум 50 символов в разделе `τ` (технология)
- Минимум 20 лигатур в межобластных точках
- Все символы прошли YMS-MMM

Скрипт проверки: `scripts/bootstrap_check.py`
Ядро не принимает пользовательские запросы до готовности.

---

## Асинхронная очередь записи (миллисекунды)

База обслуживает тысячи и миллионы пользователей.
Запись **никогда не блокирует** ответ пользователю.

```python
# Redis Queue — асинхронная запись в фоне
async def enqueue_write(symbol: SCLSymbol):
    await redis.lpush("evo:write_queue", symbol.json())
    # Worker обрабатывает очередь независимо
    # zstd сворачивается на лету в памяти — без промежуточных файлов на диск
    # Optimistic locking через version_ts при конкурентной записи
    # При conflict — retry max 3 раза, merge по принципу «новее побеждает»
```

---

## Задачи

### Фаза 0
- [ ] PostgreSQL 16 + pgvector на сервере
- [ ] Применить SQL-схему (`migrations/001_init.sql`)
- [ ] Реализовать Pydantic-модели `SCLSymbol`, `ShardLink`
- [ ] Реализовать операции: `find_symbols`, `find_by_stack`, `increment_rating`,
      `overwrite_symbol`, `create_symbol`
- [ ] Реализовать асинхронную очередь записи (Redis Queue)
- [ ] Написать `scripts/bootstrap_symbols.py` (Gemini наполняет из открытых источников)
- [ ] Написать `scripts/bootstrap_check.py` (проверка готовности)
- [ ] Тест: поиск возвращает символ с наивысшим R_f
- [ ] Тест: поиск по стеку возвращает применимые символы
- [ ] Интеграционный тест с БЛОК 01

### Фаза 1
- [ ] Автоматическое определение макро-корня по тексту
- [ ] Проверка на дублирование (similarity check перед записью)
- [ ] Классификатор Тип А / Тип Б
- [ ] Автогенерация `evolution_note`
- [ ] Поддержка лигатур (`confirmed_by >= 3`)
- [ ] Хук-допрос флагмана

---

## Сшивка со смежными блоками

| Блок | Статус | Что проверено |
|------|--------|---------------|
| [БЛОК 01](BLOCK_01_core_engine.md) Core Engine | 🔴 Не сшит | — |
| [БЛОК 03](BLOCK_03_shard_storage.md) Shard Storage | 🔴 Не сшит | — |

---

*Апдейт: 2026-06-03*
