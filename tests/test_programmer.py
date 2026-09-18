from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from t48_programmer import minipro, programmer
from t48_programmer.minipro import QueryResult
from t48_programmer.programmer import (
    detect_programmer,
    firmware_warning,
    parse_firmware,
    parse_presence_output,
    tool_version,
)

OUT_OF_DATE = """\
Found T48 00.1.28 (0x11c)
Warning: T48 support is not yet complete!
Warning: Firmware is out of date.
  Expected  00.1.31 (0x11f)
  Found     00.1.28 (0x11c)
Device code: 12345678
"""


class ParsePresenceOutputTests(unittest.TestCase):
    def test_recognises_each_programmer_minipro_reports(self) -> None:
        for line, key, model in (
            ("t48: T48", "t48", "T48"),
            ("tl866ii: TL866II+", "tl866ii", "TL866II+"),
            ("tl866a: TL866CS", "tl866a", "TL866CS"),
            ("t56: T56", "t56", "T56"),
        ):
            with self.subTest(line):
                result = parse_presence_output(line + "\n")

                self.assertTrue(result.connected)
                self.assertEqual((result.key, result.model), (key, model))

    def test_no_programmer_is_not_success_despite_exit_status_zero(self) -> None:
        result = parse_presence_output("[No programmer found]\n")

        self.assertFalse(result.connected)
        self.assertIn("No programmer", result.summary)
        self.assertEqual(result.diagnostic, "[No programmer found]")

    def test_an_unrecognised_line_is_not_a_programmer(self) -> None:
        self.assertFalse(parse_presence_output("libusb: error\n").connected)
        self.assertFalse(
            parse_presence_output("[Unknown programmer version]").connected
        )


class DetectProgrammerTests(unittest.TestCase):
    def test_reports_missing_minipro(self) -> None:
        with mock.patch.object(minipro, "run_query", return_value=None):
            result = detect_programmer()

        self.assertFalse(result.connected)
        self.assertFalse(result.tool_available)
        self.assertIn("not installed", result.summary)

    def test_asks_minipro_which_programmer_is_attached(self) -> None:
        with mock.patch.object(
            minipro, "run_query", return_value=QueryResult(0, "", "t48: T48\n")
        ) as run:
            result = detect_programmer()

        self.assertTrue(result.connected)
        run.assert_called_once_with(["-k"], timeout=8.0)

    def test_a_hung_programmer_is_reported_not_raised(self) -> None:
        error = subprocess.TimeoutExpired(["minipro", "-k"], 8.0)
        with mock.patch.object(minipro, "run_query", side_effect=error):
            result = detect_programmer()

        self.assertFalse(result.connected)
        self.assertTrue(result.tool_available)
        self.assertIn("did not respond", result.summary)

    def test_an_unstartable_minipro_counts_as_missing(self) -> None:
        with mock.patch.object(minipro, "run_query", side_effect=PermissionError("no")):
            result = detect_programmer()

        self.assertFalse(result.tool_available)


class BannerTests(unittest.TestCase):
    def test_reads_the_firmware_version(self) -> None:
        self.assertEqual(parse_firmware(OUT_OF_DATE), "00.1.28")
        self.assertEqual(parse_firmware("Chip ID: 0x1234  OK"), "")

    def test_reports_out_of_date_firmware_in_one_line(self) -> None:
        self.assertEqual(
            firmware_warning(OUT_OF_DATE),
            "Warning: Firmware is out of date. Expected  00.1.31 (0x11f) "
            "Found     00.1.28 (0x11c)",
        )
        self.assertEqual(firmware_warning("Found T48 00.1.31 (0x11f)"), "")

    def test_reads_the_minipro_version(self) -> None:
        text = "minipro version 0.7.4     A free and open TL866 series programmer\n"
        with mock.patch.object(
            minipro, "run_query", return_value=QueryResult(0, "", text)
        ):
            self.assertEqual(tool_version(), "0.7.4")
        with mock.patch.object(minipro, "run_query", return_value=None):
            self.assertEqual(tool_version(), "")
        self.assertTrue(programmer.MISSING_TOOL_SUMMARY)


if __name__ == "__main__":
    unittest.main()
