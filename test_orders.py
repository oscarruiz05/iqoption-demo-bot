import unittest
from types import SimpleNamespace

from orders import (
    CandleCache, closed_option_pnl, entry_slippage_atr, find_closed_option_pnl,
    order_entry_price, poll_order_pnl,
)
from payout import PayoutCache
from risk import RiskManager
from strategy import FREEDOM_MIN_CANDLES, STRATEGY_WINDOWS, get_signal


def candle(start, price=1.0):
    return {"from": start, "open": price, "close": price, "min": price, "max": price}


def closed_message(win, amount=1.0, win_amount=0.0):
    return {"msg": {"win": win, "sum": amount, "win_amount": win_amount}}


class ClosedOptionTests(unittest.TestCase):
    def test_pnl_matches_check_win_v4(self):
        self.assertAlmostEqual(closed_option_pnl(closed_message("win", 2, 3.7)), 1.7)
        self.assertEqual(closed_option_pnl(closed_message("loose", 2)), -2.0)
        self.assertEqual(closed_option_pnl(closed_message("equal", 2, 2)), 0.0)
        self.assertIsNone(closed_option_pnl({"msg": {}}))

    def test_poll_never_waits_for_missing_order(self):
        client = SimpleNamespace(api=SimpleNamespace(socket_option_closed={}))
        self.assertIsNone(poll_order_pnl(client, 7))
        client.api.socket_option_closed[7] = closed_message("loose", 1)
        self.assertEqual(poll_order_pnl(client, 7), -1.0)

    def test_fallback_finds_order_in_history(self):
        history = {"msg": {"closed_options": [
            {"id": [5], "win": "loose", "win_amount": 0, "amount": 1},
            {"id": [9], "win": "win", "win_amount": 1.85, "amount": 1},
        ]}}
        client = SimpleNamespace(get_optioninfo_v2=lambda limit: history)
        self.assertAlmostEqual(find_closed_option_pnl(client, 9), 0.85)
        self.assertEqual(find_closed_option_pnl(client, 5), -1.0)
        self.assertIsNone(find_closed_option_pnl(client, 4))

    def test_entry_price_prefers_opened_message(self):
        api = SimpleNamespace(
            socket_option_opened={3: {"msg": {"value": 1.2345}}},
            socket_option_closed={3: {"msg": {"value": 9.0}}},
        )
        self.assertEqual(order_entry_price(SimpleNamespace(api=api), 3), 1.2345)
        self.assertIsNone(order_entry_price(SimpleNamespace(api=api), 4))


class SlippageTests(unittest.TestCase):
    def test_positive_means_worse_entry(self):
        self.assertAlmostEqual(entry_slippage_atr("call", 1.0002, 1.0, 0.0004), 0.5)
        self.assertAlmostEqual(entry_slippage_atr("put", 1.0002, 1.0, 0.0004), -0.5)

    def test_rejects_missing_or_mis_scaled_prices(self):
        self.assertIsNone(entry_slippage_atr("call", None, 1.0, 0.001))
        self.assertIsNone(entry_slippage_atr("call", 1.0, 1.0, 0.0))
        self.assertIsNone(entry_slippage_atr("call", 1_000_000.0, 1.0, 0.001))


class CandleCacheTests(unittest.TestCase):
    def test_first_request_downloads_full_window(self):
        cache = CandleCache(size=10)
        self.assertEqual(cache.request_count("EURUSD", 600, 60), 10)

    def test_incremental_refresh_replaces_forming_candle(self):
        cache = CandleCache(size=10)
        cache.merge("EURUSD", [candle(t * 60) for t in range(10)])
        self.assertEqual(cache.request_count("EURUSD", 9 * 60 + 61, 60), 5)
        merged = cache.merge("EURUSD", [candle(9 * 60, 2.0), candle(10 * 60, 3.0)])
        self.assertEqual(len(merged), 10)
        self.assertEqual(merged[0]["from"], 60)
        self.assertEqual(merged[-2]["close"], 2.0)
        self.assertEqual(merged[-1]["from"], 600)

    def test_gap_forces_full_download(self):
        cache = CandleCache(size=10)
        cache.merge("EURUSD", [candle(t * 60) for t in range(10)])
        self.assertEqual(cache.request_count("EURUSD", 9 * 60 + 5 * 60, 60), 10)


class OpenExposureRiskTests(unittest.TestCase):
    def test_open_stakes_count_against_daily_loss(self):
        risk = RiskManager(max_trades=10, max_consecutive_losses=3, max_daily_loss=3)
        self.assertTrue(risk.can_trade(1, open_trades=1, open_stakes=1)[0])
        self.assertFalse(risk.can_trade(1, open_trades=2, open_stakes=2.5)[0])

    def test_open_trades_count_as_potential_losses(self):
        risk = RiskManager(max_trades=10, max_consecutive_losses=3, max_daily_loss=100)
        risk.record(-1)
        self.assertTrue(risk.can_trade(1, open_trades=1, open_stakes=1)[0])
        self.assertFalse(risk.can_trade(1, open_trades=2, open_stakes=2)[0])

    def test_open_trades_count_toward_daily_maximum(self):
        risk = RiskManager(max_trades=2, max_consecutive_losses=5, max_daily_loss=100)
        risk.record(1)
        self.assertFalse(risk.can_trade(1, open_trades=1, open_stakes=1)[0])


class PayoutPrefetchTests(unittest.TestCase):
    def test_prefetch_refreshes_before_ttl_and_get_uses_cache(self):
        calls = []
        client = SimpleNamespace(
            get_all_profit=lambda: calls.append(1) or {"EURUSD": {"turbo": 0.87}}
        )
        cache = PayoutCache(client, ttl_seconds=60)
        cache.prefetch()
        self.assertEqual(cache.get("EURUSD", 5), 0.87)
        self.assertEqual(len(calls), 1)
        cache._updated_at -= 50
        cache.prefetch(margin_seconds=15)
        self.assertEqual(len(calls), 2)


class FreedomWindowTests(unittest.TestCase):
    def test_freedom_uses_long_window_within_api_limit(self):
        for name in ("freedom", "freedom_v3", "freedom_v4"):
            self.assertGreaterEqual(STRATEGY_WINDOWS[name], FREEDOM_MIN_CANDLES)
            self.assertLessEqual(STRATEGY_WINDOWS[name] + 1, 1000)

    def test_freedom_requires_warmup(self):
        candles = [candle(t * 60) for t in range(FREEDOM_MIN_CANDLES - 1)]
        self.assertIsNone(get_signal(candles, "freedom_v4"))


if __name__ == "__main__":
    unittest.main()
