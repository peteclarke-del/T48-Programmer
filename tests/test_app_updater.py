"""Check for Application Updates in the About window, driven in the real window.

Each test opens the About window of a real MainWindow whose update work is
replaced by FakeService, presses its buttons the way a person would, and
checks what the window shows. The tests need PyGObject and a display. They are
skipped without them, unless T48_PROGRAMMER_REQUIRE_GTK is set, as the CI
interface job sets it, so that a broken GTK install fails the run instead of
skipping these tests without anyone noticing. Every wait is bounded.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

REQUIRE_GTK = bool(os.environ.get("T48_PROGRAMMER_REQUIRE_GTK"))

try:
    from gtk_support import shared_application  # isort: skip
    import gi
except ImportError as error:
    if REQUIRE_GTK:
        raise
    raise unittest.SkipTest(f"PyGObject is not installed: {error}") from error

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from t48_programmer import __version__  # noqa: E402
from t48_programmer.app_update import AppRelease, PackageTarget  # noqa: E402
from t48_programmer.app_updater import (  # noqa: E402
    BUSY_WHILE_RUNNING,
    CHECK_LABEL,
    RESTART_WHILE_RUNNING,
    AppUpdateControls,
    AppUpdater,
    UpdateService,
)
from t48_programmer.operation import OperationController  # noqa: E402
from t48_programmer.releases import UpdateCancelled, UpdateError  # noqa: E402
from t48_programmer.window import MainWindow  # noqa: E402

HAVE_DISPLAY = bool(Gtk.init_check()) and Gdk.Display.get_default() is not None
if REQUIRE_GTK and not HAVE_DISPLAY:
    raise RuntimeError("The interface tests need a display.")
TIMEOUT = 10.0
UBUNTU = PackageTarget(
    "ubuntu24.04", "amd64", "T48-Programmer_{version}_ubuntu24.04_amd64.deb"
)
NEWER = AppRelease(
    "9.0.0",
    "v9.0.0",
    "T48 Programmer 9.0.0",
    "https://github.com/peteclarke-del/T48-Programmer/releases/tag/v9.0.0",
    notes="Reads more formats.",
    package_name="T48-Programmer_9.0.0_ubuntu24.04_amd64.deb",
    package_url="https://example.org/T48-Programmer_9.0.0_ubuntu24.04_amd64.deb",
    package_size=24_000_000,
    sums_url="https://example.org/SHA256SUMS",
)


def wait_until(predicate, message: str, timeout: float = TIMEOUT) -> None:
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting: {message}")


def pump() -> None:
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)


def widgets_in(widget: Gtk.Widget) -> list[Gtk.Widget]:
    """Every widget below ``widget``, depth first."""
    found = []
    child = widget.get_first_child()
    while child is not None:
        found.append(child)
        found.extend(widgets_in(child))
        child = child.get_next_sibling()
    return found


def open_dialogs() -> list[Adw.MessageDialog]:
    return [
        window
        for window in Gtk.Window.list_toplevels()
        if isinstance(window, Adw.MessageDialog) and window.get_visible()
    ]


class FakeService(UpdateService):
    """The update's work, without GitHub, downloads or apt."""

    def __init__(self) -> None:
        self.installed_target: PackageTarget | None = UBUNTU
        self.release: AppRelease | None = None
        self.check_error = ""
        self.install_dismissed = False
        self.install_error = ""
        self.checks = 0
        self.downloads = 0
        self.installed: list[Path] = []
        self.step_delay = 0.0

    def target(self) -> PackageTarget | None:
        return self.installed_target

    def check(self) -> AppRelease | None:
        self.checks += 1
        if self.check_error:
            raise UpdateError(self.check_error)
        return self.release

    def download(self, release, progress, cancel) -> Path:
        self.downloads += 1
        for step in range(11):
            if cancel.is_set():
                raise UpdateCancelled("The update was cancelled.")
            progress(step * 1000, 10_000)
            time.sleep(self.step_delay)
        return Path("/nonexistent") / release.package_name

    def install(self, package: Path) -> None:
        if self.install_dismissed:
            raise UpdateCancelled(
                "The password prompt was dismissed, so nothing was installed."
            )
        if self.install_error:
            raise UpdateError(self.install_error)
        self.installed.append(package)


@unittest.skipUnless(HAVE_DISPLAY, "needs a display")
class AboutUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = shared_application()
        self.window = MainWindow(application=self.app)
        self.service = FakeService()
        self.window.app_updater = AppUpdater(self.window, self.service)
        self.window.present()
        self.addCleanup(self._close)

    def _close(self) -> None:
        for dialog in open_dialogs():
            dialog.destroy()
        if self.window.about_window is not None:
            self.window.about_window.destroy()
        self.window.destroy()
        self.app.restart_requested = False
        pump()

    def about_controls(self) -> AppUpdateControls:
        self.window.activate_action("win.about", None)
        wait_until(lambda: self.window.about_window is not None, "the About window")
        about = self.window.about_window
        found = [w for w in widgets_in(about) if isinstance(w, AppUpdateControls)]
        self.assertEqual(len(found), 1)
        return found[0]

    def wait_update(self, phase: str) -> None:
        updater = self.window.app_updater
        wait_until(lambda: updater.state.phase == phase, f"the update to be {phase}")

    def answer(self, heading: str, label: str) -> Adw.MessageDialog:
        """Press the button labelled ``label`` in the question ``heading``."""
        wait_until(lambda: open_dialogs(), f"the question {heading}")
        (dialog,) = open_dialogs()
        self.assertEqual(dialog.get_heading(), heading)
        (button,) = [
            widget
            for widget in widgets_in(dialog)
            if isinstance(widget, Gtk.Button) and widget.get_label() == label
        ]
        button.emit("clicked")
        pump()
        self.assertEqual(open_dialogs(), [])
        return dialog

    def test_the_about_window_has_the_update_button_under_the_version(self) -> None:
        controls = self.about_controls()
        version = controls.get_prev_sibling()
        self.assertTrue(version.has_css_class("app-version"))
        self.assertEqual(version.get_label(), __version__)
        self.assertEqual(controls.button.get_label(), CHECK_LABEL)
        self.assertEqual(CHECK_LABEL, "_Check for Application Updates")
        self.assertFalse(controls.status.get_visible())
        self.assertEqual(self.service.checks, 0)  # nothing is asked until the user asks

    def test_an_update_check_says_this_is_the_newest_version(self) -> None:
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("current")
        self.assertEqual(
            controls.status.get_text(),
            f"T48 Programmer {__version__} is the newest version",
        )
        self.assertEqual(controls.button.get_label(), CHECK_LABEL)
        self.assertEqual(self.service.checks, 1)

    def test_a_failed_update_check_gives_the_reason_and_never_says_newest(
        self,
    ) -> None:
        self.service.check_error = "api.github.com could not be reached: timed out."
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("failed")
        message = (
            "Could not check for a newer version: "
            "api.github.com could not be reached: timed out."
        )
        self.assertEqual(controls.status.get_text(), message)
        self.assertNotIn("newest", controls.status.get_text())
        self.assertEqual(controls.button.get_label(), CHECK_LABEL)
        self.assertIn(message, self.window._diagnostic_log[-1])

    def test_a_newer_version_is_downloaded_installed_and_restarted(self) -> None:
        self.service.release = NEWER
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("available")
        self.assertEqual(
            controls.status.get_text(),
            f"T48 Programmer 9.0.0 is available. You have version {__version__}.",
        )
        self.assertEqual(controls.button.get_label(), "_Update to 9.0.0")
        self.assertTrue(controls.button.has_css_class("suggested-action"))
        self.assertTrue(controls.page_button.get_visible())
        controls.button.emit("clicked")
        question = self.answer("Update T48 Programmer?", "_Download and Install")
        size = GLib.format_size(NEWER.package_size)
        self.assertIn(
            f"The package for Ubuntu 24.04 amd64 ({size})", question.get_body()
        )
        self.assertIn("Reads more formats.", question.get_body())
        self.wait_update("installed")
        self.assertEqual(
            [path.name for path in self.service.installed], [NEWER.package_name]
        )
        self.assertEqual(
            controls.status.get_text(),
            "T48 Programmer 9.0.0 is installed. Restart T48 Programmer to use it.",
        )
        self.assertEqual(controls.button.get_label(), "_Restart T48 Programmer")
        self.assertEqual(open_dialogs(), [])  # the About window offers the restart
        with mock.patch.object(self.window, "close") as close:
            controls.button.emit("clicked")
        close.assert_called_once_with()
        self.assertTrue(self.app.restart_requested)
        self.assertIsNone(self.window.about_window)

    def test_cancelling_the_question_downloads_nothing(self) -> None:
        self.service.release = NEWER
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("available")
        controls.button.emit("clicked")
        self.answer("Update T48 Programmer?", "_Cancel")
        self.assertEqual(self.window.app_updater.state.phase, "available")
        self.assertEqual(self.service.downloads, 0)

    def test_the_download_shows_progress_and_can_be_cancelled(self) -> None:
        self.service.release = NEWER
        self.service.step_delay = 0.2
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("available")
        self.window.app_updater.install(NEWER)
        wait_until(
            lambda: (
                controls.status.get_text().startswith("Downloading ")
                and controls.status.get_text().endswith("%")
            ),
            "the download progress",
        )
        self.assertTrue(controls.progress_line.get_visible())
        self.assertFalse(controls.button.get_visible())
        # An update in progress cannot be started a second time.
        self.window.app_updater.install(NEWER)
        self.window.app_updater.check()
        self.assertEqual((self.service.downloads, self.service.checks), (1, 1))
        controls.cancel_button.emit("clicked")
        self.wait_update("available")
        self.assertEqual(controls.status.get_text(), "The update was cancelled.")
        self.assertEqual(controls.button.get_label(), "_Update to 9.0.0")
        self.assertEqual(self.service.installed, [])

    def test_an_update_carries_on_when_the_about_window_is_closed(self) -> None:
        self.service.release = NEWER
        self.service.step_delay = 0.05
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("available")
        self.window.app_updater.install(NEWER)
        self.window.about_window.close()
        pump()
        self.assertIsNone(self.window.about_window)
        self.wait_update("installed")
        # With the About window closed, a question offers the restart.
        self.answer("Restart T48 Programmer?", "_Later")
        self.assertFalse(self.app.restart_requested)
        reopened = self.about_controls()
        self.assertEqual(reopened.button.get_label(), "_Restart T48 Programmer")

    def test_a_dismissed_password_prompt_leaves_the_update_offered(self) -> None:
        self.service.release = NEWER
        self.service.install_dismissed = True
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("available")
        self.window.app_updater.install(NEWER)
        wait_until(
            lambda: controls.status.get_text().startswith("The password prompt"),
            "the dismissed prompt",
        )
        self.assertEqual(self.window.app_updater.state.phase, "available")
        self.assertEqual(controls.button.get_label(), "_Update to 9.0.0")
        self.assertEqual(self.service.installed, [])

    def test_a_failed_install_gives_the_reason(self) -> None:
        self.service.release = NEWER
        self.service.install_error = "The system did not allow the installation."
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("available")
        self.window.app_updater.install(NEWER)
        self.wait_update("failed")
        message = "The update failed: The system did not allow the installation."
        self.assertEqual(controls.status.get_text(), message)
        self.assertIn(message, self.window._diagnostic_log[-1])

    def test_a_copy_run_from_source_is_sent_to_the_release_page(self) -> None:
        self.service.installed_target = None
        self.service.release = replace(NEWER, package_name="", package_url="")
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("available")
        self.assertIn(
            "This copy was not installed from a release package",
            controls.status.get_text(),
        )
        self.assertEqual(controls.button.get_label(), "Open Release _Page")
        self.assertFalse(controls.button.has_css_class("suggested-action"))
        self.assertFalse(controls.page_button.get_visible())
        with mock.patch("t48_programmer.app_updater.open_uri") as opened:
            controls.button.emit("clicked")
        opened.assert_called_once_with(NEWER.page_url)
        self.assertEqual(self.service.downloads, 0)

    def test_a_system_the_release_has_no_package_for_is_told_so(self) -> None:
        self.service.installed_target = replace(UBUNTU, arch="arm64")
        self.service.release = replace(NEWER, package_name="", package_url="")
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("available")
        self.assertIn(
            "The release has no package for Ubuntu 24.04 arm64",
            controls.status.get_text(),
        )
        self.assertEqual(controls.button.get_label(), "Open Release _Page")

    def test_no_update_or_restart_while_an_operation_runs(self) -> None:
        self.service.release = NEWER
        controls = self.about_controls()
        controls.button.emit("clicked")
        self.wait_update("available")
        self.window._active_operation = OperationController()
        self.window.app_updater.install(NEWER)
        self.assertEqual(controls.status.get_text(), BUSY_WHILE_RUNNING)
        self.assertEqual(
            BUSY_WHILE_RUNNING,
            "T48 Programmer can be updated once the operation on the chip has finished",
        )
        self.assertEqual(self.service.downloads, 0)
        self.window._active_operation = None
        self.window.app_updater.install(NEWER)
        self.wait_update("installed")
        self.window._active_operation = OperationController()
        with mock.patch.object(self.window, "close") as close:
            controls.button.emit("clicked")
        close.assert_not_called()
        self.assertFalse(self.app.restart_requested)
        self.assertEqual(controls.status.get_text(), RESTART_WHILE_RUNNING)
        self.window._active_operation = None


@unittest.skipUnless(HAVE_DISPLAY, "needs a display")
class DocumentationStateTests(unittest.TestCase):
    def test_the_help_screenshot_state_shows_an_update_without_asking_github(
        self,
    ) -> None:
        window = MainWindow(application=shared_application())
        window.app_updater.service = FakeService()
        self.addCleanup(window.close)
        window.present()
        window.show_documentation_state("app-update")
        about = window.about_window
        self.assertIsNotNone(about)
        self.addCleanup(about.destroy)
        (controls,) = [w for w in widgets_in(about) if isinstance(w, AppUpdateControls)]
        self.assertTrue(controls.button.get_label().startswith("_Update to "))
        self.assertEqual(window.app_updater.service.checks, 0)


if __name__ == "__main__":
    unittest.main(argv=sys.argv)
