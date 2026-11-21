from backend import audit


def test_chain_valid_then_tamper_detected():
    for i in range(5):
        audit.append("test.event", "tester", {"i": i}, "DSP-X")
    assert audit.verify_chain() == {"valid": True, "length": 5, "broken_at": None, "head": audit.list_events()[-1]["hash"]}
    audit.tamper_for_demo(3)
    res = audit.verify_chain()
    assert res["valid"] is False and res["broken_at"] == 3
