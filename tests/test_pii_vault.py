from backend.pii_vault import PiiVault, contains_raw_pii, detect


def test_detects_all_kinds_and_rejects_false_positives():
    text = ("card 4111 1111 1111 1111, iban DE89 3704 0044 0532 0130 00, ssn 078-05-1120, "
            "mail a.b@example.com, order 1234567890123 and ACC-C-1001")
    kinds = sorted(f.kind for f in detect(text))
    assert kinds == ["EMAIL", "IBAN", "PAN", "SSN"]  # non-Luhn digit run and account id ignored


def test_tokenize_is_deterministic_and_reversible():
    v = PiiVault()
    t1, c1 = v.tokenize("Card 4111 1111 1111 1111 / 4111-1111-1111-1111")
    assert t1 == "Card <PAN_001> / <PAN_001>"
    assert c1 == {"PAN": 2}
    t2, _ = v.tokenize("again 4111111111111111 and 5500 0000 0000 0004")
    assert "<PAN_001>" in t2 and "<PAN_002>" in t2
    assert v.detokenize("x <PAN_002>") == "x 5500 0000 0000 0004"
    assert not contains_raw_pii(t1 + t2)


def test_ciphertext_not_plaintext():
    from sqlalchemy import select
    from backend.db import get_engine, vault_entries
    PiiVault().tokenize("078-05-1120")
    with get_engine().connect() as c:
        row = c.execute(select(vault_entries)).mappings().one()
    assert "078" not in row["ciphertext"] and row["token"] == "<SSN_001>"
