"""The guided ROM burn: from "what is it for" to verified chips in one pass.

The guide asks five things in order, which ROM, which machine, which chip,
which image or images, and then burns. Each answer is a crumb at the top of the
page. A crumb can be pressed to go back and change that answer, and everything
the change does not invalidate is kept.

The guide holds no knowledge of its own. The ROMs, machines and chips come from
the tables in rom_sets, and the arranging is done by rom_sets.prepare(), so a
board added there appears here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GObject, Gtk  # noqa: E402

from .main_loop import call_on_main_loop  # noqa: E402
from .operations import OperationResult  # noqa: E402
from .rom_image import OpenedRom, fingerprint, identify, size_text  # noqa: E402
from .rom_sets import (  # noqa: E402
    FAMILIES,
    ChipOption,
    RomFamily,
    RomLayout,
    RomPart,
    RomSetError,
    bank_spans,
    join_banks,
    layouts_in,
    prepare,
)

STEPS = ("ROM", "Machine", "Chip", "Images", "Burn")
ROM, MACHINE, CHIP, IMAGES, BURN = range(len(STEPS))

WAITING, WRITTEN, FAILED = "Waiting", "Written and verified", "Failed"


class WizardHost(Protocol):
    """What the guide needs from the window that holds it."""

    def choose_rom(self, on_opened: Callable[[OpenedRom], None]) -> None: ...
    def choose_other_chip(self, on_chosen: Callable[[str, int], None]) -> None: ...
    def burn_part(
        self, part: RomPart, stem: str, on_finished: Callable[[OperationResult], None]
    ) -> None: ...
    def save_parts(self, parts: tuple[RomPart, ...], stem: str) -> None: ...


@dataclass(slots=True)
class Answers:
    """Everything the guide has been told so far."""

    family: RomFamily | None = None
    layout: RomLayout | None = None
    machine: str = ""
    option: ChipOption | None = None
    images: list[OpenedRom] = field(default_factory=list)

    def answered(self, step: int) -> bool:
        return bool((self.family, self.layout, self.option, self.images, False)[step])

    def crumb(self, step: int) -> str:
        """A few words for the breadcrumb once a step has been answered."""
        if not self.answered(step):
            return ""
        if step == ROM:
            return self.family.short_title
        if step == MACHINE:
            return self.machine
        if step == CHIP:
            return self.option.device
        if len(self.images) == 1:
            return self.images[0].path.name
        return f"{len(self.images)} images"

    @property
    def stem(self) -> str:
        """The name that the files of this set are built from."""
        return self.images[0].path.stem if len(self.images) == 1 else "roms"


def _row(title: str, subtitle: str = "", **properties: object) -> Adw.ActionRow:
    return Adw.ActionRow(
        title=title, subtitle=subtitle, title_lines=0, subtitle_lines=0, **properties
    )


def _text_row(text: str) -> Adw.ActionRow:
    return _row(text, activatable=False)


class RomWizard(Gtk.Box):
    """Breadcrumbs, one page for the current step, and Back and Next."""

    def __init__(self, host: WizardHost, write_action: Gio.Action) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._host = host
        self._write_action = write_action
        self.answers = Answers()
        self.step = ROM
        self.parts: tuple[RomPart, ...] = ()
        self.problem = ""
        self.status: list[str] = []

        self.crumbs: list[Gtk.Button] = []
        crumb_bar = Gtk.Box(spacing=2, margin_top=8, margin_bottom=4, margin_start=12)
        for index in range(len(STEPS)):
            if index:
                crumb_bar.append(Gtk.Image(icon_name="go-next-symbolic"))
            crumb = Gtk.Button(has_frame=False, tooltip_text=STEPS[index])
            crumb.set_child(Gtk.Label(ellipsize=3, max_width_chars=20))
            crumb.connect("clicked", lambda _button, index=index: self.go_to(index))
            crumb_bar.append(crumb)
            self.crumbs.append(crumb)
        scroller = Gtk.ScrolledWindow(child=crumb_bar)
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.append(scroller)
        self.append(Gtk.Separator())

        self._page_holder = Adw.Bin(vexpand=True)
        self.append(self._page_holder)

        self.append(Gtk.Separator())
        bar = Gtk.Box(spacing=8, margin_top=10, margin_bottom=10, margin_start=12)
        bar.set_margin_end(12)
        self.back_button = Gtk.Button(label="Back")
        self.back_button.connect("clicked", lambda _button: self.go_to(self.step - 1))
        bar.append(self.back_button)
        bar.append(Gtk.Box(hexpand=True))
        self.next_button = Gtk.Button()
        self.next_button.connect("clicked", lambda _button: self._next_pressed())
        bar.append(self.next_button)
        self.append(bar)
        # The burn button comes and goes with the programmer.
        write_action.connect("notify::enabled", lambda *_args: self._refresh_chrome())
        self.go_to(ROM)

    # Navigation

    def reachable(self, step: int) -> bool:
        """A step can be visited once every step before it has an answer."""
        return all(self.answers.answered(earlier) for earlier in range(step))

    def go_to(self, step: int) -> None:
        if not 0 <= step < len(STEPS) or not self.reachable(step):
            return
        self.step = step
        if step == BURN:
            self._prepare_parts()
        builders = (
            self._build_rom_page,
            self._build_machine_page,
            self._build_chip_page,
            self._build_images_page,
            self._build_burn_page,
        )
        self._page_holder.set_child(builders[step]())
        self._refresh_chrome()

    def _refresh_chrome(self) -> None:
        for index, crumb in enumerate(self.crumbs):
            answer = self.answers.crumb(index)
            # The answer stands in for the name of the step once there is one,
            # which keeps all five crumbs on the screen.
            crumb.get_child().set_label(answer or STEPS[index])
            crumb.set_sensitive(self.reachable(index))
            if index == self.step:
                crumb.add_css_class("heading")
            else:
                crumb.remove_css_class("heading")
        self.back_button.set_sensitive(self.step > ROM)
        self.next_button.remove_css_class("suggested-action")
        self.next_button.remove_css_class("destructive-action")
        if self.step < BURN:
            self.next_button.set_label("Next")
            self.next_button.add_css_class("suggested-action")
            self.next_button.set_sensitive(self.reachable(self.step + 1))
            return
        pending = self.next_pending()
        self.next_button.add_css_class("destructive-action")
        if pending is None:
            self.next_button.set_label("All Chips Written" if self.parts else "Burn")
            self.next_button.set_sensitive(False)
            return
        label = self.parts[pending].label
        self.next_button.set_label(
            "Burn and Verify" if len(self.parts) == 1 else f"Burn {label} and Verify"
        )
        self.next_button.set_sensitive(self._write_action.get_enabled())

    def _next_pressed(self) -> None:
        if self.step < BURN:
            self.go_to(self.step + 1)
        elif (pending := self.next_pending()) is not None:
            self.burn(pending)

    # Answers. Changing one clears what it invalidates and no more.

    def choose_family(self, family: RomFamily) -> None:
        if family != self.answers.family:
            self.answers = Answers(family=family)
        self.go_to(MACHINE)

    def choose_machine(self, layout: RomLayout, machine: str) -> None:
        if layout != self.answers.layout:
            self.answers.option = None
        self.answers.layout = layout
        self.answers.machine = machine
        self.go_to(CHIP)

    def choose_chip(self, option: ChipOption) -> None:
        self.answers.option = option
        self._trim_images()
        self.go_to(IMAGES)

    def use_other_chip(self, device: str, chip_bytes: int) -> None:
        """Take a chip from the full search, if the board can use its size."""
        layout = self.answers.layout
        sizes = {option.chip_bytes for option in layout.chips}
        fits = chip_bytes in sizes or (
            layout.bank_bytes and chip_bytes and chip_bytes % layout.bank_bytes == 0
        )
        if not fits:
            wanted = " or ".join(size_text(size) for size in sorted(sizes))
            self.problem = (
                f"{device} holds {size_text(chip_bytes)}. This board needs a chip "
                f"of {wanted}."
            )
            self.go_to(CHIP)
            return
        self.problem = ""
        self.choose_chip(ChipOption(device, chip_bytes, "Chosen from the full list"))

    def add_image(self, opened: OpenedRom) -> None:
        if opened.data is None:
            self.problem = f"{opened.path.name} is too large to be a ROM image."
        elif opened.identity.kind == "kickstart-swapped":
            # The guide would swap it again and burn a chip that reads wrong.
            self.problem = f"{opened.path.name}: {opened.identity.warnings[-1]}"
        else:
            self.problem = ""
            if self.bank_count() == 1:
                self.answers.images.clear()
            self.answers.images.append(opened)
            self._trim_images()
        self.go_to(IMAGES)

    def remove_image(self, index: int) -> None:
        del self.answers.images[index]
        self.go_to(IMAGES)

    def move_image(self, index: int, to: int) -> None:
        """Move an image to another place in the order, and so to another bank."""
        images = self.answers.images
        if index != to and 0 <= index < len(images) and 0 <= to < len(images):
            images.insert(to, images.pop(index))
        self.go_to(IMAGES)
        # The page was rebuilt. Put the keyboard back on the arrow that was
        # pressed, on the row in its new place, so it can be pressed again. At
        # the end of the list that arrow is disabled, and the other one is used.
        step = 1 if to > index else -1
        for arrow in (self.arrows.get((to, step)), self.arrows.get((to, -step))):
            if arrow is not None and arrow.get_sensitive():
                arrow.grab_focus()
                break

    def spans(self) -> list[tuple[int, int]]:
        return bank_spans(
            self.answers.layout,
            self.answers.option,
            [rom.byte_count for rom in self.answers.images],
        )

    def banks_used(self) -> int:
        return sum(count for _first, count in self.spans())

    def bank_count(self) -> int:
        return self.answers.layout.bank_count(self.answers.option)

    def _trim_images(self) -> None:
        """Drop images from the end until what is left fits the chip."""
        while self.answers.images and self.banks_used() > self.bank_count():
            self.answers.images.pop()

    # Preparing and burning

    def _prepare_parts(self) -> None:
        answers = self.answers
        try:
            data = join_banks(
                answers.layout, answers.option, [rom.data for rom in answers.images]
            )
            parts = prepare(answers.layout, answers.option, data)
        except RomSetError as error:
            parts, self.problem = (), str(error)
        else:
            self.problem = ""
        if parts != self.parts:
            self.parts = parts
            self.status = [WAITING] * len(parts)

    def next_pending(self) -> int | None:
        return next(
            (i for i, status in enumerate(self.status) if status != WRITTEN), None
        )

    def burn(self, index: int) -> None:
        def finished(result: OperationResult) -> None:
            if result.succeeded:
                self.status[index] = WRITTEN
            elif not result.cancelled:
                self.status[index] = f"{FAILED}: {result.summary}"
            self.go_to(BURN)

        self._host.burn_part(self.parts[index], self.answers.stem, finished)

    # Pages

    def _page(self, *groups: Adw.PreferencesGroup) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        if self.problem:
            warning = Adw.PreferencesGroup()
            row = _text_row(self.problem)
            row.add_prefix(Gtk.Image(icon_name="dialog-warning-symbolic"))
            warning.add(row)
            page.add(warning)
        for group in groups:
            page.add(group)
        return page

    @staticmethod
    def _choice(
        title: str, subtitle: str, chosen: bool, on_chosen: Callable[[], None]
    ) -> Adw.ActionRow:
        row = _row(title, subtitle, activatable=True)
        if chosen:
            row.add_prefix(Gtk.Image(icon_name="object-select-symbolic"))
        row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
        row.connect("activated", lambda _row: on_chosen())
        return row

    def _build_rom_page(self) -> Gtk.Widget:
        group = Adw.PreferencesGroup(
            title="What Are You Programming?",
            description="Choose the kind of ROM. The next step asks which machine "
            "it is for.",
        )
        for family in FAMILIES:
            group.add(
                self._choice(
                    family.title,
                    family.maker,
                    family == self.answers.family,
                    lambda family=family: self.choose_family(family),
                )
            )
        return self._page(group)

    def _build_machine_page(self) -> Gtk.Widget:
        family = self.answers.family
        group = Adw.PreferencesGroup(
            title="Which Machine Is It For?", description=family.note
        )
        for layout in layouts_in(family):
            for machine in layout.machines:
                group.add(
                    self._choice(
                        machine,
                        layout.summary,
                        machine == self.answers.machine,
                        lambda layout=layout, machine=machine: self.choose_machine(
                            layout, machine
                        ),
                    )
                )
        return self._page(group)

    def _build_chip_page(self) -> Gtk.Widget:
        layout = self.answers.layout
        groups = []
        for chip_bytes in sorted({option.chip_bytes for option in layout.chips}):
            banks = chip_bytes // layout.bank_bytes if layout.bank_bytes else 0
            group = Adw.PreferencesGroup(
                title=f"{size_text(chip_bytes)} Chips",
                description=f"Room for {banks} ROM images of "
                f"{size_text(layout.bank_bytes)}"
                if banks > 1
                else "",
            )
            for option in layout.chips:
                if option.chip_bytes == chip_bytes:
                    group.add(
                        self._choice(
                            option.device,
                            option.note,
                            option == self.answers.option,
                            lambda option=option: self.choose_chip(option),
                        )
                    )
            groups.append(group)
        other = Adw.PreferencesGroup(
            title="A Different Chip",
            description="The name must match the part number printed on the chip "
            "you will burn. Its size is checked against the board.",
        )
        other.add(
            self._choice(
                "Search Every Chip minipro Supports…",
                "",
                False,
                lambda: self._host.choose_other_chip(self.use_other_chip),
            )
        )
        return self._page(*groups, other)

    def _build_images_page(self) -> Gtk.Widget:
        layout, banks = self.answers.layout, self.bank_count()
        sizes = " or ".join(size_text(size) for size in layout.image_sizes)
        if banks > 1:
            description = (
                f"This chip holds up to {banks} images of "
                f"{size_text(layout.bank_bytes)}, the first in the lowest bank. One "
                "image alone is repeated into every bank and works in any socket. "
                "Add more only if the board can select a bank. Drag an image, or "
                "use its arrows, to move it to another bank."
            )
        elif len(layout.lanes) > 1:
            description = (
                f"Choose the whole ROM as one file of {sizes}. It is split across "
                f"the {' and '.join(layout.lanes)} chips for you."
            )
        else:
            description = f"Choose the ROM image, {sizes}."
        group = Adw.PreferencesGroup(
            title="ROM Images" if banks > 1 else "ROM Image", description=description
        )
        full = self.banks_used() >= banks
        add = Gtk.Button(
            label="Add Another Image…"
            if self.answers.images and banks > 1
            else "Choose Image…",
            valign=Gtk.Align.CENTER,
            sensitive=not full or banks == 1,
        )
        add.add_css_class("suggested-action")
        add.connect("clicked", lambda _button: self._host.choose_rom(self.add_image))
        group.set_header_suffix(add)
        self.add_image_button = add
        self.image_rows: list[Adw.ActionRow] = []
        self.arrows: dict[tuple[int, int], Gtk.Button] = {}
        last = len(self.answers.images) - 1
        for index, (rom, (first, count)) in enumerate(
            zip(self.answers.images, self.spans(), strict=True)
        ):
            row = _row(
                rom.path.name,
                f"{rom.identity.label}, {size_text(rom.byte_count)}",
                activatable=False,
            )
            self.image_rows.append(row)
            if banks > 1:
                where = (
                    f"Bank {first}"
                    if count == 1
                    else f"Banks {first} to {first + count - 1}"
                )
                row.add_prefix(Gtk.Label(label=where, width_chars=12, xalign=0))
            if last > 0:
                self._make_movable(row, index, last)
            remove = Gtk.Button(
                icon_name="user-trash-symbolic",
                valign=Gtk.Align.CENTER,
                has_frame=False,
                tooltip_text="Remove this image",
            )
            remove.connect("clicked", lambda _b, index=index: self.remove_image(index))
            row.add_suffix(remove)
            group.add(row)
            for warning in rom.identity.warnings:
                group.add(_text_row(warning))
        if not self.answers.images:
            group.add(_text_row("No image chosen yet."))
        return self._page(group)

    def _make_movable(self, row: Adw.ActionRow, index: int, last: int) -> None:
        """Let a row be dragged onto another, or moved with its arrows.

        Dragging carries the row's place in the list, and dropping it on a row
        moves it to that row's place. The arrows do the same one step at a
        time, for the keyboard and for anyone who would sooner not drag.
        """
        row.add_prefix(Gtk.Image(icon_name="list-drag-handle-symbolic"))
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect(
            "prepare",
            lambda _source, _x, _y: Gdk.ContentProvider.new_for_value(
                GObject.Value(GObject.TYPE_INT, index)
            ),
        )
        source.connect(
            "drag-begin",
            lambda source, _drag: source.set_icon(Gtk.WidgetPaintable.new(row), 24, 24),
        )
        row.add_controller(source)
        target = Gtk.DropTarget.new(GObject.TYPE_INT, Gdk.DragAction.MOVE)
        target.connect(
            "drop", lambda _target, moved, _x, _y: self._dropped(moved, index)
        )
        row.add_controller(target)
        for icon, step, tooltip, possible in (
            ("go-up-symbolic", -1, "Move to a lower bank", index > 0),
            ("go-down-symbolic", 1, "Move to a higher bank", index < last),
        ):
            arrow = Gtk.Button(
                icon_name=icon,
                valign=Gtk.Align.CENTER,
                has_frame=False,
                tooltip_text=tooltip,
                sensitive=possible,
            )
            arrow.connect(
                "clicked", lambda _b, step=step: self.move_image(index, index + step)
            )
            row.add_suffix(arrow)
            self.arrows[index, step] = arrow

    def _dropped(self, moved: int, onto: int) -> bool:
        # Moving rebuilds the page, and with it the row whose drop target is
        # in the middle of delivering this signal. Let the drop finish first.
        call_on_main_loop(self.move_image, moved, onto)
        return True

    def _build_burn_page(self) -> Gtk.Widget:
        answers = self.answers
        summary = Adw.PreferencesGroup(title="What Will Be Burned")
        for step in range(BURN):
            row = _row(STEPS[step], answers.crumb(step), activatable=False)
            row.add_css_class("property")
            summary.add(row)
        groups = [summary]

        if self.parts and self.bank_count() > 1:
            groups.append(self._build_bank_map())

        chips = Adw.PreferencesGroup(
            title="Chips to Program",
            description="Each chip is written and then read back and compared. "
            "Label each one as it comes out of the socket.",
        )
        save = Gtk.Button(
            label="Save All Parts…", valign=Gtk.Align.CENTER, sensitive=bool(self.parts)
        )
        save.connect(
            "clicked", lambda _b: self._host.save_parts(self.parts, answers.stem)
        )
        chips.set_header_suffix(save)
        self.burn_buttons: list[Gtk.Button] = []
        for index, part in enumerate(self.parts):
            checksums = dict(fingerprint(part.data))
            row = _row(
                f"{part.label} for {part.device}",
                f"{size_text(len(part.data))}, CRC-32 {checksums['CRC-32']}. "
                f"{self.status[index]}",
                activatable=False,
            )
            if self.status[index] == WRITTEN:
                row.add_prefix(Gtk.Image(icon_name="object-select-symbolic"))
            burn = Gtk.Button(
                label="Burn Again…" if self.status[index] == WRITTEN else "Burn…",
                valign=Gtk.Align.CENTER,
            )
            burn.connect("clicked", lambda _b, index=index: self.burn(index))
            # Follows the window's write command, so that burning is possible
            # only while a programmer is connected. Offline, Save All Parts is
            # the way out.
            self._write_action.bind_property(
                "enabled", burn, "sensitive", GObject.BindingFlags.SYNC_CREATE
            )
            row.add_suffix(burn)
            self.burn_buttons.append(burn)
            chips.add(row)
        groups.append(chips)

        notes = Adw.PreferencesGroup(
            title="Before You Burn", description=answers.layout.summary
        )
        for note in answers.layout.notes:
            notes.add(_text_row(note))
        groups.append(notes)
        return self._page(*groups)

    def _build_bank_map(self) -> Adw.PreferencesGroup:
        """What each bank of the finished chip holds, read from the chip itself."""
        layout, (part,) = self.answers.layout, self.parts
        group = Adw.PreferencesGroup(
            title="Banks", description="From the top of the chip to the bottom"
        )
        bank = layout.bank_bytes
        count = len(part.data) // bank
        for number in reversed(range(count)):
            contents = part.data[number * bank : (number + 1) * bank]
            empty = contents.count(0xFF) == bank
            holds = "Empty" if empty else identify(contents).label
            where = "read by a plain socket" if number == count - 1 else ""
            group.add(_row(f"Bank {number}", ", ".join(filter(None, (holds, where)))))
        return group
