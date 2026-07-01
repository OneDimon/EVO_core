"""
Тесты реального round-trip через shard_client (не только zstd_codec напрямую).
Проверяет: write_cell → путь провайдера local → read_cell_local → байт-в-байт совпадение.
Провайдер SHARD_PROVIDER=local не требует внешних сервисов — тест самодостаточен.

Запуск: python tests/test_shard_roundtrip.py
Требует: доступную БД (write_cell с symbol_id пишет shard_link в pgvector) —
если symbol_id не передан, обращения к БД не будет, тест можно гонять офлайн.
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shards.shard_client import write_cell, read_cell_local, _validate_path

async def run_tests():
    print("\n=== Shard round-trip tests ===\n")
    errors = []

    # T1: write_cell (без symbol_id — не трогает БД) → read_cell_local байт-в-байт
    try:
        content = "Инструкция: [[EVO:τ^{auto}_{zp_0047} | тест шарда]]\nтело решения с юникодом ЖЖ"
        path = "/evo/TEST/roundtrip_0001.zst"
        written_path = await write_cell(host="", path=path, content=content, symbol_id="")
        restored, links = await read_cell_local(written_path)
        ok = restored == content
        print(f"{'✅' if ok else '❌'} [T1] write_cell → read_cell_local byte-exact")
        if not ok:
            errors.append("T1")
            print(f"    ожидалось: {content!r}")
            print(f"    получено:  {restored!r}")
    except Exception as e:
        errors.append("T1")
        print(f"❌ [T1] Exception: {e}")

    # T2: гиперссылки восстанавливаются вместе с содержимым при чтении с шарда
    try:
        ok = len(links) == 1 and links[0]["symbol_id"] == "τ^{auto}_{zp_0047}"
        print(f"{'✅' if ok else '❌'} [T2] Hyperlinks parsed on read: {links}")
        if not ok: errors.append("T2")
    except Exception as e:
        errors.append("T2")
        print(f"❌ [T2] Exception: {e}")

    # T3: путь без /evo/ префикса отклоняется (защита path traversal)
    try:
        blocked = False
        try:
            _validate_path("/etc/passwd")
        except ValueError:
            blocked = True
        print(f"{'✅' if blocked else '❌'} [T3] Path outside /evo/ blocked")
        if not blocked: errors.append("T3")
    except Exception as e:
        errors.append("T3")
        print(f"❌ [T3] Exception: {e}")

    # T4: path traversal через .. отклоняется даже если начинается с /evo/
    try:
        blocked = False
        try:
            _validate_path("/evo/../../etc/passwd")
        except ValueError:
            blocked = True
        print(f"{'✅' if blocked else '❌'} [T4] /evo/../../ traversal blocked")
        if not blocked: errors.append("T4")
    except Exception as e:
        errors.append("T4")
        print(f"❌ [T4] Exception: {e}")

    # T5: чтение несуществующего пути не падает, возвращает пустое
    try:
        content2, links2 = await read_cell_local("/evo/TEST/does_not_exist_0099.zst")
        ok = content2 == "" and links2 == []
        print(f"{'✅' if ok else '❌'} [T5] Missing shard → empty, no exception")
        if not ok: errors.append("T5")
    except Exception as e:
        errors.append("T5")
        print(f"❌ [T5] Exception (should not raise): {e}")

    # T6: реальное сжатие — записанные байты меньше исходного текста для длинного контента
    try:
        long_content = ("Повторяющийся текст решения. " * 50) + "[[EVO:τ^{x}_{y_0001} | ссылка]]"
        path6 = "/evo/TEST/compression_0002.zst"
        await write_cell(host="", path=path6, content=long_content, symbol_id="")
        import os as _os
        full = f"/tmp/evo_shards{path6}"
        compressed_size = _os.path.getsize(full)
        ok = compressed_size < len(long_content.encode())
        print(f"{'✅' if ok else '❌'} [T6] Реальное сжатие: "
              f"{len(long_content.encode())}b → {compressed_size}b")
        if not ok: errors.append("T6")
    except Exception as e:
        errors.append("T6")
        print(f"❌ [T6] Exception: {e}")

    total = 6
    passed = total - len(errors)
    print(f"\n{'='*40}")
    print(f"Shard round-trip: {passed}/{total} passed")
    if errors:
        print(f"Failed: {errors}")
    else:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ — сжатие/распаковка/защита путей работают")
    print('='*40)
    return len(errors) == 0

if __name__ == "__main__":
    ok = asyncio.run(run_tests())
    sys.exit(0 if ok else 1)
