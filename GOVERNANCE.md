# Project governance

## Scope and roles

T48 Programmer is a native GNOME application for reading, writing and verifying
chips through XGecu programmers, built on minipro. Peter Clarke
(`@peteclarke-del`) is the current maintainer and release owner. Contributors
may propose, implement, test, and review changes. Repository administration and
release authority remain with the maintainer unless this file is updated.

## Decision priorities

Decisions are made in this order:

1. Prevent the destruction of a chip: never choose a chip or raise a voltage
   on the user's behalf, and make every write and erase explicit.
2. Burn what the machine will read. A layout that is not confirmed against a
   board is left out, however plausible it looks.
3. Fail closed when the chip, the image, the key, or the programmer's state is
   uncertain.
4. Leave facts about chips to minipro, and keep one place that knows how
   minipro is invoked.
5. Prefer evidence from real hardware, recorded with the programmer, firmware
   and chip, alongside a deterministic test.
6. Maintain a clear, keyboard-operable GNOME interface.

Significant board, security, licensing, dependency, hardware-support, or
release-policy changes require an issue before implementation. Normal changes
are decided through pull-request review.

Only the maintainer creates releases. Security reports follow
[SECURITY.md](SECURITY.md). Conduct concerns follow
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
