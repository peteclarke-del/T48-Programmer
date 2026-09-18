"""Shared fixtures: minipro output captured verbatim, and the simulator's setup.

The text below was copied from minipro 0.7.4 and is kept exactly as printed,
wrapped lists and tab characters included, because those details are what the
parsers have to survive.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from unittest import mock

EPROM_INFO = """
---------------Chip Info----------------
Name: M27C256B@DIP28
Available on: TL866II, T48, T56
Memory: 32768 Bytes
Package: DIP28
Protocol: 0x07
Read buffer size: 1024 Bytes
Write buffer size: 128 Bytes
----------------------------------------
Default VPP programming voltage: 13 V
Available VPP voltages [V]: 9, 9.5, 10,
11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5,
15.5, 16, 16.5, 17, 18, 21, 25

Default VDD write voltage: 6.5 V
Available VDD write voltages [V]: 1.2,
1.8, 2.5, 3, 3.3, 4, 4.5, 4.75, 5,
5.25, 5.5, 5.75, 6, 6.25, 6.5

Default VCC verify voltage: 5 V
Available VCC verify voltages [V]: 1.2,
1.8, 2.5, 3, 3.3, 4, 4.5, 4.75, 5,
5.25, 5.5, 5.75, 6, 6.25, 6.5

Default write pulse: 100 us
Available write pulse[us]: 1-65535
----------------------------------------
"""

WORD_WIDE_INFO = """
---------------Chip Info----------------
Name: M27C400@DIP40
Available on: T48, T56
Memory: 262144 Words
Package: DIP40
Protocol: 0x09
Read buffer size: 1024 Bytes
Write buffer size: 128 Bytes
----------------------------------------
"""

MICROCONTROLLER_INFO = """
---------------Chip Info----------------
Name: ATMEGA328P@DIP28
Available on: TL866II, T48, T56
Memory: 16384 Words + 1024 Bytes
Package: DIP28
ICSP: ICP007.JPG
Protocol: 0x1d
Read buffer size: 256 Bytes
Write buffer size: 128 Bytes
----------------------------------------
"""

SPI_FLASH_INFO = """
---------------Chip Info----------------
Name: W25Q64JV@SOIC8
Available on: TL866II, T48, T56
Memory: 8388608 Bytes
Package: DIP8
ICSP: ICP009.JPG
Protocol: 0x03
Read buffer size: 4096 Bytes
Write buffer size: 256 Bytes
----------------------------------------
Available SPI clock frequencies [MHz]:
4, 8, 15, 30
----------------------------------------
"""

LOGIC_INFO = """
---------------Chip Info----------------
Name: 7400
Package:\t DIP14
Vector count:\t 4
----------------------------------------
Default VCC voltage: 5 V
Available VCC voltages [V]: 1.8, 2.5,
3.3, 5
"""

UNKNOWN_DEVICE = "\nDevice NOPE123 not found!\n"


@contextlib.contextmanager
def simulator(delay: str = "0", absent: bool = False) -> Iterator[str]:
    """Point the application at the simulator, with an empty socket of its own."""
    with tempfile.TemporaryDirectory(prefix="t48-test-") as state:
        environment = {
            "T48_PROGRAMMER_DEMO": "1",
            "T48_PROGRAMMER_SIMULATOR_STATE": state,
            "T48_PROGRAMMER_SIMULATOR_DELAY": delay,
            "T48_PROGRAMMER_SIMULATOR_ABSENT": "1" if absent else "0",
        }
        with mock.patch.dict(os.environ, environment):
            yield state
