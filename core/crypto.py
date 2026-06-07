"""
Crypto — шифрование sensitive данных в evo_config.
Все токены и ключи шифруются AES через pgcrypto перед записью в БД.
"""
import os, base64, logging
from cryptography.fernet import Fernet

log = logging.getLogger("evo.crypto")

SENSITIVE_KEYS = {
    "TG_BOT_TOKEN", "TG_ADMIN_CHAT_ID",
    "SHARD_GDRIVE_TOKEN", "SHARD_GITHUB_TOKEN",
    "SHARD_R2_ACCESS_KEY", "SHARD_R2_SECRET_KEY",
    "GEMINI_API_KEY", "OPENAI_API_KEY",
    "EVO_HMAC_SECRET", "EVO_API_SECRET", "EVO_MASTER_KEY",
}


def _get_fernet() -> Fernet:
    key = os.getenv("EVO_ENCRYPTION_KEY", "")
    if not key:
        # В dev: генерируем детерминированный ключ из HMAC secret
        hmac_secret = os.getenv("EVO_HMAC_SECRET", "dev_key_32_chars_minimum_here!!")
        import hashlib, base64
        derived = base64.urlsafe_b64encode(
            hashlib.sha256(hmac_secret.encode()).digest()
        )
        return Fernet(derived)
    if len(key) < 32:
        raise ValueError("EVO_ENCRYPTION_KEY должен быть >= 32 символов")
    derived = base64.urlsafe_b64encode(
        key.encode()[:32].ljust(32, b'=')
    )
    return Fernet(derived)


def encrypt_value(value: str) -> str:
    """Шифрует значение для хранения в БД."""
    f = _get_fernet()
    return f.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Расшифровывает значение из БД."""
    f = _get_fernet()
    return f.decrypt(encrypted.encode()).decode()


def is_sensitive(key: str) -> bool:
    return key.upper() in SENSITIVE_KEYS or any(
        s in key.upper() for s in ["TOKEN", "SECRET", "KEY", "PASSWORD", "PRIVATE"]
    )


def mask_value(key: str, value: str) -> str:
    """Маскирует значение для логов — никогда не пишем секреты в лог."""
    if is_sensitive(key):
        return value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
    return value
