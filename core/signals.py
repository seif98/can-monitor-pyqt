from __future__ import annotations
from dataclasses import dataclass
from .frame import Frame


@dataclass(frozen=True)
class SignalDef:
    """Describes one signal inside a CAN frame (Intel / little-endian layout)."""
    name: str
    message_id: int
    start_bit: int
    length: int
    factor: float = 1.0
    offset: float = 0.0
    unit: str = ""
    signed: bool = False

    def __post_init__(self):
        if self.length < 1 or self.start_bit < 0 or self.start_bit + self.length > 64:
            raise ValueError(f"Signal {self.name!r} does not fit in 8 bytes")


def decode_signal(sig: SignalDef, data: bytes) -> float:
    """Return the physical value of a signal from raw frame data."""
    raw = int.from_bytes(data.ljust(8, b"\x00"), "little")
    raw = (raw >> sig.start_bit) & ((1 << sig.length) - 1)
    if sig.signed and raw & (1 << (sig.length - 1)):
        raw -= 1 << sig.length
    return raw * sig.factor + sig.offset


def encode_signal(sig: SignalDef, value: float, data: bytearray) -> None:
    """Write a physical value into ``data`` (an 8-byte bytearray), in place."""
    raw = round((value - sig.offset) / sig.factor)
    lo, hi = ((-(1 << (sig.length - 1)), (1 << (sig.length - 1)) - 1)
              if sig.signed else (0, (1 << sig.length) - 1))
    raw = max(lo, min(hi, raw))              # clamp to the representable range
    raw &= (1 << sig.length) - 1
    word = int.from_bytes(data, "little")
    mask = ((1 << sig.length) - 1) << sig.start_bit
    word = (word & ~mask) | (raw << sig.start_bit)
    data[:] = word.to_bytes(len(data), "little")


def decode_frame(frame: Frame, signals: list[SignalDef]) -> dict[str, float]:
    """Decode every known signal that belongs to this frame's ID."""
    return {s.name: decode_signal(s, frame.data)
            for s in signals if s.message_id == frame.arbitration_id}
