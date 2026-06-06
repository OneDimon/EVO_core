"""POST /api/v1/patch_callback — реаниматор возвращает патч флагману."""
from fastapi import APIRouter
from pydantic import BaseModel
from core.immune_system import patch_callback as get_patch

router = APIRouter()

class PatchCallbackReq(BaseModel):
    session_id: str

@router.post("/patch_callback")
async def patch_callback(req: PatchCallbackReq):
    return await get_patch(req.session_id)
