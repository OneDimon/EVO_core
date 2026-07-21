# shards/ — Shard Storage (Блок 03)

**Перед правкой обязательно прочитать:** `../BLOCK_03_shard_storage.md`.

## Что здесь
- `zstd_codec.py` — сжатие/распаковка, парсинг гиперссылок `[[EVO:...]]`.
- `shard_client.py` — провайдеры хранения: `local` (dev, офлайн-тесты),
  `gdrive` (service-account JWT, см. `.env.example` про
  `SHARD_GDRIVE_CREDENTIALS_JSON`/`SHARD_GDRIVE_ROOT_FOLDER` — это Drive
  folder ID из URL, не имя папки), `github`, `r2`. Переключение — `SHARD_PROVIDER`.

## Правила
- `write_cell`/`read_cell_local` — round-trip должен быть побайтовым
  (см. `tests/test_shard_roundtrip.py`, самодостаточный офлайн-тест).
- Учётные данные провайдеров (`SHARD_GDRIVE_CREDENTIALS_JSON`,
  `SHARD_GITHUB_TOKEN`, `SHARD_R2_*`) — только через `.env`, шифруются при
  сохранении в `evo_config` (`core/crypto.py`). Никогда не хардкодить, не
  логировать содержимое credentials.
- zstd compress/decompress — CPU-bound, вызывать через `asyncio.to_thread`
  из любого async-контекста.
