"""Recognising what a ROM image is before it is burned into a chip.

Identification is advice. It never blocks a write, because plenty of valid
images are none of the kinds known here. Its job is to catch the mistakes that
waste a chip: a Kickstart that is still encrypted, an image that has already
been byte-swapped once, a download that was cut short.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass, replace
from pathlib import Path

KIB = 1024
# Larger files are passed to minipro untouched but are not read into memory to
# be identified. No ROM this application knows about comes near this size.
MAX_INSPECTED_BYTES = 64 * KIB * KIB
# A Kickstart is 256 KB or 512 KB, and 1 MB with an extended ROM joined to it.
# Nothing larger is one, and the checksum is not worth running on a 64 MB file
# that happens to begin with the same four bytes.
MAX_KICKSTART_BYTES = 2 * KIB * KIB
# Amiga Forever keys are about 2 KB.
MAX_KEY_BYTES = 64 * KIB

_KICKSTART_RELEASES = {
    30: "1.0",
    31: "1.1",
    33: "1.2",
    34: "1.3",
    36: "2.0",
    37: "2.04",
    39: "3.0",
    40: "3.1",
    45: "3.X",
    46: "3.1.4",
    47: "3.2",
}
# The first word of a Kickstart gives its size class, 0x1111 for 256 KB and
# 0x1114 for 512 KB, and the second word is a JMP.
_KICKSTART_MAGICS = (b"\x11\x11\x4e\xf9", b"\x11\x14\x4e\xf9")
_CLOANTO_MAGIC = b"AMIROMTYPE1"

# TOS opens with a branch over its header. Both branch lengths are in use.
_TOS_BRANCHES = (b"\x60\x2e", b"\x60\x1e")
_TOS_BASES = {0xFC0000, 0xE00000}
_TOS_COUNTRIES = (
    "USA",
    "Germany",
    "France",
    "United Kingdom",
    "Spain",
    "Italy",
    "Sweden",
    "Switzerland (French)",
    "Switzerland (German)",
    "Turkey",
    "Finland",
    "Norway",
    "Denmark",
    "Saudi Arabia",
    "Netherlands",
    "Czech Republic",
    "Hungary",
)

_ACORN_MAX_BYTES = 16 * KIB
_ACORN_COPYRIGHT = b"\x00(C)"


@dataclass(frozen=True, slots=True)
class ImageIdentity:
    """What an image appears to be, in a form the window can show as rows."""

    kind: str
    title: str
    details: tuple[tuple[str, str], ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        """The title, with the ROM's own name where it carries one."""
        name = dict(self.details).get("Title")
        return f"{self.title}, {name}" if name else self.title


def size_text(byte_count: int) -> str:
    """A size the way ROM sizes are spoken of: 512 KB, not 524288 bytes."""
    if byte_count and byte_count % (KIB * KIB) == 0:
        return f"{byte_count // (KIB * KIB)} MB"
    if byte_count and byte_count % KIB == 0:
        return f"{byte_count // KIB} KB"
    return f"{byte_count:,} bytes"


def swap_byte_pairs(data: bytes) -> bytes:
    """Exchange the two bytes of every 16-bit word."""
    if len(data) % 2:
        raise ValueError("An image with an odd number of bytes has no 16-bit words.")
    swapped = bytearray(len(data))
    swapped[0::2] = data[1::2]
    swapped[1::2] = data[0::2]
    return bytes(swapped)


def kickstart_sum(data: bytes) -> int:
    """The sum of the big-endian 32-bit words, with end-around carry.

    Adding each carry back in as it happens gives the same result as adding
    all the words first and folding the overflow in afterwards, and the second
    way is one call into C where the first is a loop over 131,072 words.
    """
    total = sum(struct.unpack(f">{len(data) // 4}I", data))
    while total > 0xFFFFFFFF:
        total = (total & 0xFFFFFFFF) + (total >> 32)
    return total


def kickstart_checksum_valid(data: bytes) -> bool:
    """True when the image sums to 0xFFFFFFFF.

    This is the check the Amiga makes at reset. A ROM that fails it gives a
    red screen, so it is worth knowing before the chip is programmed.
    """
    if not data or len(data) % 4:
        return False
    return kickstart_sum(data) == 0xFFFFFFFF


KEY_FILE_NAME = "rom.key"


class RomKeyError(ValueError):
    """The key does not decrypt the ROM."""


def is_encrypted(data: bytes) -> bool:
    return data.startswith(_CLOANTO_MAGIC)


def xor_with_key(body: bytes, key: bytes) -> bytes:
    """XOR a body with a key repeated to its length. It is its own inverse."""
    size = len(body)
    repeated = (key * (size // len(key) + 1))[:size]
    mixed = int.from_bytes(body, "big") ^ int.from_bytes(repeated, "big")
    return mixed.to_bytes(size, "big")


def decrypt_kickstart(data: bytes, key: bytes) -> bytes:
    """Decrypt a Cloanto Amiga Forever ROM with the contents of its rom.key.

    The scheme is a repeating XOR over everything after the 11-byte magic. XOR
    with the wrong key gives bytes as plausible to a program as the right ones,
    so the result is only accepted if it is a Kickstart whose checksum adds up.
    That check is what makes a key valid.
    """
    if not key:
        raise RomKeyError("The key file is empty.")
    if len(data) > MAX_KICKSTART_BYTES + len(_CLOANTO_MAGIC):
        raise RomKeyError("The file is too large to be an encrypted Kickstart.")
    plain = xor_with_key(data[len(_CLOANTO_MAGIC) :], key)
    if plain[:4] not in _KICKSTART_MAGICS or not kickstart_checksum_valid(plain):
        raise RomKeyError(
            "This key does not decrypt this ROM. The key must be the rom.key "
            "from the same Amiga Forever installation as the ROM."
        )
    return plain


def _identify_kickstart(data: bytes) -> ImageIdentity | None:
    if is_encrypted(data):
        return ImageIdentity(
            "kickstart-encrypted",
            "Encrypted Amiga Kickstart",
            warnings=(
                "This is a Cloanto Amiga Forever ROM that is still encrypted. It "
                "needs its rom.key. Burned as it stands, it will not boot.",
            ),
        )
    if not 16 <= len(data) <= MAX_KICKSTART_BYTES:
        return None
    swapped = swap_byte_pairs(data[:4]) in _KICKSTART_MAGICS
    if swapped:
        data = swap_byte_pairs(data[: len(data) & ~1])
    if data[:4] not in _KICKSTART_MAGICS:
        return None
    version = int.from_bytes(data[12:14], "big")
    revision = int.from_bytes(data[14:16], "big")
    release = _KICKSTART_RELEASES.get(version)
    title = f"Amiga Kickstart {release}" if release else "Amiga Kickstart"
    details = [("Version", f"{version}.{revision}")]
    warnings = []
    if kickstart_checksum_valid(data):
        details.append(("Checksum", "Valid"))
    else:
        details.append(("Checksum", "Invalid"))
        warnings.append(
            "The Kickstart checksum does not add up. The file is damaged, "
            "patched without a corrected checksum, or incomplete."
        )
    if swapped:
        details.append(("Byte order", "Already swapped for an EPROM programmer"))
        warnings.append(
            "This image is already byte-swapped. Write it as it is. The guided "
            "ROM burn would swap it a second time."
        )
        return ImageIdentity(
            "kickstart-swapped",
            f"{title} (byte-swapped)",
            tuple(details),
            tuple(warnings),
        )
    return ImageIdentity("kickstart", title, tuple(details), tuple(warnings))


def _bcd(value: int) -> int:
    return (value >> 4) * 10 + (value & 0x0F)


def _identify_tos(data: bytes) -> ImageIdentity | None:
    if len(data) < 0x20 or data[:2] not in _TOS_BRANCHES:
        return None
    base = int.from_bytes(data[8:12], "big")
    if base not in _TOS_BASES:
        return None
    major, minor = data[2], data[3]
    month, day = _bcd(data[0x18]), _bcd(data[0x19])
    year = _bcd(data[0x1A]) * 100 + _bcd(data[0x1B])
    configuration = int.from_bytes(data[0x1C:0x1E], "big")
    country = configuration >> 1
    details = [
        ("Version", f"{major}.{minor:02d}"),
        ("Built", f"{year:04d}-{month:02d}-{day:02d}"),
        (
            "Country",
            _TOS_COUNTRIES[country] if country < len(_TOS_COUNTRIES) else "Other",
        ),
        ("Video", "PAL" if configuration & 1 else "NTSC"),
        ("ROM address", f"0x{base:06X}"),
    ]
    return ImageIdentity("tos", f"Atari TOS {major}.{minor:02d}", tuple(details))


def _identify_acorn(data: bytes) -> ImageIdentity | None:
    """A BBC Micro or Electron sideways ROM, found by its copyright pointer.

    Byte 7 holds the offset of a zero byte followed by "(C)". The MOS reads the
    same four bytes to decide whether a socket holds a ROM at all, so a file
    that fails this test would be ignored by the machine as well.
    """
    if not 16 <= len(data) <= _ACORN_MAX_BYTES:
        return None
    pointer = data[7]
    if data[pointer : pointer + 4] != _ACORN_COPYRIGHT:
        return None
    title = data[9:pointer].split(b"\x00")[0].decode("ascii", errors="replace")
    rom_type = data[6]
    roles = [
        name for bit, name in ((0x80, "Service"), (0x40, "Language")) if rom_type & bit
    ]
    details = (
        ("Title", title.strip() or "Untitled"),
        ("Version byte", f"{data[8]}"),
        ("Entry points", " and ".join(roles) or "None declared"),
    )
    return ImageIdentity("acorn-rom", "Acorn sideways ROM", details)


def _identify_text_format(data: bytes) -> ImageIdentity | None:
    head = data[:2]
    if head[:1] == b":" and data[1:9].isalnum():
        return ImageIdentity("ihex", "Intel HEX file")
    if head in (b"S0", b"S1", b"S2", b"S3"):
        return ImageIdentity("srec", "Motorola S-record file")
    return None


_IDENTIFIERS = (
    _identify_kickstart,
    _identify_tos,
    _identify_acorn,
    _identify_text_format,
)


def identify(data: bytes) -> ImageIdentity:
    """Describe an image, falling back to a plain binary of its size."""
    for identifier in _IDENTIFIERS:
        identity = identifier(data)
        if identity is not None:
            return identity
    return ImageIdentity("binary", "Binary image")


def crc32_text(data: bytes) -> str:
    """The CRC-32 the way ROM listings print it."""
    return f"{zlib.crc32(data):08X}"


def fingerprint(data: bytes) -> tuple[tuple[str, str], ...]:
    """The size and checksums people compare against ROM listings."""
    return (
        ("Size", f"{size_text(len(data))} ({len(data):,} bytes)"),
        ("CRC-32", crc32_text(data)),
        ("SHA-1", hashlib.sha1(data, usedforsecurity=False).hexdigest()),
    )


def is_text_format(identity: ImageIdentity) -> bool:
    """True for a file whose length says nothing about the data it carries."""
    return identity.kind in ("ihex", "srec")


def copies_to_fill(image_bytes: int, chip_bytes: int, identity: ImageIdentity) -> int:
    """How many times the image goes into the chip exactly, or 0 if it does not.

    A ROM smaller than its chip often has to be repeated to fill it, because
    the machine reads whichever part of the chip its spare address pins select.
    A BBC Micro reads the top half of a 32 KB chip, so a 16 KB ROM written once
    at the bottom is never seen. That only makes sense when the image divides
    into the chip a whole number of times, and only for a raw image, since the
    length of a HEX file says nothing about the data in it.
    """
    if is_text_format(identity) or not 0 < image_bytes < chip_bytes:
        return 0
    return chip_bytes // image_bytes if chip_bytes % image_bytes == 0 else 0


def fit_text(image_bytes: int, chip_bytes: int, identity: ImageIdentity) -> str:
    """One sentence on whether the image fills the chip, or "" when unknown."""
    if is_text_format(identity):
        return "minipro works out the size when it decodes the file."
    if not chip_bytes:
        return ""
    if image_bytes == chip_bytes:
        return "Fits the chip exactly."
    return (
        f"The image is {size_text(image_bytes)} and the chip holds "
        f"{size_text(chip_bytes)}."
    )


class RomKeyMissing(RomKeyError):
    """The ROM is encrypted and no key was found or given."""


@dataclass(frozen=True, slots=True)
class OpenedRom:
    """A file as it will be used: decrypted if need be, and identified."""

    path: Path
    byte_count: int
    data: bytes | None
    identity: ImageIdentity
    decrypted: bool = False


def find_key(rom_path: Path) -> Path | None:
    """The rom.key beside a ROM, whatever case its name is in."""
    try:
        siblings = list(rom_path.parent.iterdir())
    except OSError:
        return None
    return next(
        (
            path
            for path in siblings
            if path.name.lower() == KEY_FILE_NAME and path.is_file()
        ),
        None,
    )


def read_at_most(path: Path, limit: int) -> bytes | None:
    """The contents of a regular file of up to ``limit`` bytes, else None.

    The size is not taken from stat() and trusted. A FIFO or a device reports
    a size of nothing and then never stops giving bytes, and a file can grow
    between the stat and the read. Anything but a regular file is refused, and
    the read itself stops one byte past the limit.
    """
    if not path.is_file():
        raise OSError(f"{path.name} is not a regular file")
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    return data if len(data) <= limit else None


def open_rom(path: Path, key_path: Path | None = None) -> OpenedRom:
    """Read and identify a file, decrypting an Amiga Forever ROM on the way.

    The key is the one given, or else the rom.key beside the ROM. Raises
    RomKeyMissing when there is neither, RomKeyError when the key is wrong, and
    OSError when a file cannot be read.
    """
    data = read_at_most(path, MAX_INSPECTED_BYTES)
    if data is None:
        return OpenedRom(
            path, path.stat().st_size, None, ImageIdentity("binary", "Image")
        )
    if not is_encrypted(data):
        return OpenedRom(path, len(data), data, identify(data))
    key_path = key_path or find_key(path)
    if key_path is None:
        raise RomKeyMissing(
            f"{path.name} is an encrypted Amiga Forever ROM, and there is no "
            f"{KEY_FILE_NAME} beside it."
        )
    key = read_at_most(key_path, MAX_KEY_BYTES)
    if key is None:
        raise RomKeyError(f"{key_path.name} is too large to be a key.")
    data = decrypt_kickstart(data, key)
    identity = identify(data)
    identity = replace(
        identity,
        details=(*identity.details, ("Encryption", f"Decrypted with {key_path.name}")),
    )
    return OpenedRom(path, len(data), data, identity, decrypted=True)


def describe(opened: OpenedRom) -> str:
    """One line on what a file is: its identity, its size, and its CRC-32."""
    facts = [opened.identity.label, size_text(opened.byte_count)]
    if opened.data is not None:
        facts.append(f"CRC-32 {crc32_text(opened.data)}")
    return ", ".join(facts)
