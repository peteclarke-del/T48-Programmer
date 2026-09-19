"""Main application window."""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import __version__, chips, minipro, operations, samples  # noqa: E402
from .app_update import AppRelease, parse_version  # noqa: E402
from .app_updater import AppUpdateControls, AppUpdater, attach_to_about  # noqa: E402
from .branding import (  # noqa: E402
    APPLICATION_ICON,
    APPLICATION_NAME,
    APPLICATION_SUBTITLE,
    HOMEPAGE,
    MINIPRO_HOMEPAGE,
)
from .chip_chooser import ChipChooser  # noqa: E402
from .help_view import HelpView  # noqa: E402
from .main_loop import call_on_main_loop  # noqa: E402
from .operation import OperationController  # noqa: E402
from .options_panel import OptionsPanel  # noqa: E402
from .programmer import (  # noqa: E402
    ProgrammerProbeResult,
    detect_programmer,
    tool_version,
)
from .rom_image import (  # noqa: E402
    KEY_FILE_NAME,
    ImageIdentity,
    OpenedRom,
    RomKeyError,
    RomKeyMissing,
    copies_to_fill,
    describe,
    fingerprint,
    fit_text,
    identify,
    open_rom,
    size_text,
)
from .rom_sets import (  # noqa: E402
    FAMILIES_BY_KEY,
    LAYOUTS_BY_KEY,
    RomPart,
    fit_to_chip,
)
from .rom_wizard import BURN, MACHINE, ROM, RomWizard  # noqa: E402

_POLL_SECONDS = 5


_IMAGE_PATTERNS = ("*.bin", "*.rom", "*.img", "*.hex", "*.ihex", "*.srec", "*.s19")

# Heading, body and button for the operations that ask first. The body is
# formatted with the chip and the image name.
_CONFIRMATIONS = {
    "write": (
        "Write to the Chip?",
        "{image} will be written to the {chip} in the socket. Whatever the chip "
        "holds now will be lost.",
        "Write",
    ),
    "erase": (
        "Erase the Chip?",
        "Everything on the {chip} in the socket will be erased.",
        "Erase",
    ),
    "hardware_check": (
        "Is the Socket Empty?",
        "The self test drives every pin with every supply in turn. A chip left "
        "in the socket may be destroyed. Remove it before continuing.",
        "Socket Is Empty",
    ),
}

# What the result page says when an operation succeeds.
_SUCCESS_HEADINGS = {
    "read": "Chip Read",
    "write": "Chip Written",
    "verify": "The Chip Matches the Image",
    "blank_check": "The Chip Is Blank",
    "erase": "Chip Erased",
    "read_id": "Chip Identified",
    "pin_check": "Pin Contacts Are Good",
    "logic_test": "The Device Passed Its Test",
    "hardware_check": "The Programmer Passed Its Self Test",
    "detect_spi_8": "SPI Flash Detection",
    "detect_spi_16": "SPI Flash Detection",
}
_PIN_TEST_UNSUPPORTED = "Pin test is not supported"

_OFFLINE_WITH_MINIPRO = (
    "Offline. No programmer is connected. Images, ROM sets and the chip database "
    "are all available."
)
_OFFLINE_WITHOUT_MINIPRO = (
    "Offline. minipro is not installed, so chips cannot be listed. Images and ROM "
    "sets are available."
)


def action_name(key: str) -> str:
    """The name of the window action for a minipro action: read_id is read-id."""
    return key.replace("_", "-")


class MainWindow(Adw.ApplicationWindow):
    """The start page, and the pages that replace it while work is done."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.set_title(APPLICATION_NAME)
        self.set_default_size(760, 820)
        self.set_size_request(460, 400)
        self._file_chooser: Gtk.FileChooserNative | None = None
        self._active_operation: OperationController | None = None
        self._active_action: minipro.Action | None = None
        self._diagnostic_log: list[str] = []
        self._scratch: tempfile.TemporaryDirectory[str] | None = None
        self._programmer = ProgrammerProbeResult(False, "")
        self._tool_version = ""
        self._firmware = ""
        self._detection_active = False
        self._initial_detection_complete = False
        self.chip = ""
        self.chip_info: chips.ChipInfo | None = None
        self.image_path: Path | None = None
        self.image_data: bytes | None = None
        self.image_bytes = 0
        self.image_identity: ImageIdentity | None = None
        self._image_facts: tuple[tuple[str, str], ...] = ()
        self._image_stamp: tuple[int, int] | None = None
        self.last_result: operations.OperationResult | None = None
        self.last_dialog: Adw.MessageDialog | None = None
        self.wizard: RomWizard | None = None
        self.app_updater = AppUpdater(self)
        self.about_window: Adw.AboutWindow | None = None

        self._create_window_actions()
        toolbar_view = Adw.ToolbarView()
        header_bar = Adw.HeaderBar()
        self._back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._back_button.set_tooltip_text("Back to start")
        self._back_button.set_visible(False)
        self._back_button.connect("clicked", lambda _button: self.show_dashboard())
        header_bar.pack_start(self._back_button)
        header_bar.set_title_widget(
            Adw.WindowTitle(title=APPLICATION_NAME, subtitle=APPLICATION_SUBTITLE)
        )
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_button.set_tooltip_text("Main menu")
        menu_button.set_menu_model(self._build_main_menu())
        header_bar.pack_end(menu_button)
        toolbar_view.add_top_bar(header_bar)
        # Shown on every page while no programmer answers, so that Offline is a
        # state the window is visibly in and not something to be inferred from
        # greyed-out buttons.
        self.offline_banner = Adw.Banner(button_label="Reconnect")
        self.offline_banner.set_action_name("win.reconnect")
        toolbar_view.add_top_bar(self.offline_banner)

        self._stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self._toasts = Adw.ToastOverlay(child=self._stack)
        toolbar_view.set_content(self._toasts)
        self.set_content(toolbar_view)
        self._stack.add_named(self._build_checking_page(), "checking")
        self._stack.add_named(self._build_dashboard(), "dashboard")
        self._stack.add_named(self._build_progress_page(), "progress")
        self._stack.set_visible_child_name("checking")
        self.connect("close-request", self._close_requested)
        self._poll_source = GLib.timeout_add_seconds(
            _POLL_SECONDS, self._poll_programmer
        )

    # Menus and actions

    def _create_window_actions(self) -> None:
        callbacks: dict[str, Callable[[], None]] = {
            "open-image": self._choose_image,
            "rom-wizard": self.open_rom_wizard,
            "reset-options": lambda: self.options_panel.reset(),
            "choose-chip": self.choose_chip,
            "chip-info": self.show_chip_information,
            "reconnect": self.begin_programmer_detection,
            "help": self._show_help,
            "diagnostics": self._show_diagnostic_log,
            "check-updates": self.check_for_updates,
            "about": self._show_about,
            "quit": self.close,
        }
        for key in minipro.ACTIONS:
            callbacks[action_name(key)] = lambda key=key: self.start_action(key)
        self._window_actions: dict[str, Gio.SimpleAction] = {}
        for name, callback in callbacks.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _parameter, fn=callback: fn())
            self.add_action(action)
            self._window_actions[name] = action
        self._set_hardware_actions_enabled(False)

    def _set_hardware_actions_enabled(self, enabled: bool) -> None:
        """Every minipro action needs a programmer to answer."""
        for key in minipro.ACTIONS:
            self._window_actions[action_name(key)].set_enabled(enabled)
        if self.wizard is not None:
            self.wizard.set_can_burn(enabled)

    def _build_main_menu(self) -> Gio.MenuModel:
        def item(key: str, ellipsis: bool = False) -> tuple[str, str]:
            title = minipro.ACTIONS[key].title + ("…" if ellipsis else "")
            return title, f"win.{action_name(key)}"

        menus = {
            "File": (
                ("Open Image…", "win.open-image"),
                ("Guided ROM Burn…", "win.rom-wizard"),
                ("Reset Options", "win.reset-options"),
                ("Quit", "win.quit"),
            ),
            "Chip": (
                ("Choose Chip…", "win.choose-chip"),
                ("Chip Information", "win.chip-info"),
                item("read_id"),
                item("detect_spi_8"),
                item("detect_spi_16"),
            ),
            "Device": (
                item("read", ellipsis=True),
                item("write", ellipsis=True),
                item("verify"),
                item("blank_check"),
                item("erase", ellipsis=True),
                item("pin_check"),
                item("logic_test"),
            ),
            "Programmer": (
                ("Reconnect", "win.reconnect"),
                ("Self Test…", "win.hardware-check"),
            ),
            "Help": (
                ("User Guide", "win.help"),
                ("Diagnostic Log", "win.diagnostics"),
                ("Check for Application Updates…", "win.check-updates"),
                (f"About {APPLICATION_NAME}", "win.about"),
            ),
        }
        root = Gio.Menu()
        for title, entries in menus.items():
            submenu = Gio.Menu()
            for label, target in entries:
                submenu.append(label, target)
            root.append_submenu(title, submenu)
        return root

    # Pages

    def _build_checking_page(self) -> Gtk.Widget:
        page = Adw.StatusPage(
            icon_name="media-flash-symbolic",
            title="Looking for the Programmer…",
            description="Checking the USB connection",
        )
        spinner = Gtk.Spinner(spinning=True)
        spinner.set_size_request(32, 32)
        page.set_child(spinner)
        return page

    def _build_progress_page(self) -> Gtk.Widget:
        self._progress_page = Adw.StatusPage(icon_name="media-flash-symbolic")
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_top=12,
            width_request=380,
            halign=Gtk.Align.CENTER,
        )
        self._progress_bar = Gtk.ProgressBar(show_text=True)
        box.append(self._progress_bar)
        self._progress_stage = Gtk.Label(xalign=0)
        self._progress_stage.add_css_class("heading")
        box.append(self._progress_stage)
        self._cancel_button = Gtk.Button(
            label="Cancel", halign=Gtk.Align.CENTER, margin_top=12
        )
        self._cancel_button.connect("clicked", lambda _button: self.cancel_operation())
        box.append(self._cancel_button)
        self._progress_page.set_child(box)
        return self._progress_page

    def _row_button(self, row: Adw.ActionRow, label: str, target: str) -> None:
        """Put a command button at the end of a start page row.

        The buttons share a size group, so they are all as wide as the widest
        and line up down the page at both edges.
        """
        button = Gtk.Button(label=label, valign=Gtk.Align.CENTER)
        button.set_action_name(target)
        self._row_buttons.add_widget(button)
        row.add_suffix(button)

    def _build_dashboard(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        self._row_buttons = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.HORIZONTAL)

        hardware = Adw.PreferencesGroup(title="Programmer")
        self._programmer_row = Adw.ActionRow(title="Looking for the programmer…")
        self._programmer_row.add_prefix(Gtk.Image(icon_name="media-flash-symbolic"))
        self._row_button(self._programmer_row, "Reconnect", "win.reconnect")
        hardware.add(self._programmer_row)
        page.add(hardware)

        guide = Adw.PreferencesGroup(title="Retro Computer ROMs")
        guide_row = Adw.ActionRow(
            title="Guided ROM Burn",
            subtitle="Amiga Kickstart, Atari TOS and Acorn ROMs, from the image to "
            "verified chips",
        )
        self._row_button(guide_row, "Start…", "win.rom-wizard")
        guide.add(guide_row)
        page.add(guide)

        target = Adw.PreferencesGroup(title="Chip and Image")
        self._chip_row = Adw.ActionRow(title_lines=1)
        self._row_button(self._chip_row, "Choose…", "win.choose-chip")
        target.add(self._chip_row)
        self._image_row = Adw.ActionRow(title_lines=1)
        self._row_button(self._image_row, "Open…", "win.open-image")
        target.add(self._image_row)
        # The details have a row of their own. An expander draws its arrow
        # after any button it is given, which would push Open out of line with
        # the buttons above it.
        self._image_details = Adw.ExpanderRow(title="Image Details", visible=False)
        self._image_detail_rows: list[Gtk.Widget] = []
        target.add(self._image_details)
        page.add(target)

        actions = Adw.PreferencesGroup()
        buttons = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8,
            halign=Gtk.Align.CENTER,
            homogeneous=True,
        )
        for key, label in (
            ("read", "Read…"),
            ("write", "Write…"),
            ("verify", "Verify"),
            ("blank_check", "Blank Check"),
            ("erase", "Erase…"),
        ):
            button = Gtk.Button(label=label)
            button.set_action_name(f"win.{action_name(key)}")
            if key == "write":
                button.add_css_class("suggested-action")
            buttons.append(button)
        actions.add(buttons)
        page.add(actions)

        self.options_panel = OptionsPanel()
        page.add(self.options_panel)
        self._refresh_target_rows()
        return page

    def show_dashboard(self) -> None:
        self._back_button.set_visible(False)
        self._stack.set_visible_child_name("dashboard")

    def _show_workspace(self, content: Gtk.Widget) -> None:
        existing = self._stack.get_child_by_name("workspace")
        if existing is not None:
            self._stack.remove(existing)
        self._stack.add_named(content, "workspace")
        self._back_button.set_visible(True)
        self._stack.set_visible_child_name("workspace")

    def _show_result(
        self,
        title: str,
        body: str,
        transcript: str = "",
        icon_name: str = "emblem-ok-symbolic",
        buttons: tuple[Gtk.Widget, ...] = (),
    ) -> None:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        status = Adw.StatusPage(icon_name=icon_name, title=title, description=body)
        status.set_vexpand(True)
        if buttons:
            row = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=8,
                halign=Gtk.Align.CENTER,
            )
            for button in buttons:
                row.append(button)
            status.set_child(row)
        page.append(status)
        if transcript:
            page.append(self._build_transcript(transcript, height=220))
        self._show_workspace(page)

    @staticmethod
    def _build_transcript(text: str, height: int) -> Gtk.Widget:
        view = Gtk.TextView(
            editable=False,
            cursor_visible=False,
            monospace=True,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            top_margin=6,
            bottom_margin=6,
            left_margin=6,
            right_margin=6,
        )
        view.get_buffer().set_text(text)
        scroller = Gtk.ScrolledWindow(
            min_content_height=height, margin_start=18, margin_end=18, margin_bottom=18
        )
        scroller.add_css_class("card")
        scroller.set_child(view)
        return scroller

    def toast(self, message: str) -> None:
        self._toasts.add_toast(Adw.Toast(title=message))

    # Chip and image

    def _refresh_target_rows(self) -> None:
        if self.chip:
            self._chip_row.set_title(self.chip)
            info = self.chip_info
            facts = (
                [size_text(info.code_bytes), info.package, info.memory]
                if info is not None and info.code_bytes
                else [info.package if info is not None else ""]
            )
            self._chip_row.set_subtitle(", ".join(fact for fact in facts if fact))
        else:
            self._chip_row.set_title("No chip chosen")
            self._chip_row.set_subtitle("Every operation needs to know the exact part")

        for row in self._image_detail_rows:
            self._image_details.remove(row)
        self._image_detail_rows.clear()
        if self.image_path is None or self.image_identity is None:
            self._image_row.set_title("No image opened")
            self._image_row.set_subtitle("Needed to write or verify a chip")
            self._image_details.set_visible(False)
            return
        identity = self.image_identity
        summary = [identity.title, size_text(self.image_bytes)]
        fit = self._fit_text() if self.chip else ""
        self._image_row.set_title(self.image_path.name)
        self._image_row.set_subtitle(", ".join(summary) + (f". {fit}" if fit else ""))
        for warning in identity.warnings:
            row = Adw.ActionRow(title=warning, title_lines=0, activatable=False)
            row.add_prefix(Gtk.Image(icon_name="dialog-warning-symbolic"))
            self._image_detail_rows.append(row)
        for label, value in self._image_facts:
            row = Adw.ActionRow(title=label, subtitle=value, subtitle_selectable=True)
            row.add_css_class("property")
            self._image_detail_rows.append(row)
        for row in self._image_detail_rows:
            self._image_details.add_row(row)
        warnings = len(identity.warnings)
        self._image_details.set_subtitle(
            "Checksums and what the image was identified as"
            if not warnings
            else f"{warnings} warning" + ("s" if warnings > 1 else "")
        )
        self._image_details.set_visible(bool(self._image_detail_rows))
        self._image_details.set_expanded(bool(warnings))

    @property
    def _programmer_key(self) -> str:
        """The programmer whose chip database is in use: the one attached, or the T48."""
        return self._programmer.key or minipro.DEFAULT_PROGRAMMER

    @property
    def _chip_bytes(self) -> int:
        return self.chip_info.code_bytes if self.chip_info else 0

    def _fit_text(self) -> str:
        return fit_text(self.image_bytes, self._chip_bytes, self.image_identity)

    def _open_chooser(self, on_chosen: Callable[[str], None]) -> None:
        catalogue = chips.load_catalogue(self._programmer_key)
        if not catalogue:
            self._show_error("Choose Chip", self._programmer.summary)
            return
        ChipChooser(self, catalogue, on_chosen).present()

    def choose_chip(self) -> None:
        self._open_chooser(self.set_chip)

    def set_chip(self, name: str) -> None:
        """Select a chip and ask minipro what it knows about it."""
        self.chip = name
        self.chip_info = chips.chip_info(name, self._programmer_key)
        self.options_panel.set_chip_info(self.chip_info)
        self._refresh_target_rows()

    def show_chip_information(self) -> None:
        if not self.chip:
            self.toast("Choose a chip first.")
            return
        self._show_result(
            self.chip,
            "What minipro knows about this chip",
            self.chip_info.text if self.chip_info else "minipro gave no answer.",
            icon_name="dialog-information-symbolic",
        )

    def _choose_image(self) -> None:
        self._choose_file(
            "Open Image", Gtk.FileChooserAction.OPEN, "Open", self.load_image
        )

    def load_image(self, path: Path) -> None:
        """Make a file the current image and work out what it is."""
        self.open_rom_with_key(path, self._set_image)

    def open_rom_with_key(
        self,
        path: Path,
        on_opened: Callable[[OpenedRom], None],
        key_path: Path | None = None,
    ) -> None:
        """Open a ROM, asking for the key if it is encrypted and has none beside it."""
        try:
            on_opened(open_rom(path, key_path))
        except RomKeyMissing as error:
            self._ask_for_key(path, on_opened, str(error))
        except RomKeyError as error:
            self._show_error("Encrypted Kickstart", str(error))
        except OSError as error:
            self._show_error("Open Image", f"The file could not be read: {error}")

    def _ask_for_key(
        self, path: Path, on_opened: Callable[[OpenedRom], None], reason: str
    ) -> None:
        def choose_key() -> None:
            self._choose_file(
                f"Choose {KEY_FILE_NAME}",
                Gtk.FileChooserAction.OPEN,
                "Use Key",
                lambda key: self.open_rom_with_key(path, on_opened, key),
                filtered=False,
            )

        self._ask(
            "This Kickstart Is Encrypted",
            f"{reason} Choose the {KEY_FILE_NAME} that came with it. The ROM is "
            "decrypted in memory and the file is left as it is.",
            {
                "cancel": ("Cancel", None),
                "choose": (f"Choose {KEY_FILE_NAME}…", choose_key),
            },
            appearance=Adw.ResponseAppearance.SUGGESTED,
            default="choose",
        )

    def _set_image(self, opened: OpenedRom) -> None:
        path = opened.path
        if opened.decrypted:
            # minipro is given a file, and it must be given the plain one.
            path = self._scratch_folder() / f"{path.stem}-decrypted{path.suffix}"
            path.write_bytes(opened.data)
        self.image_path = path
        self.image_data = opened.data
        # Kept from the moment of opening. The file may be moved or deleted
        # while the window still describes it.
        self.image_bytes = opened.byte_count
        self.image_identity = opened.identity
        # Worked out once. The rows are redrawn every time the chip changes,
        # and hashing a large image each time would stall the window.
        self._image_facts = opened.identity.details + (
            fingerprint(opened.data) if opened.data is not None else ()
        )
        self._image_stamp = self._stamp(path)
        self._refresh_target_rows()

    @staticmethod
    def _stamp(path: Path) -> tuple[int, int] | None:
        try:
            status = path.stat()
        except OSError:
            return None
        return status.st_size, status.st_mtime_ns

    def _image_is_as_opened(self) -> bool:
        """False, having read the file again, if it changed since it was opened.

        minipro is given the path and reads the file itself. If the file has
        been rebuilt in the meantime, what is burned is not what the window
        identified, checked for size and described in its confirmation.
        """
        if self.image_path is None or self._stamp(self.image_path) == self._image_stamp:
            return True
        name = self.image_path.name
        self.load_image(self.image_path)
        self.toast(f"{name} has changed on disk and was read again. Check it first.")
        return False

    def _set_image_from_memory(self, path: Path, data: bytes) -> bool:
        """Save bytes the window already holds and make them the current image."""
        try:
            path.write_bytes(data)
        except OSError as error:
            self._show_error("Save Image", f"{path.name} could not be saved: {error}")
            return False
        # There is no need to read back and hash what was just written.
        self._set_image(OpenedRom(path, len(data), data, identify(data)))
        return True

    # The guided ROM burn

    def open_rom_wizard(self) -> None:
        """Start the guide, from the open image when it is a ROM it knows."""
        if self.wizard is not None:
            self.wizard.release()
            self._stack.remove(self.wizard)
        self.wizard = RomWizard(self, can_burn=self._programmer.connected)
        self._stack.add_named(self.wizard, "wizard")
        identity = self.image_identity
        family = FAMILIES_BY_KEY.get(identity.kind) if identity else None
        if family is not None and self.image_data is not None:
            self.wizard.answers.family = family
            self.wizard.answers.images.append(
                OpenedRom(self.image_path, self.image_bytes, self.image_data, identity)
            )
            self.wizard.go_to(MACHINE)
        self._show_wizard()

    def _show_wizard(self) -> None:
        self._back_button.set_visible(True)
        self._stack.set_visible_child_name("wizard")

    def choose_rom(self, on_opened: Callable[[OpenedRom], None]) -> None:
        self._choose_file(
            "Choose ROM Image",
            Gtk.FileChooserAction.OPEN,
            "Choose",
            lambda path: self.open_rom_with_key(path, on_opened),
        )

    def choose_other_chip(self, on_chosen: Callable[[str, int], None]) -> None:
        def chosen(name: str) -> None:
            info = chips.chip_info(name, self._programmer_key)
            on_chosen(name, info.code_bytes if info is not None else 0)

        self._open_chooser(chosen)

    def _scratch_folder(self) -> Path:
        """A private folder for generated images, removed when the window closes."""
        if self._scratch is None:
            self._scratch = tempfile.TemporaryDirectory(prefix="t48-programmer-")
        return Path(self._scratch.name)

    @staticmethod
    def _part_path(part: RomPart, stem: str, folder: Path) -> Path:
        return folder / f"{stem}-{part.file_stem}.bin"

    def burn_part(
        self,
        part: RomPart,
        stem: str,
        on_finished: Callable[[operations.OperationResult], None],
    ) -> None:
        """Write one chip of a set and verify it, then report back to the guide."""
        if self._held_by_update():
            return
        if not self._programmer.connected:
            self.toast("Offline. Save the parts, or connect a programmer to burn them.")
            return
        path = self._part_path(part, stem, self._scratch_folder())
        if not self._set_image_from_memory(path, part.data):
            return
        minipro.insert_blank_chip(part.device)
        self.set_chip(part.device)
        self._confirm_action(minipro.ACTIONS["write"], path, on_finished)

    def save_parts(self, parts: tuple[RomPart, ...], stem: str) -> None:
        self._choose_file(
            "Save ROM Set Parts",
            Gtk.FileChooserAction.SELECT_FOLDER,
            "Save Here",
            lambda folder: self.write_parts(parts, stem, folder),
        )

    def write_parts(self, parts: tuple[RomPart, ...], stem: str, folder: Path) -> None:
        try:
            for part in parts:
                self._part_path(part, stem, folder).write_bytes(part.data)
        except OSError as error:
            self._show_error("Save ROM Set Parts", f"A part was not saved: {error}")
            return
        self.toast(f"Saved {len(parts)} files to {folder.name}")

    # Operations

    def start_action(self, key: str) -> None:
        """Begin an operation, gathering a file and a confirmation as needed."""
        action = minipro.ACTIONS[key]
        if self._active_operation is not None or self._held_by_update():
            return
        # The menu entries and buttons are disabled while offline, but this is
        # also reached directly, from the guided ROM burn for one.
        if not self._programmer.connected:
            self.toast(f"Offline. Connect a programmer to use {action.title}.")
            return
        if action.needs_chip and not self.chip:
            self.toast("Choose a chip first.")
            return
        if action.file_role == "input" and self.image_path is None:
            self.toast("Open an image first.")
            return
        if action.file_role == "input" and not self._image_is_as_opened():
            return
        if action.file_role == "output":
            suffix = self.options_panel.options().file_format or "bin"
            self._choose_file(
                action.title,
                Gtk.FileChooserAction.SAVE,
                "Read",
                lambda path: self.run_action(action, path),
                suggested_name=f"{self.chip.partition('@')[0]}.{suffix}",
            )
            return
        path = self.image_path if action.file_role else None
        if key in _CONFIRMATIONS:
            self._confirm_action(action, path)
        else:
            self.run_action(action, path)

    def _held_by_update(self) -> bool:
        """True, with a word to the user, while an update is being installed.

        apt is replacing minipro and its chip database at that moment. The
        updater will not install while an operation runs, and this is the other
        half of the same rule.
        """
        if self.app_updater.installing:
            self.toast("An update is being installed. Try again when it has finished.")
            return True
        return False

    def _confirm_action(
        self,
        action: minipro.Action,
        path: Path | None,
        on_finished: Callable[[operations.OperationResult], None] | None = None,
    ) -> None:
        heading, body, confirm_label = _CONFIRMATIONS[action.key]
        body = body.format(chip=self.chip, image=path.name if path else "")
        if path is not None and self.image_identity is not None:
            notes = [self._fit_text(), *self.image_identity.warnings]
            body = "\n\n".join([body, *(note for note in notes if note)])
        copies = self._copies_to_fill() if action.key == "write" else 0
        if copies and on_finished is None:
            self._confirm_short_write(heading, body, path, copies)
            return
        self._ask(
            heading,
            body,
            {
                "cancel": ("Cancel", None),
                "confirm": (
                    confirm_label,
                    lambda: self.run_action(action, path, on_finished),
                ),
            },
        )

    def _copies_to_fill(self) -> int:
        """How many copies of the image fill the chip, where that is worth asking.

        Only for a plain memory chip and its code memory. The data EEPROM of a
        microcontroller is another size altogether, and firmware written twice
        is not a ROM made visible but a mistake.
        """
        info = self.chip_info
        if self.image_data is None or self.image_identity is None or info is None:
            return 0
        if not info.is_plain_memory or self.options_panel.options().memory not in (
            "",
            "code",
        ):
            return 0
        return copies_to_fill(self.image_bytes, info.code_bytes, self.image_identity)

    def _confirm_short_write(
        self, heading: str, body: str, path: Path, copies: int
    ) -> None:
        """Ask how an image that goes into the chip several times should be written.

        Written once, it sits at the bottom of the chip, and a machine that
        reads another part of the chip never sees it. The guided ROM burn
        repeats such an image without asking, because it knows the board. Here
        the board is not known, so the choice is put to the user.
        """
        times = "twice" if copies == 2 else f"{copies} times"
        body += (
            f"\n\nFill the Chip writes the image {times}, so that it is found "
            "whichever part of the chip the machine reads. Some machines need "
            "this: a BBC Micro reads the top of a chip larger than 16 KB. Write "
            "Once puts the image at the bottom and leaves the rest of the chip as "
            "it is."
        )

        def write_once() -> None:
            # Choosing this is the consent that the size option in Options
            # stands for, so it need not be found and switched on as well.
            options = self.options_panel.options()
            allowed = replace(options, size_policy=options.size_policy or "warn")
            self.run_action(minipro.ACTIONS["write"], path, options=allowed)

        self._ask(
            heading,
            body,
            {
                "cancel": ("Cancel", None),
                "once": ("Write Once", write_once),
                "fill": ("Fill the Chip", lambda: self.write_filled(copies)),
            },
        )

    def write_filled(self, copies: int) -> None:
        """Repeat the current image to fill the chip, and write that.

        The filled image becomes the current image, so that the start page
        describes what is in the chip and a later Verify compares all of it.
        """
        original = self.image_path
        filled = self._scratch_folder() / f"{original.stem}-x{copies}{original.suffix}"
        (data,) = fit_to_chip(
            self.image_data, len(self.image_data) * copies, segmented=False
        )
        if self._set_image_from_memory(filled, data):
            self.run_action(minipro.ACTIONS["write"], filled)

    def run_action(
        self,
        action: minipro.Action,
        path: Path | None = None,
        on_finished: Callable[[operations.OperationResult], None] | None = None,
        options: minipro.Options | None = None,
    ) -> None:
        """Run minipro in a worker thread and follow it on the progress page.

        With on_finished, the caller is a guide that is part way through its own
        page. It gets the result, the window returns to it, and the write is
        always verified, because the guide promises a verified chip.
        """
        controller = OperationController()
        self._active_operation = controller
        self._active_action = action
        options = options or self.options_panel.options()
        if on_finished is not None:
            options = replace(options, skip_verify=False)
        self._progress_page.set_title(action.progress_title)
        self._progress_page.set_description(
            "Leave the chip and the cable alone until this finishes."
        )
        self._progress_bar.set_fraction(0)
        self._progress_bar.set_text("")
        self._progress_stage.set_text("Starting minipro…")
        self._cancel_button.set_sensitive(True)
        self._back_button.set_visible(False)
        self._stack.set_visible_child_name("progress")

        def worker() -> None:
            result = operations.run_action(
                action,
                chip=self.chip,
                path=path,
                options=options,
                on_progress=lambda update: call_on_main_loop(
                    self._update_progress, update
                ),
                controller=controller,
            )
            call_on_main_loop(self._finish_action, result, path, on_finished)

        threading.Thread(
            target=worker, name=f"minipro-{action.key}", daemon=True
        ).start()

    def _update_progress(self, update: operations.Progress) -> bool:
        self._progress_stage.set_text(update.stage)
        if update.fraction is None:
            self._progress_bar.pulse()
            self._progress_bar.set_text("")
        else:
            self._progress_bar.set_fraction(update.fraction)
            self._progress_bar.set_text(f"{update.fraction:.0%}")
        return GLib.SOURCE_REMOVE

    def cancel_operation(self) -> None:
        """Stop minipro, asking first when the chip would be left half done."""
        if self._active_operation is None or self._active_action is None:
            return
        if not self._active_action.destructive:
            self._cancel_now()
            return
        self._ask(
            "Stop Part Way Through?",
            "The chip will be left partly programmed and will need to be erased "
            "and written again.",
            {"continue": ("Keep Going", None), "stop": ("Stop", self._cancel_now)},
        )

    def _cancel_now(self) -> None:
        if self._active_operation is not None:
            self._active_operation.cancel()
            self._cancel_button.set_sensitive(False)
            self._progress_stage.set_text("Stopping minipro…")

    def _finish_action(
        self,
        result: operations.OperationResult,
        path: Path | None,
        on_finished: Callable[[operations.OperationResult], None] | None = None,
    ) -> bool:
        self._active_operation = None
        self._active_action = None
        self.last_result = result
        action = result.action
        self.record_diagnostic(action.title, f"{result.summary}\n{result.transcript}")
        if result.firmware:
            self._firmware = result.firmware
            self._refresh_programmer_row(result.firmware_warning)
        if on_finished is not None:
            self._show_wizard()
            on_finished(result)
        elif result.succeeded:
            self._show_success(result, path)
        else:
            self.show_dashboard()
        if result.cancelled:
            self.toast(result.summary)
        elif not result.succeeded:
            self._show_error(action.title, result.summary, result.transcript)
        return GLib.SOURCE_REMOVE

    def _show_success(
        self, result: operations.OperationResult, path: Path | None
    ) -> None:
        action = result.action
        heading = _SUCCESS_HEADINGS[action.key]
        body = result.summary
        buttons: list[Gtk.Widget] = []
        if _PIN_TEST_UNSUPPORTED in result.transcript and action.key == "pin_check":
            heading = "No Pin Test on This Programmer"
            body = "minipro can test pin contacts on the TL866II+ and T76 only."
        elif action.key in ("write", "verify") and path is not None:
            verified = "Verification OK" in result.transcript
            body = f"{path.name} and the {self.chip} " + (
                "were compared byte for byte and are the same."
                if verified
                else "were not compared, because verification was turned off."
            )
        elif action.key == "read" and path is not None:
            body = f"Saved to {path}"
            opened = self._open_quietly(path)
            if opened is not None:
                body += "\n" + describe(opened)
                buttons.append(
                    self._suggested("Use as Current Image", self._use_image, opened)
                )
        elif action.key == "read_id" and result.chip_id:
            body = f"The chip reports ID {result.chip_id}, which matches {self.chip}."
        elif action.key.startswith("detect_spi"):
            catalogue = set(chips.load_catalogue(self._programmer_key))
            found = [
                line for line in result.transcript.splitlines() if line in catalogue
            ]
            body = f"{len(found)} matching parts. They are listed below."
            if len(found) == 1:
                body = f"The flash identifies as {found[0]}."
                buttons.append(
                    self._suggested(f"Choose {found[0]}", self._use_detected, found[0])
                )
        self._show_result(heading, body, result.transcript, buttons=tuple(buttons))

    @staticmethod
    def _open_quietly(path: Path) -> OpenedRom | None:
        """A file just read from a chip, opened once for the result page.

        A Kickstart is not encrypted in a chip, so no key is asked for, and a
        file that cannot be read back is simply not described.
        """
        try:
            return open_rom(path)
        except (OSError, RomKeyError):
            return None

    @staticmethod
    def _suggested(
        label: str, action: Callable[..., None], *arguments: object
    ) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.add_css_class("suggested-action")
        button.connect("clicked", lambda _button: action(*arguments))
        return button

    def _use_image(self, opened: OpenedRom) -> None:
        self._set_image(opened)
        self.show_dashboard()

    def _use_detected(self, name: str) -> None:
        self.set_chip(name)
        self.show_dashboard()

    # Files

    def _choose_file(
        self,
        title: str,
        chooser_action: Gtk.FileChooserAction,
        accept_label: str,
        on_chosen: Callable[[Path], None],
        suggested_name: str = "",
        filtered: bool = True,
    ) -> None:
        chooser = Gtk.FileChooserNative.new(
            title, self, chooser_action, accept_label, "Cancel"
        )
        if chooser_action == Gtk.FileChooserAction.OPEN and filtered:
            images = Gtk.FileFilter()
            images.set_name("ROM and firmware images")
            for pattern in _IMAGE_PATTERNS:
                images.add_pattern(pattern)
                images.add_pattern(pattern.upper())
            everything = Gtk.FileFilter()
            everything.set_name("All files")
            everything.add_pattern("*")
            chooser.add_filter(images)
            chooser.add_filter(everything)
        if suggested_name:
            chooser.set_current_name(suggested_name)

        def respond(chooser: Gtk.FileChooserNative, response: int) -> None:
            self._file_chooser = None
            selected = chooser.get_file()
            if response == Gtk.ResponseType.ACCEPT and selected is not None:
                selected_path = selected.get_path()
                if selected_path is not None:
                    on_chosen(Path(selected_path))

        chooser.connect("response", respond)
        # Held so that the native dialog is not collected while it is open.
        self._file_chooser = chooser
        chooser.show()

    # Help, diagnostics and errors

    def _show_help(self) -> None:
        self.set_default_size(1080, 820)
        self._show_workspace(HelpView())

    def _show_about(self) -> None:
        about = Adw.AboutWindow(
            transient_for=self,
            modal=True,
            application_name=APPLICATION_NAME,
            application_icon=APPLICATION_ICON,
            developer_name="Pete Clarke",
            version=__version__,
            comments="A native GNOME interface for XGecu chip programmers, built "
            "on minipro.",
            website=HOMEPAGE,
            issue_url=f"{HOMEPAGE}/issues",
            developers=["Pete Clarke"],
            copyright="Copyright 2026 Pete Clarke",
            license_type=Gtk.License.GPL_3_0,
        )
        about.add_link("minipro", MINIPRO_HOMEPAGE)
        about.set_debug_info(
            f"minipro {self._tool_version or 'not found'}\n"
            f"Programmer: {self._programmer.model or 'none'}\n"
            f"Firmware: {self._firmware or 'not yet read'}"
        )
        controls = AppUpdateControls(self.app_updater)
        if not attach_to_about(about, controls):
            # This libadwaita lays its About window out differently. The update
            # must still have somewhere to show its progress and its questions.
            self.record_diagnostic(
                "Check for Application Updates",
                "The About window had no place for the update controls.",
            )
            self._show_update_window(controls)

        def closed(_window: Adw.AboutWindow) -> bool:
            controls.detach()
            if self.about_window is about:
                self.about_window = None
            return False

        about.connect("close-request", closed)
        self.about_window = about
        about.present()

    # Application updates

    def _show_update_window(self, controls: AppUpdateControls) -> None:
        """A window of their own for the update controls, when About has no room."""
        holder = Adw.Window(
            transient_for=self, title="Application Updates", default_width=380
        )
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        for side in ("top", "bottom", "start", "end"):
            getattr(controls, f"set_margin_{side}")(18)
        view.set_content(controls)
        holder.set_content(view)
        holder.present()

    def check_for_updates(self) -> None:
        """Open the About window and check there, so that there is one check.

        The state of an update lives in the About window: the answer, the
        download, the password prompt and the offer to restart. The menu entry
        is a shorter way to the same button and not a second way to update.
        """
        if self.about_window is None:
            self._show_about()
        self.app_updater.check()

    def operation_running(self) -> bool:
        """True while minipro is working on a chip."""
        return self._active_operation is not None

    def app_update_installed(self, release: AppRelease) -> None:
        """Offer to restart when the update finished with the About window closed."""
        if self.about_window is not None or self.operation_running():
            return
        self._ask(
            f"Restart {APPLICATION_NAME}?",
            f"{release.name} is installed. Restart {APPLICATION_NAME} to use it.",
            {
                "later": ("_Later", None),
                "restart": ("_Restart", self.app_updater.restart),
            },
            appearance=Adw.ResponseAppearance.SUGGESTED,
        )

    def restart(self) -> bool:
        """Quit and start the installed version, unless minipro is working."""
        if self.operation_running():
            return False
        application = self.get_application()
        if application is not None:
            application.restart_requested = True
        if self.about_window is not None:
            self.about_window.close()
        self.close()
        return True

    def record_diagnostic(self, title: str, detail: str) -> None:
        """Add an entry to the session's Diagnostic Log."""
        self._diagnostic_log.append(
            f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] "
            f"{title}\n{detail.strip()}"
        )

    def _show_diagnostic_log(self) -> None:
        text = "\n\n".join(self._diagnostic_log) or "Nothing has been recorded yet."
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18)
        copy = Gtk.Button(label="Copy All", halign=Gtk.Align.END, margin_end=18)
        copy.connect("clicked", lambda _button: self._copy_text(text))
        page.append(copy)
        transcript = self._build_transcript(text, height=300)
        transcript.set_vexpand(True)
        page.append(transcript)
        self._show_workspace(page)

    def _copy_text(self, text: str) -> None:
        Gdk.Display.get_default().get_clipboard().set(text)
        self.toast("Copied")

    def _ask(
        self,
        heading: str,
        body: str,
        responses: dict[str, tuple[str, Callable[[], None] | None]],
        *,
        appearance: Adw.ResponseAppearance | None = Adw.ResponseAppearance.DESTRUCTIVE,
        default: str = "",
        extra_child: Gtk.Widget | None = None,
    ) -> Adw.MessageDialog:
        """Put a question, and run whatever goes with the answer.

        responses maps each answer to its label and to what it does, in the
        order the buttons appear. The first is the safe answer: it is what
        closing the dialog means, and the default unless another is named. The
        last is the one that acts, and takes the appearance given.
        """
        dialog = Adw.MessageDialog.new(self, heading, body)
        for name, (label, _action) in responses.items():
            dialog.add_response(name, label)
        names = list(responses)
        if appearance is not None and len(names) > 1:
            dialog.set_response_appearance(names[-1], appearance)
        dialog.set_default_response(default or names[0])
        dialog.set_close_response(names[0])
        if extra_child is not None:
            dialog.set_extra_child(extra_child)

        def respond(_dialog: Adw.MessageDialog, response: str) -> None:
            action = responses.get(response, ("", None))[1]
            if action is not None:
                action()

        dialog.connect("response", respond)
        self.last_dialog = dialog
        dialog.present()
        return dialog

    def _show_error(
        self, title: str, summary: str, diagnostic: str = ""
    ) -> Adw.MessageDialog:
        if not diagnostic:
            return self._ask(title, summary, {"close": ("Close", None)})
        return self._ask(
            title,
            summary,
            {
                "close": ("Close", None),
                "copy": ("Copy Details", lambda: self._copy_text(diagnostic)),
            },
            appearance=None,
            extra_child=self._build_transcript(diagnostic, height=140),
        )

    # Programmer detection

    def begin_programmer_detection(self, *, silent: bool = False) -> None:
        """Run detection without blocking GTK's event loop."""
        if self._detection_active:
            return
        self._detection_active = True
        if not silent:
            self._programmer_row.set_title("Looking for the programmer…")
            self._programmer_row.set_subtitle("")

        def worker() -> None:
            # Whatever goes wrong, the window must hear that detection is over,
            # or it stays on "Looking for the programmer" for good.
            try:
                result = detect_programmer()
                version = self._tool_version or tool_version()
            except Exception as error:  # noqa: BLE001 - reported, not lost
                result = ProgrammerProbeResult(
                    False, f"The programmer could not be looked for: {error!r}"
                )
                version = self._tool_version
            call_on_main_loop(
                self._finish_programmer_detection, result, version, silent
            )

        threading.Thread(
            target=worker, name="programmer-detection", daemon=True
        ).start()

    def _poll_programmer(self) -> bool:
        if (
            self._initial_detection_complete
            and self._active_operation is None
            and self._stack.get_visible_child_name() == "dashboard"
        ):
            self.begin_programmer_detection(silent=True)
        return GLib.SOURCE_CONTINUE

    def _refresh_programmer_row(self, warning: str = "") -> None:
        result = self._programmer
        tool = f"minipro {self._tool_version}" if self._tool_version else ""
        if result.connected:
            firmware = f"Firmware {self._firmware}" if self._firmware else ""
            facts = [firmware, tool, warning]
            self._programmer_row.set_title(f"{result.model} connected")
        else:
            facts = [result.summary, tool if result.tool_available else ""]
            self._programmer_row.set_title("Offline")
        # Some facts are sentences and some are not, so the stops are made even.
        self._programmer_row.set_subtitle(
            ". ".join(fact.rstrip(".") for fact in facts if fact)
        )

    def _finish_programmer_detection(
        self, result: ProgrammerProbeResult, version: str, silent: bool
    ) -> bool:
        was_connected = self._programmer.connected
        first = not self._initial_detection_complete
        self._detection_active = False
        self._initial_detection_complete = True
        changed_model = result.connected and result.key != self._programmer_key
        self._programmer = result
        self._tool_version = version
        if not result.connected:
            self._firmware = ""
        self._set_hardware_actions_enabled(result.connected)
        self.offline_banner.set_title(
            _OFFLINE_WITH_MINIPRO if result.tool_available else _OFFLINE_WITHOUT_MINIPRO
        )
        self.offline_banner.set_revealed(not result.connected)
        self._refresh_programmer_row()
        if changed_model and self.chip:
            # Each programmer has its own database. The size and the voltages
            # on show were another model's.
            self.set_chip(self.chip)
        if first:
            self.show_dashboard()
        if was_connected != result.connected or not silent:
            self.record_diagnostic(
                "Programmer detection", f"{result.summary}\n{result.diagnostic}"
            )
        if not result.connected and not silent and not result.tool_available:
            self._show_error(
                "minipro Is Not Installed",
                "This application drives the programmer through minipro, which "
                "was not found. The release package includes it. For a copy run "
                "from source, see docs/INSTALLATION.md. Images can still be "
                "opened and ROM sets prepared without it.",
            )
        return GLib.SOURCE_REMOVE

    def _close_requested(self, _window: Gtk.Window) -> bool:
        if self._active_operation is not None:
            self.toast("minipro is still working. Cancel it or wait for it to finish.")
            return True
        # Done here and not on "destroy": GTK emits that at dispose, which does
        # not come while Python still holds the window. The timer holds the
        # window too, and would go on looking for a programmer for ever.
        if self._poll_source:
            GLib.source_remove(self._poll_source)
            self._poll_source = 0
        if self._scratch is not None:
            self._scratch.cleanup()
            self._scratch = None
        return False

    # Documentation

    def show_documentation_state(self, state: str) -> None:
        """Put the window in a fixed state for the documentation screenshots."""
        self._stack.set_transition_duration(0)
        image = self._scratch_folder() / "kick40068.A1200.rom"
        image.write_bytes(samples.kickstart())
        self._finish_programmer_detection(detect_programmer(), tool_version(), True)
        self.set_chip("M27C400@DIP40")
        self.load_image(image)
        if state == "help":
            self._show_help()
        elif state == "guide-burn":
            self.open_rom_wizard()
            pair = LAYOUTS_BY_KEY["amiga-pair"]
            self.wizard.choose_machine(pair, "A1200")
            self.wizard.choose_chip(pair.chips[0])
            self.wizard.go_to(BURN)
        elif state in ("guide-banks", "guide-images"):
            self.open_rom_wizard()
            acorn = LAYOUTS_BY_KEY["acorn-rom"]
            self.wizard.choose_family(FAMILIES_BY_KEY[acorn.family])
            self.wizard.choose_machine(acorn, "BBC Master")
            self.wizard.choose_chip(
                next(chip for chip in acorn.chips if chip.device == "W27C512@DIP28")
            )
            for title in ("BASIC", "View", "ViewSheet"):
                rom = self._scratch_folder() / f"{title.lower()}.rom"
                rom.write_bytes(samples.acorn_rom(title=title))
                self.wizard.add_image(open_rom(rom))
            if state == "guide-banks":
                self.wizard.go_to(BURN)
        elif state == "short-write":
            # The question asked when an image goes into the chip twice.
            rom = self._scratch_folder() / "Micro-C v1.0 (1987)(Beebug).bin"
            rom.write_bytes(samples.acorn_rom(title="Micro-C"))
            self.set_chip("AT28C256")
            self.load_image(rom)
            self.start_action("write")
        elif state == "app-update":
            # The About window after Check for Application Updates found the next
            # minor version. Nothing is fetched from GitHub.
            major, minor, _patch = parse_version(__version__) or (0, 0, 0)
            version = f"{major}.{minor + 1}.0"
            download = f"{HOMEPAGE}/releases/download/v{version}"
            self.app_updater.show_result(
                AppRelease(
                    version,
                    f"v{version}",
                    f"{APPLICATION_NAME} {version}",
                    f"{HOMEPAGE}/releases/tag/v{version}",
                    package_url=f"{download}/package.deb",
                    sums_url=f"{download}/SHA256SUMS",
                )
            )
            self._show_about()
        elif state == "guide":
            self.open_rom_wizard()
            self.wizard.go_to(ROM)
        elif state == "result":
            self.run_action(minipro.ACTIONS["write"], image)
