"""POST /api/v1/handshake — прошивка флагмана при подключении."""
import hmac, hashlib, os, uuid
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class HandshakeRequest(BaseModel):
    flagship_id: str
    ready: bool = True
    # Необязательно: если флагман уже знает API-ключ пользователя — сессия
    # сразу привязывается к user_id. Без этого execution_mode-предпочтение
    # личного кабинета (api/routes/query.py) не сможет резолвиться — сессия
    # без user_id формально валидна (handshake — единственный эндпоинт без
    # обязательной авторизации, см. NO_AUTH_PATHS), но безымянна.
    api_key: Optional[str] = None

class HandshakeResponse(BaseModel):
    status: str
    session_id: str
    hmac_key: str   # сессионный ключ для подписи (TLS защищает передачу)
    system_prompt: str  # полный протокол — FLAGSHIP_SYSTEM_PROMPT.md.
    # До этого фикса ничего в коде не отдавало этот файл флагману вообще,
    # несмотря на собственный заголовок файла: "Вшивается незаметно для
    # пользователя при подключении через CLI/MCP" — верно только для
    # Claude Code, читающего .claude/CLAUDE.md локально при работе НАД
    # этим репозиторием; внешний флагман, подключающийся по HTTP к
    # реальному API, не получал протокол никак и ниоткуда.


_SYSTEM_PROMPT_CACHE = {"text": None, "mtime": None}

def _load_system_prompt() -> str:
    """
    Читает FLAGSHIP_SYSTEM_PROMPT.md с диска, кэширует по mtime — файл
    меняется редко (правки протокола), перечитывать на каждый handshake
    не нужно, но и не должен требовать рестарта процесса при правке.
    """
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "FLAGSHIP_SYSTEM_PROMPT.md")
    try:
        mtime = os.path.getmtime(path)
        if _SYSTEM_PROMPT_CACHE["mtime"] != mtime:
            with open(path, "r", encoding="utf-8") as f:
                _SYSTEM_PROMPT_CACHE["text"] = f.read()
            _SYSTEM_PROMPT_CACHE["mtime"] = mtime
        return _SYSTEM_PROMPT_CACHE["text"]
    except Exception as e:
        import logging
        logging.getLogger("evo.handshake").error(
            f"FLAGSHIP_SYSTEM_PROMPT.md не найден/не читается: {e}"
        )
        return ""

@router.post("/handshake", response_model=HandshakeResponse)
async def handshake(req: HandshakeRequest):
    if not req.ready:
        raise HTTPException(400, "Flagship not ready")
    session_id = str(uuid.uuid4())
    # Генерируем сессионный HMAC ключ
    secret = os.getenv("EVO_HMAC_SECRET", "")
    if not secret and os.getenv("EVO_ENV", "production") == "production":
        raise HTTPException(500, "EVO_HMAC_SECRET не задан в .env")
    if not secret:
        secret = "dev_secret_32_chars_minimum_here"  # только для development
    session_key = hmac.new(
        secret.encode(), session_id.encode(), hashlib.sha256
    ).hexdigest()

    user_id = None
    if req.api_key:
        try:
            from db.users import get_user_by_any_key
            user = await get_user_by_any_key(req.api_key)
            user_id = user["id"] if user else None
        except Exception as e:
            import logging
            logging.getLogger("evo.handshake").warning(f"api_key resolve failed: {e}")

    # Сохранить сессию в БД
    try:
        from db.pg_client import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO evo_sessions (session_id, flagship_id, hmac_key, user_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (session_id) DO NOTHING
            """, session_id, req.flagship_id, session_key, user_id)
    except Exception as e:
        import logging
        logging.getLogger("evo.handshake").warning(f"Session save failed: {e}")

    return HandshakeResponse(
        status="synced",
        session_id=session_id,
        hmac_key=session_key,
        system_prompt=_load_system_prompt()
    )
