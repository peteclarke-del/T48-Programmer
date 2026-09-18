"""Thread-safe cancellation for minipro subprocess operations."""

from __future__ import annotations

import signal
import subprocess
import threading

# How long an interrupted minipro is given to go before it is killed.
KILL_AFTER_SECONDS = 5.0


class OperationController:
    """Cancel a running minipro by delivering the terminal interrupt.

    minipro installs no SIGINT handler, so the interrupt ends it at once and
    the USB transaction is abandoned where it stood. That is harmless for a
    read or a verify. After a write or an erase the chip holds whatever had
    been programmed so far, which is why the window asks before cancelling
    those.

    Should a future minipro catch the interrupt and carry on, it is killed a
    few seconds later. Without that the Cancel button, already spent, would
    leave the user to wait out the full timeout of the operation.
    """

    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def register(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._process = process
            cancelled = self._cancelled.is_set()
        if cancelled:
            self._interrupt(process)

    def unregister(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._process is process:
                self._process = None

    def cancel(self) -> None:
        self._cancelled.set()
        with self._lock:
            process = self._process
        if process is not None:
            self._interrupt(process)

    @classmethod
    def _interrupt(cls, process: subprocess.Popen[str]) -> None:
        cls._signal(process, signal.SIGINT)
        backstop = threading.Timer(
            KILL_AFTER_SECONDS, cls._signal, (process, signal.SIGKILL)
        )
        backstop.daemon = True
        backstop.start()

    @staticmethod
    def _signal(process: subprocess.Popen[str], number: int) -> None:
        try:
            if process.poll() is None:
                process.send_signal(number)
        except OSError:
            # The process exited between poll() and signal delivery.
            pass
