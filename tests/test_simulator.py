"""The whole chain below the window, against the bundled simulator.

These start a real process and read it through the real runner, so they cover
what the unit tests replace with fakes: the carriage-return progress line, the
merged streams, the exit statuses, and cancellation by signal.
"""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import support

from t48_programmer import samples, simulator
from t48_programmer.minipro import ACTIONS, Options
from t48_programmer.operation import OperationController
from t48_programmer.operations import Progress, run_action
from t48_programmer.programmer import detect_programmer, tool_version
from t48_programmer.rom_image import KIB

EEPROM = "AT28C256"
UV_EPROM = "M27C256B@DIP28"


class SimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        context = support.simulator()
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        folder = tempfile.TemporaryDirectory(prefix="t48-images-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def image(self, name: str, data: bytes) -> Path:
        path = self.folder / name
        path.write_bytes(data)
        return path

    def test_the_programmer_and_the_tool_are_found(self) -> None:
        result = detect_programmer()

        self.assertTrue(result.connected)
        self.assertEqual((result.key, result.model), ("t48", "T48"))
        self.assertEqual(tool_version(), "0.7.4")

    def test_what_is_written_is_what_is_read_back(self) -> None:
        source = self.image("source.bin", samples.filler(32 * KIB, 0x21))
        copy = self.folder / "copy.bin"
        progress: list[Progress] = []

        written = run_action(
            ACTIONS["write"], chip=EEPROM, path=source, on_progress=progress.append
        )
        read = run_action(ACTIONS["read"], chip=EEPROM, path=copy)
        verified = run_action(ACTIONS["verify"], chip=EEPROM, path=source)

        self.assertTrue(written.succeeded, written.transcript)
        self.assertIn("Verification OK", written.transcript)
        self.assertEqual(written.firmware, "00.1.31")
        self.assertTrue(read.succeeded)
        self.assertEqual(copy.read_bytes(), source.read_bytes())
        self.assertTrue(verified.succeeded)
        fractions = [p.fraction for p in progress if p.stage == "Writing Code"]
        self.assertIn(0.0, fractions)
        self.assertIn(0.52, fractions)
        self.assertEqual(fractions[-1], 1.0)

    def test_a_blank_chip_passes_a_blank_check_and_a_written_one_fails(self) -> None:
        source = self.image("source.bin", samples.filler(32 * KIB, 0x21))

        blank = run_action(ACTIONS["blank_check"], chip=EEPROM)
        run_action(ACTIONS["write"], chip=EEPROM, path=source)
        used = run_action(ACTIONS["blank_check"], chip=EEPROM)

        self.assertTrue(blank.succeeded)
        self.assertFalse(used.succeeded)
        self.assertIn("not blank", used.summary)

    def test_a_uv_eprom_cannot_be_erased_or_written_twice(self) -> None:
        first = self.image("first.bin", samples.filler(32 * KIB, 0x10))
        second = self.image("second.bin", samples.filler(32 * KIB, 0x77))

        self.assertTrue(
            run_action(ACTIONS["write"], chip=UV_EPROM, path=first).succeeded
        )
        erased = run_action(ACTIONS["erase"], chip=UV_EPROM)
        rewritten = run_action(ACTIONS["write"], chip=UV_EPROM, path=second)

        self.assertFalse(erased.succeeded)
        self.assertIn("ultraviolet", erased.summary)
        self.assertFalse(rewritten.succeeded)
        self.assertIn("does not match the image", rewritten.summary)

    def test_a_wrong_sized_image_is_refused_unless_allowed(self) -> None:
        short = self.image("short.bin", samples.acorn_rom(16 * KIB))

        refused = run_action(ACTIONS["write"], chip=EEPROM, path=short)
        allowed = run_action(
            ACTIONS["write"],
            chip=EEPROM,
            path=short,
            options=Options(size_policy="warn"),
        )

        self.assertFalse(refused.succeeded)
        self.assertIn("16384 bytes and the chip holds 32768", refused.summary)
        self.assertTrue(allowed.succeeded, allowed.transcript)
        self.assertIn("Warning: Incorrect file size", allowed.transcript)

    def test_chip_id_pin_test_logic_test_and_self_test(self) -> None:
        identified = run_action(ACTIONS["read_id"], chip=UV_EPROM)
        anonymous = run_action(ACTIONS["read_id"], chip=EEPROM)
        pins = run_action(ACTIONS["pin_check"], chip=EEPROM)
        logic = run_action(ACTIONS["logic_test"], chip="7400")
        hardware = run_action(ACTIONS["hardware_check"])
        detected = run_action(ACTIONS["detect_spi_8"])

        self.assertEqual(identified.chip_id, "0x208D")
        self.assertIn("no ID to read", anonymous.summary)
        self.assertTrue(pins.succeeded)
        self.assertIn("Pin test is not supported", pins.transcript)
        self.assertIn("Logic test successful", logic.transcript)
        self.assertIn("completed successfully", hardware.transcript)
        self.assertIn("W25Q64JV@SOIC8", detected.transcript.splitlines())

    def test_the_chips_are_kept_in_a_folder_of_the_users_own(self) -> None:
        # A fixed name in /tmp could be made first by someone else, with a link
        # in it for a write to the chip to follow.
        with mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(self.folder)}):
            os.environ.pop("T48_PROGRAMMER_SIMULATOR_STATE")
            folder = simulator.state_folder()

        self.assertEqual(folder.parent, self.folder)
        self.assertTrue(folder.name.endswith(str(os.getuid())))
        self.assertEqual(folder.stat().st_mode & 0o777, 0o700)

    def test_a_state_folder_that_is_not_a_folder_is_refused(self) -> None:
        planted = self.folder / "planted"
        planted.symlink_to(self.folder)

        with (
            mock.patch.dict(
                os.environ, {"T48_PROGRAMMER_SIMULATOR_STATE": str(planted)}
            ),
            self.assertRaises(SystemExit),
        ):
            simulator.state_folder()

    def test_an_unknown_chip_is_reported_by_name(self) -> None:
        result = run_action(ACTIONS["read_id"], chip="NOPE123")

        self.assertIn("called NOPE123", result.summary)


class SlowSimulatorTests(unittest.TestCase):
    def test_cancelling_stops_minipro_part_way(self) -> None:
        with support.simulator(delay="0.2"), tempfile.TemporaryDirectory() as folder:
            controller = OperationController()
            started = threading.Event()

            def on_progress(_update: Progress) -> None:
                started.set()
                controller.cancel()

            result = run_action(
                ACTIONS["read"],
                chip=EEPROM,
                path=Path(folder) / "never.bin",
                on_progress=on_progress,
                controller=controller,
            )

            self.assertTrue(started.is_set())
            self.assertTrue(result.cancelled)
            self.assertFalse(result.succeeded)
            self.assertFalse((Path(folder) / "never.bin").exists())

    def test_an_unplugged_programmer(self) -> None:
        with support.simulator(absent=True):
            probe = detect_programmer()
            result = run_action(ACTIONS["read_id"], chip=EEPROM)

        self.assertFalse(probe.connected)
        self.assertTrue(probe.tool_available)
        self.assertIn("not connected", result.summary)


if __name__ == "__main__":
    unittest.main()
