# pragma version ~=0.4.3

"""
@notice Minimal ERC-1271 + ECDSA routing example.
@dev This deliberately does not implement ERC-6492 deployment or ERC-7739 rehashing.
     Put those policies in a trusted validator/domain layer and test them separately.
"""

struct Signature:
    r: bytes32
    s: bytes32
    v: uint8

ERC1271_MAGIC: constant(bytes4) = 0x1626ba7e
SECP256K1_HALF_N: constant(uint256) = 57896044618658097711785492504343953926418782139537452191302581570759080747168

@internal
@view
def _erc1271(signer: address, digest: bytes32, signature: Signature) -> bool:
    v_word: bytes32 = convert(convert(signature.v, uint256), bytes32)
    v_byte: Bytes[1] = slice(v_word, 31, 1)
    signature_bytes: Bytes[65] = concat(signature.r, signature.s, v_byte)
    success: bool = False
    response: Bytes[32] = b""
    success, response = raw_call(
        signer,
        abi_encode(
            digest,
            signature_bytes,
            method_id=method_id("isValidSignature(bytes32,bytes)"),
        ),
        max_outsize=32,
        is_static_call=True,
        revert_on_failure=False,
    )
    return (
        success
        and len(response) == 32
        and convert(slice(response, 0, 4), bytes4) == ERC1271_MAGIC
    )

@external
@view
def verify(signer: address, digest: bytes32, signature: Signature) -> bool:
    if signer == empty(address):
        return False

    # A code-bearing EOA may support ERC-1271 through delegation. If it does not,
    # ECDSA remains a valid route. Code presence is not an account-type oracle.
    if signer.codesize > 0 and self._erc1271(signer, digest, signature):
        return True

    if signature.v != 27 and signature.v != 28:
        return False
    if convert(signature.s, uint256) > SECP256K1_HALF_N:
        return False
    recovered: address = ecrecover(
        digest,
        convert(signature.v, uint256),
        convert(signature.r, uint256),
        convert(signature.s, uint256),
    )
    return recovered == signer
