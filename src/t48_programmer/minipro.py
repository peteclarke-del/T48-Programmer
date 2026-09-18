"""Where minipro is, and the command line for everything asked of it.

This module is the only place that knows minipro's flags. The rest of the
application names an action and fills in an Options record, and build_command
turns the pair into an argument list. Nothing here touches the hardware, so
the whole contract with minipro can be tested without a programmer.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, fields
from pathlib import Path

from . import simulator

# Runs the bundled simulator in place of minipro, for the interface tests, the
# documentation screenshots, and anyone who wants to look before buying.
DEMO_VARIABLE = "T48_PROGRAMMER_DEMO"
# Names a particular minipro, such as one built from a checkout.
EXECUTABLE_VARIABLE = "T48_PROGRAMMER_MINIPRO"

# The name minipro's -q option takes for each programmer that -k reports. The
# TL866II+, T48 and T56 share a USB identity, and minipro tells them apart by
# asking the firmware, so the key is only known once a programmer answers.
DATABASE_NAMES = {
    "tl866a": "TL866A",
    "tl866ii": "TL866II",
    "t48": "T48",
    "t56": "T56",
    "t76": "T76",
}
DEFAULT_PROGRAMMER = "t48"

MEMORY_SECTIONS = ("code", "data", "config", "user")
READ_FORMATS = ("ihex", "srec")
SIZE_POLICIES = ("warn", "ignore")
ICSP_MODES = ("vcc", "no_vcc")


def demo_mode() -> bool:
    return os.environ.get(DEMO_VARIABLE) == "1"


def insert_blank_chip(device: str) -> None:
    """In the demonstration, stand in for the person putting in a fresh chip.

    The simulator remembers what each kind of chip holds, and a set of six
    chips is six chips of one kind. Without this, the second would be written
    over the first and fail to verify. With real hardware this does nothing.
    """
    if demo_mode():
        simulator.insert_blank_chip(device)


def base_command() -> list[str] | None:
    """The start of every minipro command, or None when minipro is absent."""
    if demo_mode():
        # Run by path, so the simulator starts whatever PYTHONPATH holds.
        return [sys.executable, str(Path(__file__).with_name("simulator.py"))]
    executable = os.environ.get(EXECUTABLE_VARIABLE) or shutil.which("minipro")
    return [executable] if executable else None


@dataclass(frozen=True, slots=True)
class Options:
    """Every choice minipro offers for an operation on a chip.

    An empty string or False leaves minipro to its default. The voltages and
    the pulse stay as the text minipro printed for them, because "12.5" has to
    go back exactly as it came.
    """

    memory: str = ""
    file_format: str = ""
    size_policy: str = ""
    icsp: str = ""
    skip_erase: bool = False
    skip_verify: bool = False
    skip_blank: bool = False
    skip_id: bool = False
    ignore_id: bool = False
    unprotect: bool = False
    protect: bool = False
    pin_check: bool = False
    vpp: str = ""
    vdd: str = ""
    vcc: str = ""
    pulse: str = ""
    spi_clock: str = ""


# Options that are a bare flag.
_SWITCHES = {
    "skip_erase": "-e",
    "skip_verify": "-v",
    "skip_blank": "-B",
    "skip_id": "-x",
    "ignore_id": "-y",
    "unprotect": "-u",
    "protect": "-P",
    "pin_check": "-z",
}
# Options where the chosen value selects the flag.
_CHOICES = {
    "size_policy": {"warn": ["-s"], "ignore": ["-S"]},
    "icsp": {"vcc": ["-i"], "no_vcc": ["-I"]},
}
# Options that carry their value after a flag.
_VALUES = {"memory": "-c", "file_format": "-f"}
# Options passed as "-o name=value".
_SETTINGS = ("vpp", "vdd", "vcc", "pulse", "spi_clock")

_EVERY_CHIP_ACTION = frozenset({"ignore_id", "pin_check", "icsp"})
_ELECTRICAL = frozenset({"vpp", "vdd", "vcc", "pulse"})


@dataclass(frozen=True, slots=True)
class Action:
    """One thing minipro can be asked to do, and the options that apply to it.

    minipro rejects some combinations outright, such as skipping the ID read
    during a write, and silently ignores others. Listing the accepted options
    here keeps a choice made for one action from leaking into the next.
    """

    key: str
    title: str
    flags: tuple[str, ...]
    progress_title: str
    file_role: str = ""
    needs_chip: bool = True
    destructive: bool = False
    options: frozenset[str] = frozenset()


ACTIONS = {
    action.key: action
    for action in (
        Action(
            "read",
            "Read Chip to File",
            ("-r",),
            "Reading chip…",
            file_role="output",
            options=_EVERY_CHIP_ACTION
            | {"memory", "file_format", "skip_id", "spi_clock"},
        ),
        Action(
            "write",
            "Write Image to Chip",
            ("-w",),
            "Writing chip…",
            file_role="input",
            destructive=True,
            options=_EVERY_CHIP_ACTION
            | _ELECTRICAL
            | {
                "memory",
                "size_policy",
                "skip_erase",
                "skip_verify",
                "skip_blank",
                "unprotect",
                "protect",
                "spi_clock",
            },
        ),
        Action(
            "verify",
            "Verify Chip Against Image",
            ("-m",),
            "Verifying chip…",
            file_role="input",
            options=_EVERY_CHIP_ACTION
            | {"memory", "size_policy", "skip_id", "spi_clock"},
        ),
        Action(
            "blank_check",
            "Blank Check",
            ("-b",),
            "Checking that the chip is blank…",
            options=_EVERY_CHIP_ACTION | {"memory", "skip_id", "spi_clock"},
        ),
        Action(
            "erase",
            "Erase Chip",
            ("-E",),
            "Erasing chip…",
            destructive=True,
            options=_EVERY_CHIP_ACTION | {"unprotect", "spi_clock"},
        ),
        Action(
            "read_id",
            "Read Chip ID",
            ("-D",),
            "Reading the chip ID…",
            options=frozenset({"icsp"}),
        ),
        Action(
            "pin_check",
            "Test Pin Contacts",
            ("-z",),
            "Testing pin contacts…",
            options=frozenset({"icsp"}),
        ),
        Action(
            "logic_test",
            "Test Logic IC or RAM",
            ("-T",),
            "Testing the device…",
            options=frozenset({"vcc"}),
        ),
        Action(
            "hardware_check",
            "Programmer Self Test",
            ("-t",),
            "Testing the programmer…",
            needs_chip=False,
        ),
        Action(
            "detect_spi_8",
            "Detect 8-Pin SPI Flash",
            ("-a", "8"),
            "Detecting the SPI flash…",
            needs_chip=False,
        ),
        Action(
            "detect_spi_16",
            "Detect 16-Pin SPI Flash",
            ("-a", "16"),
            "Detecting the SPI flash…",
            needs_chip=False,
        ),
    )
}


def option_arguments(action: Action, options: Options) -> list[str]:
    """The arguments for the options this action accepts, in a stable order."""
    arguments: list[str] = []
    for field in fields(options):
        name = field.name
        value = getattr(options, name)
        if not value or name not in action.options:
            continue
        if name in _SWITCHES:
            arguments.append(_SWITCHES[name])
        elif name in _CHOICES:
            arguments.extend(_CHOICES[name][value])
        elif name in _VALUES:
            arguments.extend([_VALUES[name], value])
        elif name in _SETTINGS:
            arguments.extend(["-o", f"{name}={value}"])
    return arguments


def build_command(
    base: list[str],
    action: Action,
    chip: str = "",
    path: Path | None = None,
    options: Options | None = None,
) -> list[str]:
    """The full argument list for one operation.

    The result is always a list handed straight to the process, never a shell
    string. Chip names contain "@", "(" and spaces, and an image can live in
    any folder the user can name.
    """
    if action.needs_chip and not chip:
        raise ValueError(f"{action.title} needs a chip to be chosen.")
    if action.file_role and path is None:
        raise ValueError(f"{action.title} needs a file.")
    command = list(base)
    if action.needs_chip:
        command.extend(["-p", chip])
    command.extend(action.flags)
    if action.file_role:
        command.append(str(path))
    command.extend(option_arguments(action, options or Options()))
    return command


def run_query(arguments: list[str], timeout: float = 20.0) -> str | None:
    """Run a short minipro query and return its output, or None without minipro.

    minipro prints listings on stdout and everything else on stderr, so the two
    are joined. Standard input is closed because minipro asks which database to
    list when no programmer is attached and -q was not given.
    """
    base = base_command()
    if base is None:
        return None
    completed = subprocess.run(
        [*base, *arguments],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        text=True,
        errors="replace",
        timeout=timeout,
    )
    return "\n".join(part for part in (completed.stdout, completed.stderr) if part)


def database_name(programmer_key: str) -> str:
    """The -q value for a programmer, falling back to the T48."""
    return DATABASE_NAMES.get(programmer_key, DATABASE_NAMES[DEFAULT_PROGRAMMER])
