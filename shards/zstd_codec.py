"""zstd компрессия/декомпрессия на лету в памяти — без файлов на диске."""
import zstandard as zstd
import re

def compress(content: str) -> bytes:
    cctx = zstd.ZstdCompressor(level=3)
    return cctx.compress(content.encode('utf-8'))

def decompress(data: bytes) -> str:
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(data).decode('utf-8')

def parse_hyperlinks(content: str) -> list[dict]:
    """
    Парсинг гиперлинков из тела ячейки.
    Формат: [[EVO:τ^{auto}_{zp_0047} | описание задачи]]
    """
    pattern = r'\[\[EVO:([^\]|]+?)(?:\s*\|\s*([^\]]*))?\]\]'
    links = []
    for m in re.finditer(pattern, content):
        symbol_id = m.group(1).strip()
        description = m.group(2).strip() if m.group(2) else ""
        links.append({"symbol_id": symbol_id, "description": description})
    return links
