from decimal import Decimal

from app.utils.hashing import dumps, json_hash, sha256_text


def test_known_sha256_value() -> None:
    assert sha256_text("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_decimal_is_written_as_a_bare_number() -> None:
    assert dumps({"group_revenue": Decimal("28301607.81")}, indent=None) == '{"group_revenue":28301607.81}'


def test_small_decimal_never_uses_exponent_notation() -> None:
    assert dumps({"x": Decimal("0.00000001")}, indent=None) == '{"x":0.00000001}'


def test_null_and_text_pass_through() -> None:
    assert dumps({"sgd_bank_gbp": None, "note": "no rate"}, indent=None) == '{"sgd_bank_gbp":null,"note":"no rate"}'


def test_hash_does_not_depend_on_key_order() -> None:
    assert json_hash({"a": 1, "b": Decimal("2.50")}) == json_hash({"b": Decimal("2.50"), "a": 1})


def test_hash_changes_when_a_value_changes() -> None:
    assert json_hash({"rate": Decimal("1.2530")}) != json_hash({"rate": Decimal("1.2630")})
