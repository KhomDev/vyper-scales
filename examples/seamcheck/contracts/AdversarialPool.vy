# pragma version ~=0.4.3

BPS: constant(uint256) = 10_000
SCALE_6_TO_18: constant(uint256) = 10**12

fee_bps: public(uint256)
slippage_bps: public(uint256)
reject: public(bool)

@external
def configure(_fee_bps: uint256, _slippage_bps: uint256, _reject: bool):
    assert _fee_bps + _slippage_bps < BPS
    self.fee_bps = _fee_bps
    self.slippage_bps = _slippage_bps
    self.reject = _reject

@external
def exchange(i: uint256, j: uint256, dx: uint256, min_dy: uint256) -> uint256:
    assert not self.reject, "fixture: forced revert"
    gross: uint256 = dx * SCALE_6_TO_18
    dy: uint256 = gross * (BPS - self.fee_bps - self.slippage_bps) // BPS
    assert dy >= min_dy, "fixture: slippage"
    return dy
