"""Shared lifecycle management for streaming minipro commands."""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .operation import OperationController

# minipro redraws its progress line with a carriage return and an erase-line
# escape, and rings the terminal bell on an overcurrent trip. None of that
# belongs in a label or a log.
_TERMINAL_NOISE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x07")


@dataclass(frozen=True, slots=True)
class StreamingProcessResult:
    return_code: int
    output: str
    timed_out: bool
    cancelled: bool


def clean_line(raw_line: str) -> str:
    """Remove terminal control sequences and surrounding whitespace."""
    return _TERMINAL_NOISE.sub("", raw_line).strip()


def run_streaming_process(
    command: Sequence[str],
    *,
    timeout: float,
    on_line: Callable[[str], None] | None = None,
    controller: OperationController | None = None,
    process_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
) -> StreamingProcessResult:
    """Run a command, reporting each line of output as it arrives.

    minipro writes everything to stderr, so the two streams are merged. Text
    mode is used for its universal newlines: a progress update ends with a bare
    carriage return, and treating that as a line ending is what delivers each
    percentage as it is written instead of all at once when the stage finishes.
    Standard input is closed because minipro falls back to interactive
    questions in a few situations, and a question nobody can answer would hang
    the operation until the timeout.
    """
    process = process_factory(
        list(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    )
    if controller is not None:
        controller.register(process)

    timed_out = threading.Event()

    def stop_process() -> None:
        if process.poll() is None:
            timed_out.set()
            process.kill()

    timer = threading.Timer(timeout, stop_process)
    timer.daemon = True
    timer.start()
    output_lines: list[str] = []
    try:
        for raw_line in process.stdout or ():
            line = clean_line(raw_line)
            if not line:
                continue
            output_lines.append(line)
            if on_line is not None:
                on_line(line)
        return_code = process.wait()
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait()
        raise
    finally:
        timer.cancel()
        if process.stdout is not None:
            process.stdout.close()
        if controller is not None:
            controller.unregister(process)

    return StreamingProcessResult(
        return_code,
        "\n".join(output_lines),
        timed_out.is_set(),
        controller.cancelled if controller is not None else False,
    )
