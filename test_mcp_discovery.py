import unittest

from mcp_discovery import (
    MCPConfigurationError,
    classify_tool,
    validate_server_url,
)


class MCPDiscoveryTests(unittest.TestCase):
    def test_accepts_exact_official_turbo_url(self):
        self.assertEqual(
            validate_server_url(
                "turbo-options", "https://turbo-options.mcp.iqoption.com"
            ),
            "https://turbo-options.mcp.iqoption.com",
        )

    def test_rejects_http_url(self):
        with self.assertRaises(MCPConfigurationError):
            validate_server_url(
                "turbo-options", "http://turbo-options.mcp.iqoption.com"
            )

    def test_rejects_unknown_host(self):
        with self.assertRaises(MCPConfigurationError):
            validate_server_url("turbo-options", "https://example.com")

    def test_rejects_credentials_inside_url(self):
        with self.assertRaises(MCPConfigurationError):
            validate_server_url(
                "binary-options",
                "https://token@binary-options.mcp.iqoption.com",
            )

    def test_marks_order_tool_as_potential_write(self):
        self.assertTrue(classify_tool("place_order", "Open a turbo position"))

    def test_keeps_market_data_tool_read_only(self):
        self.assertFalse(classify_tool("get_candles", "Read historical candles"))

    def test_read_tools_are_not_misclassified_by_their_descriptions(self):
        self.assertFalse(classify_tool("list_assets", "Assets used to place trades"))
        self.assertFalse(classify_tool("list_positions", "Currently open positions"))
        self.assertFalse(classify_tool("get_trade_history", "Closed trades"))

    def test_marks_real_iq_order_tools_as_writes(self):
        self.assertTrue(classify_tool("place_trade"))
        self.assertTrue(classify_tool("rollover_position"))
        self.assertTrue(classify_tool("sell_position"))


if __name__ == "__main__":
    unittest.main()
