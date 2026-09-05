import unittest
from datetime import date
from zoneinfo import ZoneInfo
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
import numpy as np
from assets import (
    is_connection_error, next_asset_batch, parse_assets, rejection_cooldown_seconds,
)
from backtest import run_backtest
from config import REAL_CONFIRMATION_PHRASE, validate_account_mode
from performance import analyze_pnls, wilson_interval
from payout import PayoutCache, option_kind
from model_research import fit_logistic, probabilities, trade_pnls
from risk import RiskManager, extract_pnl, load_daily_risk
from strategy import detect_signal
from signals import Signal
from support_channel import bearish_rejection, bullish_rejection, cluster_levels


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

    def test_blocks_trade_that_would_exceed_daily_loss(self):
        risk = RiskManager(10, 9, 5)
        risk.record(-3)
        self.assertFalse(risk.can_trade(next_stake=3)[0])

    def test_restart_restores_only_selected_utc_day(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "trades.csv"
            path.write_text(
                "utc_time,pnl\n"
                "2026-09-03T23:59:00+00:00,-1\n"
                "2026-09-04T00:01:00+00:00,-2\n"
                "2026-09-04T00:02:00+00:00,0.8\n",
                encoding="utf-8",
            )
            risk = load_daily_risk(path, 10, 3, 5, day=date(2026, 9, 4))
            self.assertEqual(risk.trades, 2)
            self.assertAlmostEqual(risk.pnl, -1.2)
            self.assertEqual(risk.consecutive_losses, 0)

    def test_daily_boundary_uses_configured_timezone(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "trades.csv"
            path.write_text(
                "utc_time,pnl\n2026-09-04T03:30:00+00:00,-3\n"
                "2026-09-04T05:30:00+00:00,0.8\n",
                encoding="utf-8",
            )
            risk = load_daily_risk(
                path, 10, 3, 5, day=date(2026, 9, 4),
                day_timezone=ZoneInfo("America/Bogota"),
            )
            self.assertEqual(risk.trades, 1)
            self.assertAlmostEqual(risk.pnl, 0.8)


class PerformanceTests(unittest.TestCase):
    def test_break_even_reflects_asymmetric_payout(self):
        report = analyze_pnls([0.82, -1.0] * 20, minimum_trades=1, minimum_edge=0)
        self.assertAlmostEqual(report.break_even_win_rate, 1 / 1.82)
        self.assertFalse(report.validated)

    def test_small_profitable_sample_is_not_validated(self):
        report = analyze_pnls([0.82] * 8 + [-1.0] * 2, minimum_trades=200)
        self.assertFalse(report.validated)
        self.assertTrue(any("muestra insuficiente" in reason for reason in report.reasons))

    def test_wilson_interval_contains_observed_rate(self):
        low, high = wilson_interval(60, 100)
        self.assertLess(low, 0.60)
        self.assertGreater(high, 0.60)


class PayoutTests(unittest.TestCase):
    def test_uses_turbo_up_to_five_minutes(self):
        self.assertEqual(option_kind(5), "turbo")
        self.assertEqual(option_kind(15), "binary")

    def test_reads_and_caches_payout(self):
        class Client:
            calls = 0

            def get_all_profit(self):
                self.calls += 1
                return {"EURUSD": {"turbo": 0.87}}

        client = Client()
        cache = PayoutCache(client, ttl_seconds=60)
        self.assertEqual(cache.get("EURUSD", 5), 0.87)
        self.assertEqual(cache.get("EURUSD", 5), 0.87)
        self.assertEqual(client.calls, 1)


class ModelResearchTests(unittest.TestCase):
    def test_regularized_model_learns_simple_direction(self):
        feature = np.tile(np.array([-2.0, -1.0, 1.0, 2.0]), 50)
        x = np.column_stack([np.ones(len(feature)), feature])
        y = (feature > 0).astype(float)
        prediction = probabilities(x, fit_logistic(x, y, l2=0.01))
        self.assertLess(prediction[0], 0.5)
        self.assertGreater(prediction[-1], 0.5)

    def test_probability_threshold_uses_binary_payout(self):
        pnls = trade_pnls(
            np.array([0.8, 0.2, 0.51]), np.array([1.0, 1.0, 1.0]), 0.6, 0.85
        )
        self.assertEqual(pnls, [0.85, -1.0])


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

    def test_detects_reconnect_error_even_if_health_check_is_stale(self):
        self.assertTrue(is_connection_error("get_candles need reconnect"))
        self.assertTrue(is_connection_error("[WinError 10054] connection interrupted"))
        self.assertFalse(is_connection_error("active is suspended"))

    def test_asset_batches_rotate_without_duplicates(self):
        assets = ("A", "B", "C", "D", "E", "F")
        first, cursor = next_asset_batch(assets, 0, 2)
        second, cursor = next_asset_batch(assets, cursor, 2)
        third, cursor = next_asset_batch(assets, cursor, 2)
        self.assertEqual(first + second + third, assets)
        self.assertEqual(cursor, 0)

    def test_batch_size_is_limited_to_available_assets(self):
        batch, cursor = next_asset_batch(("A", "B"), 0, 5)
        self.assertEqual(batch, ("A", "B"))
        self.assertEqual(cursor, 0)

    def test_practice_does_not_require_real_confirmation(self):
        validate_account_mode("PRACTICE", True, False, "", 10, 1)

    def test_real_observation_mode_is_allowed(self):
        validate_account_mode("REAL", False, False, "", 10, 1)

    def test_real_trading_requires_explicit_enable(self):
        with self.assertRaises(ValueError):
            validate_account_mode("REAL", True, False, REAL_CONFIRMATION_PHRASE, 1, 1)

    def test_real_trading_requires_exact_confirmation(self):
        with self.assertRaises(ValueError):
            validate_account_mode("REAL", True, True, "CONFIRMO", 1, 1)

    def test_real_trading_rejects_amount_over_limit(self):
        with self.assertRaises(ValueError):
            validate_account_mode("REAL", True, True, REAL_CONFIRMATION_PHRASE, 2, 1)

    def test_real_trading_accepts_all_safeguards(self):
        validate_account_mode("REAL", True, True, REAL_CONFIRMATION_PHRASE, 1, 1)

    def test_rejects_unknown_account(self):
        with self.assertRaises(ValueError):
            validate_account_mode("DEMO", False, False, "", 1, 1)


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
                    min=last["ema20"] - 0.00025, max=last["ema20"] + 0.00095, rsi14=55)
    else:
        prev.update(open=prev["ema20"] - 0.0008, close=prev["ema20"] + 0.0001,
                    min=prev["ema20"] - 0.0010, max=prev["ema20"] + 0.0002, rsi14=50)
        last.update(open=last["ema20"] + 0.0001, close=last["ema20"] - 0.0008,
                    min=last["ema20"] - 0.00095, max=last["ema20"] + 0.00025, rsi14=45)
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

    def test_rejects_weak_adx(self):
        frame = setup_frame("call")
        frame["adx14"] = 15
        self.assertIsNone(detect_signal(frame))

    def test_requires_opposite_pullback_candle(self):
        frame = setup_frame("call")
        previous = frame.index[-2]
        frame.loc[previous, "open"] = frame.loc[previous, "close"] - 0.0002
        self.assertIsNone(detect_signal(frame))


class SupportChannelTests(unittest.TestCase):
    def test_clusters_levels_with_repeated_touches(self):
        levels = [1.1000, 1.1002, 1.1050, 1.1051, 1.1200]
        clusters = cluster_levels(levels, tolerance=0.0003)
        self.assertEqual(len(clusters), 2)
        self.assertAlmostEqual(clusters[0], 1.1001)

    def test_rejects_isolated_level(self):
        self.assertEqual(cluster_levels([1.1000, 1.1100], tolerance=0.0003), [])

    def test_detects_bullish_rejection_candle(self):
        row = {"open": 1.1004, "close": 1.1008, "min": 1.0995, "max": 1.1009}
        self.assertTrue(bullish_rejection(row))

    def test_detects_bearish_rejection_candle(self):
        row = {"open": 1.1006, "close": 1.1002, "min": 1.1001, "max": 1.1015}
        self.assertTrue(bearish_rejection(row))


class BacktestTests(unittest.TestCase):
    def test_flat_market_produces_no_trades(self):
        candles = [
            {"from": index * 300, "open": 1.0, "close": 1.0, "min": 1.0, "max": 1.0}
            for index in range(100)
        ]
        result = run_backtest(candles, payout=0.82)
        self.assertEqual(result.report.trades, 0)

    def test_backtest_never_passes_more_than_live_window(self):
        import backtest

        observed_lengths = []
        original = backtest.get_signal
        backtest.get_signal = lambda candles, strategy: observed_lengths.append(len(candles))
        try:
            run_backtest([
                {"from": index * 300, "open": 1.0, "close": 1.0,
                 "min": 1.0, "max": 1.0}
                for index in range(200)
            ])
        finally:
            backtest.get_signal = original
        self.assertTrue(observed_lengths)
        self.assertLessEqual(max(observed_lengths), 80)

    def test_skips_entry_across_timestamp_gap(self):
        import backtest

        candles = [
            {"from": index * 300, "open": 1.0, "close": 1.1,
             "min": 0.9, "max": 1.2}
            for index in range(63)
        ]
        candles[60]["from"] += 300
        candles[61]["from"] += 300
        candles[62]["from"] += 300
        original = backtest.get_signal
        backtest.get_signal = lambda rows, strategy: Signal(
            "call", rows[-1]["from"], rows[-1]["close"], 1, 1, 50, "test"
        )
        try:
            result = run_backtest(candles, payout=0.82, cooldown_bars=1)
        finally:
            backtest.get_signal = original
        self.assertNotIn(candles[59]["from"], result.signal_times)


if __name__ == "__main__":
    unittest.main()
