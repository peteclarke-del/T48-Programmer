"""Command-line entry point for the desktop application."""

from __future__ import annotations

import sys


def main() -> int:
    """Run the GTK application."""
    # Imported here so that importing the package does not require GTK.
    from .application import ProgrammerApplication

    return ProgrammerApplication().run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
