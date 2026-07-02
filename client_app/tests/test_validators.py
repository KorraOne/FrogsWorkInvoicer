from invoicing.validators import normalize_abn, normalize_account_number, normalize_bsb


def test_normalize_abn_accepts_separators_and_returns_digits():
    assert normalize_abn("12 345 678 901") == "12345678901"


def test_normalize_abn_empty_is_ok():
    assert normalize_abn("") == ""


def test_normalize_abn_rejects_wrong_length():
    try:
        normalize_abn("123")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "ABN must be 11 digits."


def test_normalize_bsb_accepts_common_formats():
    assert normalize_bsb("123456") == "123-456"
    assert normalize_bsb("123 456") == "123-456"
    assert normalize_bsb("123-456") == "123-456"


def test_normalize_bsb_empty_is_ok():
    assert normalize_bsb("") == ""


def test_normalize_bsb_rejects_wrong_length():
    try:
        normalize_bsb("1234")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "BSB must be 6 digits."


def test_normalize_account_number_digits_only_and_length_range():
    assert normalize_account_number("12 34-56") == "123456"


def test_normalize_account_number_empty_is_ok():
    assert normalize_account_number("") == ""


def test_normalize_account_number_rejects_out_of_range():
    try:
        normalize_account_number("1234")
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert str(exc) == "Account number must be 5–9 digits."

