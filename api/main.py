"""EVO-core API v0.3 — Фаза 2 (все блоки подключены)."""
import logging, asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.middleware.security import EVOSecurityMiddleware, check_required_secrets
from api.routes import (handshake, concierge, query, step_done,
                         result, hook_reply, admin, patch_callback, mcp)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

app = FastAPI(title="EVO-core API", version="0.3.0-phase2")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])
app.add_middleware(EVOSecurityMiddleware)

for r in [handshake, concierge, query, step_done, result,
          hook_reply, admin, patch_callback, mcp]:
    app.include_router(r.router, prefix="/api/v1")

@app.on_event("startup")
async def startup():
    check_required_secrets()  # блокирует если секреты не заданы
    from core.config_manager import init_config_table
    await init_config_table()
    # Запускаем планировщик СОН
    asyncio.create_task(_sleep_scheduler())
    logging.getLogger("evo").info("EVO-core Phase 2 started")

async def _sleep_scheduler():
    """Каждые сутки пересчитывает окно СОН и входит в него."""
    import asyncio
    from core.sleep_mode import calculate_sleep_window, enter_sleep
    from datetime import datetime, timezone
    while True:
        now = datetime.now(timezone.utc)
        sleep_hour = await calculate_sleep_window()
        if now.hour == sleep_hour:
            await enter_sleep()
            await asyncio.sleep(3600)   # 1 час сна
        else:
            await asyncio.sleep(300)    # проверка каждые 5 мин

@app.get("/health")
async def health():
    return {"status": "ok", "phase": "2",
            "blocks": {"01":"active","02":"active","03":"active",
                       "06":"active","07":"active","sleep":"scheduled"}}
