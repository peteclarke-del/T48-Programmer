from __future__ import annotations

import signal
import subprocess
import sys
import time
import unittest
from unittest import mock
from unittest.mock import Mock

from t48_programmer import operation
from t48_programmer.operation import OperationController


def running_process() -> Mock:
    process = Mock()
    process.poll.return_value = None
    return process


class OperationControllerTests(unittest.TestCase):
    def test_cancel_interrupts_the_registered_process(self) -> None:
        controller = OperationController()
        process = running_process()
        controller.register(process)

        controller.cancel()

        self.assertTrue(controller.cancelled)
        process.send_signal.assert_called_once_with(signal.SIGINT)

    def test_a_process_registered_after_cancel_is_interrupted_at_once(self) -> None:
        controller = OperationController()
        controller.cancel()
        process = running_process()

        controller.register(process)

        process.send_signal.assert_called_once_with(signal.SIGINT)

    def test_a_finished_process_is_left_alone(self) -> None:
        controller = OperationController()
        process = Mock()
        process.poll.return_value = 0
        controller.register(process)

        controller.cancel()

        process.send_signal.assert_not_called()

    def test_an_unregistered_process_is_not_signalled(self) -> None:
        controller = OperationController()
        process = running_process()
        controller.register(process)
        controller.unregister(process)

        controller.cancel()

        process.send_signal.assert_not_called()

    def test_a_process_that_exits_during_delivery_is_not_an_error(self) -> None:
        controller = OperationController()
        process = running_process()
        process.send_signal.side_effect = ProcessLookupError()
        controller.register(process)

        controller.cancel()

        self.assertTrue(controller.cancelled)


class StubbornProcessTests(unittest.TestCase):
    def test_a_process_that_ignores_the_interrupt_is_killed_soon_after(self) -> None:
        # minipro has no SIGINT handler today. Were it to grow one, the Cancel
        # button, already spent, would leave the user to wait out the timeout.
        script = (
            "import signal, time\n"
            "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
            "print('ready', flush=True)\n"
            "time.sleep(60)\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", script], stdout=subprocess.PIPE, text=True
        )
        self.addCleanup(process.stdout.close)
        self.assertEqual(process.stdout.readline().strip(), "ready")
        controller = OperationController()
        controller.register(process)

        with mock.patch.object(operation, "KILL_AFTER_SECONDS", 0.3):
            started = time.monotonic()
            controller.cancel()
            status = process.wait(timeout=10)

        self.assertEqual(status, -signal.SIGKILL)
        self.assertLess(time.monotonic() - started, 5)


if __name__ == "__main__":
    unittest.main()
