"""Клиент для работы с шардами (бесплатные облака / Cloudflare R2)."""
import aiohttp, os, logging
from .zstd_codec import compress, decompress, parse_hyperlinks

log = logging.getLogger("evo.shards")

async def read_cell(host: str, path: str, mirror: str = None) -> tuple[str, list]:
    """
    Читает ячейку с шарда, декомпрессирует, парсит гиперлинки.
    Возвращает: (content, hyperlinks)
    """
    for h in filter(None, [host, mirror]):
        try:
            url = f"https://{h}{path}"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        raw = await r.read()
                        content = decompress(raw)
                        links = parse_hyperlinks(content)
                        return content, links
        except Exception as e:
            log.warning(f"Shard read failed {h}{path}: {e}")
    raise RuntimeError(f"Cannot read shard: {host}{path}")

async def write_cell(host: str, path: str, content: str) -> bool:
    """Записывает ячейку на шард (zstd на лету в памяти)."""
    compressed = compress(content)
    # TODO: реализовать под конкретного провайдера (Google Drive API / R2 / etc)
    # Для Фазы 0: заглушка — сохраняем локально для тестов
    import os
    os.makedirs(f"/tmp/evo_shards{os.path.dirname(path)}", exist_ok=True)
    with open(f"/tmp/evo_shards{path}", 'wb') as f:
        f.write(compressed)
    log.info(f"Cell written: {path} ({len(compressed)} bytes)")
    return True

async def read_cell_local(path: str) -> tuple[str, list]:
    """Локальное чтение для тестов Фазы 0."""
    try:
        with open(f"/tmp/evo_shards{path}", 'rb') as f:
            raw = f.read()
        content = decompress(raw)
        links = parse_hyperlinks(content)
        return content, links
    except FileNotFoundError:
        return "", []
