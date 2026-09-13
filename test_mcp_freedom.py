import unittest

from mcp_discovery import MCPConfigurationError
from mcp_freedom import (
    choose_expiration,
    normalize_candles,
    select_assets,
    select_balance,
)


class MCPFreedomHelpersTests(unittest.TestCase):
    def test_selects_training_balance(self):
        rows = [
            {"balance_id": 1, "type": "regular"},
            {"balance_id": 2, "type": "training"},
        ]
        self.assertEqual(select_balance(rows, "TRAINING")["balance_id"], 2)

    def test_refuses_missing_requested_balance(self):
        with self.assertRaises(MCPConfigurationError):
            select_balance([{"balance_id": 1, "type": "regular"}], "TRAINING")

    def test_selects_only_requested_open_assets(self):
        rows = [
            {"asset_id": 1, "name": "EURUSD-OTC", "is_open": True},
            {"asset_id": 2, "name": "GBPUSD-OTC", "is_open": False},
            {"asset_id": 3, "name": "AUDCAD-OTC", "is_open": True},
        ]
        selected = select_assets(rows, {"EURUSD-OTC", "GBPUSD-OTC"})
        self.assertEqual([row["asset_id"] for row in selected], [1])

    def test_uses_an_expiration_offered_by_the_server(self):
        offered = [1300, 1600, 1900]
        self.assertEqual(choose_expiration(offered, 5, now=1000), 1300)

    def test_drops_currently_forming_candle(self):
        payload = {
            "candles": [
                {"from": 900, "open": 1, "close": 2, "min": 1, "max": 2},
                {"from": 960, "open": 2, "close": 3, "min": 2, "max": 3},
            ]
        }
        result = normalize_candles(payload, now=1000)
        self.assertEqual([row["from"] for row in result], [900])


if __name__ == "__main__":
    unittest.main()
