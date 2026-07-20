BPS = 10_000
SCALE_6_TO_18 = 10**12


def adversarial_quote(dx: int, fee_bps: int, slippage_bps: int, reject: bool) -> int:
    if reject:
        raise ValueError("fixture: forced revert")
    return dx * SCALE_6_TO_18 * (BPS - fee_bps - slippage_bps) // BPS


def test_adversarial_pool_model():
    dx = 5_000_000
    assert adversarial_quote(dx, 10, 40, False) == dx * SCALE_6_TO_18 * 9_950 // BPS
    try:
        adversarial_quote(dx, 10, 40, True)
    except ValueError:
        pass
    else:
        raise AssertionError("revert path was not exercised")
