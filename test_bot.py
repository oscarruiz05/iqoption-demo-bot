import unittest
import pandas as pd
from assets import parse_assets, rejection_cooldown_seconds
from risk import RiskManager, extract_pnl
from strategy import detect_signal


class RiskTests(unittest.TestCase):
    def test_stops_after_consecutive_losses(self):
        risk = RiskManager(10, 3, 5)
        for _ in range(3):
            risk.record(-1)
        self.assertFalse(risk.can_trade()[0])

    def test_win_resets_loss_streak(self):
        risk = RiskManager(10, 3, 5)
        risk.record(-1)
        risk.record(0.8)
        self.assertEqual(risk.consecutive_losses, 0)

    def test_stops_on_daily_loss(self):
        risk = RiskManager(10, 9, 2)
        risk.record(-2)
        self.assertFalse(risk.can_trade()[0])


class ResultTests(unittest.TestCase):
    def test_extracts_pnl_from_tuple(self):
        self.assertEqual(extract_pnl((True, 0.85)), 0.85)

    def test_extracts_loss_from_tuple(self):
        self.assertEqual(extract_pnl((True, -1)), -1.0)

    def test_accepts_numeric_legacy_result(self):
        self.assertEqual(extract_pnl(0), 0.0)

    def test_rejects_unfinished_result(self):
        with self.assertRaises(ValueError):
            extract_pnl((False, None))


class ConfigTests(unittest.TestCase):
    def test_parses_multiple_assets(self):
        self.assertEqual(
            parse_assets(" audcad-otc, EURUSD-OTC, audcad-otc, "),
            ("AUDCAD-OTC", "EURUSD-OTC"),
        )

    def test_rejects_empty_items(self):
        self.assertEqual(parse_assets(" , , "), ())

    def test_suspended_asset_uses_long_cooldown(self):
        self.assertEqual(
            rejection_cooldown_seconds("Cannot purchase an option (active is suspended)"),
            900,
        )

    def test_unknown_rejection_uses_default_cooldown(self):
        self.assertEqual(rejection_cooldown_seconds("temporary error"), 300)


def setup_frame(direction: str) -> pd.DataFrame:
    bullish = direction == "call"
    rows = []
    for index in range(21):
        ema20 = 1.0000 + index * 0.0001 if bullish else 1.0000 - index * 0.0001
        ema50 = ema20 - 0.002 if bullish else ema20 + 0.002
        rows.append({
            "from": index,
            "open": ema20,
            "close": ema20,
            "min": ema20 - 0.001,
            "max": ema20 + 0.001,
            "ema20": ema20,
            "ema50": ema50,
            "rsi14": 50,
        })

    prev, last = rows[-2], rows[-1]
    if bullish:
        prev.update(open=prev["ema20"] + 0.0008, close=prev["ema20"] - 0.0001,
                    min=prev["ema20"] - 0.0002, max=prev["ema20"] + 0.0010, rsi14=50)
        last.update(open=last["ema20"] - 0.0001, close=last["ema20"] + 0.0008,
                    min=last["ema20"] - 0.0002, max=last["ema20"] + 0.0009, rsi14=55)
    else:
        prev.update(open=prev["ema20"] - 0.0008, close=prev["ema20"] + 0.0001,
                    min=prev["ema20"] - 0.0010, max=prev["ema20"] + 0.0002, rsi14=50)
        last.update(open=last["ema20"] + 0.0001, close=last["ema20"] - 0.0008,
                    min=last["ema20"] - 0.0009, max=last["ema20"] + 0.0002, rsi14=45)
    return pd.DataFrame(rows)


class StrategyTests(unittest.TestCase):
    def test_accepts_strict_call_setup(self):
        self.assertEqual(detect_signal(setup_frame("call")).direction, "call")

    def test_accepts_strict_put_setup(self):
        self.assertEqual(detect_signal(setup_frame("put")).direction, "put")

    def test_rejects_large_confirmation_candle(self):
        frame = setup_frame("call")
        frame.loc[frame.index[-1], "max"] += 0.004
        self.assertIsNone(detect_signal(frame))

    def test_rejects_rsi_without_momentum(self):
        frame = setup_frame("call")
        frame.loc[frame.index[-1], "rsi14"] = 49
        self.assertIsNone(detect_signal(frame))


if __name__ == "__main__":
    unittest.main()
