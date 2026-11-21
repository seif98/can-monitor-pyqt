from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    """A single CAN frame (classic CAN, up to 8 data bytes)."""
    timestamp: float          # seconds
    arbitration_id: int       # 11-bit (or 29-bit) identifier
    data: bytes

    def __post_init__(self):
        if len(self.data) > 8:
            raise ValueError("Classic CAN frames carry at most 8 data bytes")
        if not 0 <= self.arbitration_id <= 0x1FFFFFFF:
            raise ValueError("arbitration_id out of range")

    @property
    def dlc(self) -> int:
        return len(self.data)

    def data_hex(self) -> str:
        return self.data.hex(" ").upper()
