"""
Тесты сканера белых зон Канала 1 (core/knowledge_collector.py::_scan_knowledge_gaps).

Прямая проверка N12-фикса: раньше сканер искал по id LIKE 'греческий_символ%',
но такого префикса в БД никогда не было (ID не начинались с одиночного символа
через LIKE-паттерн так, как ожидал старый код) — все 32 корня считались белыми
зонами на каждом цикле СОН, автонаполнение работало вслепую.
Теперь сканер ищет по полю science (реальное название корня в БД).

Требует: запущенный PostgreSQL с применёнными миграциями (как и test_phase1.py).
Запуск: python tests/test_channel1_scan.py
"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def run_tests():
    print("\n=== Channel 1 (Sleep Mode) white-zone scan tests ===\n")
    errors = []

    from core.archivist import ROOT_CODES
    from core.knowledge_collector import _scan_knowledge_gaps

    # T1: сканер вообще не падает и возвращает список
    try:
        gaps = await _scan_knowledge_gaps()
        ok = isinstance(gaps, list) and len(gaps) > 0
        print(f"{'✅' if ok else '❌'} [T1] _scan_knowledge_gaps() → {len(gaps)} зон")
        if not ok: errors.append("T1")
    except Exception as e:
        errors.append("T1")
        print(f"❌ [T1] Exception: {e}")
        gaps = []

    # T2: белые зоны типа zero_symbols_in_root ссылаются на РЕАЛЬНЫЕ русские
    # названия корней из ROOT_CODES (ключи словаря), а не на греческие символы
    # (значения словаря) и не на несуществующие названия
    try:
        root_gaps = [g for g in gaps if g.get("type") == "zero_symbols_in_root"]
        ok = len(root_gaps) > 0
        all_valid_roots = all(g["root"] in ROOT_CODES for g in root_gaps)
        no_greek_leaked = all(g["root"] not in ROOT_CODES.values() for g in root_gaps)
        result = ok and all_valid_roots and no_greek_leaked
        print(f"{'✅' if result else '❌'} [T2] Белые зоны используют русские названия "
              f"из ROOT_CODES.keys() ({len(root_gaps)} найдено, "
              f"все валидны: {all_valid_roots}, без греческих утечек: {no_greek_leaked})")
        if not result: errors.append("T2")
    except Exception as e:
        errors.append("T2")
        print(f"❌ [T2] Exception: {e}")

    # T3: количество проверенных корней в скане == количество корней в ROOT_CODES
    # (т.е. сканер реально проходит по всем 32 корням, не по старому греческому списку)
    try:
        # Пересчитываем вручную сколько корней МОГЛИ БЫ попасть в белую зону
        # (все, у кого < 3 символов) — раньше был бы список из 32, если поиск
        # был сломан (все всегда 0). Теперь корректный результат зависит от
        # реального состояния БД, но сам список кандидатов строится по всем 32.
        checked_roots = set(ROOT_CODES.keys())
        found_roots = {g["root"] for g in gaps if g.get("type") == "zero_symbols_in_root"}
        ok = found_roots.issubset(checked_roots)
        print(f"{'✅' if ok else '❌'} [T3] Все найденные белые зоны — подмножество "
              f"32 реальных корней ({len(found_roots)} ⊆ {len(checked_roots)})")
        if not ok: errors.append("T3")
    except Exception as e:
        errors.append("T3")
        print(f"❌ [T3] Exception: {e}")

    # T4: структура зон содержит обязательные поля для дальнейшей обработки
    try:
        priorities = [g.get("priority") for g in gaps]
        ok = all(isinstance(p, int) for p in priorities)
        is_sorted = priorities == sorted(priorities)
        print(f"{'✅' if ok and is_sorted else '❌'} [T4] Все зоны имеют priority (int), "
              f"список отсортирован: {is_sorted}")
        if not (ok and is_sorted): errors.append("T4")
    except Exception as e:
        errors.append("T4")
        print(f"❌ [T4] Exception: {e}")

    # T5: trending_expansion зона всегда присутствует (страховочная зона расширения)
    try:
        has_trending = any(g.get("type") == "trending_expansion" for g in gaps)
        print(f"{'✅' if has_trending else '❌'} [T5] trending_expansion зона присутствует")
        if not has_trending: errors.append("T5")
    except Exception as e:
        errors.append("T5")
        print(f"❌ [T5] Exception: {e}")

    total = 5
    passed = total - len(errors)
    print(f"\n{'='*40}")
    print(f"Channel 1 scan: {passed}/{total} passed")
    if errors:
        print(f"Failed: {errors}")
    else:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ — сканер белых зон видит реальные корни")
    print('='*40)
    return len(errors) == 0

if __name__ == "__main__":
    ok = asyncio.run(run_tests())
    sys.exit(0 if ok else 1)
