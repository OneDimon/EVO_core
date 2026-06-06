"""
Bootstrap — первичное наполнение ядра через AI Router.
Запускать: python scripts/bootstrap.py
Наполняет по убыванию востребованности: глобальные → технические → частные.
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ai_router import ai_router
from db.pg_client import insert_symbol, find_symbols, get_pool
from shards.shard_client import write_cell

# Базовые символы для старта (Фаза 0)
BOOTSTRAP_SYMBOLS = [
    {"science":"Технология","section":"Автоматизация","subsection":"n8n",
     "label":"задача: n8n webhook триггер | лекарство: POST node + JSON parse"},
    {"science":"Технология","section":"БД","subsection":"PostgreSQL",
     "label":"задача: async pg pool | лекарство: asyncpg pool min=2 max=10"},
    {"science":"Технология","section":"Автоматизация","subsection":"ZennoPoster",
     "label":"задача: авторизация через куки | лекарство: cookie manager + session save"},
    {"science":"Экономика","section":"Платежи","subsection":"Крипто",
     "label":"задача: крипто-шлюз без KYC | лекарство: TON/USDT прямой перевод"},
    {"science":"Философия","section":"Логика","subsection":"Верификация",
     "label":"задача: проверка истинности утверждения | лекарство: тройное подтверждение"},
    {"science":"Кибернетика","section":"Алгоритмика","subsection":"Поиск",
     "label":"задача: векторный поиск по смыслу | лекарство: cosine similarity pgvector"},
    {"science":"Технология","section":"Инфраструктура","subsection":"Docker",
     "label":"задача: контейнеризация сервиса | лекарство: docker-compose + healthcheck"},
    {"science":"Технология","section":"ИИ","subsection":"Роутинг",
     "label":"задача: fallback между AI моделями | лекарство: цепочка провайдеров с backoff"},
]

async def bootstrap():
    print("=== EVO-core Bootstrap ===")
    pool = await get_pool()

    for i, sym_data in enumerate(BOOTSTRAP_SYMBOLS):
        # Векторизация
        text = f"{sym_data['label']} {sym_data['science']} {sym_data['section']} {sym_data['subsection']}"
        vector = await ai_router.embed(text)

        # Генерация ID
        sci = sym_data['science'][:1]
        sec = sym_data['section'][:4].lower().replace(' ','_')
        sub = sym_data['subsection'][:4].lower()
        num = str(i+1).zfill(4)
        symbol_id = f"{sci}^{{{sec}}}_{{{sub}_{num}}}"

        # Сохранение тела на шард
        shard_path = f"/evo/{sci.upper()}/{symbol_id}.zst"
        await write_cell("", shard_path, sym_data['label'])

        # Запись в pgvector
        await insert_symbol({
            "id": symbol_id,
            "label": sym_data['label'],
            "vector": vector,
            "science": sym_data['science'],
            "section": sym_data['section'],
            "subsection": sym_data['subsection'],
            "applicable_stacks": [],
            "shard_host": "",
            "shard_path": shard_path,
        })
        print(f"  ✓ [{i+1}/{len(BOOTSTRAP_SYMBOLS)}] {symbol_id}: {sym_data['label'][:60]}")

    print(f"\n✅ Bootstrap complete: {len(BOOTSTRAP_SYMBOLS)} symbols")
    await pool.close()

if __name__ == "__main__":
    asyncio.run(bootstrap())
