"""
Shard Client — БЛОК 03, Фаза 1
Провайдеры: local | gdrive | github | r2
Конфиг: Admin UI → config_manager → везде автоматически.
Автопришивка shard_link к символу после записи.
"""
import logging
from shards.zstd_codec import compress, decompress, parse_hyperlinks

log = logging.getLogger("evo.shards")


def _validate_path(path: str) -> str:
    """Защита от path traversal. path должен начинаться с /evo/"""
    if not path:
        raise ValueError("Пустой путь к шарду")
    # Нормализуем и проверяем
    import posixpath
    normalized = posixpath.normpath(path)
    if ".." in normalized or not normalized.startswith("/evo/"):
        raise ValueError(f"Недопустимый путь к шарду: {path}")
    # Только безопасные символы
    import re
    if not re.match(r"^[/a-zA-Z0-9_.^{}\-]+$", normalized):
        raise ValueError(f"Недопустимые символы в пути: {path}")
    return normalized



async def _provider() -> str:
    from core.config_manager import get
    return await get("SHARD_PROVIDER", "local")


async def read_cell(host: str, path: str, mirror: str = None) -> tuple[str, list]:
    prov = await _provider()
    for h in filter(None, [host, mirror, "local"]):
        try:
            raw = await _read(prov, path)
            if raw:
                content = decompress(raw)
                return content, parse_hyperlinks(content)
        except Exception as e:
            log.warning(f"read fail {h}{path}: {e}")
    return "", []


async def read_cell_local(path: str) -> tuple[str, list]:
    try:
        raw = _local_read(path)
        content = decompress(raw)
        return content, parse_hyperlinks(content)
    except FileNotFoundError:
        return "", []


async def write_cell(host: str, path: str, content: str, symbol_id: str = "") -> str:
    """Запись + автопришивка shard_link к символу в pgvector."""
    path = _validate_path(path)
    prov = await _provider()
    data = compress(content)
    try:
        final_path = await _write(prov, path, data)
    except Exception as e:
        log.error(f"write fail {path}: {e}")
        final_path = _local_write(path, data)

    if symbol_id:
        await _attach_link(symbol_id, final_path, host)

    log.info(f"Shard written: {final_path} ({len(data)}b) [{prov}]")
    return final_path


async def write_legacy_cell(path: str, content: str) -> str:
    """Сохраняет legacy тело при Тип А (старое рядом с новым)."""
    legacy_path = path.replace(".zst", "_legacy.zst")
    data = compress(content)
    prov = await _provider()
    try:
        return await _write(prov, legacy_path, data)
    except Exception:
        return _local_write(legacy_path, data)


async def _attach_link(symbol_id: str, shard_path: str, host: str):
    """Автопришивка: после записи на шард обновляет shard_path в pgvector."""
    from db.pg_client import get_pool
    from core.config_manager import get
    mirror = await get("SHARD_MIRROR_HOST", "")
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE scl_symbols
            SET shard_host=$2, shard_path=$3, shard_mirror=$4, last_updated=NOW()
            WHERE id=$1
        """, symbol_id, host or "", shard_path, mirror or None)
    log.debug(f"shard_link → {symbol_id}: {shard_path}")


# ── Провайдеры ─────────────────────────────────────────────────────────────────

def _local_read(path: str) -> bytes:
    with open(f"/tmp/evo_shards{path}", 'rb') as f:
        return f.read()

def _local_write(path: str, data: bytes) -> str:
    import os
    full = f"/tmp/evo_shards{path}"
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'wb') as f: f.write(data)
    return path

async def _read(prov: str, path: str) -> bytes:
    if prov == "gdrive":   return await _gdrive_read(path)
    if prov == "github":   return await _github_read(path)
    if prov == "r2":       return await _r2_read(path)
    return _local_read(path)

async def _write(prov: str, path: str, data: bytes) -> str:
    if prov == "gdrive":   return await _gdrive_write(path, data)
    if prov == "github":   return await _github_write(path, data)
    if prov == "r2":       return await _r2_write(path, data)
    return _local_write(path, data)

async def _gdrive_read(path: str) -> bytes:
    from core.config_manager import get
    import httpx
    token  = await get("SHARD_GDRIVE_TOKEN")
    folder = await get("SHARD_GDRIVE_FOLDER")
    name   = path.split("/")[-1]
    async with httpx.AsyncClient() as c:
        r = await c.get("https://www.googleapis.com/drive/v3/files",
            params={"q": f"name='{name}' and '{folder}' in parents", "fields": "files(id)"},
            headers={"Authorization": f"Bearer {token}"})
        files = r.json().get("files", [])
        if not files: raise FileNotFoundError(name)
        r2 = await c.get(f"https://www.googleapis.com/drive/v3/files/{files[0]['id']}",
            params={"alt": "media"}, headers={"Authorization": f"Bearer {token}"})
        return r2.content

async def _gdrive_write(path: str, data: bytes) -> str:
    from core.config_manager import get
    import httpx, json as _j
    token  = await get("SHARD_GDRIVE_TOKEN")
    folder = await get("SHARD_GDRIVE_FOLDER")
    name   = path.split("/")[-1]
    meta   = _j.dumps({"name": name, "parents": [folder]})
    async with httpx.AsyncClient() as c:
        await c.post("https://www.googleapis.com/upload/drive/v3/files",
            params={"uploadType": "multipart"},
            headers={"Authorization": f"Bearer {token}"},
            content=data)
    return path

async def _github_read(path: str) -> bytes:
    from core.config_manager import get
    import httpx, base64
    token = await get("SHARD_GITHUB_TOKEN")
    repo  = await get("SHARD_GITHUB_REPO")
    async with httpx.AsyncClient() as c:
        r = await c.get(f"https://api.github.com/repos/{repo}/contents{path}",
            headers={"Authorization": f"token {token}"})
        return base64.b64decode(r.json()['content'].replace('\n',''))

async def _github_write(path: str, data: bytes) -> str:
    from core.config_manager import get
    import httpx, base64, json as _j
    token = await get("SHARD_GITHUB_TOKEN")
    repo  = await get("SHARD_GITHUB_REPO")
    enc   = base64.b64encode(data).decode()
    url   = f"https://api.github.com/repos/{repo}/contents{path}"
    async with httpx.AsyncClient() as c:
        r   = await c.get(url, headers={"Authorization": f"token {token}"})
        sha = r.json().get("sha", "") if r.status_code == 200 else ""
        body = {"message": f"shard: {path}", "content": enc}
        if sha: body["sha"] = sha
        await c.put(url, headers={"Authorization": f"token {token}",
            "Content-Type": "application/json"}, content=_j.dumps(body))
    return path

async def _r2_read(path: str) -> bytes:
    """
    P14 fix: R2 требует AWS Signature v4 — без неё все запросы → 403 Forbidden.
    Текущая реализация не содержит Sig v4 → тихая ошибка при деплое с R2.
    До реализации Sig v4: использовать SHARD_PROVIDER=gdrive или github.
    Реализация Sig v4: httpx + manual HMAC-SHA256 подпись заголовков.
    """
    raise NotImplementedError(
        "R2 требует AWS Signature v4. "
        "Используйте SHARD_PROVIDER=gdrive или github до реализации Sig v4. "
        "См. PROJECT_MAP.md раздел 'Что осталось'."
    )

async def _r2_write(path: str, data: bytes) -> str:
    """
    P14 fix: R2 требует AWS Signature v4 — без неё PUT → 403 Forbidden.
    Тихая ошибка: шарды не пишутся, данные теряются.
    До реализации Sig v4: использовать SHARD_PROVIDER=gdrive или github.
    """
    raise NotImplementedError(
        "R2 требует AWS Signature v4. "
        "Используйте SHARD_PROVIDER=gdrive или github до реализации Sig v4. "
        "См. PROJECT_MAP.md раздел 'Что осталось'."
    )
