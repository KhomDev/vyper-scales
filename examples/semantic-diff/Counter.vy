# pragma version ~=0.4.3

value: public(uint256)

@external
def increment(amount: uint256):
    self.value += amount
