"""The real window, driven the way a person drives it, against the simulator.

These tests need PyGObject and a display. They are skipped without them, unless
T48_PROGRAMMER_REQUIRE_GTK is set, as the CI interface job sets it, so that a
broken GTK install fails the run instead of skipping these tests without anyone
noticing. Every wait is bounded.
"""

from __future__ import annotations

import dataclasses
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support

from gtk_support import HAVE_DISPLAY, pump, shared_application  # isort: skip
from gi.repository import Gdk, Gtk  # noqa: E402

from t48_programmer import samples  # noqa: E402
from t48_programmer.minipro import ACTIONS, Options  # noqa: E402
from t48_programmer.rom_image import (  # noqa: E402
    KIB,
    crc32_text,
    describe,
    open_rom,
    swap_byte_pairs,
)
from t48_programmer.rom_sets import FAMILIES_BY_KEY, LAYOUTS_BY_KEY  # noqa: E402
from t48_programmer.rom_wizard import (  # noqa: E402
    BURN,
    CHIP,
    FAILED,
    IMAGES,
    MACHINE,
    ROM,
    WAITING,
    WRITTEN,
    RomWizard,
)
from t48_programmer.window import MainWindow  # noqa: E402


@unittest.skipUnless(HAVE_DISPLAY, "No display is available.")
class WindowTestCase(unittest.TestCase):
    absent = False

    def setUp(self) -> None:
        context = support.simulator(absent=self.absent)
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        folder = tempfile.TemporaryDirectory(prefix="t48-window-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

        self.window = MainWindow(application=shared_application())
        self.addCleanup(self.window.close)
        self.window.present()
        self.window.begin_programmer_detection()
        self.assertTrue(pump(lambda: self.page == "dashboard"), "detection never ended")

    @property
    def page(self) -> str:
        return self.window._stack.get_visible_child_name()

    def enabled(self, action: str) -> bool:
        return self.window.lookup_action(action).get_enabled()

    def image(self, name: str, data: bytes) -> Path:
        path = self.folder / name
        path.write_bytes(data)
        return path

    def respond(self, response: str) -> None:
        """Answer the dialog the window has just presented."""
        dialog = self.window.last_dialog
        self.assertIsNotNone(dialog)
        dialog.response(response)
        dialog.close()

    def wait_for_result(self) -> None:
        self.window.last_result = None
        self.assertTrue(
            pump(lambda: self.window.last_result is not None), "minipro never finished"
        )


class ConnectedWindowTests(WindowTestCase):
    def test_a_connected_programmer_enables_the_hardware_commands(self) -> None:
        self.assertEqual(self.window._programmer_row.get_title(), "T48 connected")
        self.assertIn("minipro 0.7.4", self.window._programmer_row.get_subtitle())
        for action in ("read", "write", "erase", "hardware-check", "detect-spi-8"):
            with self.subTest(action):
                self.assertTrue(self.enabled(action))

    def test_choosing_a_chip_shows_its_size_and_offers_its_voltages(self) -> None:
        self.window.set_chip("M27C400@DIP40")

        self.assertEqual(self.window._chip_row.get_title(), "M27C400@DIP40")
        self.assertIn("512 KB", self.window._chip_row.get_subtitle())
        self.assertTrue(self.window.options_panel._electrical.get_visible())
        self.assertTrue(self.window.options_panel._lists["vpp"].get_visible())
        self.assertFalse(self.window.options_panel._lists["spi_clock"].get_visible())

        self.window.set_chip("AT28C256")

        self.assertFalse(self.window.options_panel._electrical.get_visible())

    def test_an_opened_image_is_identified_and_measured_against_the_chip(self) -> None:
        self.window.set_chip("M27C400@DIP40")
        self.window.load_image(self.image("kick31.rom", samples.kickstart()))

        subtitle = self.window._image_row.get_subtitle()

        self.assertEqual(self.window._image_row.get_title(), "kick31.rom")
        self.assertIn("Amiga Kickstart 3.1", subtitle)
        self.assertIn("Fits the chip exactly.", subtitle)
        self.assertFalse(self.window._image_details.get_expanded())

        self.window.set_chip("AT28C256")

        self.assertIn("the chip holds 32 KB", self.window._image_row.get_subtitle())

    def test_the_start_page_buttons_line_up(self) -> None:
        buttons = self.window._row_buttons.get_widgets()
        self.window.load_image(self.image("kick31.rom", samples.kickstart()))
        pump(lambda: False, timeout=0.3)

        self.assertEqual(
            sorted(button.get_label() for button in buttons),
            ["Choose…", "Open…", "Reconnect", "Start…"],
        )
        self.assertEqual(len({button.get_width() for button in buttons}), 1)
        # Every button ends at the same distance from the edge of the window.
        edges = {
            round(
                button.compute_bounds(self.window)[1].get_x()
                + button.compute_bounds(self.window)[1].get_width()
            )
            for button in buttons
        }
        self.assertEqual(len(edges), 1)

    def test_image_details_appear_only_when_there_is_an_image(self) -> None:
        self.assertFalse(self.window._image_details.get_visible())

        self.window.load_image(self.image("kick31.rom", samples.kickstart()))

        self.assertTrue(self.window._image_details.get_visible())

    def test_a_suspect_image_opens_its_warnings(self) -> None:
        damaged = bytearray(samples.kickstart())
        damaged[0x2000] ^= 0xFF
        self.window.load_image(self.image("bad.rom", bytes(damaged)))

        self.assertTrue(self.window._image_details.get_expanded())

    def test_an_image_deleted_after_opening_does_not_break_the_page(self) -> None:
        path = self.image("gone.rom", samples.acorn_rom())
        self.window.load_image(path)
        path.unlink()

        self.window.set_chip("27128@DIP28")

        self.assertIn("Fits the chip exactly.", self.window._image_row.get_subtitle())

    def test_commands_that_lack_a_chip_or_an_image_say_so_and_do_nothing(self) -> None:
        self.window.start_action("erase")
        self.assertEqual(self.page, "dashboard")
        self.assertIsNone(self.window.last_dialog)

        self.window.set_chip("AT28C256")
        self.window.start_action("write")

        self.assertEqual(self.page, "dashboard")
        self.assertIsNone(self.window.last_dialog)

    def test_a_write_asks_first_and_cancel_leaves_the_chip_alone(self) -> None:
        self.window.set_chip("AT28C256")
        self.window.load_image(self.image("basic.rom", samples.filler(32 * KIB, 3)))

        self.window.start_action("write")
        self.assertIn("basic.rom", self.window.last_dialog.get_body())
        self.assertIn("AT28C256", self.window.last_dialog.get_body())
        self.respond("cancel")

        self.assertEqual(self.page, "dashboard")
        self.assertIsNone(self.window.last_result)

    def short_image(self) -> bytes:
        rom = samples.acorn_rom(16 * KIB, "Micro-C")
        self.window.set_chip("AT28C256")
        self.window.load_image(self.image("micro-c.bin", rom))
        return rom

    def read_chip(self) -> bytes:
        copy = self.folder / "readback.bin"
        self.window.run_action(ACTIONS["read"], copy)
        self.wait_for_result()
        return copy.read_bytes()

    def test_a_short_image_that_divides_into_the_chip_offers_to_fill_it(self) -> None:
        self.short_image()

        self.window.start_action("write")
        dialog = self.window.last_dialog

        self.assertIn("The image is 16 KB and the chip holds 32 KB.", dialog.get_body())
        self.assertIn("writes the image twice", dialog.get_body())
        self.assertIn("BBC Micro", dialog.get_body())
        for response in ("cancel", "once", "fill"):
            with self.subTest(response):
                self.assertTrue(dialog.has_response(response))
        self.assertEqual(dialog.get_default_response(), "cancel")
        self.respond("cancel")
        self.assertIsNone(self.window.last_result)

    def test_filling_writes_the_image_twice_and_makes_that_the_current_image(
        self,
    ) -> None:
        rom = self.short_image()

        self.window.start_action("write")
        self.respond("fill")
        self.wait_for_result()

        self.assertTrue(self.window.last_result.succeeded)
        self.assertIn("Verification OK", self.window.last_result.transcript)
        self.assertEqual(self.window.image_path.name, "micro-c-x2.bin")
        self.assertEqual(self.window.image_path.read_bytes(), rom * 2)
        self.assertIn("Fits the chip exactly.", self.window._image_row.get_subtitle())
        self.assertEqual(self.read_chip(), rom * 2)

        # Verify now compares the whole chip, and a second write asks nothing more.
        self.window.show_dashboard()
        self.window.start_action("verify")
        self.wait_for_result()
        self.assertTrue(self.window.last_result.succeeded)
        self.window.start_action("write")
        self.assertFalse(self.window.last_dialog.has_response("fill"))
        self.respond("cancel")

    def test_writing_once_is_allowed_without_finding_the_option_first(self) -> None:
        rom = self.short_image()

        self.window.start_action("write")
        self.respond("once")
        self.wait_for_result()

        self.assertTrue(
            self.window.last_result.succeeded, self.window.last_result.summary
        )
        self.assertIn(
            "Warning: Incorrect file size", self.window.last_result.transcript
        )
        self.assertEqual(self.window.image_path.name, "micro-c.bin")
        chip = self.read_chip()
        self.assertEqual(chip[: 16 * KIB], rom)
        self.assertEqual(chip[16 * KIB :], b"\xff" * 16 * KIB)

    def test_filling_is_not_offered_for_a_microcontroller_or_its_data_memory(
        self,
    ) -> None:
        # Firmware written twice is not a ROM made visible. It is a mistake.
        self.short_image()
        info = self.window.chip_info
        self.assertEqual(self.window._copies_to_fill(), 2)

        self.window.chip_info = dataclasses.replace(
            info, details={**info.details, "Memory": "16384 Words + 1024 Bytes"}
        )
        self.assertEqual(self.window._copies_to_fill(), 0)

        self.window.chip_info = info
        self.window.options_panel._readers["memory"] = lambda: "data"
        self.assertEqual(self.window._copies_to_fill(), 0)

    def test_an_image_rebuilt_since_it_was_opened_is_read_again_and_not_written(
        self,
    ) -> None:
        # minipro reads the file itself. What it burned would not be what the
        # window identified and described in its confirmation.
        self.window.set_chip("AT28C256")
        path = self.image("build.bin", bytes(samples.filler(32 * KIB, 1)))
        self.window.load_image(path)
        before = dict(self.window._image_facts)["CRC-32"]
        path.write_bytes(bytes(samples.filler(32 * KIB, 2)))
        os.utime(path, ns=(1, 1))

        self.window.start_action("write")

        self.assertIsNone(self.window.last_dialog)
        self.assertIsNone(self.window.last_result)
        self.assertNotEqual(dict(self.window._image_facts)["CRC-32"], before)

        self.window.start_action("write")
        self.assertIn("build.bin", self.window.last_dialog.get_body())
        self.respond("cancel")

    def test_a_different_programmer_has_the_chip_looked_up_again(self) -> None:
        self.window.set_chip("AT28C256")
        with mock.patch.object(self.window, "set_chip") as set_chip:
            other = dataclasses.replace(self.window._programmer, key="tl866ii")
            self.window._finish_programmer_detection(other, "0.7.4", True)
            set_chip.assert_called_once_with("AT28C256")
            self.window._finish_programmer_detection(other, "0.7.4", True)
            set_chip.assert_called_once()

    def test_closing_the_window_stops_it_looking_for_a_programmer(self) -> None:
        self.assertTrue(self.window._poll_source)

        self.assertFalse(self.window._close_requested(self.window))

        self.assertEqual(self.window._poll_source, 0)

    def test_an_image_that_does_not_divide_into_the_chip_is_offered_nothing(
        self,
    ) -> None:
        self.window.set_chip("AT28C256")
        self.window.load_image(
            self.image("odd.bin", bytes(samples.filler(24 * KIB, 9)))
        )

        self.window.start_action("write")

        self.assertFalse(self.window.last_dialog.has_response("fill"))
        self.assertTrue(self.window.last_dialog.has_response("confirm"))
        self.respond("cancel")

    def test_a_confirmed_write_runs_to_a_verified_result(self) -> None:
        self.window.set_chip("AT28C256")
        self.window.load_image(self.image("basic.rom", samples.filler(32 * KIB, 3)))

        self.window.start_action("write")
        self.respond("confirm")
        self.assertEqual(self.page, "progress")
        self.wait_for_result()

        self.assertTrue(self.window.last_result.succeeded)
        self.assertEqual(self.page, "workspace")
        self.assertTrue(self.window._back_button.get_visible())
        self.assertIn("Firmware 00.1.31", self.window._programmer_row.get_subtitle())
        self.assertIn("Verification OK", "\n".join(self.window._diagnostic_log))

    def test_a_failure_returns_to_the_start_page_with_an_explanation(self) -> None:
        self.window.set_chip("M27C256B@DIP28")

        self.window.start_action("erase")
        self.respond("confirm")
        self.wait_for_result()

        self.assertFalse(self.window.last_result.succeeded)
        self.assertEqual(self.page, "dashboard")
        self.assertIn("ultraviolet", self.window.last_dialog.get_body())

    def test_operations_without_a_confirmation_run_at_once(self) -> None:
        self.window.set_chip("AT28C256")

        self.window.start_action("blank_check")
        self.wait_for_result()

        self.assertTrue(self.window.last_result.succeeded)
        self.assertEqual(self.page, "workspace")

    def test_a_read_is_identified_on_the_result_page(self) -> None:
        self.window.set_chip("27128@DIP28")
        source = self.image("view.rom", samples.acorn_rom(16 * KIB, "View"))
        self.window.load_image(source)
        self.window.start_action("write")
        self.respond("confirm")
        self.wait_for_result()
        copy = self.folder / "copy.bin"

        self.window.run_action(ACTIONS["read"], copy)
        self.wait_for_result()

        self.assertEqual(copy.read_bytes(), source.read_bytes())
        self.assertEqual(
            describe(open_rom(copy)),
            f"Acorn sideways ROM, View, 16 KB, CRC-32 {crc32_text(source.read_bytes())}",
        )

    def test_the_self_test_checks_that_the_socket_is_empty(self) -> None:
        self.window.start_action("hardware_check")

        self.assertIn("Remove it", self.window.last_dialog.get_body())
        self.respond("cancel")
        self.assertIsNone(self.window.last_result)

    def test_the_window_will_not_close_while_minipro_is_working(self) -> None:
        with support.simulator(delay="0.05"):
            self.window.set_chip("AT28C256")
            self.window.start_action("blank_check")

            self.assertTrue(self.window._close_requested(self.window))

            self.window.cancel_operation()
            self.wait_for_result()

        self.assertTrue(self.window.last_result.cancelled)
        self.assertEqual(self.page, "dashboard")
        self.assertFalse(self.window._close_requested(self.window))

    def test_options_read_back_as_the_record_minipro_is_given(self) -> None:
        self.window.set_chip("M27C256B@DIP28")
        panel = self.window.options_panel
        panel._lists["vpp"].set_selected(7)
        panel._lists["size_policy"].set_selected(1)
        panel._pulse.set_value(200)

        self.assertEqual(
            panel.options(), Options(vpp="12.5", size_policy="warn", pulse="200")
        )

        panel.reset()

        self.assertEqual(panel.options(), Options())

    def test_the_help_menu_checks_for_updates_in_the_about_window(self) -> None:
        checks = []
        self.window.app_updater.check = lambda: checks.append(True)

        self.window.lookup_action("check-updates").activate(None)

        self.assertIsNotNone(self.window.about_window)
        self.assertEqual(checks, [True])
        about = self.window.about_window

        # Asked again with About already open, it checks there and opens no second.
        self.window.lookup_action("check-updates").activate(None)

        self.assertIs(self.window.about_window, about)
        self.assertEqual(checks, [True, True])
        about.close()

    def test_the_guide_and_the_log_open_in_the_window(self) -> None:
        for action in ("help", "diagnostics"):
            with self.subTest(action):
                self.window.lookup_action(action).activate(None)
                self.assertEqual(self.page, "workspace")
                self.window.show_dashboard()


class GuideTestCase(WindowTestCase):
    """Helpers that answer the guide's questions the way its rows do."""

    def open_guide(self) -> RomWizard:
        self.window.open_rom_wizard()
        self.assertEqual(self.page, "wizard")
        return self.window.wizard

    def answer(
        self, wizard: RomWizard, family: str, layout: str, machine: str, device: str
    ):
        board = LAYOUTS_BY_KEY[layout]
        wizard.choose_family(FAMILIES_BY_KEY[family])
        wizard.choose_machine(board, machine)
        wizard.choose_chip(next(c for c in board.chips if c.device == device))

    def add(self, wizard: RomWizard, name: str, data: bytes) -> None:
        wizard.add_image(open_rom(self.image(name, data)))

    def crumbs(self, wizard: RomWizard) -> list[str]:
        return [crumb.get_child().get_label() for crumb in wizard.crumbs]


class GuideTests(GuideTestCase):
    def test_the_guide_starts_by_asking_what_is_being_programmed(self) -> None:
        wizard = self.open_guide()

        self.assertEqual(wizard.step, ROM)
        self.assertEqual(
            self.crumbs(wizard), ["ROM", "Machine", "Chip", "Images", "Burn"]
        )
        self.assertEqual(
            [crumb.get_sensitive() for crumb in wizard.crumbs],
            [True, False, False, False, False],
        )
        self.assertFalse(wizard.next_button.get_sensitive())
        self.assertFalse(wizard.back_button.get_sensitive())

    def test_each_answer_becomes_a_crumb_and_opens_the_next_step(self) -> None:
        wizard = self.open_guide()

        wizard.choose_family(FAMILIES_BY_KEY["tos"])
        self.assertEqual(wizard.step, MACHINE)
        wizard.choose_machine(LAYOUTS_BY_KEY["atari-st-six"], "ST with six chips")
        self.assertEqual(wizard.step, CHIP)
        wizard.choose_chip(LAYOUTS_BY_KEY["atari-st-six"].chips[0])
        self.assertEqual(wizard.step, IMAGES)
        self.assertFalse(wizard.next_button.get_sensitive())
        self.add(wizard, "tos104uk.img", samples.tos(192 * KIB, (1, 4)))
        self.assertTrue(wizard.next_button.get_sensitive())
        wizard.go_to(BURN)

        self.assertEqual(
            self.crumbs(wizard),
            ["TOS", "ST with six chips", "M27C256B@DIP28", "tos104uk.img", "Burn"],
        )
        self.assertTrue(all(crumb.get_sensitive() for crumb in wizard.crumbs))

    def test_a_single_tos_image_is_split_for_six_chips_or_for_two(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "tos", "atari-st-six", "six", "M27C256B@DIP28")
        self.add(wizard, "tos104uk.img", samples.tos(192 * KIB, (1, 4)))
        wizard.go_to(BURN)

        self.assertEqual(
            [part.label for part in wizard.parts],
            ["HI 0", "HI 1", "HI 2", "LO 0", "LO 1", "LO 2"],
        )

        wizard.go_to(MACHINE)
        wizard.choose_machine(LAYOUTS_BY_KEY["atari-st-two"], "two")

        # A different board needs a different chip, but the image is kept.
        self.assertEqual(wizard.step, CHIP)
        self.assertIsNone(wizard.answers.option)
        self.assertEqual(len(wizard.answers.images), 1)
        wizard.choose_chip(LAYOUTS_BY_KEY["atari-st-two"].chips[0])
        wizard.go_to(BURN)
        self.assertEqual([part.label for part in wizard.parts], ["HI", "LO"])

    def test_going_back_to_a_crumb_keeps_the_later_answers(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "kickstart", "amiga-single", "A500", "M27C400@DIP40")
        self.add(wizard, "kick13.rom", samples.kickstart(256 * KIB, 34, 5))

        wizard.crumbs[CHIP].emit("clicked")
        self.assertEqual(wizard.step, CHIP)
        wizard.choose_chip(LAYOUTS_BY_KEY["amiga-single"].chips[1])

        self.assertEqual(wizard.step, IMAGES)
        self.assertEqual(wizard.answers.images[0].path.name, "kick13.rom")
        self.assertEqual(wizard.answers.option.device, "AM27C400@DIP40")

    def test_a_different_rom_starts_the_answers_again(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "kickstart", "amiga-single", "A500", "M27C400@DIP40")

        wizard.go_to(ROM)
        wizard.choose_family(FAMILIES_BY_KEY["acorn-rom"])

        self.assertIsNone(wizard.answers.layout)
        self.assertFalse(wizard.reachable(CHIP))

    def test_an_open_image_the_guide_knows_is_carried_into_it(self) -> None:
        self.window.load_image(self.image("kick31.rom", samples.kickstart()))

        wizard = self.open_guide()

        self.assertEqual(wizard.step, MACHINE)
        self.assertEqual(wizard.answers.family.key, "kickstart")
        self.assertEqual(wizard.answers.images[0].path.name, "kick31.rom")

    def test_an_image_of_the_wrong_size_is_explained_on_the_burn_page(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "tos", "atari-ste", "STE", "M27C1001@DIP32")
        self.add(wizard, "tos104.img", samples.tos(192 * KIB, (1, 4)))

        wizard.go_to(BURN)

        self.assertEqual(wizard.parts, ())
        self.assertIn("takes an image of 256 KB", wizard.problem)
        self.assertFalse(wizard.next_button.get_sensitive())

    def test_a_kickstart_that_is_already_swapped_is_not_swapped_again(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "kickstart", "amiga-single", "A500", "M27C400@DIP40")

        self.add(wizard, "swapped.rom", swap_byte_pairs(samples.kickstart()))

        self.assertEqual(wizard.answers.images, [])
        self.assertIn("already byte-swapped", wizard.problem)
        self.assertFalse(wizard.reachable(BURN))

    def test_a_refusal_is_not_still_showing_on_another_step(self) -> None:
        wizard = self.open_guide()
        wizard.choose_family(FAMILIES_BY_KEY["tos"])
        wizard.choose_machine(LAYOUTS_BY_KEY["atari-st-six"], "six")
        wizard.use_other_chip("W27C512@DIP28", 64 * KIB)
        self.assertTrue(wizard.problem)

        wizard.go_to(MACHINE)

        self.assertEqual(wizard.problem, "")

    def test_a_guide_that_has_been_replaced_gives_up_what_it_held(self) -> None:
        # PyGObject cannot free a widget whose handlers refer back to it, so
        # the old guide lingers. It must not keep the images and chips with it.
        first = self.open_guide()
        self.answer(first, "kickstart", "amiga-single", "A500", "M27C400@DIP40")
        self.add(first, "kick31.rom", samples.kickstart())
        first.go_to(BURN)
        self.assertTrue(first.parts)

        second = self.open_guide()

        self.assertIsNot(second, first)
        self.assertEqual(first.answers.images, [])
        self.assertEqual(first.parts, ())
        self.assertIsNone(first.get_parent())
        # And it no longer hears from the window.
        self.window._set_hardware_actions_enabled(False)
        self.assertEqual(first.burn_buttons, [])

    def test_a_chip_from_the_full_list_must_be_the_size_the_board_needs(self) -> None:
        wizard = self.open_guide()
        wizard.choose_family(FAMILIES_BY_KEY["tos"])
        wizard.choose_machine(LAYOUTS_BY_KEY["atari-st-six"], "six")

        wizard.use_other_chip("W27C512@DIP28", 64 * KIB)
        self.assertEqual(wizard.step, CHIP)
        self.assertIn("needs a chip of 32 KB", wizard.problem)

        wizard.use_other_chip("AT28C256", 32 * KIB)
        self.assertEqual(wizard.step, IMAGES)
        self.assertEqual(wizard.answers.option.device, "AT28C256")
        self.assertEqual(wizard.problem, "")


class GuideBankTests(GuideTestCase):
    def test_a_16_kb_chip_takes_one_image_and_a_larger_one_takes_several(self) -> None:
        wizard = self.open_guide()
        self.answer(
            wizard, "acorn-rom", "acorn-rom", "BBC Micro Model B", "27128@DIP28"
        )
        self.add(wizard, "basic.rom", samples.acorn_rom(title="BASIC"))
        self.add(wizard, "view.rom", samples.acorn_rom(title="View"))

        self.assertEqual([rom.path.name for rom in wizard.answers.images], ["view.rom"])

        wizard.go_to(CHIP)
        wizard.choose_chip(
            next(c for c in wizard.answers.layout.chips if c.device == "AT28C256")
        )
        self.add(wizard, "basic.rom", samples.acorn_rom(title="BASIC"))

        self.assertEqual(len(wizard.answers.images), 2)
        self.assertFalse(wizard.add_image_button.get_sensitive())
        wizard.go_to(BURN)
        (part,) = wizard.parts
        self.assertEqual(part.data[: 16 * KIB], samples.acorn_rom(title="View"))
        self.assertEqual(part.data[16 * KIB :], samples.acorn_rom(title="BASIC"))

    def test_choosing_a_smaller_chip_drops_the_images_that_no_longer_fit(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "W27C512@DIP28")
        for title in ("A", "B", "C"):
            self.add(wizard, f"{title}.rom", samples.acorn_rom(title=title))

        wizard.go_to(CHIP)
        wizard.choose_chip(wizard.answers.layout.chips[2])

        self.assertEqual([rom.path.name for rom in wizard.answers.images], ["A.rom"])

    def eight_roms(self) -> RomWizard:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "SST39SF010A")
        for number in range(8):
            self.add(
                wizard, f"rom{number}.rom", samples.acorn_rom(title=f"ROM {number}")
            )
        return wizard

    def order(self, wizard: RomWizard) -> str:
        return "".join(rom.path.stem[-1] for rom in wizard.answers.images)

    def test_eight_images_fill_a_128_kb_flash_chip(self) -> None:
        wizard = self.eight_roms()

        self.assertEqual(self.order(wizard), "01234567")
        self.assertFalse(wizard.add_image_button.get_sensitive())
        wizard.go_to(BURN)
        (part,) = wizard.parts
        self.assertEqual(len(part.data), 128 * KIB)
        self.assertEqual(part.data[-16 * KIB :], samples.acorn_rom(title="ROM 7"))

    def test_an_image_is_moved_to_another_bank_and_the_chip_follows(self) -> None:
        wizard = self.eight_roms()

        wizard.move_image(7, 0)

        self.assertEqual(self.order(wizard), "70123456")
        self.assertEqual(wizard.step, IMAGES)
        wizard.go_to(BURN)
        self.assertEqual(
            wizard.parts[0].data[: 16 * KIB], samples.acorn_rom(title="ROM 7")
        )

    def test_dropping_a_row_on_another_moves_it_there(self) -> None:
        wizard = self.eight_roms()
        row = wizard.image_rows[5]
        controllers = list(row.observe_controllers())
        self.assertTrue(any(isinstance(c, Gtk.DragSource) for c in controllers))
        (target,) = [c for c in controllers if isinstance(c, Gtk.DropTarget)]

        # Row 1 is dropped on row 5. The drop is accepted, and the page is
        # rebuilt once the drop has finished and not during it.
        self.assertTrue(wizard._dropped(1, 5))
        self.assertEqual(self.order(wizard), "01234567")
        pump(lambda: self.order(wizard) != "01234567", timeout=2)

        self.assertEqual(self.order(wizard), "02345167")
        self.assertEqual(target.get_actions(), Gdk.DragAction.MOVE)

    def test_the_arrows_move_one_bank_at_a_time_and_keep_the_keyboard(self) -> None:
        wizard = self.eight_roms()
        self.assertFalse(wizard.arrows[0, -1].get_sensitive())
        self.assertFalse(wizard.arrows[7, 1].get_sensitive())

        wizard.arrows[6, 1].emit("clicked")

        self.assertEqual(self.order(wizard), "01234576")
        # ROM 6 is now last and cannot go higher, so the up arrow takes the focus.
        self.assertTrue(wizard.arrows[7, -1].is_focus())

        wizard.arrows[3, -1].emit("clicked")
        wizard.arrows[2, -1].emit("clicked")

        self.assertEqual(self.order(wizard), "03124576")
        self.assertTrue(wizard.arrows[1, -1].is_focus())

    def test_a_move_that_goes_nowhere_changes_nothing(self) -> None:
        wizard = self.eight_roms()

        for index, to in ((2, 2), (0, -1), (7, 8), (9, 0)):
            wizard.move_image(index, to)

        self.assertEqual(self.order(wizard), "01234567")

    def test_one_image_has_nothing_to_be_moved_past(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "SST39SF010A")
        self.add(wizard, "only.rom", samples.acorn_rom(title="Only"))

        self.assertEqual(wizard.arrows, {})
        controllers = list(wizard.image_rows[0].observe_controllers())
        self.assertFalse(any(isinstance(c, Gtk.DragSource) for c in controllers))

    def test_reordering_after_a_burn_marks_the_chip_as_waiting_again(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "AT28C256")
        self.add(wizard, "a.rom", samples.acorn_rom(title="A"))
        self.add(wizard, "b.rom", samples.acorn_rom(title="B"))
        wizard.go_to(BURN)
        wizard.burn(0)
        self.respond("confirm")
        self.wait_for_result()
        self.assertEqual(wizard.status, [WRITTEN])

        wizard.go_to(IMAGES)
        wizard.move_image(1, 0)
        wizard.go_to(BURN)

        # What is in the socket no longer matches what the guide would burn.
        self.assertEqual(wizard.status, [WAITING])

    def test_a_master_mos_is_shown_across_the_banks_it_takes(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "SST39SF020A")
        self.add(wizard, "mos320.rom", bytes(samples.filler(128 * KIB, 0x4D)))
        self.add(wizard, "view.rom", samples.acorn_rom(title="View"))

        self.assertEqual(wizard.spans(), [(0, 8), (8, 1)])
        self.assertEqual(wizard.banks_used(), 9)
        self.assertTrue(wizard.add_image_button.get_sensitive())

        wizard.go_to(CHIP)
        wizard.choose_chip(
            next(c for c in wizard.answers.layout.chips if c.device == "SST39SF010A")
        )

        # Eight banks hold the MOS and nothing else.
        self.assertEqual(
            [rom.path.name for rom in wizard.answers.images], ["mos320.rom"]
        )
        self.assertFalse(wizard.add_image_button.get_sensitive())

    def test_an_image_that_will_not_fit_is_refused_with_the_reason(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Micro Model B", "2764@DIP28")

        self.add(wizard, "basic.rom", samples.acorn_rom(16 * KIB, "BASIC"))

        # Leaving it out without a word would look as though nothing happened.
        self.assertEqual(wizard.answers.images, [])
        self.assertIn("basic.rom is 16 KB", wizard.problem)
        self.assertIn("8 KB chip", wizard.problem)

        wizard.go_to(CHIP)
        wizard.choose_chip(
            next(c for c in wizard.answers.layout.chips if c.device == "SST39SF010A")
        )
        self.add(wizard, "view.rom", samples.acorn_rom(title="View"))
        self.add(wizard, "mos320.rom", bytes(samples.filler(128 * KIB, 0x4D)))

        self.assertEqual([rom.path.name for rom in wizard.answers.images], ["view.rom"])
        self.assertIn("room for 112 KB more", wizard.problem)

    def test_a_smaller_chip_says_which_images_it_dropped(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "W27C512@DIP28")
        for title in ("A", "B", "C"):
            self.add(wizard, f"{title}.rom", samples.acorn_rom(title=title))

        wizard.go_to(CHIP)
        wizard.choose_chip(
            next(c for c in wizard.answers.layout.chips if c.device == "AT28C256")
        )

        self.assertEqual(
            wizard.problem, "C.rom will not fit this chip and was removed."
        )

    def test_an_image_can_be_removed(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "W27C512@DIP28")
        self.add(wizard, "a.rom", samples.acorn_rom(title="A"))
        self.add(wizard, "b.rom", samples.acorn_rom(title="B"))

        wizard.remove_image(0)

        self.assertEqual([rom.path.name for rom in wizard.answers.images], ["b.rom"])


class GuideBurnTests(GuideTestCase):
    def test_the_chips_are_burned_and_verified_one_after_another(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "tos", "atari-ste", "STE", "M27C1001@DIP32")
        self.add(wizard, "tos206.img", samples.tos())
        wizard.go_to(BURN)
        self.assertEqual(wizard.next_button.get_label(), "Burn HI and Verify")

        wizard.next_button.emit("clicked")
        self.assertIn("tos206-hi.bin", self.window.last_dialog.get_body())
        self.respond("confirm")
        self.wait_for_result()

        self.assertEqual(self.page, "wizard")
        self.assertEqual(wizard.status, [WRITTEN, WAITING])
        self.assertIn("Verification OK", self.window.last_result.transcript)
        self.assertEqual(wizard.next_button.get_label(), "Burn LO and Verify")

        wizard.next_button.emit("clicked")
        self.respond("confirm")
        self.wait_for_result()

        self.assertEqual(wizard.status, [WRITTEN, WRITTEN])
        self.assertEqual(wizard.next_button.get_label(), "All Chips Written")
        self.assertFalse(wizard.next_button.get_sensitive())

    def test_the_guide_verifies_even_when_verification_is_turned_off(self) -> None:
        self.window.options_panel._readers["skip_verify"] = lambda: True
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "AT28C256")
        self.add(wizard, "view.rom", samples.acorn_rom(title="View"))
        wizard.go_to(BURN)

        wizard.burn(0)
        self.respond("confirm")
        self.wait_for_result()

        self.assertIn("Verification OK", self.window.last_result.transcript)
        self.assertEqual(wizard.status, [WRITTEN])

    def test_a_failed_chip_stays_pending_with_the_reason(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "AT28C256")
        self.add(wizard, "view.rom", samples.acorn_rom(title="View"))
        wizard.go_to(BURN)

        # The cable comes out between the confirmation and the write.
        with support.simulator(absent=True):
            wizard.burn(0)
            self.respond("confirm")
            self.wait_for_result()

        self.assertEqual(self.page, "wizard")
        self.assertTrue(wizard.status[0].startswith(FAILED))
        self.assertIn("not connected", wizard.status[0])
        self.assertEqual(wizard.next_pending(), 0)
        self.assertIn("not connected", self.window.last_dialog.get_body())

    def test_declining_the_confirmation_burns_nothing(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "acorn-rom", "acorn-rom", "BBC Master", "AT28C256")
        self.add(wizard, "view.rom", samples.acorn_rom(title="View"))
        wizard.go_to(BURN)

        wizard.burn(0)
        self.respond("cancel")

        self.assertEqual(wizard.status, [WAITING])
        self.assertIsNone(self.window.last_result)

    def test_parts_are_saved_under_the_name_of_the_image(self) -> None:
        wizard = self.open_guide()
        self.answer(wizard, "kickstart", "amiga-pair", "A1200", "M27C400@DIP40")
        self.add(wizard, "kick31.rom", samples.kickstart())
        wizard.go_to(BURN)
        out = self.folder / "out"
        out.mkdir()

        self.window.write_parts(wizard.parts, wizard.answers.stem, out)

        self.assertEqual(
            sorted(path.name for path in out.iterdir()),
            ["kick31-hi.bin", "kick31-lo.bin"],
        )


class EncryptedKickstartWindowTests(GuideTestCase):
    KEY = bytes(range(1, 250)) * 9

    def test_a_rom_with_its_key_beside_it_is_decrypted_and_can_be_burned(self) -> None:
        rom = self.image("amiga-os-310.rom", samples.encrypted_kickstart(self.KEY))
        self.image("rom.key", self.KEY)

        self.window.load_image(rom)

        self.assertEqual(self.window.image_identity.kind, "kickstart")
        self.assertEqual(self.window.image_path.read_bytes(), samples.kickstart())
        self.assertNotEqual(self.window.image_path, rom)
        self.assertEqual(rom.read_bytes()[:11], b"AMIROMTYPE1")

        wizard = self.open_guide()
        self.assertEqual(wizard.answers.family.key, "kickstart")

    def test_a_rom_without_a_key_asks_for_one(self) -> None:
        rom = self.image("amiga-os-310.rom", samples.encrypted_kickstart(self.KEY))

        self.window.load_image(rom)

        self.assertIsNone(self.window.image_path)
        self.assertIn("no rom.key beside it", self.window.last_dialog.get_body())

    def test_a_key_that_does_not_fit_is_refused(self) -> None:
        rom = self.image("amiga-os-310.rom", samples.encrypted_kickstart(self.KEY))
        wrong = self.image("other.key", self.KEY[::-1])

        self.window.open_rom_with_key(rom, self.window._set_image, wrong)

        self.assertIsNone(self.window.image_path)
        self.assertIn("does not decrypt this ROM", self.window.last_dialog.get_body())


class OfflineWindowTests(WindowTestCase):
    absent = True

    def test_the_window_says_it_is_offline_on_every_page(self) -> None:
        self.assertTrue(self.window.offline_banner.get_revealed())
        self.assertIn("Offline", self.window.offline_banner.get_title())
        self.assertEqual(self.window._programmer_row.get_title(), "Offline")
        self.assertEqual(
            self.window._programmer_row.get_subtitle(),
            "No programmer was found on USB. minipro 0.7.4",
        )

        self.window.lookup_action("help").activate(None)

        self.assertTrue(self.window.offline_banner.get_revealed())

    def test_only_the_commands_that_need_the_programmer_are_disabled(self) -> None:
        for action in ("read", "write", "erase", "read-id", "hardware-check"):
            with self.subTest(action):
                self.assertFalse(self.enabled(action))
        for action in ("open-image", "rom-wizard", "choose-chip", "chip-info", "help"):
            with self.subTest(action):
                self.assertTrue(self.enabled(action))

    def test_a_hardware_command_reached_directly_does_nothing(self) -> None:
        self.window.set_chip("AT28C256")
        self.window.load_image(self.image("basic.rom", samples.filler(32 * KIB, 3)))

        for key in ("write", "erase", "read_id", "hardware_check"):
            with self.subTest(key):
                self.window.start_action(key)

                self.assertEqual(self.page, "dashboard")
                self.assertIsNone(self.window.last_dialog)
                self.assertIsNone(self.window.last_result)

    def test_chips_can_be_looked_up_and_images_measured_against_them(self) -> None:
        self.window.set_chip("W27C512@DIP28")
        self.window.load_image(self.image("view.rom", samples.acorn_rom()))

        self.assertIn("64 KB", self.window._chip_row.get_subtitle())
        self.assertIn("Acorn sideways ROM", self.window._image_row.get_subtitle())
        self.assertIn("the chip holds 64 KB", self.window._image_row.get_subtitle())

        self.window.show_chip_information()

        self.assertEqual(self.page, "workspace")

    def test_the_guide_prepares_and_saves_a_set_but_cannot_burn_it(self) -> None:
        self.window.open_rom_wizard()
        wizard = self.window.wizard
        board = LAYOUTS_BY_KEY["amiga-single"]
        wizard.choose_family(FAMILIES_BY_KEY["kickstart"])
        wizard.choose_machine(board, "A500")
        wizard.choose_chip(board.chips[0])
        wizard.add_image(open_rom(self.image("kick31.rom", samples.kickstart())))
        wizard.go_to(BURN)
        out = self.folder / "out"
        out.mkdir()

        self.assertTrue(wizard.burn_buttons)
        self.assertFalse(any(button.get_sensitive() for button in wizard.burn_buttons))
        self.assertFalse(wizard.next_button.get_sensitive())

        wizard.burn(0)
        self.assertIsNone(self.window.last_dialog)
        self.assertEqual(self.window.chip, "")

        self.window.write_parts(wizard.parts, wizard.answers.stem, out)
        self.assertEqual([path.name for path in out.iterdir()], ["kick31-rom.bin"])


class ConnectionChangeTests(WindowTestCase):
    def detect(self, absent: bool) -> None:
        with support.simulator(absent=absent):
            self.window._detection_active = False
            self.window.begin_programmer_detection(silent=True)
            self.assertTrue(
                pump(lambda: self.window._programmer.connected is not absent),
                "the change was never noticed",
            )

    def test_unplugging_goes_offline_and_plugging_in_comes_back(self) -> None:
        self.window.load_image(self.image("kick31.rom", samples.kickstart()))
        self.window.open_rom_wizard()
        wizard = self.window.wizard
        board = LAYOUTS_BY_KEY["amiga-single"]
        wizard.choose_machine(board, "A500")
        wizard.choose_chip(board.chips[0])
        wizard.go_to(BURN)
        button = wizard.burn_buttons[0]
        self.assertFalse(self.window.offline_banner.get_revealed())
        self.assertTrue(button.get_sensitive())
        self.assertTrue(wizard.next_button.get_sensitive())

        self.detect(absent=True)

        self.assertTrue(self.window.offline_banner.get_revealed())
        self.assertFalse(self.enabled("write"))
        self.assertFalse(button.get_sensitive())
        self.assertFalse(wizard.next_button.get_sensitive())
        self.assertIn("Programmer detection", "\n".join(self.window._diagnostic_log))

        self.detect(absent=False)

        self.assertFalse(self.window.offline_banner.get_revealed())
        self.assertTrue(self.enabled("write"))
        self.assertTrue(button.get_sensitive())
        self.assertTrue(wizard.next_button.get_sensitive())


if __name__ == "__main__":
    unittest.main()
