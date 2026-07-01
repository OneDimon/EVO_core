"""Тесты нотации SCL символов — проверка уникальности и расшифровки."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shards.zstd_codec import parse_hyperlinks, compress, decompress

def test_hyperlinks():
    content = """
Инструкция по авторизации.
[[EVO:τ^{auto}_{zp_0047} | авторизация ZennoPoster HSR]]
[[EVO:ε^{pay}_{crypto_0021}:step_3 | крипто-шлюз без KYC]]
"""
    links = parse_hyperlinks(content)
    assert len(links) == 2
    assert links[0]["symbol_id"] == "τ^{auto}_{zp_0047}"
    assert links[0]["description"] == "авторизация ZennoPoster HSR"
    assert links[1]["symbol_id"] == "ε^{pay}_{crypto_0021}:step_3"
    print("✅ Hyperlink parsing OK")

def test_zstd_roundtrip():
    original = "Инструкция: настроить cookie manager в ZennoPoster\n[[EVO:τ^{auto}_{zp_0047} | тест]]"
    compressed = compress(original)
    restored = decompress(compressed)
    assert restored == original, f"Roundtrip failed!\n{original}\n!=\n{restored}"
    ratio = len(compressed) / len(original.encode())
    print(f"✅ zstd roundtrip OK (compression ratio: {ratio:.2f})")

def test_symbol_id_format():
    """Проверка что ID соответствует нотации SCL."""
    import re
    valid_ids = [
        "τ^{auto^2}_{zp_0047}",
        "ε^{pay}_{crypto_0021}",
        "Φ^{logic}_{ded_0003}",
    ]
    # Базовая проверка формата
    pattern = r'^.+\^\{.+\}_\{.+_\d{4}\}$'
    for sid in valid_ids:
        assert re.match(pattern, sid), f"Invalid ID format: {sid}"
    print(f"✅ Symbol ID format OK ({len(valid_ids)} tested)")

def test_root_code_generator_matches_spec():
    """
    Проверка КОДА, а не только формата: реальный _get_root_code из archivist.py
    должен возвращать однобуквенные греческие символы (SCL_SYMBOLIC_NOTATION.md),
    а не латинские коды. Этот тест должен был поймать регрессию P16 (Tc/Mt вместо τ/μ),
    но не существовал — добавлен как страховка от повторения.
    """
    from core.archivist import ROOT_CODES, _get_root_code

    # 1. Все коды — ровно один символ (не 2+ латинских буквы)
    for science, code in ROOT_CODES.items():
        assert len(code) == 1, (
            f"Корень '{science}' имеет код '{code}' длиной {len(code)} — "
            f"должен быть ОДИН символ по SCL_SYMBOLIC_NOTATION.md"
        )

    # 2. Все коды — греческие буквы, не латиница/кириллица
    for science, code in ROOT_CODES.items():
        codepoint = ord(code)
        is_greek = 0x0370 <= codepoint <= 0x03FF
        assert is_greek, f"Корень '{science}' имеет код '{code}' — не греческая буква"

    # 3. Все 32 кода уникальны (иначе коллизия ID между разными областями знаний)
    codes = list(ROOT_CODES.values())
    assert len(codes) == len(set(codes)), (
        f"Дубликаты в ROOT_CODES: {[c for c in codes if codes.count(c) > 1]}"
    )

    # 4. Функция реально использует таблицу, а не собственную логику
    assert _get_root_code("Технология") == "τ"
    assert _get_root_code("ИИ") == ROOT_CODES["ИИ"]

    # 5. Неизвестный корень не роняет генерацию — возвращает валидный fallback
    fallback = _get_root_code("Совершенно новая несуществующая область знаний")
    assert len(fallback) == 1 and 0x0370 <= ord(fallback) <= 0x03FF

    print(f"✅ ROOT_CODES соответствует SCL_SYMBOLIC_NOTATION.md: "
          f"{len(ROOT_CODES)} корней, все греческие, все уникальные")

def test_no_latin_homoglyphs():
    """
    Дополнительная защита: некоторые заглавные греческие буквы визуально
    неотличимы от латиницы (Α=A, Β=B, Ε=E, Ζ=Z, Η=H, Ι=I, Κ=K, Μ=M, Ν=N,
    Ο=O, Ρ=P, Τ=T, Υ=Y, Χ=X). Их использование в ROOT_CODES создаёт
    путаницу при чтении ID глазами и при ручном вводе.
    """
    from core.archivist import ROOT_CODES

    homoglyphs = set("ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ")  # заглавные греческие похожие на латиницу
    bad = [(k, v) for k, v in ROOT_CODES.items() if v in homoglyphs]
    assert not bad, f"Найдены омографы латиницы в ROOT_CODES: {bad}"
    print("✅ Нет визуальных омографов латиницы в ROOT_CODES")

if __name__ == "__main__":
    test_hyperlinks()
    test_zstd_roundtrip()
    test_symbol_id_format()
    test_root_code_generator_matches_spec()
    test_no_latin_homoglyphs()
    print("\n✅ All notation tests passed")
