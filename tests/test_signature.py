"""
Тест core/signature.py — offline, не требует БД/Redis (тестируются чистые
функции _canonical/_compute, DB-зависимые sign_response/verify_request
проверяются живьём через test_phase0.py/test_full.py на поднятом стеке).

Запуск: python tests/test_signature.py
"""
from core.signature import _compute


def test_key_order_does_not_affect_signature():
    key = "test_session_key_123"
    p1 = {"b": 1, "a": 2, "status": "ok"}
    p2 = {"a": 2, "status": "ok", "b": 1}
    assert _compute(p1, key) == _compute(p2, key)


def test_evo_signature_field_excluded_from_its_own_computation():
    key = "test_session_key_123"
    p1 = {"a": 2, "status": "ok"}
    p2 = {**p1, "evo_signature": "garbage_from_previous_round"}
    assert _compute(p1, key) == _compute(p2, key)


def test_different_payloads_yield_different_signatures():
    key = "test_session_key_123"
    p1 = {"a": 2, "status": "ok"}
    p2 = {"a": 2, "status": "different"}
    assert _compute(p1, key) != _compute(p2, key)


def test_different_keys_yield_different_signatures():
    p = {"a": 2, "status": "ok"}
    assert _compute(p, "key_one") != _compute(p, "key_two")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        t()
        passed += 1
        print(f"✅ {t.__name__}")
    print(f"\n{passed}/{len(tests)} passed")
