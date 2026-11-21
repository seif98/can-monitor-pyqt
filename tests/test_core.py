import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import (Frame, SignalDef, decode_signal, encode_signal, decode_frame,
                  CanSimulator, DEFAULT_SIGNALS, CsvLogger, read_log, FrameFilter)


class TestSignals(unittest.TestCase):
    def test_roundtrip_unsigned(self):
        sig = SignalDef("rpm", 0x100, 0, 16, factor=0.25)
        data = bytearray(8)
        encode_signal(sig, 3000.0, data)
        self.assertAlmostEqual(decode_signal(sig, bytes(data)), 3000.0)

    def test_roundtrip_signed(self):
        sig = SignalDef("angle", 0x300, 16, 16, factor=0.1, signed=True)
        data = bytearray(8)
        encode_signal(sig, -45.5, data)
        self.assertAlmostEqual(decode_signal(sig, bytes(data)), -45.5, places=1)

    def test_offset(self):
        sig = SignalDef("temp", 0x200, 0, 8, offset=-40)
        data = bytearray(8)
        encode_signal(sig, 90.0, data)
        self.assertEqual(data[0], 130)
        self.assertAlmostEqual(decode_signal(sig, bytes(data)), 90.0)

    def test_clamping(self):
        sig = SignalDef("x", 1, 0, 8)
        data = bytearray(8)
        encode_signal(sig, 9999, data)
        self.assertEqual(data[0], 255)

    def test_signals_dont_overwrite_each_other(self):
        a = SignalDef("a", 1, 0, 8)
        b = SignalDef("b", 1, 8, 8)
        data = bytearray(8)
        encode_signal(a, 10, data)
        encode_signal(b, 200, data)
        self.assertEqual((data[0], data[1]), (10, 200))

    def test_bad_signal_rejected(self):
        with self.assertRaises(ValueError):
            SignalDef("bad", 1, 60, 8)


class TestFrame(unittest.TestCase):
    def test_too_long(self):
        with self.assertRaises(ValueError):
            Frame(0.0, 0x100, bytes(9))

    def test_hex(self):
        self.assertEqual(Frame(0, 1, b"\x01\xab").data_hex(), "01 AB")


class TestSimulator(unittest.TestCase):
    def test_rates_and_decoding(self):
        sim = CanSimulator(seed=1)
        frames = sim.poll(1.0)
        counts = {}
        for f in frames:
            counts[f.arbitration_id] = counts.get(f.arbitration_id, 0) + 1
        self.assertAlmostEqual(counts[0x100], 101, delta=2)   # 100 Hz
        self.assertAlmostEqual(counts[0x300], 51, delta=2)    # 50 Hz
        self.assertAlmostEqual(counts[0x200], 11, delta=2)    # 10 Hz
        self.assertEqual(frames, sorted(frames, key=lambda f: f.timestamp))
        for f in frames:
            vals = decode_frame(f, DEFAULT_SIGNALS)
            if "EngineSpeed" in vals:
                self.assertTrue(500 < vals["EngineSpeed"] < 5000)

    def test_deterministic(self):
        a = CanSimulator(seed=7).poll(0.5)
        b = CanSimulator(seed=7).poll(0.5)
        self.assertEqual(a, b)

    def test_incremental_poll_has_no_duplicates(self):
        sim = CanSimulator(seed=1)
        first = sim.poll(0.5)
        second = sim.poll(1.0)
        self.assertTrue(max(f.timestamp for f in first) < min(f.timestamp for f in second))


class TestLogger(unittest.TestCase):
    def test_write_and_read_back(self):
        frames = CanSimulator(seed=3).poll(0.2)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "log.csv"
            with CsvLogger(path) as log:
                log.write_many(frames)
            self.assertEqual(log.count, len(frames))
            back = list(read_log(path))
        self.assertEqual(len(back), len(frames))
        self.assertEqual(back[0].data, frames[0].data)
        self.assertEqual(back[0].arbitration_id, frames[0].arbitration_id)


class TestFilter(unittest.TestCase):
    def setUp(self):
        self.frames = [Frame(0, i, b"") for i in (0x100, 0x200, 0x300)]

    def test_empty_accepts_all(self):
        self.assertEqual(len(FrameFilter().apply(self.frames)), 3)

    def test_ids(self):
        self.assertEqual([f.arbitration_id for f in FrameFilter(ids={0x200}).apply(self.frames)], [0x200])

    def test_range_and_hide(self):
        flt = FrameFilter(id_min=0x100, id_max=0x200, hide_ids={0x100})
        self.assertEqual([f.arbitration_id for f in flt.apply(self.frames)], [0x200])


if __name__ == "__main__":
    unittest.main()
