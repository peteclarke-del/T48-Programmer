#!/usr/bin/env python3
"""A stand-in for minipro that needs no programmer and no chip.

It accepts the options the application passes and answers in minipro's own
words, including the carriage-return progress line, so the real parsers and the
real subprocess runner are what get exercised. The chip in the imaginary socket
is a file, so a write followed by a read returns what was written, a UV EPROM
can only have bits cleared until it is wiped, and a second write over a used
EPROM fails verification just as it does on the bench.

Run by path as a script. It imports nothing from the package, so it starts the
same way whether or not the package is installed.

Environment:
  T48_PROGRAMMER_SIMULATOR_STATE   folder holding the chip contents
  T48_PROGRAMMER_SIMULATOR_DELAY   seconds per progress step, default 0.02
  T48_PROGRAMMER_SIMULATOR_ABSENT  set to 1 to unplug the programmer
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

VERSION = "0.7.4"
BANNER = "Found T48 00.1.31 (0x11f)"
SEPARATOR = "-" * 40
ERASED = 0xFF
STEPS = 25

UV_EPROM, EEPROM, FLASH, SPI_FLASH, LOGIC = "uv", "eeprom", "flash", "spi", "logic"

T48_VOLTAGES = (
    "Default VPP programming voltage: {vpp} V\n"
    "Available VPP voltages [V]: 9, 9.5, 10, \n"
    "11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5, \n"
    "15.5, 16, 16.5, 17, 18, 21, 25\n\n"
    "Default VDD write voltage: 6.5 V\n"
    "Available VDD write voltages [V]: 1.2, \n"
    "1.8, 2.5, 3, 3.3, 4, 4.5, 4.75, 5, \n"
    "5.25, 5.5, 5.75, 6, 6.25, 6.5\n\n"
    "Default VCC verify voltage: 5 V\n"
    "Available VCC verify voltages [V]: 1.2, \n"
    "1.8, 2.5, 3, 3.3, 4, 4.5, 4.75, 5, \n"
    "5.25, 5.5, 5.75, 6, 6.25, 6.5\n\n"
    "Default write pulse: 100 us\n"
    "Available write pulse[us]: 1-65535\n" + SEPARATOR + "\n"
)
SPI_CLOCKS = (
    "Available SPI clock frequencies [MHz]: \n4, 8, 15, 30\n" + SEPARATOR + "\n"
)
LOGIC_VOLTAGES = (
    "Default VCC voltage: 5 V\nAvailable VCC voltages [V]: 1.8, 2.5, \n3.3, 5\n"
)


@dataclass(frozen=True)
class Chip:
    name: str
    kind: str
    size: int
    package: str
    chip_id: int = 0
    word_wide: bool = False
    vpp: str = "12.5"


CHIPS = {
    chip.name.upper(): chip
    for chip in (
        Chip("M27C400@DIP40", UV_EPROM, 512 * 1024, "DIP40", 0x20B2, word_wide=True),
        Chip("AM27C400@DIP40", UV_EPROM, 512 * 1024, "DIP40", 0x0198, word_wide=True),
        Chip("MX27C4100@DIP40", UV_EPROM, 512 * 1024, "DIP40", 0xC2D8, word_wide=True),
        Chip("M27C1001@DIP32", UV_EPROM, 128 * 1024, "DIP32", 0x2005),
        Chip("AT27C010@DIP32", UV_EPROM, 128 * 1024, "DIP32", 0x1E05, vpp="13"),
        Chip("AM27C010@DIP32", UV_EPROM, 128 * 1024, "DIP32", 0x010E),
        Chip("M27C256B@DIP28", UV_EPROM, 32 * 1024, "DIP28", 0x208D, vpp="13"),
        Chip("AT27C256R@DIP28", UV_EPROM, 32 * 1024, "DIP28", 0x1E8C, vpp="13"),
        Chip("AM27C256@DIP28", UV_EPROM, 32 * 1024, "DIP28", 0x0110),
        Chip("27128@DIP28", UV_EPROM, 16 * 1024, "DIP28", vpp="21"),
        Chip("2764@DIP28", UV_EPROM, 8 * 1024, "DIP28", vpp="21"),
        Chip("M2764A@DIP28", UV_EPROM, 8 * 1024, "DIP28", 0x2008),
        Chip("M27128A@DIP28", UV_EPROM, 16 * 1024, "DIP28", 0x2089),
        Chip("M27C512@DIP28", UV_EPROM, 64 * 1024, "DIP28", 0x203D),
        Chip("AM27C020@DIP32", UV_EPROM, 256 * 1024, "DIP32", 0x0197),
        Chip("SST39SF010A", FLASH, 128 * 1024, "DIP32", 0xBFB5),
        Chip("SST39SF020A", FLASH, 256 * 1024, "DIP32", 0xBFB6),
        Chip("W27C512@DIP28", EEPROM, 64 * 1024, "DIP28", 0xDA08, vpp="12"),
        Chip("AT28C256", EEPROM, 32 * 1024, "DIP28"),
        Chip("AT28C64B", EEPROM, 8 * 1024, "DIP28"),
        Chip("SST39SF040", FLASH, 512 * 1024, "DIP32", 0xBFB7),
        Chip("AM29F040B@DIP32", FLASH, 512 * 1024, "DIP32", 0x01A4),
        Chip("W25Q64JV@SOIC8", SPI_FLASH, 8 * 1024 * 1024, "DIP8", 0xEF4017),
        Chip("7400", LOGIC, 0, "DIP14"),
        Chip("74245", LOGIC, 0, "DIP20"),
    )
}


def say(text: str = "") -> None:
    print(text, file=sys.stderr, flush=True)


def delay() -> float:
    return float(os.environ.get("T48_PROGRAMMER_SIMULATOR_DELAY", "0.02"))


def state_folder() -> Path:
    """Where the chips are kept: a folder that is this user's and no one else's.

    A fixed name in /tmp can be made first by another user of the machine, who
    could leave a symbolic link in it where a chip would go, and a write to the
    chip would then overwrite whatever the link pointed at. The folder is kept
    under the user's runtime directory where there is one, is made private, and
    is refused if it turns out to belong to someone else.
    """
    named = os.environ.get("T48_PROGRAMMER_SIMULATOR_STATE")
    if named:
        folder = Path(named)
    else:
        base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
        folder = Path(base) / f"t48-programmer-simulator-{os.getuid()}"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    status = folder.lstat()
    if status.st_uid != os.getuid() or not stat.S_ISDIR(status.st_mode):
        raise SystemExit(f"{folder} is not a folder of yours, so it was not used.")
    return folder


def state_file(chip: Chip) -> Path:
    folder = state_folder()
    safe_name = "".join(c if c.isalnum() else "_" for c in chip.name)
    return folder / f"{safe_name}.bin"


def insert_blank_chip(device: str) -> None:
    """Forget what a chip held, as when a fresh one goes into the socket."""
    chip = CHIPS.get(device.upper())
    if chip is not None:
        state_file(chip).unlink(missing_ok=True)


def load_chip(chip: Chip) -> bytearray:
    path = state_file(chip)
    if path.is_file() and path.stat().st_size == chip.size:
        return bytearray(path.read_bytes())
    return bytearray([ERASED]) * chip.size


def stage(label: str, percentages: bool = True) -> None:
    """Draw one progress stage the way minipro's progress_status() does."""
    started = time.monotonic()
    sys.stderr.write(f"\r\x1b[K{label}")
    sys.stderr.flush()
    if percentages:
        for step in range(STEPS + 1):
            sys.stderr.write(f"\r\x1b[K{label}{step * 100 // STEPS:2d}%")
            sys.stderr.flush()
            time.sleep(delay())
    elapsed = time.monotonic() - started
    sys.stderr.write(f"\r\x1b[K{label}{elapsed:.2f} Sec  OK\n")
    sys.stderr.flush()


def chip_info(chip: Chip) -> str:
    lines = ["", "---------------Chip Info----------------", f"Name: {chip.name}"]
    if chip.kind == LOGIC:
        lines += [f"Package:\t {chip.package}", "Vector count:\t 4", SEPARATOR]
        return "\n".join(lines) + "\n" + LOGIC_VOLTAGES
    memory = f"{chip.size // 2} Words" if chip.word_wide else f"{chip.size} Bytes"
    lines += [
        "Available on: T48, T56",
        f"Memory: {memory}",
        f"Package: {chip.package}",
        "Protocol: 0x07",
        "Read buffer size: 1024 Bytes",
        "Write buffer size: 128 Bytes",
        SEPARATOR,
    ]
    text = "\n".join(lines) + "\n"
    if chip.kind == UV_EPROM or chip.name.startswith("W27C"):
        text += T48_VOLTAGES.format(vpp=chip.vpp)
    if chip.kind == SPI_FLASH:
        text += SPI_CLOCKS
    return text


def first_difference(expected: bytes, actual: bytes) -> int | None:
    if expected == actual:
        return None
    return next(
        i
        for i, pair in enumerate(zip(expected, actual, strict=True))
        if pair[0] != pair[1]
    )


def verify(expected: bytes, actual: bytes, blank_check: bool) -> int:
    stage("Reading Code...  ")
    at = first_difference(expected, actual)
    if at is not None:
        say(
            f"Verification failed at address 0x{at:04X}: "
            f"File=0x{expected[at]:02X}, Device=0x{actual[at]:02X}"
        )
        return 1
    say("Code memory section is blank." if blank_check else "Verification OK")
    return 0


def load_image(arguments: argparse.Namespace, chip: Chip) -> bytes | None:
    data = Path(arguments.write or arguments.verify).read_bytes()
    if len(data) == chip.size:
        return data
    if arguments.no_size_error or arguments.no_size_warning:
        if arguments.no_size_error:
            say(f"Warning: Incorrect file size: {len(data)} (needed {chip.size})")
        return data[: chip.size].ljust(chip.size, bytes([ERASED]))
    say(f"Incorrect file size: {len(data)} (needed {chip.size}, use -s/S to ignore)")
    return None


def run_chip_action(arguments: argparse.Namespace, chip: Chip) -> int:
    say(BANNER)
    say("Warning: T48 support is not yet complete!")
    if arguments.pin_check:
        say("Pin test is not supported.")
        if not any(
            (arguments.read, arguments.write, arguments.verify, arguments.erase)
        ) and not (arguments.blank_check or arguments.read_id):
            return 0
    if arguments.logic_test:
        if chip.kind != LOGIC:
            say("T48: test vectors are not defined for this device type.")
            return 1
        say("      1  2  3  4  5  6  7  8  9  10 11 12 13 14")
        for vector in range(4):
            say(f"{vector:04d}: 0  0  H  0  0  H  G  H  0  0  H  0  0  V")
        say("Logic test successful.")
        return 0
    if chip.kind == LOGIC:
        say("This device can only be tested. Use -T.")
        return 1

    contents = load_chip(chip)
    if chip.chip_id and not arguments.skip_id:
        say(f"Chip ID: 0x{chip.chip_id:04X}  OK")
    elif arguments.read_id:
        say("This chip doesn't have a chip ID!")
        return 1
    if arguments.read_id:
        return 0

    if arguments.erase:
        if chip.kind == UV_EPROM:
            say("This chip can't be erased!")
            return 1
        stage("Erasing... ", percentages=False)
        state_file(chip).write_bytes(bytes([ERASED]) * chip.size)
        return 0
    if arguments.blank_check:
        return verify(bytes([ERASED]) * chip.size, bytes(contents), blank_check=True)
    if arguments.read:
        stage("Reading Code...  ")
        Path(arguments.read).write_bytes(contents)
        return 0

    image = load_image(arguments, chip)
    if image is None:
        return 1
    if arguments.verify:
        return verify(image, bytes(contents), blank_check=False)

    if chip.kind == UV_EPROM:
        # Programming an EPROM can only turn ones into zeros.
        written = bytes(old & new for old, new in zip(contents, image, strict=True))
    else:
        if not arguments.skip_erase and chip.kind != EEPROM:
            stage("Erasing... ", percentages=False)
        written = image
    stage("Writing Code...  ")
    state_file(chip).write_bytes(written)
    if arguments.skip_verify:
        return 0
    return verify(image, written, blank_check=False)


def parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="minipro", add_help=False)
    for flags, name in (
        (("-l", "--list"), "list"),
        (("-k", "--presence_check"), "presence_check"),
        (("-V", "--version"), "version"),
        (("-D", "--read_id"), "read_id"),
        (("-b", "--blank_check"), "blank_check"),
        (("-B", "--skip_blank"), "skip_blank"),
        (("-z", "--pin_check"), "pin_check"),
        (("-e", "--skip_erase"), "skip_erase"),
        (("-E", "--erase"), "erase"),
        (("-u", "--unprotect"), "unprotect"),
        (("-P", "--protect"), "protect"),
        (("-v", "--skip_verify"), "skip_verify"),
        (("-T", "--logic_test"), "logic_test"),
        (("-i", "--icsp_vcc"), "icsp_vcc"),
        (("-I", "--icsp_no_vcc"), "icsp_no_vcc"),
        (("-s", "--no_size_error"), "no_size_error"),
        (("-S", "--no_size_warning"), "no_size_warning"),
        (("-x", "--skip_id"), "skip_id"),
        (("-y", "--no_id_error"), "no_id_error"),
        (("-t", "--hardware_check"), "hardware_check"),
    ):
        parser.add_argument(*flags, dest=name, action="store_true")
    for flags, name in (
        (("-L", "--search"), "search"),
        (("-q", "--programmer"), "programmer"),
        (("-d", "--get_info"), "get_info"),
        (("-p", "--device"), "device"),
        (("-r", "--read"), "read"),
        (("-w", "--write"), "write"),
        (("-m", "--verify"), "verify"),
        (("-c", "--page"), "page"),
        (("-f", "--format"), "format"),
        (("-a", "--auto_detect"), "auto_detect"),
    ):
        parser.add_argument(*flags, dest=name)
    parser.add_argument("-o", dest="settings", action="append", default=[])
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    arguments = parse(argv)
    absent = os.environ.get("T48_PROGRAMMER_SIMULATOR_ABSENT") == "1"

    if arguments.version:
        say(f"minipro version {VERSION}     A free and open TL866 series programmer")
        return 0
    if arguments.presence_check:
        say("[No programmer found]" if absent else "t48: T48")
        return 0
    if arguments.list or arguments.search is not None:
        wanted = (arguments.search or "").upper()
        for chip in CHIPS.values():
            if wanted in chip.name.upper():
                print(chip.name)
        return 0
    if arguments.get_info:
        chip = CHIPS.get(arguments.get_info.upper())
        if chip is None:
            say(f"\nDevice {arguments.get_info} not found!")
            return 1
        sys.stderr.write(chip_info(chip))
        return 0
    if absent:
        say("No programmer found.")
        return 1
    if arguments.hardware_check:
        say(BANNER)
        for name, count in (("VPP", 28), ("VCC", 32), ("GND", 34)):
            say(f"Testing {count} {name} pins")
            for pin in range(1, 4):
                say(f"{name} pin {pin} state is Good")
        say("Hardware test completed successfully!")
        return 0
    if arguments.auto_detect:
        say(BANNER)
        say("Autodetecting device (ID:0xEF4017)")
        print("W25Q64JV@SOIC8")
        say("1 device(s) found.")
        return 0
    if not arguments.device:
        say("Device required. Use -p <device> to specify a device.")
        return 1
    chip = CHIPS.get(arguments.device.upper())
    if chip is None:
        say(f"\nDevice {arguments.device} not found!")
        return 1
    return run_chip_action(arguments, chip)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        # minipro has no SIGINT handler and dies the same way.
        raise SystemExit(130) from None
