"""The files around the code: metadata, scripts, and the pinned minipro."""

from __future__ import annotations

import re
import shutil
import subprocess
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from t48_programmer import __version__, branding
from t48_programmer.simulator import VERSION as SIMULATED_MINIPRO_VERSION

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PACKAGING = ROOT / "packaging"


class VersionTests(unittest.TestCase):
    def test_the_package_is_the_only_statement_of_the_version(self) -> None:
        # Read as text: tomllib arrived in Python 3.11 and 3.10 is supported.
        project = (ROOT / "pyproject.toml").read_text()

        self.assertIn('dynamic = ["version"]', project)
        self.assertIn('version = { attr = "t48_programmer.__version__" }', project)
        self.assertNotRegex(project, r'(?m)^version\s*=\s*"')

    def test_the_newest_release_in_the_metadata_is_this_version(self) -> None:
        tree = ElementTree.parse(DATA / f"{branding.APPLICATION_ID}.metainfo.xml")
        releases = [release.get("version") for release in tree.iter("release")]

        self.assertEqual(releases[0], __version__)

    def test_the_simulator_speaks_for_the_minipro_the_package_bundles(self) -> None:
        pinned = (PACKAGING / "minipro-version.txt").read_text().strip()

        self.assertEqual(SIMULATED_MINIPRO_VERSION, pinned)

    def test_the_minipro_source_is_pinned_by_a_sha256(self) -> None:
        checksum = (PACKAGING / "minipro-source.sha256").read_text().strip()

        self.assertRegex(checksum, r"^[0-9a-f]{64}$")


class MetadataTests(unittest.TestCase):
    def test_the_desktop_entry_and_metadata_carry_the_application_id(self) -> None:
        desktop = DATA / f"{branding.APPLICATION_ID}.desktop"
        tree = ElementTree.parse(DATA / f"{branding.APPLICATION_ID}.metainfo.xml")

        self.assertIn(f"Name={branding.APPLICATION_NAME}\n", desktop.read_text())
        self.assertIn(f"Icon={branding.APPLICATION_ICON}\n", desktop.read_text())
        self.assertEqual(tree.findtext("id"), branding.APPLICATION_ID)
        self.assertEqual(tree.findtext("launchable"), desktop.name)

    @unittest.skipUnless(
        shutil.which("desktop-file-validate"), "validator not installed"
    )
    def test_the_desktop_entry_is_valid(self) -> None:
        desktop = DATA / f"{branding.APPLICATION_ID}.desktop"

        completed = subprocess.run(
            ["desktop-file-validate", str(desktop)], capture_output=True, text=True
        )

        self.assertEqual(completed.stdout + completed.stderr, "")


class IconTests(unittest.TestCase):
    ICON = (
        ROOT
        / "src/t48_programmer/data/icons/hicolor/scalable/apps"
        / f"{branding.APPLICATION_ICON}.svg"
    )

    def test_the_icon_is_named_after_the_application_and_is_valid_svg(self) -> None:
        root = ElementTree.parse(self.ICON).getroot()

        self.assertEqual(branding.APPLICATION_ICON, branding.APPLICATION_ID)
        self.assertTrue(root.tag.endswith("svg"))
        self.assertEqual(root.get("viewBox"), "0 0 128 128")

    def test_the_icon_travels_in_the_wheel_and_in_the_package(self) -> None:
        self.assertIn(
            "data/icons/hicolor/*/apps/*.svg", (ROOT / "pyproject.toml").read_text()
        )
        self.assertIn(
            "usr/share/icons/hicolor/scalable/apps",
            (PACKAGING / "build-deb.sh").read_text(),
        )


class ScriptTests(unittest.TestCase):
    def test_shell_scripts_parse(self) -> None:
        scripts = {
            "bash": [ROOT / "t48-programmer", PACKAGING / "build-deb.sh"],
            "sh": [
                PACKAGING / "t48-programmer",
                PACKAGING / "postinst",
                PACKAGING / "postrm",
            ],
        }
        for shell, paths in scripts.items():
            for path in paths:
                with self.subTest(path=path.name, shell=shell):
                    completed = subprocess.run(
                        [shell, "-n", str(path)], capture_output=True, text=True
                    )
                    self.assertEqual(completed.stderr, "")

    def test_the_udev_rules_grant_access_and_do_not_only_mark_the_device(self) -> None:
        # minipro 0.7.4 marks the device in one file and grants access in
        # another. Shipping the first alone gives a programmer nobody can open.
        rules = (PACKAGING / "60-t48-programmer.rules").read_text()
        granting = [
            line for line in rules.splitlines() if line.startswith("ATTRS{idVendor}")
        ]

        self.assertEqual(len(granting), 3)
        for line in granting:
            with self.subTest(line):
                self.assertIn('TAG+="uaccess"', line)
                self.assertIn('GROUP="plugdev"', line)
        # The TL866II+, T48 and T56 share this USB identity.
        self.assertTrue(any('"a466"' in line and '"0a53"' in line for line in granting))

    def test_the_package_never_owns_a_file_a_distribution_minipro_owns(self) -> None:
        script = (PACKAGING / "build-deb.sh").read_text()

        installed = re.findall(r"rules\.d/([\w.-]+\.rules)\"", script)

        self.assertEqual(installed, ["60-t48-programmer.rules"])


if __name__ == "__main__":
    unittest.main()
