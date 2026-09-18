from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from t48_programmer import samples
from t48_programmer.rom_image import (
    KIB,
    ImageIdentity,
    RomKeyError,
    RomKeyMissing,
    decrypt_kickstart,
    find_key,
    fingerprint,
    fit_text,
    identify,
    kickstart_checksum_valid,
    open_rom,
    size_text,
    swap_byte_pairs,
)


class SizeTextTests(unittest.TestCase):
    def test_uses_the_units_rom_sizes_are_spoken_in(self) -> None:
        self.assertEqual(size_text(512 * KIB), "512 KB")
        self.assertEqual(size_text(2 * KIB * KIB), "2 MB")
        self.assertEqual(size_text(5892), "5,892 bytes")
        self.assertEqual(size_text(0), "0 bytes")


class SwapBytePairsTests(unittest.TestCase):
    def test_exchanges_each_pair(self) -> None:
        self.assertEqual(swap_byte_pairs(b"\x11\x14\x4e\xf9"), b"\x14\x11\xf9\x4e")

    def test_twice_is_the_original(self) -> None:
        image = samples.kickstart(256 * KIB)
        self.assertEqual(swap_byte_pairs(swap_byte_pairs(image)), image)

    def test_an_odd_length_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            swap_byte_pairs(b"\x00\x01\x02")


class KickstartTests(unittest.TestCase):
    def test_identifies_release_version_and_checksum(self) -> None:
        identity = identify(samples.kickstart(512 * KIB, 40, 68))

        self.assertEqual(identity.kind, "kickstart")
        self.assertEqual(identity.title, "Amiga Kickstart 3.1")
        self.assertIn(("Version", "40.68"), identity.details)
        self.assertIn(("Checksum", "Valid"), identity.details)
        self.assertEqual(identity.warnings, ())

    def test_identifies_a_256_kb_kickstart(self) -> None:
        identity = identify(samples.kickstart(256 * KIB, 34, 5))

        self.assertEqual(identity.title, "Amiga Kickstart 1.3")

    def test_an_unlisted_version_is_still_a_kickstart(self) -> None:
        self.assertEqual(
            identify(samples.kickstart(version=99)).title, "Amiga Kickstart"
        )

    def test_a_damaged_image_fails_its_checksum(self) -> None:
        image = bytearray(samples.kickstart())
        image[0x1000] ^= 0xFF

        identity = identify(bytes(image))

        self.assertFalse(kickstart_checksum_valid(bytes(image)))
        self.assertIn(("Checksum", "Invalid"), identity.details)
        self.assertIn("checksum", identity.warnings[0])

    def test_a_truncated_image_fails_its_checksum(self) -> None:
        self.assertFalse(kickstart_checksum_valid(samples.kickstart()[:-4]))
        self.assertFalse(kickstart_checksum_valid(b""))
        self.assertFalse(kickstart_checksum_valid(b"\x00\x01\x02"))

    def test_recognises_an_image_that_is_already_byte_swapped(self) -> None:
        identity = identify(swap_byte_pairs(samples.kickstart()))

        self.assertEqual(identity.kind, "kickstart-swapped")
        self.assertIn(("Checksum", "Valid"), identity.details)
        self.assertIn("already byte-swapped", identity.warnings[-1])

    def test_recognises_an_encrypted_amiga_forever_rom(self) -> None:
        identity = identify(b"AMIROMTYPE1" + bytes(1024))

        self.assertEqual(identity.kind, "kickstart-encrypted")
        self.assertIn("rom.key", identity.warnings[0])


KEY = bytes(range(1, 250)) * 9


class EncryptedKickstartTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="t48-keys-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.rom = self.folder / "amiga-os-310-a1200.rom"
        self.rom.write_bytes(samples.encrypted_kickstart(KEY))

    def test_the_right_key_gives_a_kickstart_with_a_valid_checksum(self) -> None:
        plain = decrypt_kickstart(self.rom.read_bytes(), KEY)

        self.assertEqual(plain, samples.kickstart())
        self.assertTrue(kickstart_checksum_valid(plain))

    def test_a_wrong_key_is_refused_and_not_passed_off_as_a_rom(self) -> None:
        for key in (KEY[::-1], KEY[:-1], b"\x00", b""):
            with self.subTest(len(key)), self.assertRaises(RomKeyError):
                decrypt_kickstart(self.rom.read_bytes(), key)

    def test_the_key_beside_the_rom_is_used_whatever_its_case(self) -> None:
        (self.folder / "ROM.KEY").write_bytes(KEY)

        opened = open_rom(self.rom)

        self.assertTrue(opened.decrypted)
        self.assertEqual(opened.identity.kind, "kickstart")
        self.assertEqual(opened.byte_count, 512 * KIB)
        self.assertIn(("Encryption", "Decrypted with ROM.KEY"), opened.identity.details)
        self.assertEqual(find_key(self.rom).name, "ROM.KEY")

    def test_no_key_is_reported_as_missing_so_that_one_can_be_asked_for(self) -> None:
        with self.assertRaisesRegex(RomKeyMissing, "no rom.key beside it"):
            open_rom(self.rom)

    def test_a_key_from_elsewhere_can_be_named(self) -> None:
        elsewhere = self.folder / "keys"
        elsewhere.mkdir()
        (elsewhere / "my.key").write_bytes(KEY)

        self.assertTrue(open_rom(self.rom, elsewhere / "my.key").decrypted)

    def test_a_plain_rom_is_opened_as_it_is(self) -> None:
        plain = self.folder / "tos206.img"
        plain.write_bytes(samples.tos())

        opened = open_rom(plain)

        self.assertFalse(opened.decrypted)
        self.assertEqual(opened.identity.title, "Atari TOS 2.06")
        self.assertEqual(opened.identity.label, "Atari TOS 2.06")

    def test_a_label_carries_the_name_a_rom_gives_itself(self) -> None:
        self.assertEqual(
            identify(samples.acorn_rom(title="View")).label, "Acorn sideways ROM, View"
        )


class TosTests(unittest.TestCase):
    def test_identifies_version_date_country_and_video(self) -> None:
        identity = identify(samples.tos(256 * KIB, (2, 6)))

        self.assertEqual(identity.title, "Atari TOS 2.06")
        self.assertEqual(
            dict(identity.details),
            {
                "Version": "2.06",
                "Built": "1991-11-14",
                "Country": "United Kingdom",
                "Video": "PAL",
                "ROM address": "0xE00000",
            },
        )

    def test_a_192_kb_tos_sits_at_the_st_rom_address(self) -> None:
        identity = identify(samples.tos(192 * KIB, (1, 4)))

        self.assertEqual(identity.title, "Atari TOS 1.04")
        self.assertIn(("ROM address", "0xFC0000"), identity.details)

    def test_a_branch_alone_is_not_enough(self) -> None:
        self.assertEqual(identify(b"\x60\x2e" + bytes(64)).kind, "binary")


class AcornTests(unittest.TestCase):
    def test_identifies_a_sideways_rom_by_its_copyright_pointer(self) -> None:
        identity = identify(samples.acorn_rom(16 * KIB, "View"))

        self.assertEqual(identity.kind, "acorn-rom")
        self.assertIn(("Title", "View"), identity.details)
        self.assertIn(("Entry points", "Service"), identity.details)

    def test_a_language_rom_declares_both_entries(self) -> None:
        image = bytearray(samples.acorn_rom(8 * KIB))
        image[6] = 0xC2

        self.assertIn(
            ("Entry points", "Service and Language"), identify(bytes(image)).details
        )

    def test_a_pointer_to_anything_else_is_not_a_rom(self) -> None:
        image = bytearray(samples.acorn_rom())
        image[7] += 1

        self.assertEqual(identify(bytes(image)).kind, "binary")

    def test_nothing_larger_than_a_socket_is_considered(self) -> None:
        self.assertEqual(identify(samples.acorn_rom(32 * KIB)).kind, "binary")


class OtherFormatTests(unittest.TestCase):
    def test_text_formats(self) -> None:
        self.assertEqual(identify(b":10000000C3000000\n").kind, "ihex")
        self.assertEqual(identify(b"S00600004844521B\n").kind, "srec")

    def test_anything_else_is_a_binary_image(self) -> None:
        self.assertEqual(identify(b""), ImageIdentity("binary", "Binary image"))
        self.assertEqual(identify(bytes(range(256))).kind, "binary")

    def test_fingerprint(self) -> None:
        self.assertEqual(
            fingerprint(b"123456789"),
            (
                ("Size", "9 bytes (9 bytes)"),
                ("CRC-32", "CBF43926"),
                ("SHA-1", "f7c3bc1d808e04732adf679965ccc34ca7ae3441"),
            ),
        )


class FitTextTests(unittest.TestCase):
    BINARY = ImageIdentity("binary", "Binary image")

    def test_an_exact_fit(self) -> None:
        self.assertEqual(
            fit_text(32 * KIB, 32 * KIB, self.BINARY), "Fits the chip exactly."
        )

    def test_a_mismatch_gives_both_sizes(self) -> None:
        self.assertEqual(
            fit_text(16 * KIB, 32 * KIB, self.BINARY),
            "The image is 16 KB and the chip holds 32 KB.",
        )

    def test_an_unknown_chip_size_says_nothing(self) -> None:
        self.assertEqual(fit_text(16 * KIB, 0, self.BINARY), "")

    def test_a_hex_file_is_not_judged_by_its_length(self) -> None:
        text = fit_text(45000, 16 * KIB, ImageIdentity("ihex", "Intel HEX file"))

        self.assertIn("minipro works out the size", text)


if __name__ == "__main__":
    unittest.main()
