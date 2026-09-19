from __future__ import annotations

import unittest

from t48_programmer import chips, minipro, samples, simulator
from t48_programmer.rom_image import KIB, identify, swap_byte_pairs
from t48_programmer.rom_sets import (
    FAMILIES,
    FAMILIES_BY_KEY,
    LAYOUTS,
    LAYOUTS_BY_KEY,
    RomSetError,
    bank_spans,
    fit_to_chip,
    join_banks,
    layouts_in,
    prepare,
    split_lanes,
)


def first_chip(key: str):
    layout = LAYOUTS_BY_KEY[key]
    return layout, layout.chips[0]


def reassemble(layout, parts) -> bytes:
    """Undo prepare(): what the processor would read from the finished chips.

    Every chip is trimmed to the length of data it was given, chips of the same
    lane are joined in order, the byte swap is undone, and the lanes are dealt
    back together. If this returns the original image, the chips are right.
    """
    lanes: dict[str, bytes] = {}
    for part in parts:
        lanes[part.label.split()[0]] = lanes.get(part.label.split()[0], b"") + part.data
    columns = []
    for name in layout.lanes:
        lane = lanes[name]
        if layout.byte_swap:
            lane = swap_byte_pairs(lane)
        columns.append(lane)
    width = layout.lane_bytes
    stride = width * len(columns)
    out = bytearray(len(columns[0]) * len(columns))
    for index, column in enumerate(columns):
        for byte in range(width):
            out[index * width + byte :: stride] = column[byte::width]
    return bytes(out)


class SplitLanesTests(unittest.TestCase):
    def test_eight_bit_pairs_take_alternate_bytes(self) -> None:
        self.assertEqual(split_lanes(bytes(range(8)), 2, 1), [b"\0\2\4\6", b"\1\3\5\7"])

    def test_sixteen_bit_pairs_take_alternate_words(self) -> None:
        self.assertEqual(split_lanes(bytes(range(8)), 2, 2), [b"\0\1\4\5", b"\2\3\6\7"])

    def test_four_lanes_serve_a_32_bit_bus_from_8_bit_chips(self) -> None:
        self.assertEqual(
            split_lanes(bytes(range(8)), 4, 1), [b"\0\4", b"\1\5", b"\2\6", b"\3\7"]
        )

    def test_one_lane_is_the_image(self) -> None:
        self.assertEqual(split_lanes(bytes(range(8)), 1, 2), [bytes(range(8))])

    def test_an_image_that_does_not_divide_is_refused(self) -> None:
        with self.assertRaisesRegex(RomSetError, "does not divide"):
            split_lanes(bytes(7), 2, 1)


class FitToChipTests(unittest.TestCase):
    def test_an_exact_fit_is_unchanged(self) -> None:
        self.assertEqual(fit_to_chip(b"abcd", 4, segmented=False), [b"abcd"])

    def test_a_smaller_lane_is_repeated_to_fill_the_chip(self) -> None:
        self.assertEqual(fit_to_chip(b"ab", 8, segmented=False), [b"abababab"])

    def test_a_lane_that_does_not_repeat_evenly_is_padded_as_erased(self) -> None:
        self.assertEqual(fit_to_chip(b"abc", 4, segmented=False), [b"abc\xff"])

    def test_a_larger_lane_is_cut_only_where_the_board_allows(self) -> None:
        self.assertEqual(
            fit_to_chip(b"abcdef", 2, segmented=True), [b"ab", b"cd", b"ef"]
        )
        with self.assertRaisesRegex(RomSetError, "will not fit"):
            fit_to_chip(b"abcdef", 2, segmented=False)
        with self.assertRaisesRegex(RomSetError, "will not fit"):
            fit_to_chip(b"abcde", 2, segmented=True)


class AmigaTests(unittest.TestCase):
    def test_a_single_rom_is_byte_swapped_for_the_programmer(self) -> None:
        layout, chip = first_chip("amiga-single")
        image = samples.kickstart(512 * KIB)

        (part,) = prepare(layout, chip, image)

        self.assertEqual(part.label, "ROM")
        self.assertEqual(part.device, "M27C400@DIP40")
        self.assertEqual(part.data, swap_byte_pairs(image))
        self.assertEqual(part.data[:4], b"\x14\x11\xf9\x4e")
        self.assertEqual(identify(part.data).kind, "kickstart-swapped")

    def test_a_256_kb_kickstart_is_written_twice(self) -> None:
        layout, chip = first_chip("amiga-single")
        image = samples.kickstart(256 * KIB, 34, 5)

        (part,) = prepare(layout, chip, image)

        self.assertEqual(len(part.data), 512 * KIB)
        self.assertEqual(part.data[: 256 * KIB], part.data[256 * KIB :])
        self.assertEqual(swap_byte_pairs(part.data[: 256 * KIB]), image)

    def test_a_pair_splits_the_32_bit_bus_into_hi_and_lo_words(self) -> None:
        layout, chip = first_chip("amiga-pair")
        image = samples.kickstart(512 * KIB)

        hi, lo = prepare(layout, chip, image)

        self.assertEqual((hi.label, lo.label), ("HI", "LO"))
        self.assertEqual(len(hi.data), 512 * KIB)
        # The first long of a 512 KB Kickstart is 11 14 4E F9. HI holds its
        # first word and LO its second, each swapped for the programmer.
        self.assertEqual(hi.data[:2], b"\x14\x11")
        self.assertEqual(lo.data[:2], b"\xf9\x4e")
        self.assertEqual(hi.data[: 256 * KIB], hi.data[256 * KIB :])


class AtariTests(unittest.TestCase):
    def test_six_chips_in_three_pairs_from_the_bottom_of_the_rom(self) -> None:
        layout, chip = first_chip("atari-st-six")
        image = samples.tos(192 * KIB, (1, 4))

        parts = prepare(layout, chip, image)

        self.assertEqual(
            [part.label for part in parts],
            ["HI 0", "HI 1", "HI 2", "LO 0", "LO 1", "LO 2"],
        )
        self.assertTrue(all(len(part.data) == 32 * KIB for part in parts))
        by_label = {part.label: part.data for part in parts}
        self.assertEqual(by_label["HI 0"][:2], bytes([image[0], image[2]]))
        self.assertEqual(by_label["LO 0"][:2], bytes([image[1], image[3]]))
        self.assertEqual(by_label["HI 1"][0], image[64 * KIB])

    def test_two_chips_leave_the_spare_quarter_erased(self) -> None:
        layout, chip = first_chip("atari-st-two")

        hi, lo = prepare(layout, chip, samples.tos(192 * KIB, (1, 2)))

        self.assertEqual(len(hi.data), 128 * KIB)
        self.assertEqual(hi.data[96 * KIB :], b"\xff" * (32 * KIB))
        self.assertEqual(lo.data[96 * KIB :], b"\xff" * (32 * KIB))

    def test_the_ste_pair_fills_two_27c010_exactly(self) -> None:
        layout, chip = first_chip("atari-ste")
        image = samples.tos(256 * KIB)

        hi, lo = prepare(layout, chip, image)

        self.assertEqual(hi.data, image[0::2])
        self.assertEqual(lo.data, image[1::2])


class AcornTests(unittest.TestCase):
    def test_a_16_kb_rom_is_repeated_up_the_chip(self) -> None:
        layout = LAYOUTS_BY_KEY["acorn-rom"]
        image = samples.acorn_rom(16 * KIB)

        for chip in (chip for chip in layout.chips if chip.chip_bytes >= 16 * KIB):
            with self.subTest(chip.device):
                (part,) = prepare(layout, chip, image)

                self.assertEqual(len(part.data), chip.chip_bytes)
                # The BBC Micro reads the top 16 KB of whatever is fitted.
                self.assertEqual(part.data[-16 * KIB :], image)

    def test_an_8_kb_rom_fits_a_2764_and_a_16_kb_rom_does_not(self) -> None:
        layout = LAYOUTS_BY_KEY["acorn-rom"]
        small = layout.chips[0]

        (part,) = prepare(layout, small, samples.acorn_rom(8 * KIB))

        self.assertEqual(len(part.data), 8 * KIB)
        with self.assertRaisesRegex(RomSetError, "will not fit"):
            prepare(layout, small, samples.acorn_rom(16 * KIB))


class BankTests(unittest.TestCase):
    """Acorn machines page ROMs in 16 KB banks, so one chip can hold several."""

    LAYOUT = LAYOUTS_BY_KEY["acorn-rom"]
    A = samples.acorn_rom(16 * KIB, "A")
    B = samples.acorn_rom(16 * KIB, "B")
    SMALL = samples.acorn_rom(8 * KIB, "Small")

    def chip(self, device: str):
        return next(chip for chip in self.LAYOUT.chips if chip.device == device)

    def burn(self, device: str, images: list[bytes]) -> bytes:
        chip = self.chip(device)
        (part,) = prepare(self.LAYOUT, chip, join_banks(self.LAYOUT, chip, images))
        return part.data

    def test_the_chip_sizes_run_from_8_kb_to_256_kb(self) -> None:
        sizes = sorted({chip.chip_bytes // KIB for chip in self.LAYOUT.chips})

        self.assertEqual(sizes, [8, 16, 32, 64, 128, 256])
        self.assertEqual(self.LAYOUT.bank_count(self.chip("2764@DIP28")), 1)
        self.assertEqual(self.LAYOUT.bank_count(self.chip("27128@DIP28")), 1)
        self.assertEqual(self.LAYOUT.bank_count(self.chip("W27C512@DIP28")), 4)
        self.assertEqual(self.LAYOUT.bank_count(self.chip("SST39SF020A")), 16)

    def test_one_image_is_repeated_into_every_bank(self) -> None:
        self.assertEqual(self.burn("W27C512@DIP28", [self.A]), self.A * 4)

    def test_images_go_in_order_from_the_bottom_of_the_chip(self) -> None:
        data = self.burn("AT28C256", [self.A, self.B])

        self.assertEqual(data[: 16 * KIB], self.A)
        self.assertEqual(data[16 * KIB :], self.B)

    def test_a_set_that_divides_the_chip_is_repeated_and_others_leave_it_erased(
        self,
    ) -> None:
        self.assertEqual(
            self.burn("W27C512@DIP28", [self.A, self.B]), (self.A + self.B) * 2
        )
        self.assertEqual(
            self.burn("W27C512@DIP28", [self.A, self.B, self.A]),
            self.A + self.B + self.A + b"\xff" * 16 * KIB,
        )

    def test_an_8_kb_image_fills_its_bank(self) -> None:
        data = self.burn("AT28C256", [self.SMALL, self.B])

        self.assertEqual(data, self.SMALL * 2 + self.B)

    def test_an_8_kb_image_in_an_8_kb_chip_is_not_doubled(self) -> None:
        self.assertEqual(self.burn("2764@DIP28", [self.SMALL]), self.SMALL)

    def test_a_master_mos_of_eight_banks_fills_a_128_kb_chip(self) -> None:
        mos = samples.filler(128 * KIB, 0x4D)

        self.assertEqual(self.burn("M27C1001@DIP32", [bytes(mos)]), bytes(mos))

    def test_an_image_is_labelled_with_the_banks_it_really_takes(self) -> None:
        chip = self.chip("SST39SF020A")
        sizes = [16 * KIB, 8 * KIB, 128 * KIB, 16 * KIB]

        self.assertEqual(
            bank_spans(self.LAYOUT, chip, sizes), [(0, 1), (1, 1), (2, 8), (10, 1)]
        )
        self.assertEqual(
            bank_spans(self.LAYOUT, self.chip("2764@DIP28"), [8 * KIB]), [(0, 1)]
        )

    def test_a_board_without_banks_counts_each_image_as_one(self) -> None:
        # A 192 KB TOS is one image, however many 32 KB chips it is cut across.
        # Counting it as six banks once threw the image away.
        layout, chip = first_chip("atari-st-six")

        self.assertEqual(bank_spans(layout, chip, [192 * KIB]), [(0, 1)])

    def test_eight_images_fill_a_128_kb_flash_chip_in_order(self) -> None:
        images = [samples.acorn_rom(16 * KIB, f"ROM {n}") for n in range(8)]

        data = self.burn("SST39SF010A", images)

        for number, image in enumerate(images):
            with self.subTest(bank=number):
                self.assertEqual(
                    data[number * 16 * KIB : (number + 1) * 16 * KIB], image
                )

    def test_what_cannot_be_banked_is_refused(self) -> None:
        chip = self.chip("W27C512@DIP28")
        for images, message in (
            ([self.A] * 5, "will not fit a 64 KB chip"),
            ([bytes(1000)], "does not fit 16 KB banks"),
            ([bytes(24 * KIB)], "does not fit 16 KB banks"),
            ([], "Choose the ROM image"),
        ):
            with self.subTest(message), self.assertRaisesRegex(RomSetError, message):
                join_banks(self.LAYOUT, chip, images)

    def test_a_board_that_does_not_page_takes_one_image(self) -> None:
        layout, chip = first_chip("atari-ste")
        image = samples.tos()

        self.assertEqual(join_banks(layout, chip, [image]), image)
        with self.assertRaisesRegex(RomSetError, "one ROM image"):
            join_banks(layout, chip, [image, image])


class EveryLayoutTests(unittest.TestCase):
    def test_the_processor_reads_back_the_original_image(self) -> None:
        for layout in LAYOUTS:
            for size in layout.image_sizes:
                image = samples.filler(size, 0x5A)
                for chip in layout.chips:
                    lane_bytes = size // len(layout.lanes)
                    if lane_bytes > chip.chip_bytes and not layout.segmented:
                        continue
                    with self.subTest(layout=layout.key, size=size, chip=chip.device):
                        parts = prepare(layout, chip, bytes(image))
                        trimmed = [
                            type(part)(part.label, part.device, part.data[:lane_bytes])
                            for part in parts
                        ]
                        self.assertEqual(reassemble(layout, trimmed), bytes(image))

    def test_every_part_fills_its_chip_exactly(self) -> None:
        for layout in LAYOUTS:
            for chip in layout.chips:
                size = min(layout.image_sizes)
                with self.subTest(layout=layout.key, chip=chip.device):
                    for part in prepare(layout, chip, bytes(size)):
                        self.assertEqual(len(part.data), chip.chip_bytes)
                        self.assertEqual(part.device, chip.device)

    def test_a_wrong_sized_image_is_refused_with_the_sizes_that_fit(self) -> None:
        layout, chip = first_chip("atari-ste")

        with self.assertRaisesRegex(RomSetError, "256 KB.*192 KB"):
            prepare(layout, chip, bytes(192 * KIB))

    def test_every_board_belongs_to_a_family_the_identifier_can_name(self) -> None:
        produced = {
            identify(image).kind
            for image in (samples.kickstart(), samples.tos(), samples.acorn_rom())
        }

        self.assertEqual({family.key for family in FAMILIES}, produced)
        for layout in LAYOUTS:
            with self.subTest(layout.key):
                self.assertIn(layout.family, FAMILIES_BY_KEY)
                self.assertIn(layout, layouts_in(FAMILIES_BY_KEY[layout.family]))

    def test_machines_are_grouped_by_the_roms_they_take(self) -> None:
        single = LAYOUTS_BY_KEY["amiga-single"].machines
        pair = LAYOUTS_BY_KEY["amiga-pair"].machines

        # The A600 has one ROM, like the A500. It is the A1200 that has two.
        self.assertIn("A600", single)
        self.assertEqual(pair, ("A1200", "A3000", "A4000"))
        every = [machine for layout in LAYOUTS for machine in layout.machines]
        self.assertEqual(len(every), len(set(every)))
        self.assertNotIn("A1000", every)

    def test_the_chips_this_project_was_built_around_are_offered(self) -> None:
        # The parts on the bench, by the names minipro gives them. The speed
        # and package suffixes printed on a chip are not part of that name:
        # an AT28C256-15PU is AT28C256, an SST39SF010A-70-4C-PHE is
        # SST39SF010A, and an AM27C400-120DC is AM27C400@DIP40.
        def devices(key: str) -> set[str]:
            return {chip.device for chip in LAYOUTS_BY_KEY[key].chips}

        self.assertLessEqual({"AT28C256", "SST39SF010A"}, devices("acorn-rom"))
        self.assertIn("AM27C400@DIP40", devices("amiga-single"))
        self.assertIn("AM27C400@DIP40", devices("amiga-pair"))
        acorn = LAYOUTS_BY_KEY["acorn-rom"]
        banks = {chip.device: acorn.bank_count(chip) for chip in acorn.chips}
        self.assertEqual((banks["AT28C256"], banks["SST39SF010A"]), (2, 8))

    @unittest.skipUnless(
        minipro.base_command() and not minipro.demo_mode(), "minipro is not installed"
    )
    def test_every_offered_chip_is_in_minipro_with_the_size_claimed(self) -> None:
        # Runs wherever a real minipro is found, or is named with
        # T48_PROGRAMMER_MINIPRO. A name minipro does not know, or a size that
        # differs, would send someone to the last page of the guide with a
        # chip that cannot be burned.
        catalogue = set(chips.load_catalogue("t48"))
        self.assertGreater(len(catalogue), 1000)
        for device, size in sorted(
            {
                (chip.device, chip.chip_bytes)
                for layout in LAYOUTS
                for chip in layout.chips
            }
        ):
            with self.subTest(device):
                self.assertIn(device, catalogue)
                self.assertEqual(chips.chip_info(device, "t48").code_bytes, size)

    def test_the_simulator_knows_every_chip_the_guide_offers(self) -> None:
        # Otherwise the demonstration breaks at the chip step for that board.
        for layout in LAYOUTS:
            for chip in layout.chips:
                with self.subTest(layout=layout.key, chip=chip.device):
                    simulated = simulator.CHIPS[chip.device.upper()]
                    self.assertEqual(simulated.size, chip.chip_bytes)

    def test_keys_are_unique_and_file_names_are_plain(self) -> None:
        self.assertEqual(len(LAYOUTS_BY_KEY), len(LAYOUTS))
        layout, chip = first_chip("atari-st-six")
        stems = [part.file_stem for part in prepare(layout, chip, bytes(192 * KIB))]

        self.assertEqual(stems, ["hi-0", "hi-1", "hi-2", "lo-0", "lo-1", "lo-2"])


if __name__ == "__main__":
    unittest.main()
