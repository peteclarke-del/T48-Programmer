from __future__ import annotations

import unittest

from t48_programmer.help_content import HELP_TOPICS
from t48_programmer.minipro import ACTIONS
from t48_programmer.rom_sets import FAMILIES


def guide_text() -> str:
    return " ".join(
        " ".join((section.heading, *section.paragraphs, *section.steps))
        for topic in HELP_TOPICS
        for section in topic.sections
    )


class HelpContentTests(unittest.TestCase):
    def test_topics_are_distinct_and_complete(self) -> None:
        slugs = [topic.slug for topic in HELP_TOPICS]

        self.assertEqual(len(slugs), len(set(slugs)))
        for topic in HELP_TOPICS:
            with self.subTest(topic.slug):
                self.assertTrue(topic.title and topic.summary and topic.sections)
                for section in topic.sections:
                    self.assertTrue(section.paragraphs)

    def test_the_guide_names_commands_as_the_menus_do(self) -> None:
        text = guide_text()
        for key in ("read_id", "detect_spi_8", "logic_test", "blank_check"):
            with self.subTest(key):
                self.assertIn(ACTIONS[key].title, text)
        for phrase in (
            "Guided ROM Burn",
            "Reset Options",
            "Diagnostic Log",
            "Self Test",
        ):
            with self.subTest(phrase):
                self.assertIn(phrase, text)

    def test_every_supported_machine_is_explained(self) -> None:
        text = guide_text()
        for machine in ("Amiga", "Atari", "Acorn"):
            with self.subTest(machine):
                self.assertIn(machine, text)
        self.assertEqual(
            {family.maker.split()[0] for family in FAMILIES},
            {"Commodore", "Atari", "BBC"},
        )


if __name__ == "__main__":
    unittest.main()
