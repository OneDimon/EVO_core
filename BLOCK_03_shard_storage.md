# БЛОК 03 — Shard Storage (Холодное хранилище)

**Назначение:** Хранит тела скиллов (инструкции, код, конфиги) в zstd-сжатом виде на бесплатных облачных шардах с зеркалированием. Отвечает за компрессию, декомпрессию и автороутинг между основным шардом и зеркалом.

[← Вернуться к карте проекта](README.md)

---

## Статус

| Параметр | Значение |
|----------|----------|
| **Фаза** | Фаза 0 — второй в очереди (после БЛОК 02) |
| **Статус блока** | 🔴 Не начат |
| **Последний апдейт** | 2026-06-03 |

---

## Коннекторы

### Получает на вход
| Источник | Что приходит | Формат |
|----------|-------------|--------|
| [БЛОК 01](BLOCK_01_core_engine.md) | Команда декомпрессии | `{shard_host, shard_path, mirror?}` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Новое тело скилла для архивации | `{content: str, target_path: str}` |
| [БЛОК 02](BLOCK_02_language_library.md) | ShardLink из найденного символа | `ShardLink` |

### Отдаёт на выход
| Получатель | Что отдаёт | Формат |
|-----------|-----------|--------|
| [БЛОК 01](BLOCK_01_core_engine.md) | Декомпрессированное тело скилла | `UTF-8 text` |
| [БЛОК 01](BLOCK_01_core_engine.md) | Путь к новому сохранённому файлу | `str (shard_path)` |

---

## Зависимости

**Должен быть готов до:**
- [БЛОК 02](BLOCK_02_language_library.md) — нужен для того чтобы ShardLink в символе был реальным и указывал на существующую ячейку

**Внешние зависимости:**
- Доступ к бесплатным облачным хранилищам (Google Drive API / Mega / аналоги)
- При масштабировании: Cloudflare R2 (S3-совместимый, бесплатный egress)

---

## Архитектура хранилища

```
Шард 01 (основной, 15 ГБ)      Шард 01-mirror (зеркало)
  /evo/AUTO/ZP/HSR/0047.zst  ←→  /evo/AUTO/ZP/HSR/0047.zst
  /evo/AUTO/N8N/WEBHOOK/0033.zst
  /evo/PAY/CRYPTO/0021.zst
  ...

Шард 02 (основной, 15 ГБ)      Шард 02-mirror (зеркало)
  ...
```

**Структура пути:** `/evo/{section}/{subsection}/{id}.zst`

**Почему rate limits не критичны:** данные читаются один раз при инициации сессии и разворачиваются в RAM-кэш ядра. Повторных обращений к шарду нет пока сессия активна. Запись — асинхронная, после завершения сессии.

---

## Гиперлинки внутри инструкций

В теле zstd-файла могут быть вшиты ссылки на связанные скиллы:

```
[[EVO:SCL-0021-PAY-CRYPTO]]
[[EVO:SCL-0033-N8N-WORKFLOW:step_3]]
```

При декомпрессии БЛОК 01 сканирует тело на наличие таких маркеров и параллельно запрашивает у БЛОК 03 связанные ячейки — до того как флагман начнёт работу.

---

## ZSTD-словари

Предобученные словари ускоряют компрессию/декомпрессию в 2–4 раза на однотипном контенте.

```bash
# Собрать словарь на типовом контенте раздела
zstd --train ./corpus/n8n_workflows/*.json -o dicts/n8n_dict.zst

# Компрессия с словарём
zstd -D dicts/n8n_dict.zst input.json -o output.json.zst

# Декомпрессия с словарём
zstd -D dicts/n8n_dict.zst -d output.json.zst -o restored.json
```

Словари хранятся локально на сервере ядра. Один словарь на каждый раздел (`n8n`, `zennoposter`, `crm`, `crypto_pay`).

---

## Операции

```python
import zstandard as zstd
import aiohttp

async def decompress_from_shard(shard_link: ShardLink) -> str:
    """Скачать и декомпрессировать ячейку. Fallback на зеркало."""
    for host in [shard_link.host, shard_link.mirror]:
        if not host:
            continue
        try:
            url = f"https://{host}{shard_link.path}"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=10) as r:
                    compressed = await r.read()
            dctx = zstd.ZstdDecompressor()
            return dctx.decompress(compressed).decode('utf-8')
        except Exception:
            continue
    raise RuntimeError(f"Не удалось загрузить шард: {shard_link}")

async def compress_to_shard(content: str, target_path: str,
                             dict_path: str = None) -> str:
    """Сжать и загрузить на шард. Асинхронно."""
    cctx = zstd.ZstdCompressor(
        dict_data=zstd.ZstdCompressionDict(
            open(dict_path,'rb').read()) if dict_path else None,
        level=3
    )
    compressed = cctx.compress(content.encode('utf-8'))
    # TODO: загрузка на выбранный облачный провайдер
    # Вернуть финальный путь к файлу
    return target_path
```

---

## Задачи

### Фаза 0
- [ ] Выбрать провайдера бесплатного хранилища (Google Drive API / Mega)
- [ ] Реализовать `decompress_from_shard` с fallback на зеркало
- [ ] Реализовать `compress_to_shard` с асинхронной загрузкой
- [ ] Создать структуру папок на шарде (`/evo/section/subsection/`)
- [ ] Создать первые ячейки для bootstrap-символов (БЛОК 02)
- [ ] Написать тесты: компрессия → загрузка → скачивание → декомпрессия = оригинал
- [ ] Интеграционный тест с БЛОК 01: ядро получает тело скилла корректно

### Фаза 1
- [ ] Собрать словари zstd для разделов (n8n, zennoposter, crm, crypto)
- [ ] Встроить словари в компрессор/декомпрессор
- [ ] Парсер гиперлинков: при декомпрессии параллельно подтянуть связанные ячейки
- [ ] Автороутинг: при недоступности основного шарда — моментальный переход на зеркало

### Масштабирование
- [ ] Миграция на Cloudflare R2 при росте объёма

---

## Сшивка со смежными блоками

| Блок | Статус сшивки | Что проверено |
|------|--------------|---------------|
| [БЛОК 01](BLOCK_01_core_engine.md) Core Engine | 🔴 Не сшит | — |
| [БЛОК 02](BLOCK_02_language_library.md) Language Library | 🔴 Не сшит | — |

---

*Апдейт: 2026-06-03*
