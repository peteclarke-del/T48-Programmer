"""Turning one ROM image into the files that go into a machine's chips.

An operating system ROM is published as a single file in the order the
processor sees it. The chips on the board rarely hold it that way. A 16-bit bus
is served by a pair of 8-bit chips that each take alternate bytes, a large ROM
is cut into smaller ones, a programmer numbers the bytes of a 16-bit EPROM in
the opposite order to a 68000, and a small ROM in a larger chip has to be
repeated because the spare address pins are not under the machine's control.

Every arrangement supported here is one row of LAYOUTS, and prepare() is the
one routine that carries them all out. Adding a machine means adding a row.

Acorn machines page their ROMs in 16 KB banks, so a chip larger than 16 KB can
hold several. join_banks() lines the images up on bank boundaries first, and
the result goes through prepare() like any other image.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .rom_image import KIB, size_text, swap_byte_pairs

ERASED_BYTE = b"\xff"


class RomSetError(ValueError):
    """The image cannot be arranged in the way that was asked."""


@dataclass(frozen=True, slots=True)
class ChipOption:
    """A chip that suits the socket, by the name minipro knows it by."""

    device: str
    chip_bytes: int
    note: str = ""


@dataclass(frozen=True, slots=True)
class RomFamily:
    """One kind of ROM, which is the first thing the guide asks about.

    key is what rom_image.identify() calls an image of this kind, so an image
    that is already open can choose the family by itself.
    """

    key: str
    title: str
    short_title: str
    maker: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class RomLayout:
    """How one family of boards spreads a ROM image across its chips.

    lanes names the chips that share each bus word, in the order their data
    appears in the image, and lane_bytes is how much each one takes per turn:
    1 for 8-bit chips, 2 for 16-bit chips. A single lane means the image is not
    interleaved. segmented allows each lane to be cut across several chips.
    bank_bytes is set for machines that page their ROMs, and is the size of one
    page. family is the key of the RomFamily the board belongs to.
    """

    key: str
    family: str
    machines: tuple[str, ...]
    summary: str
    image_sizes: tuple[int, ...]
    chips: tuple[ChipOption, ...]
    lanes: tuple[str, ...] = ("ROM",)
    lane_bytes: int = 1
    byte_swap: bool = False
    segmented: bool = False
    bank_bytes: int = 0
    notes: tuple[str, ...] = ()

    @property
    def title(self) -> str:
        return ", ".join(self.machines)

    def bank_count(self, option: ChipOption) -> int:
        """How many separate images the chip can hold on this board."""
        if not self.bank_bytes:
            return 1
        return max(1, option.chip_bytes // self.bank_bytes)


@dataclass(frozen=True, slots=True)
class RomPart:
    """The finished contents of one chip."""

    label: str
    device: str
    data: bytes

    @property
    def file_stem(self) -> str:
        return self.label.lower().replace(" ", "-")


_EPROM_27C400 = tuple(
    ChipOption(device, 512 * KIB)
    for device in ("M27C400@DIP40", "AM27C400@DIP40", "MX27C4100@DIP40")
)
_EPROM_27C010 = tuple(
    ChipOption(device, 128 * KIB)
    for device in ("M27C1001@DIP32", "AT27C010@DIP32", "AM27C010@DIP32")
)
_AMIGA_ORDER_NOTE = (
    "A programmer numbers the two bytes of each 16-bit word in the opposite "
    "order to the 68000, so the image is byte-swapped here. Do not swap it "
    "again in another tool."
)
_MODEL_NOTE = (
    "Kickstart images are specific to a model. An A500 image will not start an "
    "A1200, whatever chip it is in."
)
_ACORN_REPEAT_NOTE = (
    "The BBC Micro holds pins 1 and 27 of the socket high. On a chip larger "
    "than 16 KB one or both of those pins are address lines, so the machine "
    "reads the top of the chip. The image is repeated to fill the chip, which "
    "puts a copy there."
)

_ACORN_BANK_NOTE = (
    "Different ROMs in one chip appear only where something drives the upper "
    "address pins: a switch, a ROM board, or a Master socket linked for 32 KB, "
    "which presents both banks as two ROM slots. A plain socket reads the top "
    "bank and nothing else."
)
_ADAPTER_NOTE = "32-pin. Needs an adapter in a 28-pin socket"

FAMILIES = (
    RomFamily(
        "kickstart",
        "Amiga Kickstart",
        "Kickstart",
        "Commodore Amiga",
        "The A1000 loads Kickstart from disk and has no ROM socket to fill. An "
        "encrypted Amiga Forever ROM is decrypted with the rom.key beside it.",
    ),
    RomFamily("tos", "Atari TOS", "TOS", "Atari ST, Mega ST, STE and Mega STE"),
    RomFamily(
        "acorn-rom",
        "Acorn MOS, BASIC or a sideways ROM",
        "Acorn ROM",
        "BBC Micro, Master and Electron",
        "The Atom is not covered. It takes 4 KB ROMs in 24-pin sockets, and its "
        "pinout has not been confirmed against a board.",
    ),
)
FAMILIES_BY_KEY = {family.key: family for family in FAMILIES}

LAYOUTS = (
    RomLayout(
        "amiga-single",
        "kickstart",
        ("A500", "A500 Plus", "A600", "A2000", "CDTV"),
        "One 40-pin ROM. A 27C400 drops into the socket.",
        (256 * KIB, 512 * KIB),
        _EPROM_27C400,
        lane_bytes=2,
        byte_swap=True,
        notes=(
            _AMIGA_ORDER_NOTE,
            "A 256 KB Kickstart, 1.3 and earlier, is written twice to fill the "
            "512 KB chip, so it appears wherever the board looks for it.",
            "A500 boards at revision 3 and 5 need a wire modification before "
            "they can address a 512 KB ROM.",
            _MODEL_NOTE,
        ),
    ),
    RomLayout(
        "amiga-pair",
        "kickstart",
        ("A1200", "A3000", "A4000"),
        "Two 16-bit ROMs, HI and LO, that together supply the 32-bit bus.",
        (512 * KIB,),
        _EPROM_27C400,
        lanes=("HI", "LO"),
        lane_bytes=2,
        byte_swap=True,
        notes=(
            "HI holds the first 16-bit word of every 32-bit long, data lines "
            "D31 to D16, and LO holds the second. Fit each chip to the socket "
            "that the original of the same name came from.",
            _AMIGA_ORDER_NOTE,
            "A 27C400 has 40 pins and the A1200 sockets have 42. The chip sits "
            "at the end of the socket away from the notch, leaving socket pins "
            "1 and 42 empty. Check this against the board before power on.",
            _MODEL_NOTE,
        ),
    ),
    RomLayout(
        "atari-st-six",
        "tos",
        ("ST, STF, STFM or Mega ST with six ROM chips",),
        "TOS 1.0x in six 32 KB chips. A 27C256 fits the socket.",
        (192 * KIB,),
        tuple(
            ChipOption(device, 32 * KIB)
            for device in ("M27C256B@DIP28", "AT27C256R@DIP28", "AM27C256@DIP28")
        ),
        lanes=("HI", "LO"),
        segmented=True,
        notes=(
            "HI chips hold the even bytes, data lines D15 to D8, and LO chips "
            "hold the odd bytes. Pair 0 is the lowest 64 KB of TOS, at "
            "0xFC0000, and pair 2 is the highest.",
        ),
    ),
    RomLayout(
        "atari-st-two",
        "tos",
        ("ST, STF, STFM or Mega ST with two ROM chips",),
        "TOS 1.0x in two 1 Mbit chips.",
        (192 * KIB,),
        _EPROM_27C010,
        lanes=("HI", "LO"),
        notes=(
            "The two sockets are 28-pin and were made for 1 Mbit mask ROMs. No "
            "28-pin EPROM has that pinout, so a 27C010 needs a pin adapter in "
            "each socket.",
            "Each chip carries 96 KB of TOS. The rest is left erased.",
        ),
    ),
    RomLayout(
        "atari-ste",
        "tos",
        ("STE or Mega STE",),
        "TOS 1.06, 1.62, 2.05 or 2.06 in two 32-pin chips.",
        (256 * KIB,),
        _EPROM_27C010,
        lanes=("HI", "LO"),
        notes=(
            "HI holds the even bytes, data lines D15 to D8, and LO holds the "
            "odd bytes. The 32-pin sockets take a 27C010 with no adapter.",
        ),
    ),
    RomLayout(
        "acorn-rom",
        "acorn-rom",
        (
            "BBC Micro Model B",
            "BBC Micro Model B+",
            "BBC Master",
            "Electron with a ROM cartridge or Plus 1",
        ),
        "8 KB and 16 KB images, paged in 16 KB banks.",
        (8 * KIB, 16 * KIB),
        (
            ChipOption("2764@DIP28", 8 * KIB, "EPROM"),
            ChipOption("M2764A@DIP28", 8 * KIB, "EPROM"),
            ChipOption("27128@DIP28", 16 * KIB, "EPROM, the original fit"),
            ChipOption("M27128A@DIP28", 16 * KIB, "EPROM"),
            ChipOption("M27C256B@DIP28", 32 * KIB, "EPROM"),
            ChipOption("AT27C256R@DIP28", 32 * KIB, "EPROM"),
            ChipOption("AT28C256", 32 * KIB, "EEPROM, erased electrically"),
            ChipOption("W27C512@DIP28", 64 * KIB, "EEPROM, erased electrically"),
            ChipOption("M27C512@DIP28", 64 * KIB, "EPROM"),
            ChipOption("M27C1001@DIP32", 128 * KIB, f"EPROM. {_ADAPTER_NOTE}"),
            ChipOption("SST39SF010A", 128 * KIB, f"Flash. {_ADAPTER_NOTE}"),
            ChipOption("AM27C020@DIP32", 256 * KIB, f"EPROM. {_ADAPTER_NOTE}"),
            ChipOption("SST39SF020A", 256 * KIB, f"Flash. {_ADAPTER_NOTE}"),
        ),
        bank_bytes=16 * KIB,
        notes=(
            _ACORN_REPEAT_NOTE,
            _ACORN_BANK_NOTE,
            "A 128 KB Master MOS image is eight banks and fills a 128 KB chip.",
        ),
    ),
)

LAYOUTS_BY_KEY = {layout.key: layout for layout in LAYOUTS}


def split_lanes(data: bytes, lane_count: int, lane_bytes: int) -> list[bytes]:
    """Deal an image out to its lanes, lane_bytes at a time to each in turn."""
    stride = lane_count * lane_bytes
    if len(data) % stride:
        raise RomSetError(
            f"The image is {len(data):,} bytes, which does not divide into "
            f"{lane_count} lanes of {lane_bytes * 8}-bit words."
        )
    lanes = []
    for lane in range(lane_count):
        out = bytearray(len(data) // lane_count)
        for byte in range(lane_bytes):
            out[byte::lane_bytes] = data[lane * lane_bytes + byte :: stride]
        lanes.append(bytes(out))
    return lanes


def fit_to_chip(data: bytes, chip_bytes: int, *, segmented: bool) -> list[bytes]:
    """The contents of each chip needed to hold one lane.

    A lane smaller than the chip is repeated when it fits a whole number of
    times, which makes it visible whatever the unused address pins are doing.
    When it does not fit evenly the remainder is left erased. A lane larger
    than the chip is cut across several chips, where the board allows it.
    """
    if len(data) > chip_bytes:
        if not segmented or len(data) % chip_bytes:
            raise RomSetError(
                f"{size_text(len(data))} will not fit a {size_text(chip_bytes)} chip."
            )
        return [data[at : at + chip_bytes] for at in range(0, len(data), chip_bytes)]
    if chip_bytes % len(data) == 0:
        return [data * (chip_bytes // len(data))]
    return [data + ERASED_BYTE * (chip_bytes - len(data))]


def join_banks(layout: RomLayout, option: ChipOption, images: Sequence[bytes]) -> bytes:
    """Line several images up on bank boundaries, the first at the bottom.

    An image smaller than a bank is repeated to fill it, for the same reason a
    small ROM is repeated in a large chip. An image of several banks, such as a
    128 KB Master MOS, takes that many. On a board that does not page its ROMs
    there is one image and it is returned as it is.
    """
    if not images:
        raise RomSetError("Choose the ROM image first.")
    if not layout.bank_bytes:
        if len(images) > 1:
            raise RomSetError("This board takes one ROM image.")
        return images[0]
    bank = min(layout.bank_bytes, option.chip_bytes)
    joined = bytearray()
    for number, image in enumerate(images, start=1):
        if not image or (len(image) % bank and bank % len(image)):
            raise RomSetError(
                f"Image {number} is {size_text(len(image))}, which does not fit "
                f"{size_text(bank)} banks."
            )
        joined += image * max(1, bank // len(image))
    if len(joined) > option.chip_bytes:
        raise RomSetError(
            f"{size_text(len(joined))} of images will not fit a "
            f"{size_text(option.chip_bytes)} chip."
        )
    return bytes(joined)


def prepare(layout: RomLayout, option: ChipOption, data: bytes) -> tuple[RomPart, ...]:
    """Arrange an image for a board, giving the contents of every chip."""
    whole_banks = layout.bank_bytes and len(data) % layout.bank_bytes == 0
    if len(data) not in layout.image_sizes and not whole_banks:
        expected = " or ".join(size_text(size) for size in layout.image_sizes)
        raise RomSetError(
            f"This board takes an image of {expected}. "
            f"The file is {size_text(len(data))}."
        )
    parts: list[RomPart] = []
    lanes = split_lanes(data, len(layout.lanes), layout.lane_bytes)
    for name, lane in zip(layout.lanes, lanes, strict=True):
        if layout.byte_swap:
            lane = swap_byte_pairs(lane)
        chips = fit_to_chip(lane, option.chip_bytes, segmented=layout.segmented)
        for index, contents in enumerate(chips):
            label = f"{name} {index}" if len(chips) > 1 else name
            parts.append(RomPart(label, option.device, contents))
    return tuple(parts)


def layouts_for(image_bytes: int, image_kind: str = "") -> tuple[RomLayout, ...]:
    """The layouts that accept an image of this size, the likeliest first.

    Size alone is ambiguous: 256 KB is both a Kickstart 1.3 and an STE TOS. The
    boards for the kind of image that was recognised lead the list, and the
    rest stay on it, because a MOS ROM or a patched image carries no header to
    be recognised by.
    """
    fitting = [layout for layout in LAYOUTS if image_bytes in layout.image_sizes]
    fitting.sort(key=lambda layout: layout.family != image_kind)
    return tuple(fitting)


def layouts_in(family: RomFamily) -> tuple[RomLayout, ...]:
    """The boards that take this kind of ROM."""
    return tuple(layout for layout in LAYOUTS if layout.family == family.key)
