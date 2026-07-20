# pragma version ~=0.4.3

# Deliberately unsafe as security evidence: no decimal scaling, fee, loss, or revert.
@external
def exchange(i: uint256, j: uint256, dx: uint256, min_dy: uint256) -> uint256:
    return dx
