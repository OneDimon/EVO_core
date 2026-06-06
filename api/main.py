"""EVO-core API — точка входа FastAPI."""
import logging, os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import handshake, concierge, query, step_done, result, hook_reply

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

app = FastAPI(title="EVO-core API", version="0.1.0-phase0")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
    allow_methods=["*"], allow_headers=["*"])

app.include_router(handshake.router, prefix="/api/v1")
app.include_router(concierge.router, prefix="/api/v1")
app.include_router(query.router,     prefix="/api/v1")
app.include_router(step_done.router, prefix="/api/v1")
app.include_router(result.router,    prefix="/api/v1")
app.include_router(hook_reply.router,prefix="/api/v1")

@app.get("/health")
async def health():
    return {"status": "ok", "phase": "0"}

@app.get("/")
async def root():
    return {"evo": "core", "version": "0.1.0-phase0",
            "docs": "Read PROJECT_MAP.md first"}
