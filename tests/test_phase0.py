"""
Тесты Фазы 0 — проверка полного цикла:
запрос флагмана → консьерж → поиск → выдача картриджа → step_done

Запуск: python tests/test_phase0.py
Требует: запущенный API (uvicorn api.main:app)
"""
import asyncio, httpx, json, sys

BASE = "http://localhost:8000/api/v1"

async def run_tests():
    async with httpx.AsyncClient() as client:
        print("\n=== EVO-core Phase 0 Tests ===\n")
        errors = []

        # TEST 1: Health check
        r = await client.get("http://localhost:8000/health")
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} [T1] Health check")
        if not ok: errors.append("T1")

        # TEST 2: Handshake
        r = await client.post(f"{BASE}/handshake",
            json={"flagship_id": "claude-sonnet", "ready": True})
        ok = r.status_code == 200 and "session_id" in r.json()
        session_id = r.json().get("session_id", "test-session")
        print(f"{'✅' if ok else '❌'} [T2] Handshake → session_id: {session_id[:8]}...")
        if not ok: errors.append("T2")

        # TEST 3: Concierge — первый запрос
        r = await client.post(f"{BASE}/concierge", json={
            "session_id": session_id,
            "user_request": "Настроить авторизацию ZennoPoster для HSR"
        })
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} [T3] Concierge questions: {r.json().get('status')}")
        if not ok: errors.append("T3")

        # TEST 4: Concierge — ответы флагмана
        r = await client.post(f"{BASE}/concierge", json={
            "session_id": session_id,
            "user_request": "Настроить авторизацию ZennoPoster для HSR",
            "concierge_answers": {
                "task_type": "new",
                "detected_stack": ["zennoposter", "n8n"],
                "constraints": [],
                "project_type": "automation",
                "new_project": True
            }
        })
        ok = r.status_code == 200 and r.json().get("status") == "context_accepted"
        print(f"{'✅' if ok else '❌'} [T4] Concierge context accepted")
        if not ok: errors.append("T4")

        # TEST 5: Query — поиск картриджа
        r = await client.post(f"{BASE}/query", json={
            "session_id": session_id,
            "user_request": "Настроить авторизацию ZennoPoster для Honkai Star Rail",
            "flagship_plan": [
                "Настроить cookie manager в ZennoPoster",
                "Сохранить сессию после авторизации",
                "Верифицировать через n8n webhook"
            ],
            "context": {
                "detected_stack": ["zennoposter", "n8n"],
                "project_type": "automation"
            }
        })
        ok = r.status_code == 200 and "scenario" in r.json()
        scenario = r.json().get("scenario", "unknown")
        print(f"{'✅' if ok else '❌'} [T5] Query → scenario: {scenario}")
        if not ok: errors.append("T5")

        # TEST 6: Step done — раскрытие шага
        r = await client.post(f"{BASE}/step_done", json={
            "session_id": session_id,
            "step_completed": 1,
            "step_result": "success",
            "next_step_requested": 2
        })
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} [T6] Step done → {r.json().get('status')}")
        if not ok: errors.append("T6")

        # TEST 7: Result — workability = false → rejected
        r = await client.post(f"{BASE}/result", json={
            "session_id": session_id,
            "status": "completed",
            "result": "Авторизация настроена",
            "workability_confirmed": False,
            "workability_proof": "",
            "solution_quality": "ideal",
            "applied_stack": ["zennoposter"]
        })
        ok = r.status_code == 200 and r.json().get("status") == "failed"
        print(f"{'✅' if ok else '❌'} [T7] Result workability=false → rejected")
        if not ok: errors.append("T7")

        # TEST 8: Result — workability = true → verified
        r = await client.post(f"{BASE}/result", json={
            "session_id": session_id,
            "status": "completed",
            "result": "Авторизация ZennoPoster HSR настроена через cookie manager",
            "workability_confirmed": True,
            "workability_proof": "HTTP 200 OK on ZP test run",
            "solution_quality": "ideal",
            "applied_stack": ["zennoposter", "n8n"]
        })
        ok = r.status_code == 200 and r.json().get("status") == "verified"
        print(f"{'✅' if ok else '❌'} [T8] Result workability=true → verified + hook_query")
        if not ok: errors.append("T8")

        # TEST 9: Hook reply — no update
        r = await client.post(f"{BASE}/hook_reply", json={
            "session_id": session_id,
            "has_update": False
        })
        ok = r.status_code == 200 and r.json().get("status") == "session_complete"
        print(f"{'✅' if ok else '❌'} [T9] Hook reply no_update → session_complete")
        if not ok: errors.append("T9")

        # ИТОГ
        total = 9
        passed = total - len(errors)
        print(f"\n{'='*40}")
        print(f"Phase 0 Tests: {passed}/{total} passed")
        if errors:
            print(f"Failed: {errors}")
        else:
            print("✅ ALL TESTS PASSED — Phase 0 READY")
        print('='*40)
        return len(errors) == 0

if __name__ == "__main__":
    result = asyncio.run(run_tests())
    sys.exit(0 if result else 1)
