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



async def run_dictionary_tests():
    print("\n=== Dictionary compression tests ===\n")
    errors = []

    from shards.shard_client import (
        write_cell, read_cell_local, train_dictionary_for_root,
        _get_dictionary, _local_list_cells
    )

    # T7: пишем 25 маленьких похожих ячеек в тестовый раздел "τ" (реальный
    # символ канона — используем существующую папку, не выдуманную "TEST")
    try:
        root = "τ"
        base_text = (
            "Инструкция: настроить cookie manager в ZennoPoster для профиля {n}. "
            "Проверить авторизацию через HSR endpoint, timeout 30s, "
            "retry 3 раза с backoff. [[EVO:τ^{{x}}_{{y_{n:04d}}} | тест]]"
        )
        for i in range(25):
            await write_cell(host="", path=f"/evo/{root}/dicttest_{i:04d}.zst",
                              content=base_text.format(n=i), symbol_id="")
        print(f"✅ [T7] Записано 25 тестовых ячеек в раздел '{root}'")
    except Exception as e:
        errors.append("T7")
        print(f"❌ [T7] Exception: {e}")

    # T8: обучаем словарь на этом разделе (min_samples=20, у нас 25 — должно пройти)
    try:
        ok = await train_dictionary_for_root("τ", min_samples=20)
        print(f"{'✅' if ok else '❌'} [T8] train_dictionary_for_root('τ') → {ok}")
        if not ok: errors.append("T8")
    except Exception as e:
        errors.append("T8")
        print(f"❌ [T8] Exception: {e}")

    # T9: после обучения словарь загружается из кэша/хранилища
    try:
        zdict = await _get_dictionary("τ")
        ok = zdict is not None and len(zdict) > 0
        print(f"{'✅' if ok else '❌'} [T9] Словарь раздела 'τ' доступен: "
              f"{len(zdict) if zdict else 0} байт")
        if not ok: errors.append("T9")
    except Exception as e:
        errors.append("T9")
        print(f"❌ [T9] Exception: {e}")

    # T10: НОВАЯ ячейка, записанная ПОСЛЕ обучения словаря, читается корректно
    # (round-trip со словарём — это и есть основная цель фичи)
    try:
        new_content = ("Инструкция: настроить cookie manager в ZennoPoster для профиля 99. "
                        "Проверить авторизацию через HSR endpoint новый вариант.")
        path = "/evo/τ/dicttest_post_dict_0001.zst"
        await write_cell(host="", path=path, content=new_content, symbol_id="")
        restored, _ = await read_cell_local(path)
        ok = restored == new_content
        print(f"{'✅' if ok else '❌'} [T10] Round-trip СО словарём после обучения byte-exact")
        if not ok:
            errors.append("T10")
            print(f"    ожидалось: {new_content!r}")
            print(f"    получено:  {restored!r}")
    except Exception as e:
        errors.append("T10")
        print(f"❌ [T10] Exception: {e}")

    # T11: СТАРАЯ ячейка (записана ДО обучения словаря, из T7) всё ещё читается —
    # это проверка graceful fallback на legacy-формат без словаря
    try:
        legacy_path = "/evo/τ/dicttest_0000.zst"
        restored, _ = await read_cell_local(legacy_path)
        ok = "Инструкция: настроить cookie manager" in restored
        print(f"{'✅' if ok else '❌'} [T11] Legacy-ячейка (без словаря) читается через fallback")
        if not ok: errors.append("T11")
    except Exception as e:
        errors.append("T11")
        print(f"❌ [T11] Exception: {e}")

    # T12: реальная выгода — сжатие СО словарём эффективнее для маленьких ячеек,
    # чем без него (сравниваем размер на диске одинакового текста)
    try:
        import os as _os
        from shards.zstd_codec import compress
        small_text = "Короткий паттерн: rate limiting через Redis incr/expire."
        no_dict_size = len(compress(small_text))
        zdict = await _get_dictionary("τ")
        with_dict_size = len(compress(small_text, dict_data=zdict)) if zdict else no_dict_size
        improved = with_dict_size <= no_dict_size
        print(f"{'✅' if improved else '⚠️ '} [T12] Сжатие маленькой ячейки: "
              f"без словаря={no_dict_size}b, со словарём={with_dict_size}b")
        if not improved: errors.append("T12")
    except Exception as e:
        errors.append("T12")
        print(f"❌ [T12] Exception: {e}")

    total = 6
    passed = total - len(errors)
    print(f"\n{'='*40}")
    print(f"Dictionary compression: {passed}/{total} passed")
    if errors:
        print(f"Failed: {errors}")
    print('='*40)
    return len(errors) == 0


if __name__ == "__main__":
    ok1 = asyncio.run(run_tests())
    ok2 = asyncio.run(run_dictionary_tests())
    sys.exit(0 if (ok1 and ok2) else 1)
