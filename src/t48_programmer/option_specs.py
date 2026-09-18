"""The wording of every option, kept apart from GTK so it can be checked.

Each entry names a field of minipro.Options. The options panel builds one
control per entry, and a test confirms that every field has exactly one, so an
option added to minipro.Options cannot be forgotten in the interface.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SwitchSpec:
    field: str
    title: str
    subtitle: str


@dataclass(frozen=True, slots=True)
class ChoiceSpec:
    """A fixed list of values. The first is minipro's own default."""

    field: str
    title: str
    subtitle: str
    choices: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SettingSpec:
    """A list of values that minipro supplies for the chosen chip."""

    field: str
    title: str
    unit: str


@dataclass(frozen=True, slots=True)
class OptionSection:
    title: str
    subtitle: str
    switches: tuple[SwitchSpec, ...] = ()
    choices: tuple[ChoiceSpec, ...] = ()


SECTIONS = (
    OptionSection(
        "Writing",
        "What happens before, during and after a write",
        switches=(
            SwitchSpec(
                "unprotect",
                "Remove Write Protection First",
                "Clears the chip's protection before writing or erasing.",
            ),
            SwitchSpec(
                "skip_erase",
                "Do Not Erase Before Writing",
                "For adding to a chip that already holds data you want to keep.",
            ),
            SwitchSpec(
                "skip_blank",
                "Skip Blank Blocks",
                "Faster, but only correct on an erased chip that can be written "
                "at any address.",
            ),
            SwitchSpec(
                "skip_verify",
                "Do Not Verify After Writing",
                "The write is not read back. Leave this off unless you have a reason.",
            ),
            SwitchSpec(
                "protect",
                "Write Protect Afterwards",
                "Sets the chip's protection once the write has been verified.",
            ),
        ),
        choices=(
            ChoiceSpec(
                "size_policy",
                "If the Image and Chip Differ in Size",
                "An image shorter than the chip leaves the rest untouched.",
                (
                    ("", "Stop with an error"),
                    ("warn", "Warn and continue"),
                    ("ignore", "Continue without a warning"),
                ),
            ),
        ),
    ),
    OptionSection(
        "Chip Checks",
        "How strictly the chip in the socket is checked",
        switches=(
            SwitchSpec(
                "ignore_id",
                "Ignore a Chip ID Mismatch",
                "For equivalent parts from another maker. A wrong voltage can "
                "destroy a chip, so be sure of the equivalence.",
            ),
            SwitchSpec(
                "skip_id",
                "Do Not Read the Chip ID",
                "Applies to reading, verifying and blank checking. minipro "
                "always reads the ID before it writes or erases.",
            ),
            SwitchSpec(
                "pin_check",
                "Test Pin Contacts First",
                "TL866II+ and T76 only. minipro has no pin test for the T48.",
            ),
        ),
    ),
    OptionSection(
        "Memory and Files",
        "Which part of the chip, and how a read is saved",
        choices=(
            ChoiceSpec(
                "memory",
                "Memory Section",
                "Microcontrollers keep code, data and fuses apart. Memory "
                "chips have only code.",
                (
                    ("", "Default"),
                    ("code", "Code"),
                    ("data", "Data"),
                    ("config", "Configuration and fuses"),
                    ("user", "User row"),
                ),
            ),
            ChoiceSpec(
                "file_format",
                "Save Reads As",
                "When writing, minipro recognises the format by itself.",
                (
                    ("", "Raw binary"),
                    ("ihex", "Intel HEX"),
                    ("srec", "Motorola S-record"),
                ),
            ),
            ChoiceSpec(
                "icsp",
                "In-Circuit Programming",
                "For a chip soldered to a board and reached through the ICSP header.",
                (
                    ("", "Off, the chip is in the socket"),
                    ("vcc", "On, the programmer powers the board"),
                    ("no_vcc", "On, the board has its own power"),
                ),
            ),
        ),
    ),
)

# The electrical section is built per chip from what minipro reports.
ELECTRICAL_TITLE = "Voltages and Timing"
ELECTRICAL_SUBTITLE = "Offered only where minipro allows them for the chosen chip"
SETTINGS = (
    SettingSpec("vpp", "Programming Voltage (VPP)", "V"),
    SettingSpec("vdd", "Write Voltage (VDD)", "V"),
    SettingSpec("vcc", "Verify Voltage (VCC)", "V"),
    SettingSpec("spi_clock", "SPI Clock", "MHz"),
)
PULSE_FIELD = "pulse"
PULSE_TITLE = "Programming Pulse"
PULSE_MAXIMUM = 65535


def covered_fields() -> list[str]:
    """Every Options field that some control sets."""
    covered = [spec.field for section in SECTIONS for spec in section.switches]
    covered += [spec.field for section in SECTIONS for spec in section.choices]
    covered += [spec.field for spec in SETTINGS]
    covered.append(PULSE_FIELD)
    return covered
