import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from orders import PendingOrder, load_pending_orders, save_pending_orders
from signals import Signal
from watchdog import Watchdog


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.events = []
        self.watchdog = Watchdog(
            180, 120,
            lambda stalled: self.events.append(("soft", stalled)),
            lambda stalled: self.events.append(("hard", stalled)),
            interrupt=lambda: self.events.append(("interrupt", None)),
            clock=self.clock,
        )

    def test_no_action_while_loop_advances(self):
        for _ in range(10):
            self.clock.now += 60
            self.watchdog.beat()
            self.watchdog.check()
        self.assertEqual(self.events, [])

    def test_stall_interrupts_once_then_exits(self):
        self.clock.now = 180
        self.watchdog.check()
        self.assertEqual([e[0] for e in self.events], ["soft", "interrupt"])
        self.clock.now = 250
        self.watchdog.check()
        self.assertEqual(len(self.events), 2)
        self.clock.now = 300
        self.watchdog.check()
        self.assertEqual(self.events[-1], ("hard", 300))

    def test_beat_after_interrupt_cancels_hard_exit(self):
        self.clock.now = 180
        self.watchdog.check()
        self.clock.now = 200
        self.watchdog.beat()
        self.clock.now = 330
        self.watchdog.check()
        self.assertNotIn("hard", [e[0] for e in self.events])
        # Una interrupción ya cancelada no se confunde con un Ctrl+C del usuario.
        self.assertFalse(self.watchdog.take_interrupt())

    def test_take_interrupt_identifies_watchdog_and_resets_timer(self):
        self.clock.now = 180
        self.watchdog.check()
        self.assertTrue(self.watchdog.take_interrupt())
        self.assertFalse(self.watchdog.take_interrupt())
        self.clock.now = 300
        self.watchdog.check()
        self.assertEqual([e[0] for e in self.events], ["soft", "interrupt"])


class PendingPersistenceTests(unittest.TestCase):
    def test_round_trip_and_cleanup(self):
        signal = Signal("call", 120, 1.1, 1.0, 1.0, 30.0, "test", "freedom_v4", 5,
                        {"atr14": 0.0004})
        order = PendingOrder(77, "AUDUSD", signal, 3.0, 5, 1_800_000_000.0,
                             quoted_payout=0.86, reference_open=1.1)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pending_orders.json"
            self.assertEqual(load_pending_orders(path), {})
            save_pending_orders(path, {77: order})
            self.assertEqual(load_pending_orders(path), {77: order})
            save_pending_orders(path, {})
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
