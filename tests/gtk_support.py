"""What every interface test shares: GTK, loaded safely, and one application.

Import this before anything from gi. Importing the package first clears the
GTK paths that a Snap-packaged terminal exports, which otherwise crash GTK as
soon as it draws. D-Bus lets a process register an application once, so the
tests share one and give each test a window of its own.
"""

from __future__ import annotations

import os

from t48_programmer.application import ProgrammerApplication  # isort: skip

_application: ProgrammerApplication | None = None


def shared_application() -> ProgrammerApplication:
    global _application
    if _application is None:
        _application = ProgrammerApplication(
            f"com.github.pclarke.T48Programmer.Test{os.getpid()}", unique=False
        )
        _application.register(None)
    return _application
