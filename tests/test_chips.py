from __future__ import annotations

import unittest
from unittest import mock

import support

from t48_programmer import chips, minipro
from t48_programmer.chips import parse_chip_info, search
from t48_programmer.minipro import QueryResult

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

    def test_the_release_names_its_defaults_and_is_given_the_values_it_accepts(
        self,
    ) -> None:
        # minipro 0.7.4 prints "VPP programming voltage: 13V" and no list. With
        # nothing offered, Voltages and Timing would never appear for the
        # minipro that the package bundles, and VPP could not be changed.
        info = parse_chip_info(support.RELEASE_EPROM_INFO, "t48")

        self.assertEqual(info.code_bytes, 32768)
        self.assertEqual(info.settings["vpp"].default, "13")
        self.assertEqual(info.settings["vpp"].choices, tuple(T48_VOLTAGES.split()))
        self.assertEqual(info.settings["vdd"].default, "6.5")
        self.assertEqual(
            info.settings["vcc"].choices, ("3.3", "4", "4.5", "5", "5.5", "6.5")
        )
        self.assertEqual(info.pulse_default, "100")

    def test_each_programmer_is_offered_only_what_it_can_supply(self) -> None:
        tl866 = parse_chip_info(support.RELEASE_EPROM_INFO, "tl866ii")
        older = parse_chip_info(support.RELEASE_EPROM_INFO, "tl866a")

        self.assertNotIn("21", tl866.settings["vpp"].choices)
        self.assertEqual(tl866.settings["vpp"].choices[-1], "18")
        self.assertEqual(older.settings["vpp"].choices[0], "10")

    def test_a_programmer_with_no_table_is_offered_nothing_it_might_refuse(
        self,
    ) -> None:
        self.assertEqual(
            parse_chip_info(support.RELEASE_EPROM_INFO, "t76").settings, {}
        )

    def test_a_list_printed_by_minipro_is_used_in_place_of_the_table(self) -> None:
        newer = support.RELEASE_EPROM_INFO + "Available VPP voltages [V]: 12, 13\n"

        self.assertEqual(
            parse_chip_info(newer, "t48").settings["vpp"].choices, ("12", "13")
        )

    def test_the_release_describes_other_kinds_of_chip(self) -> None:
        eeprom = parse_chip_info(support.RELEASE_EEPROM_INFO, "t48")
        mcu = parse_chip_info(support.RELEASE_MICROCONTROLLER_INFO, "t48")
        pld = parse_chip_info(support.RELEASE_PLD_INFO, "t48")
        logic = parse_chip_info(support.RELEASE_LOGIC_INFO, "t48")

        self.assertEqual((eeprom.code_bytes, eeprom.settings), (32768, {}))
        self.assertTrue(eeprom.is_plain_memory)
        # The release gives a microcontroller's code in bytes, not words.
        self.assertEqual(mcu.memory, "32768 Bytes + 1024 Bytes")
        self.assertFalse(mcu.is_plain_memory)
        self.assertEqual(pld.settings["vpp"].default, "16")
        self.assertEqual(set(pld.settings), {"vpp"})
        self.assertTrue(logic.is_logic)
        self.assertEqual(logic.settings["vcc"].default, "5")
        self.assertEqual(logic.settings["vcc"].choices, ("5", "3.3", "2.5", "1.8"))

    def test_an_unknown_device_is_none(self) -> None:
        self.assertIsNone(parse_chip_info(support.UNKNOWN_DEVICE))
        self.assertIsNone(parse_chip_info(""))


def found(text: str, limit: int = 100) -> list[str]:
    return search(CATALOGUE, text, limit)[0]


class SearchTests(unittest.TestCase):
    def test_is_case_insensitive(self) -> None:
        self.assertEqual(found("at28c"), ["AT28C256"])

    def test_every_word_must_match_in_any_order(self) -> None:
        self.assertEqual(
            found("dip28 27c256"),
            ["AM27C256@DIP28", "M27C256B@DIP28", "27C256@DIP28"],
        )

    def test_the_exact_part_comes_before_longer_names_that_contain_it(self) -> None:
        self.assertEqual(found("27C256")[0], "27C256@DIP28")

    def test_a_name_that_begins_with_the_text_comes_before_one_that_contains_it(
        self,
    ) -> None:
        self.assertEqual(found("M27C")[:1], ["M27C256B@DIP28"])
        self.assertEqual(found("27C")[0], "27C256@DIP28")

    def test_the_count_is_of_every_match_and_not_only_those_shown(self) -> None:
        shown, total = search(CATALOGUE, "DIP28", 2)

        self.assertEqual(len(shown), 2)
        self.assertEqual(total, 5)

    def test_no_text_lists_the_catalogue_up_to_the_limit(self) -> None:
        self.assertEqual(
            search(CATALOGUE, "  ", 2), (list(CATALOGUE[:2]), len(CATALOGUE))
        )

    def test_no_match_is_an_empty_list(self) -> None:
        self.assertEqual(search(CATALOGUE, "Z80", 10), ([], 0))


class CatalogueTests(unittest.TestCase):
    def setUp(self) -> None:
        chips.clear_cache()
        self.addCleanup(chips.clear_cache)

    def test_names_the_database_so_minipro_never_stops_to_ask(self) -> None:
        listing = QueryResult(0, "AT28C256\nAT28C256\n\nW27C512@DIP28\n", "")
        with mock.patch.object(minipro, "run_query", return_value=listing) as run:
            catalogue = chips.load_catalogue("tl866ii")

        self.assertEqual(catalogue, ("AT28C256", "W27C512@DIP28"))
        run.assert_called_once_with(["-q", "TL866II", "-l"])

    def test_an_error_on_stderr_is_never_mistaken_for_a_chip(self) -> None:
        broken = QueryResult(1, "", "infoic.xml: No such file or directory\n")
        with mock.patch.object(minipro, "run_query", return_value=broken):
            self.assertEqual(chips.load_catalogue("t48"), ())

        noisy = QueryResult(0, "AT28C256\n", "Warning: something\n")
        with mock.patch.object(minipro, "run_query", return_value=noisy):
            self.assertEqual(chips.load_catalogue("t48"), ("AT28C256",))

    def test_a_failure_is_not_remembered(self) -> None:
        # minipro may be installed or repaired while the application is open.
        for failure in (None, QueryResult(1, "", "No such file"), OSError("gone")):
            with self.subTest(failure=failure):
                effect = (
                    {"side_effect": failure}
                    if isinstance(failure, OSError)
                    else {"return_value": failure}
                )
                with mock.patch.object(minipro, "run_query", **effect):
                    self.assertEqual(chips.load_catalogue("t48"), ())
                    self.assertIsNone(chips.chip_info("AT28C256", "t48"))

        working = [
            QueryResult(0, "AT28C256\n", ""),
            QueryResult(0, "", support.EPROM_INFO),
        ]
        with mock.patch.object(minipro, "run_query", side_effect=working):
            self.assertEqual(chips.load_catalogue("t48"), ("AT28C256",))
            self.assertEqual(chips.chip_info("AT28C256", "t48").code_bytes, 32768)

    def test_an_answer_is_asked_for_once(self) -> None:
        answer = QueryResult(0, "", support.EPROM_INFO)
        with mock.patch.object(minipro, "run_query", return_value=answer) as run:
            first = chips.chip_info("M27C256B@DIP28", "t48")
            second = chips.chip_info("M27C256B@DIP28", "t48")

        self.assertIs(first, second)
        run.assert_called_once_with(["-q", "T48", "-d", "M27C256B@DIP28"])
        self.assertIn("Default VPP programming voltage: 13 V", first.text)

    def test_is_empty_without_minipro(self) -> None:
        with mock.patch.object(minipro, "run_query", return_value=None):
            self.assertEqual(chips.load_catalogue("t48"), ())

    def test_a_microcontroller_is_not_a_plain_memory(self) -> None:
        self.assertTrue(parse_chip_info(support.EPROM_INFO).is_plain_memory)
        self.assertTrue(parse_chip_info(support.WORD_WIDE_INFO).is_plain_memory)
        self.assertFalse(parse_chip_info(support.MICROCONTROLLER_INFO).is_plain_memory)
        self.assertFalse(parse_chip_info(support.LOGIC_INFO).is_plain_memory)

    def test_the_simulator_lists_and_describes_chips_like_minipro(self) -> None:
        with support.simulator():
            catalogue = chips.load_catalogue("t48")
            info = chips.chip_info("M27C400@DIP40", "t48")

        self.assertIn("AT28C256", catalogue)
        self.assertEqual(info.code_bytes, 512 * 1024)
        self.assertEqual(info.settings["vpp"].default, "12.5")


if __name__ == "__main__":
    unittest.main()
