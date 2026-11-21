from __future__ import annotations
from dataclasses import dataclass, field
from .frame import Frame


@dataclass
class FrameFilter:
    """Pass-through filter. Empty filter accepts everything.

    ``ids``: accept only these arbitration IDs.
    ``id_min`` / ``id_max``: optional inclusive range.
    ``hide_ids``: always reject these IDs.
    """
    ids: set[int] = field(default_factory=set)
    id_min: int | None = None
    id_max: int | None = None
    hide_ids: set[int] = field(default_factory=set)

    def matches(self, frame: Frame) -> bool:
        i = frame.arbitration_id
        if i in self.hide_ids:
            return False
        if self.ids and i not in self.ids:
            return False
        if self.id_min is not None and i < self.id_min:
            return False
        if self.id_max is not None and i > self.id_max:
            return False
        return True

    def apply(self, frames):
        return [f for f in frames if self.matches(f)]
