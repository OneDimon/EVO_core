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

if __name__ == "__main__":
    test_hyperlinks()
    test_zstd_roundtrip()
    test_symbol_id_format()
    print("\n✅ All notation tests passed")
