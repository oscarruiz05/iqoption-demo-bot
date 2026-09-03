import unittest
from assets import parse_assets
from risk import RiskManager, extract_pnl


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


if __name__ == "__main__":
    unittest.main()
