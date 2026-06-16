"""
POST /api/v1/register — регистрация пользователя и выдача API-ключа.
P11 fix: эндпоинт отсутствовал, кнопка "Получить ключ" на сайте не работала.
Связан с: db/users.py, site/index.html, api/main.py
"""
import re, logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db.users import create_user

log = logging.getLogger("evo.register")
router = APIRouter()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

class RegisterRequest(BaseModel):
    email: str
    plan: str = "free"

class RegisterResponse(BaseModel):
    api_key: str
    email: str
    plan: str
    message: str

@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    """
    Регистрирует нового пользователя и возвращает API-ключ.
    Бесплатный период: plan="free", без ограничений 2 месяца.
    """
    email = req.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Некорректный email")

    try:
        user = await create_user(email=email, plan=req.plan)
    except Exception as e:
        # Если email уже зарегистрирован — сообщаем без раскрытия деталей
        log.warning(f"[Register] create_user failed for {email}: {e}")
        raise HTTPException(
            status_code=409,
            detail="Email уже зарегистрирован. Проверьте почту или свяжитесь с hi@evo-core.io"
        )

    log.info(f"[Register] Новый пользователь: {email} plan={req.plan}")
    return RegisterResponse(
        api_key=user["api_key"],
        email=email,
        plan=req.plan,
        message=(
            "Ключ создан. Установка: pip install evo-core-client "
            "&& EVO_API_KEY=<key> evo connect"
        )
    )
