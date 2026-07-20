# pragma version ~=0.4.3

interface IPool:
    def exchange(i: uint256, j: uint256, dx: uint256, min_dy: uint256) -> uint256: nonpayable

pool: public(address)

@deploy
def __init__(_pool: address):
    self.pool = _pool

@external
def route(dx_6dec: uint256, min_dy_18dec: uint256) -> uint256:
    return extcall IPool(self.pool).exchange(0, 1, dx_6dec, min_dy_18dec)
