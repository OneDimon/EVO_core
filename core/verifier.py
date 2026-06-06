"""
YMS-MMM Verifier — БЛОК 06, Фаза 1
Полная сверка выданного картриджа vs применённого флагманом.
Правила: SCL_FRACTAL_PROTOCOL.md раздел 11, BLOCK_06_ymm_verifier.md
"""
import logging, json
from pydantic import BaseModel
from typing import Optional
from core.ai_router import ai_router
from db.redis_client import get_redis

log = logging.getLogger("evo.verifier")

class VerifyRequest(BaseModel):
    session_id: str
    output: str
    original_tz: str
    cartridge: dict
    applied_stack: list[str] = []
    solution_quality: str        # "ideal" | "adapted" | "gap_filled"
    deviations: Optional[str] = None
    workability_confirmed: bool
    workability_proof: str = ""

class VerificationResult(BaseModel):
    session_id: str
    passed: bool
    score: float
    action: str                  # "record_confirmation"|"analyze_delta"|"record_new_knowledge"|"fix"|"reanimate"
    failures: list[str] = []
    delta_type: Optional[str] = None   # "A" | "B"
    fix_directive: Optional[str] = None


FAIL_COUNTER_TTL = 3600  # 1 час


async def _get_fail_count(session_id: str) -> int:
    r = await get_redis()
    val = await r.get(f"evo:fails:{session_id}")
    return int(val) if val else 0


async def _increment_fail(session_id: str):
    r = await get_redis()
    key = f"evo:fails:{session_id}"
    await r.incr(key)
    await r.expire(key, FAIL_COUNTER_TTL)


async def _reset_fails(session_id: str):
    r = await get_redis()
    await r.delete(f"evo:fails:{session_id}")


async def verify(req: VerifyRequest) -> VerificationResult:
    """
    Полная верификация по чеклисту YMS-MMM.
    Шаг 1: workability — физическая проверка.
    Шаг 2: чеклист из 8 пунктов через AI Router.
    Шаг 3: маршрутизация по solution_quality.
    """
    failures = []

    # ── Шаг 1: workability ──────────────────────────────────────────
    if not req.workability_confirmed:
        failures.append("workability_confirmed = false — физическая проверка не пройдена")
        await _increment_fail(req.session_id)
        return await _fail_result(req, failures)

    # ── Шаг 2: чеклист YMS-MMM через AI Router ──────────────────────
    yms_result = await ai_router.verify(req.output, str(req.cartridge))
    if not yms_result.get("passed", False):
        failures.extend(yms_result.get("failures", ["yms_check_failed"]))
        await _increment_fail(req.session_id)
        return await _fail_result(req, failures)

    score = yms_result.get("score", 1.0)

    # ── Шаг 3: маршрутизация по solution_quality ────────────────────
    await _reset_fails(req.session_id)

    if req.solution_quality == "ideal":
        return VerificationResult(
            session_id=req.session_id, passed=True, score=score,
            action="record_confirmation"
        )

    elif req.solution_quality == "adapted":
        # Определяем Тип А или Тип Б через AI Router
        delta_raw = await ai_router.classify(
            f"original: {req.cartridge.get('instructions', '')} | "
            f"applied: {req.output[:300]} | deviations: {req.deviations}",
            "type_ab"
        )
        delta_type = "A" if "A" in delta_raw.upper() else "B"
        return VerificationResult(
            session_id=req.session_id, passed=True, score=score,
            action="analyze_delta", delta_type=delta_type
        )

    else:  # gap_filled
        return VerificationResult(
            session_id=req.session_id, passed=True, score=score,
            action="record_new_knowledge"
        )


async def _fail_result(req: VerifyRequest, failures: list[str]) -> VerificationResult:
    """Обработка провала — 1-2 раза: fix_directive, 3+ раза: reanimate."""
    count = await _get_fail_count(req.session_id)
    log.warning(f"[YMS-MMM] Fail #{count} session={req.session_id}: {failures}")

    if count >= 3:
        return VerificationResult(
            session_id=req.session_id, passed=False, score=0.0,
            action="reanimate", failures=failures,
            fix_directive="Активирован реаниматор БЛОК 07"
        )

    directive = (
        f"Исправить: {'; '.join(failures[:3])}. "
        "Проверь работоспособность реальным запуском (200 OK / зелёные тесты)."
    )
    return VerificationResult(
        session_id=req.session_id, passed=False, score=0.0,
        action="fix", failures=failures, fix_directive=directive
    )
