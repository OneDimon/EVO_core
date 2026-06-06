"""EVO-core API v0.2 — Фаза 1."""
import logging, asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import (handshake, concierge, query,
                         step_done, result, hook_reply, admin)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

app = FastAPI(title="EVO-core API", version="0.2.0-phase1")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])

for r in [handshake, concierge, query, step_done, result, hook_reply, admin]:
    app.include_router(r.router, prefix="/api/v1")

@app.on_event("startup")
async def startup():
    from core.config_manager import init_config_table
    await init_config_table()
    logging.getLogger("evo").info("EVO-core Phase 1 started")

@app.get("/health")
async def health():
    return {"status": "ok", "phase": "1"}
