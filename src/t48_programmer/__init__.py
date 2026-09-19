"""T48 Programmer, a native GNOME interface for XGecu chip programmers."""

from .gtk_environment import scrub_snap_environment

__version__ = "0.1.1"

# Every route into GTK passes through this package, so this is the one place
# that is certain to run first. See gtk_environment for what it prevents.
scrub_snap_environment()
