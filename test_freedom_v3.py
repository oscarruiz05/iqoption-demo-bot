import unittest

import pandas as pd

import freedom_v3
from freedom_v3 import detect_freedom_v3_signal


def freedom_v3_frame(direction: str) -> pd.DataFrame:
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


class FreedomV3Tests(unittest.TestCase):
    def _detect(self, frame: pd.DataFrame):
        original = freedom_v3.add_freedom_indicators
        freedom_v3.add_freedom_indicators = lambda _: frame
        try:
            return detect_freedom_v3_signal(frame)
        finally:
            freedom_v3.add_freedom_indicators = original

    def test_accepts_confirmed_call_reentry(self):
        signal = self._detect(freedom_v3_frame("call"))
        self.assertEqual(signal.direction, "call")
        self.assertEqual(signal.strategy, "freedom_v3")
        self.assertEqual(signal.expiration_min, 5)
        self.assertEqual(signal.metrics["band_walk_count"], 1.0)

    def test_accepts_confirmed_put_reentry(self):
        signal = self._detect(freedom_v3_frame("put"))
        self.assertEqual(signal.direction, "put")

    def test_rejects_without_reentry(self):
        frame = freedom_v3_frame("call")
        frame.loc[frame.index[-1], "close"] = 0.985
        self.assertIsNone(self._detect(frame))

    def test_rejects_without_rsi_recovery(self):
        frame = freedom_v3_frame("call")
        frame.loc[frame.index[-1], "rsi10"] = 24.0
        self.assertIsNone(self._detect(frame))

    def test_rejects_band_walk(self):
        frame = freedom_v3_frame("call")
        frame.loc[frame.index[-3], "close"] = 0.98
        self.assertIsNone(self._detect(frame))

    def test_rejects_wrong_confirmation_direction(self):
        frame = freedom_v3_frame("put")
        frame.loc[frame.index[-1], ["open", "close"]] = [1.0, 1.005]
        self.assertIsNone(self._detect(frame))


if __name__ == "__main__":
    unittest.main()
