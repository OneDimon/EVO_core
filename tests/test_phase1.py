"""
Тесты Фазы 1+2: YMS-MMM, Obsidian, Immune, MCP, CLI, Admin
Запуск: python tests/test_phase1.py
"""
import asyncio, httpx, sys

BASE = "http://localhost:8000/api/v1"
ADMIN_TOKEN = "dev_admin_secret"

async def run_tests():
    async with httpx.AsyncClient(timeout=30) as client:
        print("\n=== EVO-core Phase 1+2 Tests ===\n")
        errors = []

        r = await client.post(f"{BASE}/handshake",
            json={"flagship_id": "test", "ready": True})
        session_id = r.json().get("session_id", "test-001")

        # T1: Admin config set
        r = await client.post(f"{BASE}/admin/config",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"key": "SHARD_PROVIDER", "value": "local"})
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} [T1] Admin config set")
        if not ok: errors.append("T1")

        # T2: Admin config get
        r = await client.get(f"{BASE}/admin/config",
            headers={"X-Admin-Token": ADMIN_TOKEN})
        ok = r.status_code == 200 and "config" in r.json()
        print(f"{'✅' if ok else '❌'} [T2] Admin config get")
        if not ok: errors.append("T2")

        # T3: Shard test
        r = await client.get(f"{BASE}/admin/shards/test",
            headers={"X-Admin-Token": ADMIN_TOKEN})
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} [T3] Shard test → {r.json().get('status')}")
        if not ok: errors.append("T3")

        # T4: YMS-MMM ideal
        r = await client.post(f"{BASE}/result", json={
            "session_id": session_id, "status": "completed",
            "result": "Задача выполнена", "workability_confirmed": True,
            "workability_proof": "HTTP 200 OK", "solution_quality": "ideal",
            "applied_stack": ["python"], "original_tz": "Тест",
            "cartridge": {"instructions": {"step_1": {"symbol_id": "test"}}}
        })
        ok = r.status_code == 200 and r.json().get("status") == "verified"
        print(f"{'✅' if ok else '❌'} [T4] YMS-MMM ideal → {r.json().get('status')}")
        if not ok: errors.append("T4")

        # T5: YMS-MMM adapted
        r = await client.post(f"{BASE}/result", json={
            "session_id": session_id+"_a", "status": "completed",
            "result": "Flask вместо FastAPI", "workability_confirmed": True,
            "workability_proof": "OK", "solution_quality": "adapted",
            "deviations": "Flask вместо FastAPI", "applied_stack": ["flask"],
            "original_tz": "API", "cartridge": {}
        })
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} [T5] YMS-MMM adapted → {r.json().get('action')}")
        if not ok: errors.append("T5")

        # T6: Gap filled
        r = await client.post(f"{BASE}/result", json={
            "session_id": session_id+"_g", "status": "completed",
            "result": "WebSocket решение", "workability_confirmed": True,
            "workability_proof": "ws OK", "solution_quality": "gap_filled",
            "applied_stack": ["websockets"], "original_tz": "real-time",
            "cartridge": {}
        })
        ok = r.status_code == 200
        print(f"{'✅' if ok else '❌'} [T6] gap_filled → {r.json().get('action')}")
        if not ok: errors.append("T6")

        # T7: MCP list_methods
        r = await client.post(f"{BASE}/mcp", json={
            "jsonrpc": "2.0", "method": "system.list_methods", "params": {}, "id": "1"
        })
        ok = r.status_code == 200 and "methods" in r.json().get("result", {})
        print(f"{'✅' if ok else '❌'} [T7] MCP list_methods")
        if not ok: errors.append("T7")

        # T8: CLI skeletonize
        try:
            import sys as _sys, os
            _sys.path.insert(0, os.getcwd())
            from core.cli_layer import skeletonize_python
            sample = 'def foo(x):\n    """doc"""\n    return x * 2\n'
            sk = skeletonize_python(sample)
            ok = "foo" in sk
            print(f"{'✅' if ok else '❌'} [T8] CLI skeletonize")
        except Exception as e:
            print(f"❌ [T8] CLI: {e}")
            errors.append("T8")

        # T9: Hook with update
        r = await client.post(f"{BASE}/hook_reply", json={
            "session_id": session_id, "has_update": True,
            "update_description": "FastAPI 0.115 вышел",
            "compatible_with_current_stack": True, "migration_scope": "none"
        })
        ok = r.status_code == 200 and r.json().get("status") == "update_recorded"
        print(f"{'✅' if ok else '❌'} [T9] Hook update → {r.json().get('status')}")
        if not ok: errors.append("T9")

        passed = 9 - len(errors)
        print(f"\n{'='*40}")
        print(f"Phase 1+2: {passed}/9 passed")
        if not errors: print("✅ ALL PASSED — Phase 1+2 READY")
        else: print(f"Failed: {errors}")
        return len(errors) == 0

if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run_tests()) else 1)
