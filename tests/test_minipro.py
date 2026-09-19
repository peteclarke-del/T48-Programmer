from __future__ import annotations

import os
import sys
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path
from unittest import mock

from t48_programmer import minipro
from t48_programmer.minipro import ACTIONS, Options, build_command

BASE = ["minipro"]
IMAGE = Path("/roms/My Kickstart (3.1).rom")


class BaseCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="t48-minipro-")
        self.addCleanup(folder.cleanup)
        self.executable = Path(folder.name) / "minipro"
        self.executable.write_text("#!/bin/sh\n")
        self.executable.chmod(0o755)

    def test_uses_minipro_from_path(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("shutil.which", return_value=str(self.executable)),
        ):
            self.assertEqual(minipro.base_command(), [str(self.executable)])

    def test_is_none_when_minipro_is_not_installed(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("shutil.which", return_value=None),
        ):
            self.assertIsNone(minipro.base_command())

    def test_a_named_executable_takes_precedence(self) -> None:
        environment = {minipro.EXECUTABLE_VARIABLE: str(self.executable)}
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch("shutil.which", return_value="/usr/bin/minipro"),
        ):
            self.assertEqual(minipro.base_command(), [str(self.executable)])

    def test_a_named_executable_that_cannot_be_run_counts_as_no_minipro(self) -> None:
        # Otherwise it surfaces as an exception from the first button pressed.
        self.executable.chmod(0o644)
        for named in (str(self.executable), "/nonexistent/minipro"):
            with (
                self.subTest(named),
                mock.patch.dict(
                    os.environ, {minipro.EXECUTABLE_VARIABLE: named}, clear=True
                ),
            ):
                self.assertIsNone(minipro.base_command())

    def test_demo_mode_runs_the_bundled_simulator_by_path(self) -> None:
        with mock.patch.dict(os.environ, {minipro.DEMO_VARIABLE: "1"}, clear=True):
            command = minipro.base_command()

        self.assertEqual(command[0], sys.executable)
        self.assertTrue(Path(command[1]).is_file())
        self.assertEqual(Path(command[1]).name, "simulator.py")


class BuildCommandTests(unittest.TestCase):
    def test_read(self) -> None:
        self.assertEqual(
            build_command(BASE, ACTIONS["read"], "AT28C256", Path("/tmp/out.bin")),
            ["minipro", "-p", "AT28C256", "-r", "/tmp/out.bin"],
        )

    def test_names_with_shell_characters_stay_single_arguments(self) -> None:
        command = build_command(BASE, ACTIONS["write"], "AM27C4096(MXIC)@DIP40", IMAGE)

        self.assertEqual(
            command,
            ["minipro", "-p", "AM27C4096(MXIC)@DIP40", "-w", str(IMAGE)],
        )

    def test_actions_without_a_file(self) -> None:
        for key, flag in (("blank_check", "-b"), ("erase", "-E"), ("read_id", "-D")):
            with self.subTest(key):
                self.assertEqual(
                    build_command(BASE, ACTIONS[key], "W27C512@DIP28"),
                    ["minipro", "-p", "W27C512@DIP28", flag],
                )

    def test_actions_without_a_chip(self) -> None:
        self.assertEqual(
            build_command(BASE, ACTIONS["hardware_check"]), ["minipro", "-t"]
        )
        self.assertEqual(
            build_command(BASE, ACTIONS["detect_spi_8"]), ["minipro", "-a", "8"]
        )
        self.assertEqual(
            build_command(BASE, ACTIONS["detect_spi_16"]), ["minipro", "-a", "16"]
        )

    def test_a_missing_chip_or_file_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "chip"):
            build_command(BASE, ACTIONS["erase"])
        with self.assertRaisesRegex(ValueError, "file"):
            build_command(BASE, ACTIONS["write"], "AT28C256")

    def test_write_options(self) -> None:
        options = Options(
            skip_erase=True,
            skip_verify=True,
            unprotect=True,
            protect=True,
            size_policy="warn",
            vpp="12.5",
            pulse="200",
        )

        command = build_command(
            BASE, ACTIONS["write"], "M27C256B@DIP28", IMAGE, options
        )

        self.assertEqual(
            command[5:],
            ["-s", "-e", "-v", "-u", "-P", "-o", "vpp=12.5", "-o", "pulse=200"],
        )

    def test_options_for_another_action_are_left_out(self) -> None:
        # A programming voltage must not follow the user into a read, and
        # minipro refuses -x outright when it is writing.
        options = Options(vpp="21", skip_erase=True, skip_id=True, file_format="ihex")

        read = build_command(BASE, ACTIONS["read"], "2764@DIP28", IMAGE, options)
        write = build_command(BASE, ACTIONS["write"], "2764@DIP28", IMAGE, options)

        self.assertEqual(read[5:], ["-f", "ihex", "-x"])
        self.assertEqual(write[5:], ["-e", "-o", "vpp=21"])

    def test_size_and_icsp_choices_select_their_flags(self) -> None:
        options = Options(size_policy="ignore", icsp="no_vcc")

        command = build_command(
            BASE, ACTIONS["verify"], "ATMEGA8@DIP28", IMAGE, options
        )

        self.assertEqual(command[5:], ["-S", "-I"])

    def test_the_logic_test_takes_a_supply_voltage(self) -> None:
        command = build_command(
            BASE, ACTIONS["logic_test"], "7400", options=Options(vcc="3.3", vpp="12")
        )

        self.assertEqual(command, ["minipro", "-p", "7400", "-T", "-o", "vcc=3.3"])


class ActionTableTests(unittest.TestCase):
    def test_every_accepted_option_is_a_real_field(self) -> None:
        names = {field.name for field in fields(Options)}
        for action in ACTIONS.values():
            with self.subTest(action.key):
                self.assertLessEqual(action.options, names)

    def test_every_option_is_accepted_by_some_action(self) -> None:
        accepted = set().union(*(action.options for action in ACTIONS.values()))

        self.assertEqual(accepted, {field.name for field in fields(Options)})

    def test_only_writing_and_erasing_are_destructive(self) -> None:
        destructive = {key for key, action in ACTIONS.items() if action.destructive}

        self.assertEqual(destructive, {"write", "erase"})

    def test_skipping_the_id_is_never_offered_where_minipro_forbids_it(self) -> None:
        for key in ("write", "erase", "read_id"):
            with self.subTest(key):
                self.assertNotIn("skip_id", ACTIONS[key].options)


class RunQueryTests(unittest.TestCase):
    def test_is_none_without_minipro(self) -> None:
        with mock.patch.object(minipro, "base_command", return_value=None):
            self.assertIsNone(minipro.run_query(["-k"]))

    def test_keeps_the_streams_apart_and_closes_standard_input(self) -> None:
        import subprocess

        completed = subprocess.CompletedProcess([], 0, "AT28C256\n", "1 device\n")
        with (
            mock.patch.object(minipro, "base_command", return_value=["minipro"]),
            mock.patch("subprocess.run", return_value=completed) as run,
        ):
            result = minipro.run_query(["-q", "T48", "-l"])

        self.assertEqual(result, minipro.QueryResult(0, "AT28C256\n", "1 device\n"))
        self.assertTrue(result.succeeded)
        self.assertEqual(result.text, "AT28C256\n\n1 device\n")
        self.assertEqual(run.call_args.args[0], ["minipro", "-q", "T48", "-l"])
        self.assertEqual(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
        self.assertIn("timeout", run.call_args.kwargs)

    def test_database_name_falls_back_to_the_t48(self) -> None:
        self.assertEqual(minipro.database_name("tl866ii"), "TL866II")
        self.assertEqual(minipro.database_name(""), "T48")


if __name__ == "__main__":
    unittest.main()
