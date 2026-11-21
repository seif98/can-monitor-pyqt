from __future__ import annotations
import math
import random
from .frame import Frame
from .signals import SignalDef, encode_signal

DEFAULT_SIGNALS: list[SignalDef] = [
    SignalDef("EngineSpeed",   0x100, 0,  16, factor=0.25, unit="rpm"),
    SignalDef("ThrottlePos",   0x100, 16, 8,  factor=0.4,  unit="%"),
    SignalDef("CoolantTemp",   0x200, 0,  8,  offset=-40,  unit="degC"),
    SignalDef("OilPressure",   0x200, 8,  8,  factor=2.0,  unit="kPa"),
    SignalDef("VehicleSpeed",  0x300, 0,  16, factor=0.01, unit="km/h"),
    SignalDef("SteeringAngle", 0x300, 16, 16, factor=0.1,  unit="deg", signed=True),
]


class CanSimulator:
    """Generates deterministic, realistic-looking CAN traffic. No hardware needed.

    Call ``poll(now)`` regularly (e.g. from a QTimer). Each message is emitted at
    its own period, so the GUI sees traffic like a real bus.
    """

    # message id -> period in seconds
    PERIODS = {0x100: 0.01, 0x200: 0.10, 0x300: 0.02}

    def __init__(self, seed: int = 1, signals: list[SignalDef] | None = None):
        self._rng = random.Random(seed)
        self.signals = signals or DEFAULT_SIGNALS
        self._next_due = {mid: 0.0 for mid in self.PERIODS}

    def _value(self, name: str, t: float) -> float:
        n = self._rng.uniform(-1, 1)
        if name == "EngineSpeed":   return 2500 + 1500 * math.sin(t * 0.5) + 20 * n
        if name == "ThrottlePos":   return 40 + 35 * math.sin(t * 0.5 + 0.3) + n
        if name == "CoolantTemp":   return min(90, 25 + t * 2) + 0.3 * n
        if name == "OilPressure":   return 300 + 40 * math.sin(t * 0.2) + 2 * n
        if name == "VehicleSpeed":  return 60 + 50 * math.sin(t * 0.25) + 0.2 * n
        if name == "SteeringAngle": return 90 * math.sin(t * 0.8) + 0.5 * n
        return 0.0

    def build_frame(self, message_id: int, t: float) -> Frame:
        data = bytearray(8)
        for sig in self.signals:
            if sig.message_id == message_id:
                encode_signal(sig, self._value(sig.name, t), data)
        return Frame(t, message_id, bytes(data))

    def poll(self, now: float) -> list[Frame]:
        """Return every frame that has become due up to time ``now`` (seconds)."""
        frames: list[Frame] = []
        for mid, period in self.PERIODS.items():
            while self._next_due[mid] <= now:
                frames.append(self.build_frame(mid, self._next_due[mid]))
                self._next_due[mid] += period
        frames.sort(key=lambda f: f.timestamp)
        return frames
