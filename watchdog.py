"""Vigilante del ciclo principal contra esperas infinitas de iqoptionapi.

Varias funciones de la API (get_candles, get_optioninfo_v2, connect) esperan la
respuesta del WebSocket en un bucle sin límite de tiempo. Si la conexión cae en
ese momento, el bot queda congelado indefinidamente.
"""

from __future__ import annotations

import _thread
import threading
import time
from typing import Callable


# Código de salida que run_bot.ps1 interpreta como "reiniciar".
WATCHDOG_EXIT_CODE = 3


class Watchdog:
    def __init__(
        self,
        stall_seconds: float,
        hard_exit_seconds: float,
        on_soft_stall: Callable[[float], None],
        on_hard_stall: Callable[[float], None],
        *,
        check_interval: float = 5.0,
        interrupt: Callable[[], None] = _thread.interrupt_main,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.stall_seconds = stall_seconds
        self.hard_exit_seconds = hard_exit_seconds
        self.on_soft_stall = on_soft_stall
        self.on_hard_stall = on_hard_stall
        self.check_interval = check_interval
        self._interrupt = interrupt
        self._clock = clock
        self._lock = threading.Lock()
        self._last_beat = clock()
        self._interrupted_at: float | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.beat()
        self._thread = threading.Thread(target=self._run, name="watchdog", daemon=True)
        self._thread.start()

    def beat(self) -> None:
        """El ciclo principal avanza: se descarta cualquier interrupción previa."""
        with self._lock:
            self._last_beat = self._clock()
            self._interrupted_at = None

    def take_interrupt(self) -> bool:
        """True si el KeyboardInterrupt actual lo provocó el vigilante."""
        with self._lock:
            fired = self._interrupted_at is not None
            self._interrupted_at = None
            # La reconexión forzada cuenta como avance para no repetir la interrupción.
            self._last_beat = self._clock()
            return fired

    def check(self) -> None:
        """Una revisión; separada de _run para poder probarla sin hilos."""
        with self._lock:
            now = self._clock()
            stalled = now - self._last_beat
            interrupted_at = self._interrupted_at
            if interrupted_at is None and stalled >= self.stall_seconds:
                self._interrupted_at = now
                action = "soft"
            elif interrupted_at is not None and now - interrupted_at >= self.hard_exit_seconds:
                action = "hard"
            else:
                return
        if action == "soft":
            self.on_soft_stall(stalled)
            self._interrupt()
        else:
            self.on_hard_stall(stalled)

    def _run(self) -> None:
        while True:
            time.sleep(self.check_interval)
            self.check()
