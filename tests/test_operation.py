from __future__ import annotations

import signal
import unittest
from unittest.mock import Mock

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


if __name__ == "__main__":
    unittest.main()
