"""PostgreSQL + pgvector клиент для SCL символов."""
import asyncpg, os, json
from typing import Optional

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.getenv("DATABASE_URL", "postgresql://evo_user:evo_secret@localhost:5432/evo_core"),
            min_size=2, max_size=10
        )
    return _pool

async def find_symbols(query_vector: list[float], top_k: int = 5,
                       stack_filter: list[str] = None,
                       exclude_legacy: bool = True) -> list[dict]:
    """
    Безопасный векторный поиск.
    Вектор передаётся как $1::vector параметр asyncpg — без f-string подстановки в SQL.
    P1 fix: убрана уязвимость .replace("${vec_str}", ...) — теперь полная параметризация.
    """
    pool = await get_pool()
    # Валидация вектора
    if not query_vector or not all(isinstance(x, (int, float)) for x in query_vector):
        return []
    vec_str = "[" + ",".join(f"{float(x):.8f}" for x in query_vector) + "]"

    # $1 = вектор, $2 = top_k, далее опциональные фильтры
    conditions = []
    params: list = [vec_str, top_k]

    if exclude_legacy:
        conditions.append("is_legacy = FALSE")
    if stack_filter:
        params.append(stack_filter)
        conditions.append(f"applicable_stacks && ${len(params)}::text[]")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT *, 1 - (vector <=> $1::vector) AS similarity,
                   (1 - (vector <=> $1::vector)) * log(rating_frequency + 2) AS score
            FROM scl_symbols {where}
            ORDER BY score DESC LIMIT $2
        """, *params)
        return [dict(r) for r in rows]

async def get_symbol(symbol_id: str) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM scl_symbols WHERE id = $1", symbol_id)
        return dict(row) if row else None

async def insert_symbol(s: dict) -> bool:
    pool = await get_pool()
    # Валидация вектора перед вставкой
    raw_vec = s.get('vector', [])
    if not raw_vec or not all(isinstance(x, (int, float)) for x in raw_vec):
        raw_vec = [0.0] * 768  # нулевой вектор как fallback
    vec_str = "[" + ",".join(f"{float(x):.8f}" for x in raw_vec) + "]"
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO scl_symbols
            (id,label,vector,science,section,subsection,confirmed_by,confirmed_in,
             evolved_from,evolution_note,last_updated,shard_host,shard_path,shard_mirror,
             legacy_symbols,applicable_stacks,hyperlinks,is_legacy,superseded_by,
             supersedes,hypothesis,
             source_url,source_rating,source_type,auto_collected,
             version_ts)
            VALUES($1,$2,$3::vector,$4,$5,$6,$7,$8,$9,$10,NOW(),$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,
                   $21,$22,$23,$24,NOW())
            ON CONFLICT (id) DO NOTHING
        """, s['id'], s['label'], vec_str, s['science'], s['section'], s['subsection'],
            s.get('confirmed_by',1), s.get('confirmed_in',[]),
            s.get('evolved_from'), s.get('evolution_note'),
            s.get('shard_host',''), s.get('shard_path',''), s.get('shard_mirror'),
            s.get('legacy_symbols',[]), s.get('applicable_stacks',[]),
            s.get('hyperlinks',[]), s.get('is_legacy',False),
            s.get('superseded_by'), s.get('supersedes'), s.get('hypothesis',False),
            s.get('source_url'), s.get('source_rating',0),
            s.get('source_type'), s.get('auto_collected',False)
        )
    return True

async def increment_rating(symbol_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE scl_symbols SET rating_frequency = rating_frequency + 1,
            last_updated = NOW() WHERE id = $1
        """, symbol_id)

async def update_symbol_type_a(symbol_id: str, new_shard_path: str,
                                evolution_note: str, old_symbol_id: str) -> bool:
    """
    Тип А: перезапись + сохранение старого в legacy_symbols.
    N9 fix: добавлена проверка rowcount. Subquery и WHERE читают version_ts
    в разных snapshot при высокой нагрузке — конкурентный UPDATE мог молча
    применить 0 строк без какой-либо ошибки или предупреждения.
    Возвращает True если обновление реально применилось.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE scl_symbols SET
              shard_path = $2,
              evolution_note = $3,
              legacy_symbols = array_append(legacy_symbols, $4),
              rating_frequency = rating_frequency + 1,
              version_ts = NOW(), last_updated = NOW()
            WHERE id = $1 AND version_ts = (SELECT version_ts FROM scl_symbols WHERE id = $1)
        """, symbol_id, new_shard_path, evolution_note, old_symbol_id)

    # asyncpg.execute() возвращает строку вида "UPDATE 1" или "UPDATE 0"
    applied = result.split()[-1] != "0" if result else False
    if not applied:
        log.warning(
            f"[pg_client] update_symbol_type_a: concurrent update detected "
            f"для {symbol_id} — UPDATE применил 0 строк (version_ts race)"
        )
    return applied
