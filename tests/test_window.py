"""The real window, driven the way a person drives it, against the simulator.

These tests need PyGObject and a display. They are skipped without them, unless
T48_PROGRAMMER_REQUIRE_GTK is set, as the CI interface job sets it, so that a
broken GTK install fails the run instead of skipping these tests without anyone
noticing. Every wait is bounded.
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

import support

REQUIRE_GTK = bool(os.environ.get("T48_PROGRAMMER_REQUIRE_GTK"))

try:
    # The package comes first: importing it clears a Snap's GTK paths.
    from t48_programmer.application import ProgrammerApplication  # isort: skip
    import gi
except ImportError as error:
    if REQUIRE_GTK:
        raise
    raise unittest.SkipTest(f"PyGObject is not installed: {error}") from error

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from t48_programmer import samples  # noqa: E402
from t48_programmer.minipro import ACTIONS, Options  # noqa: E402
from t48_programmer.rom_image import KIB, open_rom, swap_byte_pairs  # noqa: E402
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

HAVE_DISPLAY = bool(Gtk.init_check()) and Gdk.Display.get_default() is not None
if REQUIRE_GTK and not HAVE_DISPLAY:
    raise RuntimeError("The interface tests need a display.")
TIMEOUT = 15.0


def pump(condition, timeout: float = TIMEOUT) -> bool:
    """Run the main loop until condition() holds or the time runs out."""
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        context.iteration(False)
        time.sleep(0.005)
    return True


_application: ProgrammerApplication | None = None


def shared_application() -> ProgrammerApplication:
    """One application for the whole run. D-Bus allows a process only one."""
    global _application
    if _application is None:
        _application = ProgrammerApplication(
            f"com.github.pclarke.T48Programmer.Test{os.getpid()}", unique=False
        )
        _application.register(None)
    return _application


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
        self.assertIn("Acorn sideways ROM, 16 KB", self.window._describe_file(copy))

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
