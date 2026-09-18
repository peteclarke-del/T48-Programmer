"""GTK application lifecycle."""

from __future__ import annotations

import os
from importlib.resources import files

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from .branding import APPLICATION_ICON, APPLICATION_ID, APPLICATION_NAME  # noqa: E402
from .window import MainWindow  # noqa: E402

DOCUMENTATION_STATE_VARIABLE = "T48_PROGRAMMER_DOCUMENTATION_STATE"


class ProgrammerApplication(Adw.Application):
    """T48 Programmer desktop application."""

    def __init__(
        self, application_id: str = APPLICATION_ID, *, unique: bool = True
    ) -> None:
        # The interface tests pass their own id and unique=False, so that a
        # copy of the application already running does not take their window.
        flags = Gio.ApplicationFlags.DEFAULT_FLAGS
        if not unique:
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        GLib.set_application_name(APPLICATION_NAME)
        super().__init__(application_id=application_id, flags=flags)
        self.set_accels_for_action("win.help", ["F1"])
        self.set_accels_for_action("win.open-image", ["<Control>o"])
        self.set_accels_for_action("win.choose-chip", ["<Control>k"])
        self.set_accels_for_action("win.quit", ["<Control>q"])
        # Set by the window after an update, so main() starts the new version.
        self.restart_requested = False

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        # The icon travels inside the package, in the layout an icon theme
        # expects, so it is found from a checkout and from a wheel as well as
        # from the Debian package, which also installs it system-wide.
        display = Gdk.Display.get_default()
        if display is not None:
            icons = files("t48_programmer").joinpath("data", "icons")
            Gtk.IconTheme.get_for_display(display).add_search_path(str(icons))
        Gtk.Window.set_default_icon_name(APPLICATION_ICON)

    def do_activate(self) -> None:
        window = self.get_active_window()
        if window is not None:
            window.present()
            return
        window = MainWindow(application=self)
        window.present()
        documentation_state = os.environ.get(DOCUMENTATION_STATE_VARIABLE)
        if documentation_state:
            window.show_documentation_state(documentation_state)
        else:
            window.begin_programmer_detection()
