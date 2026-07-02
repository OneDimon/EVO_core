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

    # 2. Все коды — греческие буквы, кроме ОДНОГО осознанного исключения:
    # "Математика/Алгебра" = латинская "M" (см. SCL_FRACTAL_PROTOCOL.md §5,
    # пункт 3 таблицы — так в исходной спецификации Архитектора, не баг).
    KNOWN_LATIN_EXCEPTION = {"Математика/Алгебра": "M"}
    for science, code in ROOT_CODES.items():
        if science in KNOWN_LATIN_EXCEPTION:
            assert code == KNOWN_LATIN_EXCEPTION[science]
            continue
        codepoint = ord(code)
        is_greek = 0x0370 <= codepoint <= 0x03FF
        assert is_greek, f"Корень '{science}' имеет код '{code}' — не греческая буква"

    # 3. Все 32 кода уникальны (иначе коллизия ID между разными областями знаний)
    codes = list(ROOT_CODES.values())
    assert len(codes) == len(set(codes)), (
        f"Дубликаты в ROOT_CODES: {[c for c in codes if codes.count(c) > 1]}"
    )

    # 4. Функция реально использует таблицу, а не собственную логику.
    # Имена — ТОЧНО как в SCL_FRACTAL_PROTOCOL.md §5 (составные, через "/"),
    # не сокращённые "Технология" или "ИИ" — таких ключей в каноне нет.
    assert _get_root_code("Технология/Инженерия") == "τ"
    assert _get_root_code("Нейронные сети/ИИ") == "ν"
    assert _get_root_code("Математика/Алгебра") == "M"  # латиница, осознанно (см. архивист)

    # 5. Неизвестный корень не роняет генерацию — возвращает безопасный дефолт Φ
    fallback = _get_root_code("Совершенно новая несуществующая область знаний")
    assert fallback == "Φ"

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
    # "Математика/Алгебра" — единственное осознанное исключение: это уже
    # НАСТОЯЩАЯ латиница "M" по спецификации §5, не греческий омограф.
    KNOWN_LATIN_EXCEPTION = {"Математика/Алгебра"}
    bad = [(k, v) for k, v in ROOT_CODES.items()
           if v in homoglyphs and k not in KNOWN_LATIN_EXCEPTION]
    assert not bad, f"Найдены непреднамеренные омографы латиницы в ROOT_CODES: {bad}"
    print("✅ Нет визуальных омографов латиницы в ROOT_CODES")



def test_classify_prompt_uses_canonical_names():
    """
    Регрессионный тест на баг: ai_router.classify(task="macro_root") раньше
    просил модель вернуть ГОЛЫЙ символ (τ), а весь пайплайн (ROOT_CODES,
    _get_root_code, WHERE science=$1) работает с ПОЛНЫМИ именами как ключами.
    Из-за расхождения каждый новый символ проваливался в fallback Φ.
    Проверяем СТРУКТУРНО, без вызова реального API: промпт должен перечислять
    полные канонические имена из ROOT_CODES, не голые символы.
    """
    from core.archivist import ROOT_CODES
    import core.ai_router as ar_module
    import inspect

    src = inspect.getsource(ar_module.AIRouter.classify) if hasattr(ar_module, 'AIRouter') else \
          inspect.getsource(ar_module.ai_router.classify)

    # Промпт должен строиться из ROOT_CODES.keys(), не из хардкод-списка символов
    assert "ROOT_CODES" in src, (
        "classify() должен строить список корней динамически из ROOT_CODES, "
        "а не хардкодить символы — иначе список снова разойдётся с реальным словарём"
    )
    # Не должно быть старого хардкод-паттерна голых символов через запятую
    assert "Φ,Λ,M,γ,ζ" not in src, (
        "Обнаружен старый хардкод списка символов в промпте classify() — "
        "регрессия к багу несовпадения имя/символ"
    )
    print("✅ ai_router.classify(macro_root) использует ROOT_CODES как источник истины")


def test_new_symbol_root_not_truncated():
    """
    Регрессионный тест: core/archivist.py::_new_symbol раньше делал
    root.strip()[:2] — обрезку результата классификации до 2 символов,
    что превращало полные имена в мусор и роняло поиск в ROOT_CODES.
    Проверяем что обрезка убрана из исходного кода функции.
    """
    import inspect
    from core.archivist import _new_symbol
    src = inspect.getsource(_new_symbol)
    assert "[:2]" not in src, (
        "_new_symbol снова обрезает root до 2 символов — "
        "это ломает поиск полного имени в ROOT_CODES"
    )
    assert "_get_root_code" in src, (
        "_new_symbol должен явно вызывать _get_root_code для построения "
        "короткого символа в пути шарда, не использовать root напрямую"
    )
    print("✅ _new_symbol не обрезает root, использует _get_root_code для короткого символа")


if __name__ == "__main__":
    test_hyperlinks()
    test_zstd_roundtrip()
    test_symbol_id_format()
    test_root_code_generator_matches_spec()
    test_no_latin_homoglyphs()
    test_classify_prompt_uses_canonical_names()
    test_new_symbol_root_not_truncated()
    print("\n✅ All notation tests passed")
