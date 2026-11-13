"""Signed smart-meter readings (secp256k1, the same curve as Ethereum accounts).

Each participant has a deterministic key pair derived from the run seed, so the same seed gives
the same addresses and signatures. A reading is signed over the keccak256 of its canonical JSON;
verification recovers the signer's address and compares it with the registered address.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from eth_keys import keys

from app.engine.hashing import canonical_json, keccak256


@dataclass(frozen=True)
class MeterReading:
    participant_id: str
    interval: int
    export_wh: int  # energy delivered to the network (P2P sales)
    import_wh: int  # energy taken from the network
    pv_wh: int  # reported PV generation (0 for non-PV participants)


@dataclass(frozen=True)
class SignedReading:
    reading: MeterReading
    signature: str  # 0x-prefixed 65-byte hex


class MeterKey:
    def __init__(self, seed: int, participant_id: str) -> None:
        self._sk = keys.PrivateKey(keccak256(f"meter-key:{seed}:{participant_id}"))
        self.address = self._sk.public_key.to_checksum_address()

    def sign(self, reading: MeterReading) -> SignedReading:
        sig = self._sk.sign_msg_hash(reading_hash(reading))
        return SignedReading(reading=reading, signature=sig.to_hex())


def reading_hash(reading: MeterReading) -> bytes:
    return keccak256(canonical_json(asdict(reading)))


def verify(signed: SignedReading, expected_address: str) -> bool:
    try:
        sig = keys.Signature(bytes.fromhex(signed.signature.removeprefix("0x")))
        pub = sig.recover_public_key_from_msg_hash(reading_hash(signed.reading))
    except Exception:
        return False
    return pub.to_checksum_address() == expected_address
