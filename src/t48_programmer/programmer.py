"""Detection and description of the attached programmer."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from . import minipro

# "t48: T48", as printed by minipro -k.
_PRESENCE_PATTERN = re.compile(r"^(?P<key>[a-z0-9]+):\s+(?P<model>\S.*)$")
# "Found T48 00.1.31 (0x11f)", printed at the start of every real operation.
_BANNER_PATTERN = re.compile(r"^Found (?P<model>\S+) (?P<firmware>[0-9.]+) \(")
_VERSION_PATTERN = re.compile(r"^minipro version (?P<version>\S+)")

MISSING_TOOL_SUMMARY = "minipro is not installed or is not on PATH."


@dataclass(frozen=True, slots=True)
class ProgrammerProbeResult:
    """Result of invoking ``minipro -k``."""

    connected: bool
    summary: str
    key: str = ""
    model: str = ""
    diagnostic: str = ""
    tool_available: bool = True


def parse_presence_output(output: str) -> ProgrammerProbeResult:
    """Parse the output of ``minipro -k``.

    minipro exits with status 0 whether or not a programmer answered, so the
    text is the only evidence. A line of the form "key: model" means one did.
    """
    for line in output.splitlines():
        match = _PRESENCE_PATTERN.match(line.strip())
        if match and match.group("key") in minipro.DATABASE_NAMES:
            model = match.group("model")
            return ProgrammerProbeResult(
                True,
                f"{model} connected and ready.",
                key=match.group("key"),
                model=model,
                diagnostic=output.strip(),
            )
    return ProgrammerProbeResult(
        False, "No programmer was found on USB.", diagnostic=output.strip()
    )


def detect_programmer(timeout: float = 8.0) -> ProgrammerProbeResult:
    """Locate minipro and ask it which programmer is attached."""
    try:
        output = minipro.run_query(["-k"], timeout=timeout)
    except subprocess.TimeoutExpired:
        return ProgrammerProbeResult(False, "The programmer did not respond in time.")
    except OSError as error:
        return ProgrammerProbeResult(
            False, f"minipro could not be started: {error}", tool_available=False
        )
    if output is None:
        return ProgrammerProbeResult(False, MISSING_TOOL_SUMMARY, tool_available=False)
    return parse_presence_output(output)


def parse_firmware(output: str) -> str:
    """The firmware version from an operation's banner, or an empty string."""
    for line in output.splitlines():
        match = _BANNER_PATTERN.match(line.strip())
        if match:
            return match.group("firmware")
    return ""


def firmware_warning(output: str) -> str:
    """minipro's note that the firmware is older or newer than it expects."""
    lines = [line.strip() for line in output.splitlines()]
    for index, line in enumerate(lines):
        if line.startswith("Warning: Firmware is"):
            return " ".join(lines[index : index + 3])
    return ""


def tool_version() -> str:
    """The installed minipro version, or an empty string when unknown."""
    try:
        output = minipro.run_query(["--version"])
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for line in (output or "").splitlines():
        match = _VERSION_PATTERN.match(line.strip())
        if match:
            return match.group("version")
    return ""
