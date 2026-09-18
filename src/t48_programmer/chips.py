"""The chips minipro supports, and what it knows about each one.

The catalogue is whatever the installed minipro lists for the programmer in
use, so a newer minipro brings its new chips without a change here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import minipro

_MEMORY_TERM = re.compile(r"(?P<count>\d+)\s+(?P<unit>Bytes|Words|Bits)")
_UNIT_BYTES = {"Bytes": 1.0, "Words": 2.0, "Bits": 0.125}

# The heading minipro prints above each list of values, and the option each
# list belongs to. "VCC voltages" is the logic test's list, which has no
# "verify" in its heading.
_SETTING_HEADINGS = {
    "VPP": "vpp",
    "VDD write": "vdd",
    "VCC verify": "vcc",
    "VCC": "vcc",
    "SPI clock": "spi_clock",
}
_DEFAULT_PATTERN = re.compile(
    r"^Default (?P<heading>VPP|VDD write|VCC verify|VCC)\b.*?:\s*(?P<value>[\d.]+)"
)
_AVAILABLE_PATTERN = re.compile(
    r"^Available (?P<heading>VPP|VDD write|VCC verify|VCC|SPI clock)\b[^:]*:(?P<rest>.*)$"
)
_PULSE_PATTERN = re.compile(r"^Default write pulse:\s*(?P<value>\d+)")


@dataclass(frozen=True, slots=True)
class Setting:
    """One electrical option: minipro's default and the values it accepts."""

    default: str
    choices: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChipInfo:
    """What ``minipro -d`` reports for a chip."""

    name: str
    details: dict[str, str] = field(default_factory=dict)
    settings: dict[str, Setting] = field(default_factory=dict)
    pulse_default: str = ""

    @property
    def memory(self) -> str:
        return self.details.get("Memory", "")

    @property
    def package(self) -> str:
        return self.details.get("Package", "")

    @property
    def code_bytes(self) -> int:
        """The size of the code memory in bytes, or 0 when none is reported.

        minipro describes a microcontroller as "16384 Words + 1024 Bytes",
        code first and data second. Only the first term is the size of the
        image that a plain read or write moves.
        """
        match = _MEMORY_TERM.search(self.memory)
        if match is None:
            return 0
        return int(int(match.group("count")) * _UNIT_BYTES[match.group("unit")])

    @property
    def is_logic(self) -> bool:
        """True for the logic and RAM test database, which has no memory."""
        return "Vector count" in self.details


def parse_chip_info(output: str) -> ChipInfo | None:
    """Parse the block printed by ``minipro -d``, or None if there is none.

    minipro wraps its lists of voltages across several lines, so a line with no
    heading of its own continues the list above it.
    """
    details: dict[str, str] = {}
    defaults: dict[str, str] = {}
    choices: dict[str, list[str]] = {}
    pulse_default = ""
    open_list: list[str] | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or set(line) == {"-"} or "Chip Info" in line:
            open_list = None
            continue
        if match := _AVAILABLE_PATTERN.match(line):
            open_list = choices.setdefault(_SETTING_HEADINGS[match["heading"]], [])
            line = match["rest"]
        elif match := _DEFAULT_PATTERN.match(line):
            defaults[_SETTING_HEADINGS[match["heading"]]] = match["value"]
            open_list = None
            continue
        elif match := _PULSE_PATTERN.match(line):
            pulse_default = match["value"]
            open_list = None
            continue
        elif ":" in line:
            label, _, value = line.partition(":")
            details[label.strip()] = value.strip()
            open_list = None
            continue
        if open_list is not None:
            open_list.extend(part.strip() for part in line.split(",") if part.strip())

    if "Name" not in details:
        return None
    settings = {
        option: Setting(defaults.get(option, ""), tuple(values))
        for option, values in choices.items()
    }
    return ChipInfo(details["Name"], details, settings, pulse_default)


@lru_cache(maxsize=8)
def load_catalogue(programmer_key: str = minipro.DEFAULT_PROGRAMMER) -> tuple[str, ...]:
    """Every chip name minipro lists for a programmer, in database order.

    The database is passed explicitly with -q. Without it, and with no
    programmer attached, minipro stops to ask which database is meant.
    """
    output = minipro.run_query(["-q", minipro.database_name(programmer_key), "-l"])
    if output is None:
        return ()
    names = (line.strip() for line in output.splitlines())
    return tuple(dict.fromkeys(name for name in names if name))


@lru_cache(maxsize=256)
def chip_info(
    name: str, programmer_key: str = minipro.DEFAULT_PROGRAMMER
) -> ChipInfo | None:
    """Ask minipro about one chip. None when minipro is absent or disagrees."""
    output = minipro.run_query(
        ["-q", minipro.database_name(programmer_key), "-d", name]
    )
    return parse_chip_info(output) if output else None


def search(catalogue: tuple[str, ...], text: str, limit: int = 500) -> list[str]:
    """Chips whose name contains every word typed, in any order and case.

    An exact name comes first, then names that begin with the text, then the
    rest, so typing "27C256" leads with the 27C256 parts and not with every
    longer part number that happens to contain it.
    """
    words = text.upper().split()
    if not words:
        return list(catalogue[:limit])
    needle = text.strip().upper()

    def rank(name: str) -> int:
        upper = name.upper()
        if upper == needle or upper.partition("@")[0] == needle:
            return 0
        return 1 if upper.startswith(needle) else 2

    matches = [name for name in catalogue if all(w in name.upper() for w in words)]
    matches.sort(key=rank)
    return matches[:limit]
