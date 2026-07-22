"""POST /api/v1/patch_callback — реаниматор возвращает патч флагману."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from core.immune_system import patch_callback as get_patch
from core.signature import verify_request, sign_response

router = APIRouter()

class PatchCallbackReq(BaseModel):
    session_id: str
    evo_signature: Optional[str] = None

@router.post("/patch_callback")
async def patch_callback(req: PatchCallbackReq):
    if not await verify_request(req.model_dump(), req.session_id):
        raise HTTPException(401, "invalid_evo_signature")
    result = await get_patch(req.session_id)
    return await sign_response(result, req.session_id)
