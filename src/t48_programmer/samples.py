"""Synthetic ROM images with valid headers and no copyrighted content.

Real Kickstart, TOS and Acorn ROMs belong to their owners and are not shipped
or fetched. These stand-ins carry just enough structure to be recognised, which
is all the tests and the documentation screenshots need.
"""

from __future__ import annotations

from functools import lru_cache

from .rom_image import KIB, kickstart_sum, xor_with_key

_KICKSTART_SIZE_WORDS = {256 * KIB: b"\x11\x11", 512 * KIB: b"\x11\x14"}


@lru_cache(maxsize=16)
def _pattern(length: int, seed: int) -> bytes:
    return bytes((seed + index * 7 + (index >> 8)) & 0xFF for index in range(length))


def filler(length: int, seed: int) -> bytearray:
    """Bytes that differ from their neighbours, so a bad split shows up."""
    return bytearray(_pattern(length, seed))


def kickstart(size: int = 512 * KIB, version: int = 40, revision: int = 68) -> bytes:
    """An image with a Kickstart header and a checksum the Amiga would accept."""
    image = filler(size, 0x4B)
    image[0:4] = _KICKSTART_SIZE_WORDS[size] + b"\x4e\xf9"
    image[12:14] = version.to_bytes(2, "big")
    image[14:16] = revision.to_bytes(2, "big")
    # The checksum long sits 24 bytes from the end. With that long at zero the
    # rest sums to some value, and the long that completes 0xFFFFFFFF is its
    # complement, because the carry wraps round.
    checksum_at = size - 24
    image[checksum_at : checksum_at + 4] = bytes(4)
    remainder = 0xFFFFFFFF - kickstart_sum(bytes(image))
    image[checksum_at : checksum_at + 4] = remainder.to_bytes(4, "big")
    return bytes(image)


def encrypted_kickstart(key: bytes, size: int = 512 * KIB) -> bytes:
    """A Kickstart encrypted the way Amiga Forever ships them."""
    return b"AMIROMTYPE1" + xor_with_key(kickstart(size), key)


def tos(size: int = 256 * KIB, version: tuple[int, int] = (2, 6)) -> bytes:
    """An image with a TOS header: UK, PAL, built on 14 November 1991."""
    image = filler(size, 0x54)
    base = 0xE00000 if size > 192 * KIB else 0xFC0000
    image[0:2] = b"\x60\x2e"
    image[2:4] = bytes(version)
    image[8:12] = base.to_bytes(4, "big")
    image[0x18:0x1C] = b"\x11\x14\x19\x91"
    image[0x1C:0x1E] = ((3 << 1) | 1).to_bytes(2, "big")
    return bytes(image)


def acorn_rom(size: int = 16 * KIB, title: str = "Sample ROM") -> bytes:
    """A sideways ROM with a service entry and a valid copyright pointer."""
    image = filler(size, 0x41)
    name = title.encode("ascii")
    image[0:3] = b"\x00\x00\x00"
    image[3:6] = b"\x4c\x00\x80"
    image[6] = 0x82
    image[7] = 9 + len(name)
    image[8] = 1
    image[9 : 9 + len(name)] = name
    image[9 + len(name) : 9 + len(name) + 4] = b"\x00(C)"
    return bytes(image)
