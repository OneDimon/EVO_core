"""Проверка готовности базы к продакшну."""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.pg_client import get_pool

async def check():
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM scl_symbols")
        by_science = await conn.fetch(
            "SELECT science, COUNT(*) FROM scl_symbols GROUP BY science ORDER BY COUNT DESC"
        )
    print(f"Total symbols: {total}")
    for row in by_science:
        print(f"  {row['science']}: {row['count']}")
    ready = total >= 8
    print(f"\nReady for Phase 0: {'✅ YES' if ready else '❌ NO (need >= 8 symbols)'}")
    return ready

if __name__ == "__main__":
    asyncio.run(check())
