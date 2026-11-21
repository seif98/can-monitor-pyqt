from __future__ import annotations
import csv
from pathlib import Path
from typing import Iterable, Iterator
from .frame import Frame

HEADER = ["timestamp_s", "id_hex", "dlc", "data_hex"]


class CsvLogger:
    """Write frames to a CSV file. Use as a context manager."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._fh = None
        self._writer = None
        self.count = 0

    def __enter__(self) -> "CsvLogger":
        self._fh = open(self.path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(HEADER)
        return self

    def write(self, frame: Frame) -> None:
        if self._writer is None:
            raise RuntimeError("Logger is not open")
        self._writer.writerow([f"{frame.timestamp:.6f}",
                               f"{frame.arbitration_id:X}",
                               frame.dlc, frame.data.hex()])
        self.count += 1

    def write_many(self, frames: Iterable[Frame]) -> None:
        for f in frames:
            self.write(f)

    def __exit__(self, *exc) -> None:
        if self._fh:
            self._fh.close()
        self._fh = self._writer = None


def read_log(path: str | Path) -> Iterator[Frame]:
    """Read frames back from a file produced by CsvLogger."""
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield Frame(float(row["timestamp_s"]), int(row["id_hex"], 16),
                        bytes.fromhex(row["data_hex"]))
