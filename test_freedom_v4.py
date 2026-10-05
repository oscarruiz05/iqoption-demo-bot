import unittest

import pandas as pd

import freedom_v4
from freedom_v4 import detect_freedom_v4_signal


def freedom_v4_frame(direction: str) -> pd.DataFrame:
    bullish = direction == "call"
    rows = []
    for index in range(206):
        rows.append({
            "from": index * 60,
            "open": 1.0,
            "close": 1.0,
            "min": 0.98,
            "max": 1.02,
            "ema20": 1.0,
            "ema50": 1.0,
            "rsi14": 50.0,
            "atr14": 0.02,
            "ema200": 0.95 if bullish else 1.05,
            "bb_lower14": 0.99,
            "bb_upper14": 1.01,
            "rsi10": 50.0,
        })
    if bullish:
        rows[-7]["ema200"] = 0.94
        rows[-2].update(open=0.99, close=0.98, rsi10=25.0)
        rows[-1].update(open=0.985, close=0.995, rsi10=35.0)
    else:
        rows[-7]["ema200"] = 1.06
        rows[-2].update(open=1.01, close=1.02, rsi10=75.0)
        rows[-1].update(open=1.015, close=1.005, rsi10=65.0)
    return pd.DataFrame(rows)


class FreedomV4Tests(unittest.TestCase):
    def _detect(self, frame: pd.DataFrame):
        original = freedom_v4.add_freedom_indicators
        freedom_v4.add_freedom_indicators = lambda _: frame
        try:
            return detect_freedom_v4_signal(frame)
        finally:
            freedom_v4.add_freedom_indicators = original

    def test_accepts_call_with_moderate_break_and_reentry(self):
        signal = self._detect(freedom_v4_frame("call"))
        self.assertEqual(signal.direction, "call")
        self.assertEqual(signal.strategy, "freedom_v4")
        self.assertEqual(signal.expiration_min, 5)
        self.assertAlmostEqual(signal.metrics["band_break_atr"], 0.5)
        self.assertGreaterEqual(signal.metrics["reentry_atr"], 0.1)

    def test_accepts_put_with_moderate_break_and_reentry(self):
        signal = self._detect(freedom_v4_frame("put"))
        self.assertEqual(signal.direction, "put")

    def test_rejects_excessive_break(self):
        frame = freedom_v4_frame("call")
        frame.loc[frame.index[-2], "close"] = 0.976
        self.assertIsNone(self._detect(frame))

    def test_rejects_shallow_reentry(self):
        frame = freedom_v4_frame("call")
        frame.loc[frame.index[-1], "close"] = 0.991
        self.assertIsNone(self._detect(frame))

    def test_rejects_band_walk(self):
        frame = freedom_v4_frame("put")
        frame.loc[frame.index[-3], "close"] = 1.02
        self.assertIsNone(self._detect(frame))


if __name__ == "__main__":
    unittest.main()
