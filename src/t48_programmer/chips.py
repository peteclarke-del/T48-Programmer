"""The chips minipro supports, and what it knows about each one.

The catalogue is whatever the installed minipro lists for the programmer in
use, so a newer minipro brings its new chips without a change here.
"""

from __future__ import annotations

import re
import subprocess
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

# minipro 0.7.4, the release, prints a chip's voltages more briefly than the
# builds that followed it: "VPP programming voltage: 13V", with no "Default"
# before it and no list of the values it would accept after it. Both are read.
_RELEASE_DEFAULT_PATTERN = re.compile(
    r"^(?P<heading>VPP|VDD write|VCC verify|VCC)(?: programming)? voltage:"
    r"\s*(?P<value>[\d.]+)\s*V$"
)
_RELEASE_PULSE_PATTERN = re.compile(r"^Pulse delay:\s*(?P<value>\d+)\s*us$")

# The values minipro 0.7.4 accepts for each programmer, copied from the tables
# in its main.c that it checks -o vpp, vdd and vcc against. They are used only
# when minipro names a default and gives no list of its own, which is that
# release. A newer minipro prints its lists, and what it prints is what is
# offered. Were this table left out, the release that the package bundles would
# never show Voltages and Timing, and VPP could not be changed at all.
_SUPPLIES = ("3.3", "4", "4.5", "5", "5.5", "6.5")
_VPP_TL866II = (
    "9", "9.5", "10", "11", "11.5", "12", "12.5", "13",
    "13.5", "14", "14.5", "15.5", "16", "16.5", "17", "18",
)  # fmt: skip
_VPP_TL866A = ("10", "12.5", "13.5", "14", "16", "17", "18", "21")
_LOGIC_SUPPLIES = ("5", "3.3", "2.5", "1.8")
RELEASE_VOLTAGES = {
    "tl866a": {"vpp": _VPP_TL866A, "vdd": _SUPPLIES, "vcc": _SUPPLIES},
    "tl866ii": {"vpp": _VPP_TL866II, "vdd": _SUPPLIES, "vcc": _SUPPLIES},
    "t48": {"vpp": (*_VPP_TL866II, "21", "25"), "vdd": _SUPPLIES, "vcc": _SUPPLIES},
}
RELEASE_VOLTAGES["t56"] = RELEASE_VOLTAGES["t48"]


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
    # Exactly what minipro printed, for Chip Information.
    text: str = ""

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
    def is_plain_memory(self) -> bool:
        """True for an EPROM, EEPROM or flash chip, which is one block of memory.

        minipro describes a microcontroller as code plus data, "16384 Words +
        1024 Bytes". Repeating an image to fill the chip makes sense for a ROM
        and none for firmware.
        """
        return bool(self.code_bytes) and "+" not in self.memory

    @property
    def is_logic(self) -> bool:
        """True for the logic and RAM test database, which has no memory."""
        return "Vector count" in self.details


def parse_chip_info(
    output: str, programmer_key: str = minipro.DEFAULT_PROGRAMMER
) -> ChipInfo | None:
    """Parse the block printed by ``minipro -d``, or None if there is none.

    minipro wraps its lists of voltages across several lines, so a line with no
    heading of its own continues the list above it. Where it names a default
    and lists nothing, as the 0.7.4 release does, the values that release
    accepts for this programmer are offered.
    """
    details: dict[str, str] = {}
    defaults: dict[str, str] = {}
    choices: dict[str, list[str]] = {}
    pulse_default = ""
    open_list: list[str] | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or set(line) <= {"-", "*"} or "Chip Info" in line:
            open_list = None
            continue
        if match := _AVAILABLE_PATTERN.match(line):
            open_list = choices.setdefault(_SETTING_HEADINGS[match["heading"]], [])
            line = match["rest"]
        elif match := _DEFAULT_PATTERN.match(line) or _RELEASE_DEFAULT_PATTERN.match(
            line
        ):
            defaults[_SETTING_HEADINGS[match["heading"]]] = match["value"]
            open_list = None
            continue
        elif match := _PULSE_PATTERN.match(line) or _RELEASE_PULSE_PATTERN.match(line):
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
    accepted = RELEASE_VOLTAGES.get(programmer_key, {})
    if "Vector count" in details:
        accepted = {"vcc": _LOGIC_SUPPLIES}
    for option in defaults:
        if option not in choices and option in accepted:
            choices[option] = list(accepted[option])
    settings = {
        option: Setting(defaults.get(option, ""), tuple(values))
        for option, values in choices.items()
    }
    return ChipInfo(details["Name"], details, settings, pulse_default, output.strip())


# Answers from minipro, kept for the life of the process. Only answers are
# kept. A failure is not remembered, so minipro installed or repaired while the
# application is open is found the next time it is asked.
_catalogues: dict[str, tuple[str, ...]] = {}
_chip_infos: dict[tuple[str, str], ChipInfo] = {}


def clear_cache() -> None:
    _catalogues.clear()
    _chip_infos.clear()
    _upper_case.cache_clear()


def _query(arguments: list[str]) -> minipro.QueryResult | None:
    """A query whose failure to run at all is the same as no answer."""
    try:
        return minipro.run_query(arguments)
    except (OSError, subprocess.TimeoutExpired):
        return None


def load_catalogue(programmer_key: str = minipro.DEFAULT_PROGRAMMER) -> tuple[str, ...]:
    """Every chip name minipro lists for a programmer, in database order.

    Empty when minipro is absent or the listing failed. The database is passed
    explicitly with -q. Without it, and with no programmer attached, minipro
    stops to ask which database is meant.
    """
    database = minipro.database_name(programmer_key)
    if database not in _catalogues:
        result = _query(["-q", database, "-l"])
        if result is None or not result.succeeded:
            return ()
        names = (line.strip() for line in result.stdout.splitlines())
        catalogue = tuple(dict.fromkeys(name for name in names if name))
        if not catalogue:
            return ()
        _catalogues[database] = catalogue
    return _catalogues[database]


def chip_info(
    name: str, programmer_key: str = minipro.DEFAULT_PROGRAMMER
) -> ChipInfo | None:
    """Ask minipro about one chip. None when minipro is absent or disagrees."""
    key = (minipro.database_name(programmer_key), name)
    if key not in _chip_infos:
        result = _query(["-q", key[0], "-d", name])
        info = (
            parse_chip_info(result.text, programmer_key)
            if result and result.succeeded
            else None
        )
        if info is None:
            return None
        _chip_infos[key] = info
    return _chip_infos[key]


@lru_cache(maxsize=8)
def _upper_case(catalogue: tuple[str, ...]) -> tuple[str, ...]:
    """The catalogue in capitals, made once and not on every keystroke."""
    return tuple(name.upper() for name in catalogue)


def search(catalogue: tuple[str, ...], text: str, limit: int) -> tuple[list[str], int]:
    """The best matches for what was typed, and how many matches there are in all.

    A chip matches when its name contains every word typed, in any order and
    case. An exact name comes first, then names that begin with the text, then
    the rest, so typing "27C256" leads with the 27C256 parts and not with every
    longer part number that happens to contain it. One pass over the catalogue
    sorts the matches into those three, which is all the ordering there is.
    """
    words = text.upper().split()
    if not words:
        return list(catalogue[:limit]), len(catalogue)
    uppers = _upper_case(catalogue)
    # Narrowed a word at a time. A comprehension per word is some fifteen times
    # quicker here than asking all() of a generator for each of 27,000 names.
    found = range(len(catalogue))
    for word in words:
        found = [index for index in found if word in uppers[index]]
    needle = text.strip().upper()
    exact: list[str] = []
    leading: list[str] = []
    others: list[str] = []
    for index in found:
        upper = uppers[index]
        if upper == needle or upper.partition("@")[0] == needle:
            exact.append(catalogue[index])
        elif upper.startswith(needle):
            leading.append(catalogue[index])
        else:
            others.append(catalogue[index])
    matches = exact + leading + others
    return matches[:limit], len(matches)
