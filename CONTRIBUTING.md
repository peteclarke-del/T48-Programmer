# Contributing to T48 Programmer

This application applies up to 25 V to chips that may be irreplaceable. Changes
must keep destructive actions explicit, leave the choice of voltage to minipro
and the user, and fail safely.

## Before starting

Open an issue for a new dependency, a change to how minipro is invoked, or a
redesign of a workflow. Do not attach copyrighted ROM images. Report security
defects according to [SECURITY.md](SECURITY.md).

## Rules for changes

1. Keep minipro's arguments as a list. Never build a shell command from a chip
   name or a file name. Chip names contain `@`, brackets and spaces.
2. Keep knowledge of minipro's flags in `minipro.py`, and of its output in
   `operations.py`, `programmer.py` and `chips.py`.
3. Do not store facts about chips. Sizes, voltages and clocks come from minipro
   at run time.
4. Prefer a row in a table to a branch in a function. Boards, options, actions
   and failure explanations are all tables.
5. Treat image contents, file names and minipro's output as untrusted.
6. A new parser is tested against text captured from a real minipro, kept
   exactly as printed. Add it to `tests/support.py`.
7. A new ROM layout states where its facts come from, and has a test of the
   first bytes of each chip as well as the round trip.
8. Update the user guide in `help_content.py` when behaviour or wording
   changes. The tests check that the guide names commands as the menus do.
9. Write comments that say why. The code already says what.

Prose in this project, from comments to the guide, uses plain punctuation and
no sales vocabulary. `tests/test_house_style.py` enforces what can be enforced.

## Tests

Run before submitting:

```sh
PYTHONPATH=src python3 -W error::ResourceWarning -m unittest discover -s tests -v
python3 -m compileall -q src tests tools
ruff check src tests tools
ruff format --check src tests tools
bash -n t48-programmer packaging/build-deb.sh
sh -n packaging/t48-programmer packaging/postinst packaging/postrm
desktop-file-validate data/com.github.pclarke.T48Programmer.desktop
appstreamcli validate --no-net data/com.github.pclarke.T48Programmer.metainfo.xml
```

The interface tests need a display and open real windows for a few seconds
each. Set `T48_PROGRAMMER_REQUIRE_GTK=1` to be sure they ran.

Evidence from real hardware is valuable, and should be recorded in the pull
request with the programmer, firmware, minipro version and chip. It does not
replace a deterministic test. If minipro printed something the application did
not understand, the Diagnostic Log has the exact text. Add it as a fixture.

## Pull requests

Explain the user-visible result, the chips or boards affected, whether a
destructive operation is touched, the failure modes tested, and the exact
verification commands. Keep unrelated changes in separate pull requests.
