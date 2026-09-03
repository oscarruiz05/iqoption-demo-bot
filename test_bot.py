import unittest
from risk import RiskManager


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


if __name__ == "__main__":
    unittest.main()
