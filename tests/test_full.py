"""
Финальные интеграционные тесты — полный стек EVO-core.
Фаза 0 + Фаза 1 + Безопасность + Admin + TG + MCP + CLI
Запуск: EVO_ENV=development python tests/test_full.py
"""
import asyncio, httpx, sys, os, json

BASE = "http://localhost:8000/api/v1"
ADMIN_TOKEN = os.getenv("EVO_API_SECRET", "dev_admin_secret")

async def run():
    async with httpx.AsyncClient(timeout=30) as c:
        results = {}
        session_id = None

        # ── БЛОК 01: API Core ──────────────────────────────────────────────
        print("\n=== БЛОК 01: Core Engine ===")

        # T01: Health
        r = await c.get("http://localhost:8000/health")
        results["T01_health"] = r.status_code == 200
        print(f"  {'✅' if results['T01_health'] else '❌'} T01 Health: {r.json().get('phase','?')}")

        # T02: Handshake → session
        r = await c.post(f"{BASE}/handshake", json={"flagship_id":"test","ready":True})
        results["T02_handshake"] = "session_id" in r.json() and "hmac_key" in r.json()
        session_id = r.json().get("session_id","test-001")
        print(f"  {'✅' if results['T02_handshake'] else '❌'} T02 Handshake: session={session_id[:8]}...")

        # T03: Concierge
        r = await c.post(f"{BASE}/concierge",
            json={"session_id":session_id,"user_request":"тест"})
        results["T03_concierge"] = r.status_code == 200
        print(f"  {'✅' if results['T03_concierge'] else '❌'} T03 Concierge: {r.json().get('status')}")

        # T04: Query
        r = await c.post(f"{BASE}/query", json={
            "session_id": session_id,
            "user_request": "Настроить авторизацию ZennoPoster",
            "flagship_plan": ["Шаг 1: cookie manager", "Шаг 2: сохранить сессию"],
            "context": {"detected_stack": ["zennoposter","python"]}
        })
        results["T04_query"] = r.status_code == 200 and "scenario" in r.json()
        scenario = r.json().get("scenario","?")
        print(f"  {'✅' if results['T04_query'] else '❌'} T04 Query: scenario={scenario}")

        # T05: Step done
        r = await c.post(f"{BASE}/step_done", json={
            "session_id": session_id, "step_completed": 1,
            "step_result": "success", "next_step_requested": 2
        })
        results["T05_step_done"] = r.status_code == 200
        print(f"  {'✅' if results['T05_step_done'] else '❌'} T05 Step done: {r.json().get('status')}")

        # ── БЛОК 06: YMS-MMM ──────────────────────────────────────────────
        print("\n=== БЛОК 06: YMS-MMM + Obsidian ===")

        # T06: Result workability=false → reject
        # original_tz обязателен (P9 fix) — без него 422, а не "failed"
        r = await c.post(f"{BASE}/result", json={
            "session_id": session_id, "status": "completed",
            "result": "тест", "workability_confirmed": False,
            "workability_proof": "", "solution_quality": "ideal",
            "applied_stack": ["python"], "original_tz": "тестовое задание"
        })
        results["T06_workability_reject"] = r.json().get("status") == "failed"
        print(f"  {'✅' if results['T06_workability_reject'] else '❌'} T06 Workability=false → rejected")

        # T07: Result ideal → verified
        r = await c.post(f"{BASE}/result", json={
            "session_id": session_id+"_v", "status": "completed",
            "result": "Авторизация ZennoPoster настроена через cookie manager",
            "workability_confirmed": True, "workability_proof": "HTTP 200 OK",
            "solution_quality": "ideal", "applied_stack": ["zennoposter","python"],
            "original_tz": "Настроить авторизацию ZennoPoster",
            "cartridge": {"instructions": {"step_1": {"symbol_id": "test_sym"}}}
        })
        results["T07_yms_ideal"] = r.json().get("status") == "verified"
        print(f"  {'✅' if results['T07_yms_ideal'] else '❌'} T07 YMS ideal → {r.json().get('status')}")

        # T08: Adapted solution
        r = await c.post(f"{BASE}/result", json={
            "session_id": session_id+"_adapted", "status": "completed",
            "result": "Решение адаптировано под Selenium вместо ZennoPoster",
            "workability_confirmed": True, "workability_proof": "tests passed",
            "solution_quality": "adapted",
            "deviations": "Selenium вместо ZennoPoster — другой инструмент",
            "applied_stack": ["python","selenium"], "original_tz": "авторизация",
            "cartridge": {}
        })
        results["T08_adapted"] = r.status_code == 200
        print(f"  {'✅' if results['T08_adapted'] else '❌'} T08 Adapted → {r.json().get('action')}")

        # T09: Hook reply
        r = await c.post(f"{BASE}/hook_reply", json={
            "session_id": session_id, "has_update": False
        })
        results["T09_hook"] = r.json().get("status") == "session_complete"
        print(f"  {'✅' if results['T09_hook'] else '❌'} T09 Hook no_update → {r.json().get('status')}")

        # ── БЛОК 05: MCP ──────────────────────────────────────────────────
        print("\n=== БЛОК 05: MCP Server ===")

        # T10: MCP list_methods
        r = await c.post(f"{BASE}/mcp", json={
            "jsonrpc":"2.0","method":"system.list_methods","params":{},"id":"1"
        })
        methods = r.json().get("result",{}).get("methods",[])
        results["T10_mcp"] = len(methods) > 0
        print(f"  {'✅' if results['T10_mcp'] else '❌'} T10 MCP methods: {methods}")

        # T11: MCP unknown method → error
        r = await c.post(f"{BASE}/mcp", json={
            "jsonrpc":"2.0","method":"nonexistent.method","params":{},"id":"2"
        })
        results["T11_mcp_error"] = r.json().get("error") is not None
        print(f"  {'✅' if results['T11_mcp_error'] else '❌'} T11 MCP unknown → error code")

        # ── Admin API + Security ────────────────────────────────────────────
        print("\n=== Admin API + Security ===")

        # T12: Admin without token → 403
        r = await c.get(f"{BASE}/admin/config")
        results["T12_admin_notoken"] = r.status_code == 403
        print(f"  {'✅' if results['T12_admin_notoken'] else '❌'} T12 Admin no token → {r.status_code}")

        # T13: Admin with token → 200
        r = await c.get(f"{BASE}/admin/config",
            headers={"X-Admin-Token": ADMIN_TOKEN})
        results["T13_admin_auth"] = r.status_code == 200
        print(f"  {'✅' if results['T13_admin_auth'] else '❌'} T13 Admin auth → {r.status_code}")

        # T14: Config set + get
        r = await c.post(f"{BASE}/admin/config",
            headers={"X-Admin-Token": ADMIN_TOKEN},
            json={"key":"OLLAMA_HOST","value":"http://localhost:11434"})
        results["T14_config_set"] = r.json().get("status") == "ok"
        print(f"  {'✅' if results['T14_config_set'] else '❌'} T14 Config set OLLAMA_HOST")

        # T15: Shard test
        r = await c.get(f"{BASE}/admin/shards/test",
            headers={"X-Admin-Token": ADMIN_TOKEN})
        results["T15_shard_test"] = r.status_code == 200
        print(f"  {'✅' if results['T15_shard_test'] else '❌'} T15 Shard test → {r.json().get('status')}")

        # ── БЛОК 04: CLI ──────────────────────────────────────────────────
        print("\n=== БЛОК 04: CLI Layer ===")

        # T16: Skeletonize python
        try:
            sys.path.insert(0, os.getcwd())
            from core.cli_layer import skeletonize_python, detect_stack_from_project
            sample = '''
import os
class AuthService:
    """Handles authentication."""
    def __init__(self, db):
        self.db = db
    async def login(self, user: str, password: str) -> dict:
        """Login user and return token."""
        token = await self.db.get_token(user)
        if not token:
            for i in range(10):
                token = generate_token()
                store = await self.db.save(token)
        return {"token": token, "user": user}
'''
            skeleton = skeletonize_python(sample)
            # Должен сохранить сигнатуры но убрать тела
            has_class = "AuthService" in skeleton
            has_method = "login" in skeleton
            no_loop = "for i in range" not in skeleton
            results["T16_cli_skeleton"] = has_class and has_method and no_loop
            print(f"  {'✅' if results['T16_cli_skeleton'] else '❌'} T16 CLI skeleton "
                  f"(class={has_class}, method={has_method}, no_loop={no_loop})")
        except Exception as e:
            results["T16_cli_skeleton"] = False
            print(f"  ❌ T16 CLI skeleton error: {e}")

        # T17: Detect stack
        try:
            stack_info = detect_stack_from_project(".")
            results["T17_detect_stack"] = "detected_stack" in stack_info
            print(f"  {'✅' if results['T17_detect_stack'] else '❌'} T17 Detect stack: {stack_info.get('detected_stack',[])[:4]}")
        except Exception as e:
            results["T17_detect_stack"] = False
            print(f"  ❌ T17 Detect stack error: {e}")

        # ── zstd codec ────────────────────────────────────────────────────
        print("\n=== БЛОК 03: Shard + zstd ===")

        # T18: zstd roundtrip
        try:
            from shards.zstd_codec import compress, decompress, parse_hyperlinks
            original = "Инструкция: [[EVO:τ^{auto}_{zp_0047} | авторизация ZP]] готово"
            compressed = compress(original)
            restored = decompress(compressed)
            results["T18_zstd"] = restored == original and len(compressed) < len(original.encode())
            print(f"  {'✅' if results['T18_zstd'] else '❌'} T18 zstd roundtrip "
                  f"({len(original.encode())}→{len(compressed)} bytes)")
        except Exception as e:
            results["T18_zstd"] = False
            print(f"  ❌ T18 zstd: {e}")

        # T19: Hyperlink parsing
        try:
            links = parse_hyperlinks(original)
            results["T19_hyperlinks"] = (len(links) == 1 and
                links[0]["symbol_id"] == "τ^{auto}_{zp_0047}" and
                links[0]["description"] == "авторизация ZP")
            print(f"  {'✅' if results['T19_hyperlinks'] else '❌'} T19 Hyperlinks: {links}")
        except Exception as e:
            results["T19_hyperlinks"] = False
            print(f"  ❌ T19 hyperlinks: {e}")

        # T20: Path traversal protection
        try:
            from shards.shard_client import _validate_path
            safe = _validate_path("/evo/TAU/auto/zp/0047.zst")
            blocked = False
            try:
                _validate_path("/evo/../etc/passwd")
            except ValueError:
                blocked = True
            results["T20_path_traversal"] = safe == "/evo/TAU/auto/zp/0047.zst" and blocked
            print(f"  {'✅' if results['T20_path_traversal'] else '❌'} T20 Path traversal protection")
        except Exception as e:
            results["T20_path_traversal"] = False
            print(f"  ❌ T20 path traversal: {e}")

        # ── Итог ─────────────────────────────────────────────────────────
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        failed = [k for k,v in results.items() if not v]

        print(f"\n{'='*50}")
        print(f"ИТОГ: {passed}/{total} тестов пройдено")
        if failed:
            print(f"Провалились: {failed}")
        else:
            print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ — система готова")
        print('='*50)
        return len(failed) == 0

if __name__ == "__main__":
    ok = asyncio.run(run())
    sys.exit(0 if ok else 1)
