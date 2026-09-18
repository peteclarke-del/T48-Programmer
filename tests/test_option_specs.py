from __future__ import annotations

import unittest
from dataclasses import fields

from t48_programmer import option_specs
from t48_programmer.minipro import (
    ICSP_MODES,
    MEMORY_SECTIONS,
    READ_FORMATS,
    SIZE_POLICIES,
    Options,
)


class OptionSpecTests(unittest.TestCase):
    def test_every_option_has_exactly_one_control(self) -> None:
        covered = option_specs.covered_fields()

        self.assertEqual(
            sorted(covered), sorted(field.name for field in fields(Options))
        )
        self.assertEqual(len(covered), len(set(covered)))

    def test_every_list_starts_with_minipro_s_default(self) -> None:
        for section in option_specs.SECTIONS:
            for choice in section.choices:
                with self.subTest(choice.field):
                    self.assertEqual(choice.choices[0][0], "")

    def test_lists_offer_exactly_the_values_minipro_accepts(self) -> None:
        expected = {
            "memory": MEMORY_SECTIONS,
            "file_format": READ_FORMATS,
            "size_policy": SIZE_POLICIES,
            "icsp": ICSP_MODES,
        }
        for section in option_specs.SECTIONS:
            for choice in section.choices:
                with self.subTest(choice.field):
                    values = tuple(value for value, _label in choice.choices[1:])
                    self.assertEqual(values, expected[choice.field])


if __name__ == "__main__":
    unittest.main()
