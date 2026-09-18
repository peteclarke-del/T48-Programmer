"""The project's prose rules, checked by machine.

Everything written here, from comments to the user guide, is meant to read as
one careful engineer wrote it. The rules that can be tested are tested, so that
a later change cannot quietly break them.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".py", ".md", ".toml", ".sh", ".xml", ".desktop", ".yml", ".rules"}
SKIPPED_FOLDERS = {".git", "build", "dist", "__pycache__", ".ruff_cache", ".kilo"}

# Built from code points so that this file passes its own test, however it is
# copied about.
FORBIDDEN_CHARACTERS = {
    chr(0x2014): "em dash",
    chr(0x2013): "en dash",
    chr(0x201C): "curly quotation mark",
    chr(0x201D): "curly quotation mark",
    chr(0x2018): "curly apostrophe",
    chr(0x2019): "curly apostrophe",
}
FORBIDDEN_WORDS = (
    "seamless",
    "leverage",
    "robust",
    "delve",
    "effortless",
    "cutting-edge",
    "powerful",
    "blazing",
)


def project_files() -> list[Path]:
    return [
        ROOT / "t48-programmer",
        *(
            path
            for path in ROOT.rglob("*")
            if path.suffix in TEXT_SUFFIXES and not SKIPPED_FOLDERS & set(path.parts)
        ),
    ]


class HouseStyleTests(unittest.TestCase):
    def test_there_are_files_to_check(self) -> None:
        self.assertGreater(len(project_files()), 20)

    def test_no_typographic_dashes_or_curly_quotes(self) -> None:
        found = [
            f"{path.relative_to(ROOT)}: {name}"
            for path in project_files()
            for character, name in FORBIDDEN_CHARACTERS.items()
            if character in path.read_text(encoding="utf-8")
        ]

        self.assertEqual(found, [])

    def test_no_sales_vocabulary(self) -> None:
        found = [
            f"{path.relative_to(ROOT)}: {word}"
            for path in project_files()
            if path.name != Path(__file__).name
            for word in FORBIDDEN_WORDS
            if word in path.read_text(encoding="utf-8").lower()
        ]

        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
