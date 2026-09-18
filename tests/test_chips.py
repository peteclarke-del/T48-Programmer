from __future__ import annotations

import unittest
from unittest import mock

import support

from t48_programmer import chips, minipro
from t48_programmer.chips import parse_chip_info, search

T48_VOLTAGES = "9 9.5 10 11 11.5 12 12.5 13 13.5 14 14.5 15.5 16 16.5 17 18 21 25"
CATALOGUE = (
    "AM27C256@DIP28",
    "AM27C256@PLCC32",
    "M27C256B@DIP28",
    "27C256@DIP28",
    "AT28C256",
    "W27C512@DIP28",
    "ATMEGA328P@DIP28",
)


class ParseChipInfoTests(unittest.TestCase):
    def test_eprom_with_wrapped_voltage_lists(self) -> None:
        info = parse_chip_info(support.EPROM_INFO)

        self.assertEqual(info.name, "M27C256B@DIP28")
        self.assertEqual(info.code_bytes, 32768)
        self.assertEqual(info.package, "DIP28")
        self.assertEqual(info.settings["vpp"].default, "13")
        self.assertEqual(info.settings["vpp"].choices, tuple(T48_VOLTAGES.split()))
        self.assertEqual(info.settings["vdd"].default, "6.5")
        self.assertEqual(info.settings["vdd"].choices[0], "1.2")
        self.assertEqual(info.settings["vdd"].choices[-1], "6.5")
        self.assertEqual(info.settings["vcc"].default, "5")
        self.assertEqual(len(info.settings["vcc"].choices), 15)
        self.assertEqual(info.pulse_default, "100")
        self.assertFalse(info.is_logic)

    def test_a_word_wide_chip_is_sized_in_bytes(self) -> None:
        info = parse_chip_info(support.WORD_WIDE_INFO)

        self.assertEqual(info.memory, "262144 Words")
        self.assertEqual(info.code_bytes, 512 * 1024)
        self.assertEqual(info.settings, {})

    def test_a_microcontroller_is_sized_by_its_code_memory(self) -> None:
        info = parse_chip_info(support.MICROCONTROLLER_INFO)

        self.assertEqual(info.code_bytes, 32768)
        self.assertEqual(info.details["ICSP"], "ICP007.JPG")

    def test_spi_flash_offers_clocks_and_no_voltages(self) -> None:
        info = parse_chip_info(support.SPI_FLASH_INFO)

        self.assertEqual(set(info.settings), {"spi_clock"})
        self.assertEqual(info.settings["spi_clock"].choices, ("4", "8", "15", "30"))
        self.assertEqual(info.settings["spi_clock"].default, "")

    def test_a_logic_device_has_a_supply_list_and_no_memory(self) -> None:
        info = parse_chip_info(support.LOGIC_INFO)

        self.assertTrue(info.is_logic)
        self.assertEqual(info.code_bytes, 0)
        self.assertEqual(info.package, "DIP14")
        self.assertEqual(info.settings["vcc"].choices, ("1.8", "2.5", "3.3", "5"))

    def test_an_unknown_device_is_none(self) -> None:
        self.assertIsNone(parse_chip_info(support.UNKNOWN_DEVICE))
        self.assertIsNone(parse_chip_info(""))


class SearchTests(unittest.TestCase):
    def test_is_case_insensitive(self) -> None:
        self.assertEqual(search(CATALOGUE, "at28c"), ["AT28C256"])

    def test_every_word_must_match_in_any_order(self) -> None:
        self.assertEqual(
            search(CATALOGUE, "dip28 27c256"),
            ["AM27C256@DIP28", "M27C256B@DIP28", "27C256@DIP28"],
        )

    def test_the_exact_part_comes_before_longer_names_that_contain_it(self) -> None:
        self.assertEqual(search(CATALOGUE, "27C256")[0], "27C256@DIP28")

    def test_no_text_lists_the_catalogue_up_to_the_limit(self) -> None:
        self.assertEqual(search(CATALOGUE, "  ", limit=2), list(CATALOGUE[:2]))

    def test_no_match_is_an_empty_list(self) -> None:
        self.assertEqual(search(CATALOGUE, "Z80"), [])


class CatalogueTests(unittest.TestCase):
    def setUp(self) -> None:
        chips.load_catalogue.cache_clear()
        chips.chip_info.cache_clear()
        self.addCleanup(chips.load_catalogue.cache_clear)
        self.addCleanup(chips.chip_info.cache_clear)

    def test_names_the_database_so_minipro_never_stops_to_ask(self) -> None:
        listing = "AT28C256\nAT28C256\n\nW27C512@DIP28\n"
        with mock.patch.object(minipro, "run_query", return_value=listing) as run:
            catalogue = chips.load_catalogue("tl866ii")

        self.assertEqual(catalogue, ("AT28C256", "W27C512@DIP28"))
        run.assert_called_once_with(["-q", "TL866II", "-l"])

    def test_is_empty_without_minipro(self) -> None:
        with mock.patch.object(minipro, "run_query", return_value=None):
            self.assertEqual(chips.load_catalogue("t48"), ())

    def test_asks_minipro_about_one_chip(self) -> None:
        with mock.patch.object(
            minipro, "run_query", return_value=support.EPROM_INFO
        ) as run:
            info = chips.chip_info("M27C256B@DIP28", "t48")

        self.assertEqual(info.code_bytes, 32768)
        run.assert_called_once_with(["-q", "T48", "-d", "M27C256B@DIP28"])

    def test_the_simulator_lists_and_describes_chips_like_minipro(self) -> None:
        with support.simulator():
            catalogue = chips.load_catalogue("t48")
            info = chips.chip_info("M27C400@DIP40", "t48")

        self.assertIn("AT28C256", catalogue)
        self.assertEqual(info.code_bytes, 512 * 1024)
        self.assertEqual(info.settings["vpp"].default, "12.5")


if __name__ == "__main__":
    unittest.main()
