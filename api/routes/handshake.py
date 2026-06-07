"""POST /api/v1/handshake — прошивка флагмана при подключении."""
import hmac, hashlib, os, uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class HandshakeRequest(BaseModel):
    flagship_id: str
    ready: bool = True

class HandshakeResponse(BaseModel):
    status: str
    session_id: str
    hmac_key: str   # сессионный ключ для подписи (TLS защищает передачу)

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
    # Сохранить сессию в БД
    try:
        from db.pg_client import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO evo_sessions (session_id, flagship_id, hmac_key)
                VALUES ($1, $2, $3)
                ON CONFLICT (session_id) DO NOTHING
            """, session_id, req.flagship_id, session_key)
    except Exception as e:
        import logging
        logging.getLogger("evo.handshake").warning(f"Session save failed: {e}")

    return HandshakeResponse(
        status="synced",
        session_id=session_id,
        hmac_key=session_key
    )
