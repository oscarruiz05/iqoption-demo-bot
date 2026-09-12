import unittest

import numpy as np
import pandas as pd

import freedom
from freedom import add_freedom_indicators, detect_freedom_signal


def freedom_frame(direction: str) -> pd.DataFrame:
    bullish = direction == "call"
    rows = []
    for index in range(205):
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
        rows[-6]["ema200"] = 0.94
        rows[-1].update(close=0.985, rsi10=25.0)
    else:
        rows[-6]["ema200"] = 1.06
        rows[-1].update(close=1.015, rsi10=75.0)
    return pd.DataFrame(rows)


class FreedomTests(unittest.TestCase):
    def _detect(self, frame: pd.DataFrame):
        original = freedom.add_freedom_indicators
        freedom.add_freedom_indicators = lambda _: frame
        try:
            return detect_freedom_signal(frame)
        finally:
            freedom.add_freedom_indicators = original

    def test_uses_bollinger_14_with_population_deviation(self):
        close = list(range(1, 15))
        frame = pd.DataFrame({
            "close": close,
            "min": [value - 0.1 for value in close],
            "max": [value + 0.1 for value in close],
        })
        result = add_freedom_indicators(frame)
        expected = np.mean(close) + 2 * np.std(close, ddof=0)
        self.assertAlmostEqual(result.iloc[-1]["bb_upper14"], expected)

    def test_accepts_call_with_all_four_filters(self):
        signal = self._detect(freedom_frame("call"))
        self.assertEqual(signal.direction, "call")
        self.assertEqual(signal.expiration_min, 5)
        self.assertEqual(signal.strategy, "freedom")
        self.assertAlmostEqual(signal.metrics["ema200"], 0.95)
        self.assertEqual(signal.metrics["trend_side_count"], 5.0)
        self.assertLess(signal.metrics["bb_lower"], signal.close + 0.01)

    def test_accepts_put_with_all_four_filters(self):
        signal = self._detect(freedom_frame("put"))
        self.assertEqual(signal.direction, "put")
        self.assertEqual(signal.expiration_min, 5)

    def test_rejects_wick_only_bollinger_break(self):
        frame = freedom_frame("call")
        frame.loc[frame.index[-1], "close"] = 1.0
        self.assertIsNone(self._detect(frame))

    def test_rejects_signal_without_confirmed_trend(self):
        frame = freedom_frame("call")
        frame.loc[frame.index[-6], "ema200"] = 0.96
        self.assertIsNone(self._detect(frame))


if __name__ == "__main__":
    unittest.main()
