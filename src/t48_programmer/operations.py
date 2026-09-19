"""Running one minipro operation and reporting what became of it."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import minipro
from .operation import OperationController
from .programmer import MISSING_TOOL_SUMMARY, firmware_warning, parse_firmware
from .subprocess_runner import StreamingProcessResult, run_streaming_process

# A full read of the largest parallel flash over USB full speed takes minutes,
# and a 16 MB SPI part at the slowest clock takes longer still.
OPERATION_TIMEOUT = 45 * 60.0

# minipro draws a stage as "Reading Code...  " while it starts, then as
# "Reading Code...  37%" while it runs, then as "Reading Code...  2.41 Sec  OK".
# The lines are taken apart with string methods and not regular expressions.
# The obvious expressions, a lazy ".+?" before the dots, backtrack
# quadratically, and one long line of dots from a misbehaving minipro would
# stall the reader for seconds at a time.
_STAGE_MARK = "..."
_STAGE_DONE = "OK"
_CHIP_ID_PATTERN = re.compile(r"Chip ID:\s*(?P<id>0x[0-9A-Fa-f]+)")

# What minipro prints when something is wrong, and what that means to a person
# holding a chip. The first match wins, so the specific causes come first.
_FAILURES = (
    (
        r"No programmer found",
        "The programmer is not connected, or another program is using it.",
    ),
    (
        r"Overcurrent protection",
        "The programmer cut the power because the chip drew too much current. "
        "Check that the chip is the right way round and is the chip selected.",
    ),
    (
        r"Invalid Chip ID: expected (?P<expected>\S+), got (?P<got>\S+)",
        "The chip in the socket does not identify as the selected chip "
        "(expected {expected}, read {got}). Choose the right chip, reseat it, or "
        "turn on Ignore a Chip ID Mismatch if the part is a known equivalent.",
    ),
    (
        r"Verification failed at address (?P<address>\S+):",
        "The chip does not match the image, starting at address {address}. A UV "
        "EPROM that was not fully erased, a worn chip, or the wrong programming "
        "voltage are the usual causes.",
    ),
    (
        r"Incorrect file size: (?P<file>\d+) \(needed (?P<needed>\d+)",
        "The image is {file} bytes and the chip holds {needed}. Pick the right "
        "chip, use the guided ROM burn, or allow the mismatch in Options.",
    ),
    (r"not blank", "The chip is not blank."),
    (
        r"can't be erased",
        "This chip cannot be erased by the programmer. A UV EPROM is erased "
        "under an ultraviolet lamp, and a one-time part cannot be erased at all.",
    ),
    (
        r"may be write-protected",
        "The chip may be write-protected. Turn on Remove Write Protection First "
        "and try again.",
    ),
    (
        r"Bad contact on pin:\s*(?P<pin>\d+)",
        "Pin {pin} is not making contact. Reseat the chip and clean its legs.",
    ),
    (
        r"doesn't have a chip ID",
        "This kind of chip has no ID to read. Older EPROMs and most EEPROMs "
        "cannot identify themselves.",
    ),
    (
        r"Logic test failed: (?P<count>\d+) errors",
        "The device failed its test with {count} wrong pin states. They are "
        "marked with a minus sign in the details.",
    ),
    (
        r"Device (?P<device>.+) not found!",
        "minipro does not know a chip called {device}.",
    ),
)
# minipro runs a blank check as a verify against the erased value, so a chip
# that is not blank is reported in the words of a failed verify.
_ACTION_FAILURES = {
    "blank_check": (
        (
            r"Verification failed at address (?P<address>\S+):",
            "The chip is not blank. The first programmed data is at address {address}.",
        ),
    ),
}


def _compile(failures: tuple[tuple[str, str], ...]) -> tuple:
    return tuple((re.compile(pattern), summary) for pattern, summary in failures)


_FAILURE_PATTERNS = _compile(_FAILURES)
_ACTION_FAILURE_PATTERNS = {
    key: _compile(failures) for key, failures in _ACTION_FAILURES.items()
}


@dataclass(frozen=True, slots=True)
class Progress:
    """The stage minipro is in, and how far through it when it says."""

    stage: str
    fraction: float | None = None


@dataclass(frozen=True, slots=True)
class OperationResult:
    action: minipro.Action
    succeeded: bool
    summary: str
    transcript: str
    cancelled: bool = False
    chip_id: str = ""
    firmware: str = ""
    firmware_warning: str = ""


def _is_stage_name(text: str) -> bool:
    """True for "Reading Code" or "Erasing": a capital, then letters and spaces."""
    return text[:1].isupper() and all(c.isalpha() or c == " " for c in text)


def parse_progress(line: str) -> Progress | None:
    """Read a stage or a percentage from one line, or None for anything else."""
    stage, mark, rest = line.partition(_STAGE_MARK)
    rest = rest.strip()
    if not (mark and stage):
        return None
    if rest.endswith("%") and rest[:-1].isdigit() and len(rest) <= 4:
        return Progress(stage, min(int(rest[:-1]), 100) / 100)
    if rest.split()[-1:] == [_STAGE_DONE]:
        return Progress(stage, 1.0)
    if not rest and _is_stage_name(stage):
        return Progress(stage)
    return None


def is_transient(line: str) -> bool:
    """True for a line minipro goes on to overwrite, which is not worth logging.

    The opening of a stage and each percentage are redrawn in place, and the
    line that replaces them, with the time taken, is the one that is kept.
    """
    return parse_progress(line) is not None and not line.endswith(_STAGE_DONE)


def explain_failure(transcript: str, action_key: str = "") -> str:
    """A plain account of the first recognised problem, or an empty string."""
    patterns = (*_ACTION_FAILURE_PATTERNS.get(action_key, ()), *_FAILURE_PATTERNS)
    for pattern, summary in patterns:
        if match := pattern.search(transcript):
            return summary.format(**match.groupdict())
    return ""


def _summarise(
    action: minipro.Action, process: StreamingProcessResult, transcript: str
) -> tuple[bool, str]:
    if process.cancelled:
        return False, f"{action.title} was cancelled."
    if process.timed_out:
        return False, "minipro stopped responding and was ended."
    if process.return_code == 0:
        return True, f"{action.title} finished."
    return False, explain_failure(transcript, action.key) or (
        f"minipro reported a problem (exit status {process.return_code})."
    )


def run_action(
    action: minipro.Action,
    *,
    chip: str = "",
    path: Path | None = None,
    options: minipro.Options | None = None,
    on_progress: Callable[[Progress], None] | None = None,
    controller: OperationController | None = None,
    runner: Callable[..., StreamingProcessResult] = run_streaming_process,
) -> OperationResult:
    """Run one action to completion. Call this from a worker thread.

    Always returns a result and never raises. The caller is a thread whose only
    way of telling the window that the operation is over is that result, and an
    exception lost in the thread would leave the window on its progress page
    with every command refused until it was killed.
    """
    base = minipro.base_command()
    if base is None:
        return OperationResult(action, False, MISSING_TOOL_SUMMARY, "")
    kept: list[str] = []

    def on_line(line: str) -> None:
        if not is_transient(line):
            kept.append(line)
        progress = parse_progress(line)
        if progress is not None and on_progress is not None:
            on_progress(progress)

    try:
        command = minipro.build_command(base, action, chip, path, options)
        process = runner(
            command, timeout=OPERATION_TIMEOUT, on_line=on_line, controller=controller
        )
    except OSError as error:
        return OperationResult(
            action, False, f"minipro could not be started: {error}", ""
        )
    except Exception as error:  # noqa: BLE001 - see the docstring
        return OperationResult(
            action,
            False,
            f"{action.title} stopped unexpectedly: {error!r}",
            "\n".join(kept),
        )

    transcript = "\n".join(kept)
    succeeded, summary = _summarise(action, process, transcript)
    chip_id = _CHIP_ID_PATTERN.search(transcript)
    return OperationResult(
        action,
        succeeded,
        summary,
        transcript,
        cancelled=process.cancelled,
        chip_id=chip_id["id"] if chip_id else "",
        firmware=parse_firmware(transcript),
        firmware_warning=firmware_warning(transcript),
    )
