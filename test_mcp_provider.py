import unittest

from mcp_discovery import MCPConfigurationError
from mcp_provider import MCPAccessPolicy


class MCPAccessPolicyTests(unittest.TestCase):
    def test_allows_reads_on_turbo(self):
        MCPAccessPolicy("turbo-options", "read-only").validate("get_candles")

    def test_blocks_writes_on_turbo_even_if_enabled(self):
        policy = MCPAccessPolicy("turbo-options", "read-only", allow_writes=True)
        with self.assertRaises(MCPConfigurationError):
            policy.validate("place_trade", balance_type="training")

    def test_blocks_binary_write_when_switch_is_off(self):
        policy = MCPAccessPolicy("binary-options", "read-write")
        with self.assertRaises(MCPConfigurationError):
            policy.validate("place_trade", balance_type="training")

    def test_allows_training_when_binary_write_is_enabled(self):
        policy = MCPAccessPolicy(
            "binary-options", "read-write", allow_writes=True
        )
        policy.validate("place_trade", balance_type="training")

    def test_blocks_regular_balance_by_default(self):
        policy = MCPAccessPolicy(
            "binary-options", "read-write", allow_writes=True
        )
        with self.assertRaises(MCPConfigurationError):
            policy.validate("place_trade", balance_type="regular")

    def test_real_requires_two_explicit_switches(self):
        policy = MCPAccessPolicy(
            "binary-options",
            "read-write",
            allow_writes=True,
            allow_real=True,
        )
        policy.validate("place_trade", balance_type="regular")


if __name__ == "__main__":
    unittest.main()
