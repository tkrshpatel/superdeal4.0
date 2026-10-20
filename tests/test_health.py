from superdeal.health import health_check


def test_health_check():
    assert health_check() == {
        "status": "ok",
        "service": "superdeal3",
    }
