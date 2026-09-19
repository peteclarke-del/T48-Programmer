from __future__ import annotations

import time
import unittest
from pathlib import Path
from unittest import mock

from t48_programmer import minipro
from t48_programmer.minipro import ACTIONS, Options
from t48_programmer.operations import (
    Progress,
    explain_failure,
    is_transient,
    parse_progress,
    run_action,
)
from t48_programmer.subprocess_runner import StreamingProcessResult

WRITE_TRANSCRIPT = [
    "Found T48 00.1.31 (0x11f)",
    "Warning: T48 support is not yet complete!",
    "Chip ID: 0xDA08  OK",
    "Erasing...",
    "Erasing... 0.31 Sec  OK",
    "Writing Code...",
    "Writing Code...   0%",
    "Writing Code...  50%",
    "Writing Code...  100%",
    "Writing Code...  8.12 Sec  OK",
    "Reading Code...  1.04 Sec  OK",
    "Verification OK",
]


def fake_runner(lines: list[str], return_code: int = 0, **flags: bool):
    """A runner that replays minipro output without starting a process."""
    calls: list[list[str]] = []

    def runner(command, *, timeout, on_line, controller):
        calls.append(list(command))
        for line in lines:
            on_line(line)
        return StreamingProcessResult(
            return_code,
            "\n".join(lines),
            flags.get("timed_out", False),
            flags.get("cancelled", False),
        )

    runner.calls = calls
    return runner


class ParseProgressTests(unittest.TestCase):
    def test_a_percentage(self) -> None:
        self.assertEqual(
            parse_progress("Reading Code...  37%"), Progress("Reading Code", 0.37)
        )
        self.assertEqual(
            parse_progress("Writing Code...   0%"), Progress("Writing Code", 0)
        )

    def test_the_start_of_a_stage_has_no_fraction(self) -> None:
        self.assertEqual(parse_progress("Erasing..."), Progress("Erasing"))

    def test_the_end_of_a_stage_is_complete(self) -> None:
        for line in (
            "Reading Code...  2.41 Sec  OK",
            "Erasing... 310 ms  OK",
            "Writing Code...  1m 12 Sec  OK",
        ):
            with self.subTest(line):
                self.assertEqual(parse_progress(line).fraction, 1.0)

    def test_a_line_of_nothing_but_dots_is_read_at_once(self) -> None:
        # The regular expression this replaced took 17 seconds over this line.
        line = "." * 24_000 + " OK"
        started = time.perf_counter()

        for _ in range(50):
            parse_progress(line)
            is_transient(line)

        self.assertLess(time.perf_counter() - started, 0.5)
        self.assertIsNone(parse_progress("... OK"))
        self.assertIsNone(parse_progress("Reading Code...  OKAY"))

    def test_the_release_draws_its_stages_a_little_differently(self) -> None:
        # No space before "Sec", and two spaces in the name while it runs.
        self.assertEqual(
            parse_progress("Reading Code...  2.41Sec  OK"),
            Progress("Reading Code", 1.0),
        )
        self.assertEqual(
            parse_progress("Erasing... 0.31Sec OK"), Progress("Erasing", 1.0)
        )
        self.assertEqual(
            parse_progress("Writing  Code...  37%"), Progress("Writing Code", 0.37)
        )

    def test_other_lines_are_not_progress(self) -> None:
        for line in (
            "Verification OK",
            "Chip ID: 0xDA08  OK",
            "Found T48 00.1.31 (0x11f)",
        ):
            with self.subTest(line):
                self.assertIsNone(parse_progress(line))

    def test_redrawn_lines_are_transient_and_results_are_not(self) -> None:
        self.assertTrue(is_transient("Writing Code...  50%"))
        self.assertTrue(is_transient("Erasing..."))
        self.assertFalse(is_transient("Writing Code...  8.12 Sec  OK"))
        self.assertFalse(is_transient("Verification OK"))


class ExplainFailureTests(unittest.TestCase):
    def test_each_message_minipro_prints(self) -> None:
        cases = (
            ("No programmer found.", "not connected"),
            ("\nOvercurrent protection!", "too much current"),
            (
                "Invalid Chip ID: expected 0xDA08, got 0x1E8C (AT27C256R)",
                "expected 0xDA08, read 0x1E8C",
            ),
            (
                "Verification failed at address 0x01F0: File=0x4E, Device=0x4C",
                "starting at address 0x01F0",
            ),
            (
                "Incorrect file size: 16384 (needed 32768, use -s/S to ignore)",
                "16384 bytes and the chip holds 32768",
            ),
            ("This device is not blank.", "not blank"),
            ("This chip can't be erased!", "ultraviolet"),
            ("This chip may be write-protected. Use -u and try again.", "Remove Write"),
            ("Bad contact on pin:14", "Pin 14"),
            ("This chip doesn't have a chip ID!", "no ID to read"),
            ("Logic test failed: 3 errors encountered.", "3 wrong pin states"),
            ("\nDevice NOPE123 not found!", "called NOPE123"),
        )
        for transcript, expected in cases:
            with self.subTest(transcript):
                self.assertIn(expected, explain_failure(transcript))

    def test_a_failed_blank_check_is_not_described_as_a_failed_verify(self) -> None:
        line = "Verification failed at address 0x0000: File=0xFF, Device=0x11"

        self.assertIn("not blank", explain_failure(line, "blank_check"))
        self.assertIn("address 0x0000", explain_failure(line, "blank_check"))
        self.assertIn("does not match the image", explain_failure(line, "verify"))

    def test_an_unrecognised_failure_is_left_to_the_caller(self) -> None:
        self.assertEqual(explain_failure("IO error: bulk transfer"), "")


class RunActionTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(minipro, "base_command", return_value=["minipro"])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_successful_write(self) -> None:
        runner = fake_runner(WRITE_TRANSCRIPT)
        progress: list[Progress] = []

        result = run_action(
            ACTIONS["write"],
            chip="W27C512@DIP28",
            path=Path("/roms/basic2.rom"),
            options=Options(vpp="12"),
            on_progress=progress.append,
            runner=runner,
        )

        self.assertTrue(result.succeeded)
        self.assertEqual(result.summary, "Write Image to Chip finished.")
        self.assertEqual(result.chip_id, "0xDA08")
        self.assertEqual(result.firmware, "00.1.31")
        self.assertEqual(
            runner.calls,
            [
                [
                    "minipro",
                    "-p",
                    "W27C512@DIP28",
                    "-w",
                    "/roms/basic2.rom",
                    "-o",
                    "vpp=12",
                ]
            ],
        )
        self.assertEqual(progress[0], Progress("Erasing"))
        self.assertIn(Progress("Writing Code", 0.5), progress)
        self.assertEqual(progress[-1], Progress("Reading Code", 1.0))

    def test_the_transcript_keeps_results_and_drops_redrawn_lines(self) -> None:
        result = run_action(
            ACTIONS["write"],
            chip="W27C512@DIP28",
            path=Path("x.bin"),
            runner=fake_runner(WRITE_TRANSCRIPT),
        )

        self.assertNotIn("50%", result.transcript)
        self.assertNotIn("Erasing...\n", result.transcript + "\n")
        self.assertIn("Erasing... 0.31 Sec  OK", result.transcript)
        self.assertTrue(result.transcript.endswith("Verification OK"))

    def test_a_failure_is_explained(self) -> None:
        lines = ["Found T48 00.1.31 (0x11f)", "This chip can't be erased!"]

        result = run_action(
            ACTIONS["erase"], chip="M27C256B@DIP28", runner=fake_runner(lines, 1)
        )

        self.assertFalse(result.succeeded)
        self.assertIn("ultraviolet", result.summary)

    def test_an_unexplained_failure_gives_the_exit_status(self) -> None:
        result = run_action(
            ACTIONS["read_id"], chip="AT28C256", runner=fake_runner(["IO error"], 1)
        )

        self.assertEqual(result.summary, "minipro reported a problem (exit status 1).")

    def test_cancelled_and_timed_out_are_reported_as_such(self) -> None:
        cancelled = run_action(
            ACTIONS["read"],
            chip="AT28C256",
            path=Path("x.bin"),
            runner=fake_runner([], -2, cancelled=True),
        )
        hung = run_action(
            ACTIONS["read"],
            chip="AT28C256",
            path=Path("x.bin"),
            runner=fake_runner([], -9, timed_out=True),
        )

        self.assertTrue(cancelled.cancelled)
        self.assertEqual(cancelled.summary, "Read Chip to File was cancelled.")
        self.assertFalse(hung.succeeded)
        self.assertIn("stopped responding", hung.summary)

    def test_nothing_that_goes_wrong_is_allowed_to_escape_the_worker(self) -> None:
        # The window learns that an operation is over only from the result. An
        # exception lost in the thread would leave it on the progress page,
        # refusing every command and refusing to close.
        def runner(*_args: object, **_kwargs: object):
            raise MemoryError("out of memory")

        result = run_action(ACTIONS["read_id"], chip="AT28C256", runner=runner)

        self.assertFalse(result.succeeded)
        self.assertIn("stopped unexpectedly", result.summary)
        self.assertIn("MemoryError", result.summary)

        missing_file = run_action(
            ACTIONS["write"], chip="AT28C256", runner=fake_runner([])
        )
        self.assertFalse(missing_file.succeeded)
        self.assertIn("needs a file", missing_file.summary)

    def test_without_minipro_nothing_is_run(self) -> None:
        runner = fake_runner([])
        with mock.patch.object(minipro, "base_command", return_value=None):
            result = run_action(ACTIONS["read_id"], chip="AT28C256", runner=runner)

        self.assertFalse(result.succeeded)
        self.assertIn("not installed", result.summary)
        self.assertEqual(runner.calls, [])

    def test_a_minipro_that_cannot_start_is_reported(self) -> None:
        def runner(*_args: object, **_kwargs: object):
            raise FileNotFoundError("minipro")

        result = run_action(ACTIONS["read_id"], chip="AT28C256", runner=runner)

        self.assertIn("could not be started", result.summary)


if __name__ == "__main__":
    unittest.main()
