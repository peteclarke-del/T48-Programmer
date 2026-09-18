from __future__ import annotations

import io
import subprocess
import sys
import unittest
from unittest.mock import Mock

from t48_programmer.subprocess_runner import clean_line, run_streaming_process


def fake_process(lines: list[str], return_code: int = 0) -> Mock:
    process = Mock()
    process.stdout = io.StringIO("".join(lines))
    process.wait.return_value = return_code
    process.poll.return_value = return_code
    return process


def run_python(script: str, **kwargs: object):
    return run_streaming_process([sys.executable, "-c", script], **kwargs)


class CleanLineTests(unittest.TestCase):
    def test_removes_the_erase_line_escape_minipro_redraws_with(self) -> None:
        self.assertEqual(
            clean_line("\x1b[KReading Code...  37%\n"), "Reading Code...  37%"
        )

    def test_removes_the_bell_rung_on_overcurrent(self) -> None:
        self.assertEqual(
            clean_line("Overcurrent protection!\x07\n"), "Overcurrent protection!"
        )


class StreamingProcessTests(unittest.TestCase):
    def test_streams_output_and_unregisters_process(self) -> None:
        process = fake_process(["first\n", "\n", "second\r\n"])
        controller = Mock(cancelled=False)
        lines: list[str] = []

        result = run_streaming_process(
            ["minipro", "-k"],
            timeout=10,
            on_line=lines.append,
            controller=controller,
            process_factory=Mock(return_value=process),
        )

        self.assertEqual(lines, ["first", "second"])
        self.assertEqual(result.output, "first\nsecond")
        self.assertEqual(result.return_code, 0)
        self.assertFalse(result.timed_out)
        self.assertFalse(result.cancelled)
        controller.register.assert_called_once_with(process)
        controller.unregister.assert_called_once_with(process)
        self.assertTrue(process.stdout.closed)

    def test_closes_standard_input_so_minipro_cannot_wait_for_an_answer(self) -> None:
        factory = Mock(return_value=fake_process([]))

        run_streaming_process(["minipro", "-l"], timeout=10, process_factory=factory)

        self.assertEqual(factory.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(factory.call_args.kwargs["stderr"], subprocess.STDOUT)

    def test_a_carriage_return_ends_a_line_in_a_real_process(self) -> None:
        # minipro redraws progress with a bare carriage return and no newline.
        script = (
            "import sys\n"
            "for p in (0, 50, 100):\n"
            "    sys.stderr.write(f'\\r\\x1b[KReading Code...  {p:2d}%')\n"
            "sys.stderr.write('\\r\\x1b[KReading Code...  0.5 Sec  OK\\n')\n"
        )
        lines: list[str] = []

        result = run_python(script, timeout=20, on_line=lines.append)

        self.assertEqual(result.return_code, 0)
        self.assertEqual(
            lines,
            [
                "Reading Code...   0%",
                "Reading Code...  50%",
                "Reading Code...  100%",
                "Reading Code...  0.5 Sec  OK",
            ],
        )

    def test_a_process_that_outlives_the_timeout_is_killed(self) -> None:
        result = run_python("import time; time.sleep(30)", timeout=0.3)

        self.assertTrue(result.timed_out)
        self.assertNotEqual(result.return_code, 0)

    def test_callback_failure_kills_running_process_and_unregisters_it(self) -> None:
        process = fake_process(["line\n"])
        process.poll.return_value = None
        controller = Mock(cancelled=False)

        def fail(_line: str) -> None:
            raise RuntimeError("callback failed")

        with self.assertRaisesRegex(RuntimeError, "callback failed"):
            run_streaming_process(
                ["minipro", "-r", "x"],
                timeout=10,
                on_line=fail,
                controller=controller,
                process_factory=Mock(return_value=process),
            )

        process.kill.assert_called_once_with()
        process.wait.assert_called_once_with()
        controller.unregister.assert_called_once_with(process)


if __name__ == "__main__":
    unittest.main()
