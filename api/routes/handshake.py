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
    secret = os.getenv("EVO_HMAC_SECRET", "dev_secret_32_chars_minimum_here")
    session_key = hmac.new(
        secret.encode(), session_id.encode(), hashlib.sha256
    ).hexdigest()
    return HandshakeResponse(
        status="synced",
        session_id=session_id,
        hmac_key=session_key
    )
