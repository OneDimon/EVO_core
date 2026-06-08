"""EVO-core API v0.3 — Фаза 2 (все блоки подключены)."""
import logging, asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.middleware.security import EVOSecurityMiddleware, check_required_secrets
from api.routes import (handshake, concierge, query, step_done,
                         result, hook_reply, admin, patch_callback, mcp, tg_webhook)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

app = FastAPI(title="EVO-core API", version="0.3.0-phase2")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])
app.add_middleware(EVOSecurityMiddleware)

for r in [handshake, concierge, query, step_done, result,
          hook_reply, admin, patch_callback, mcp, tg_webhook]:
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
    """APScheduler: пересчитывает окно СОН и запускает фоновые задачи."""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from core.sleep_mode import calculate_sleep_window, enter_sleep
        scheduler = AsyncIOScheduler()

        async def check_sleep():
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            sleep_hour = await calculate_sleep_window()
            if now.hour == sleep_hour:
                await enter_sleep()

        scheduler.add_job(check_sleep, 'interval', minutes=5, id='sleep_check')
        scheduler.start()
        logging.getLogger("evo").info("APScheduler started")
    except ImportError:
        # Fallback если apscheduler не установлен
        import asyncio
        from core.sleep_mode import calculate_sleep_window, enter_sleep
        from datetime import datetime, timezone
        while True:
            now = datetime.now(timezone.utc)
            sleep_hour = await calculate_sleep_window()
            if now.hour == sleep_hour:
                await enter_sleep()
                await asyncio.sleep(3600)
            else:
                await asyncio.sleep(300)

@app.get("/admin", include_in_schema=False)
async def admin_ui():
    """Admin UI — визуальная панель управления."""
    from fastapi.responses import FileResponse
    import os
    ui_path = os.path.join(os.path.dirname(__file__), '..', 'admin_ui.html')
    if os.path.exists(ui_path):
        return FileResponse(ui_path)
    return {"error": "admin_ui.html not found"}

@app.get("/health")
async def health():
    return {"status": "ok", "phase": "2",
            "blocks": {"01":"active","02":"active","03":"active",
                       "06":"active","07":"active","sleep":"scheduled"}}
