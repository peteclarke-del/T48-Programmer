"""The Options group of the main page, built from option_specs."""

from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from . import option_specs as specs  # noqa: E402
from .chips import ChipInfo  # noqa: E402
from .minipro import Options  # noqa: E402


class OptionsPanel(Adw.PreferencesGroup):
    """Collapsed sections of switches and lists that read back as Options."""

    def __init__(self) -> None:
        super().__init__(
            title="Options",
            description="minipro's defaults suit most chips. Open a section to "
            "change one.",
        )
        # One reader per Options field. Each returns the field's current value.
        self._readers: dict[str, Callable[[], str | bool]] = {}
        self._resetters: list[Callable[[], None]] = []
        self._lists: dict[str, Adw.ComboRow] = {}
        # The value minipro takes for each entry of each list, by field.
        self._values: dict[str, list[str]] = {}
        for section in specs.SECTIONS:
            expander = Adw.ExpanderRow(title=section.title, subtitle=section.subtitle)
            for switch in section.switches:
                expander.add_row(self._build_switch(switch))
            for choice in section.choices:
                expander.add_row(
                    self._build_list(choice.field, choice.title, choice.subtitle)
                )
                values, labels = zip(*choice.choices, strict=True)
                self._fill_list(choice.field, list(labels), list(values))
            self.add(expander)

        self._electrical = Adw.ExpanderRow(
            title=specs.ELECTRICAL_TITLE, subtitle=specs.ELECTRICAL_SUBTITLE
        )
        for setting in specs.SETTINGS:
            self._electrical.add_row(self._build_list(setting.field, setting.title, ""))
        self._pulse = Adw.SpinRow.new_with_range(0, specs.PULSE_MAXIMUM, 10)
        self._pulse.set_title(specs.PULSE_TITLE)
        self._readers[specs.PULSE_FIELD] = lambda: (
            str(int(self._pulse.get_value())) if self._pulse.get_value() else ""
        )
        self._resetters.append(lambda: self._pulse.set_value(0))
        self._electrical.add_row(self._pulse)
        self.add(self._electrical)
        self.set_chip_info(None)

    def _build_switch(self, spec: specs.SwitchSpec) -> Adw.SwitchRow:
        row = Adw.SwitchRow(title=spec.title, subtitle=spec.subtitle)
        self._readers[spec.field] = row.get_active
        self._resetters.append(lambda: row.set_active(False))
        return row

    def _build_list(self, field: str, title: str, subtitle: str) -> Adw.ComboRow:
        row = Adw.ComboRow(title=title, subtitle=subtitle)
        self._lists[field] = row
        self._readers[field] = lambda: self._values[field][row.get_selected()]
        self._resetters.append(lambda: row.set_selected(0))
        return row

    def _fill_list(self, field: str, labels: list[str], values: list[str]) -> None:
        row = self._lists[field]
        self._values[field] = values
        row.set_model(Gtk.StringList.new(labels))
        row.set_selected(0)

    def set_chip_info(self, info: ChipInfo | None) -> None:
        """Offer the voltages and clocks minipro lists for this chip.

        The lists differ from chip to chip and from programmer to programmer,
        so they are taken from minipro each time and never assumed. A setting
        the chip does not have is hidden, and the section is hidden when the
        chip has none.
        """
        settings = info.settings if info is not None else {}
        for spec in specs.SETTINGS:
            setting = settings.get(spec.field)
            row = self._lists[spec.field]
            row.set_visible(setting is not None)
            if setting is None:
                self._fill_list(spec.field, ["Default"], [""])
                continue
            default = (
                f"Default, {setting.default} {spec.unit}"
                if setting.default
                else "Default"
            )
            labels = [default, *(f"{value} {spec.unit}" for value in setting.choices)]
            self._fill_list(spec.field, labels, ["", *setting.choices])
        has_pulse = info is not None and bool(info.pulse_default)
        self._pulse.set_visible(has_pulse)
        self._pulse.set_value(0)
        self._pulse.set_subtitle(
            f"Microseconds. 0 keeps the default of {info.pulse_default}."
            if has_pulse
            else ""
        )
        self._electrical.set_visible(bool(settings) or has_pulse)

    def options(self) -> Options:
        return Options(**{field: read() for field, read in self._readers.items()})

    def reset(self) -> None:
        for reset in self._resetters:
            reset()
