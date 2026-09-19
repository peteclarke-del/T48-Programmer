# Architecture

T48 Programmer is a front end. minipro does everything that touches the chip,
and this application decides what to ask of it, follows it while it works, and
explains what it said. That division shapes the code.

## Principles

**minipro is the authority.** The chip list, the size of each chip, and the
voltages and clocks each one allows are all read from the installed minipro at
run time. Nothing about a chip is stored in this application. A newer minipro
brings its new chips with it, and a value minipro would refuse cannot be
offered.

**The contract with minipro lives in one module.** `minipro.py` is the only
place that knows a flag. Everything else names an action and fills in an
`Options` record. When minipro changes an option, one file changes.

**Tables, not branches.** The actions, the options that each accepts, the
wording of each option, the failure messages, the ROM layouts and the help
topics are all data. Each table has one routine that acts on it. Adding a board
or an option is adding a row, and the tests check the tables against each
other.

**Everything below the window is testable without GTK or hardware.** The
modules in the first table below import neither. The simulator stands in for
minipro as a real process, so the tests exercise the real runner and the real
parsers, not mocks of them.

## Modules

Without GTK:

| Module | Responsibility |
| --- | --- |
| `minipro.py` | Where minipro is, the `Action` table, the `Options` record, and `build_command`, which turns the two into an argument list |
| `subprocess_runner.py` | Runs a command, delivers its output line by line, enforces a timeout, and cleans terminal control sequences |
| `operation.py` | Thread-safe cancellation by SIGINT |
| `operations.py` | Runs one action: progress parsing, the transcript, and the table that turns minipro's messages into plain explanations |
| `programmer.py` | Detection through `minipro -k`, the firmware banner, and the minipro version |
| `chips.py` | The catalogue from `minipro -l`, search, and the parser for `minipro -d` |
| `rom_image.py` | Identification of Kickstart, TOS, Acorn and text-format images, checksums, decryption with rom.key, and the fit of an image to a chip |
| `rom_sets.py` | The ROM families, the board layouts, `join_banks()` and `prepare()` |
| `option_specs.py` | The title and explanation of every option |
| `help_content.py` | The user guide, as data |
| `samples.py` | Synthetic ROM images with valid headers, for tests and screenshots |
| `simulator.py` | A stand-in for minipro, run as a script |
| `app_update.py` | The update itself: which release is newer, which package suits this system, the checksum, and the install command |
| `releases.py` | Reading the latest GitHub release and downloading its files |
| `gtk_environment.py` | Removes GTK paths inherited from a Snap-packaged terminal |

With GTK:

| Module | Responsibility |
| --- | --- |
| `application.py` | The `Adw.Application`, accelerators, and the documentation-state hook |
| `window.py` | The start page, progress, results, errors, the diagnostic log, programmer detection and Offline mode |
| `options_panel.py` | Builds the Options group from `option_specs` and reads it back as `Options` |
| `chip_chooser.py` | The chip search window |
| `rom_wizard.py` | The guided ROM burn: breadcrumbs, five steps, and the burn sequence |
| `help_view.py` | Renders `help_content` |
| `app_updater.py` | The update's state and its controls in the About window |
| `main_loop.py` | The one way a worker thread hands a result to GTK |

## How an operation runs

1. A button or menu entry activates a `win.*` action, which calls
   `MainWindow.start_action(key)`.
2. `start_action` refuses when offline or when a chip or image is missing,
   asks for a file when the action produces one, and asks for confirmation when
   the action is destructive.
3. `run_action` shows the progress page and starts a worker thread. GTK is
   never touched from that thread.
4. The worker calls `operations.run_action`, which builds the command with
   `minipro.build_command` and hands it to `run_streaming_process`.
5. Each line of output is parsed for progress. Updates reach the window through
   `GLib.idle_add`.
6. The result, with a summary, a transcript, the chip ID and the firmware
   version, returns the same way. Success gets a result page. Failure returns
   to the start page with an explanation and the transcript. Both are added to
   the diagnostic log.

## How the guided ROM burn fits in

`rom_wizard.py` holds the answers given so far and builds one page per step
from the tables in `rom_sets.py`. It knows nothing about boards. A row added to
`LAYOUTS` appears in it.

It talks to the window through four methods, listed in its `WizardHost`
protocol: choose a ROM file, choose a chip from the full search, burn one part,
and save the parts. `burn_part` runs the ordinary write, with its confirmation
and its progress page, and passes a callback down the same path. When the write
ends, the window returns to the guide and hands it the result, where any other
write would show a result page. That callback also forces verification on,
because the guide promises verified chips whatever the Options say.

Changing an answer clears only what it invalidates. A different ROM family
starts again. A different machine keeps the image and asks for the chip again.
A different chip keeps the images and drops only those that no longer fit.

## Details worth knowing

**Progress arrives on carriage returns.** minipro redraws its progress line
with `\r` and an erase-line escape, and ends it with a newline only when the
stage is finished. The runner opens the pipe in text mode, where universal
newlines make `\r` a line ending, so each percentage is delivered as it is
written. A reader that waited for `\n` would show nothing and then 100%.

**Everything is on stderr.** minipro prints all of its messages there and only
listings on stdout. The runner merges the two.

**Standard input is closed.** With no programmer attached and no `-q`, minipro
stops to ask which database to list. Every query names the database, and stdin
is `/dev/null` so that a question nobody can answer ends at once.

**minipro has no SIGINT handler.** Cancelling ends it where it stands. After a
read that is harmless. After a write the chip is half programmed, so the
window asks first.

**A blank check fails in the words of a verify.** minipro implements it as a
verify against the erased value, so a chip that is not blank is reported as
"Verification failed". `operations.py` keeps a per-action table so that the
explanation fits the question that was asked.

**The exit status of `minipro -k` is always 0.** Presence is read from the
text.

**A key is valid if the checksum says so.** Amiga Forever encrypts a Kickstart
with a repeating XOR. XOR with the wrong key gives bytes that look as good as
the right ones to a program, so `decrypt_kickstart` accepts a result only if it
has a Kickstart header and its checksum adds up.

**Bank maps are read from the chip.** The last page of the guide does not work
out which image went where. It cuts the finished chip into banks and identifies
each one, so what it shows is what will be burned.

**A failure is not an answer, and is not cached.** The chip list and each
chip's details are kept for the life of the process, but only when minipro gave
them. If minipro is installed or repaired while the application is open, the
next request finds it.

**An update is verified by the side that installs it.** See SECURITY.md. The
application's own check of the download is a courtesy that fails early. The
check that protects the machine is the one `packaging/install-update` makes as
root, on a copy that only root can touch.

**Shell scripts are checked one at a time.** `bash -n one two` checks only
`one`. `packaging/check-scripts.sh` holds the list and is what CI, the release
workflow and the tests all run.

**One udev rules file.** minipro 0.7.4 marks the device in one rules file and
grants access in another. The package ships a single file that does both, under
its own name, so that it cannot clash with a distribution's minipro package or
install the mark without the permission.

## Environment variables

| Variable | Effect |
| --- | --- |
| `T48_PROGRAMMER_DEMO=1` | Run the simulator in place of minipro |
| `T48_PROGRAMMER_MINIPRO` | Path to the minipro to run |
| `T48_PROGRAMMER_SIMULATOR_STATE` | Folder holding the simulated chips |
| `T48_PROGRAMMER_SIMULATOR_DELAY` | Seconds per progress step |
| `T48_PROGRAMMER_SIMULATOR_ABSENT=1` | Simulate an unplugged programmer |
| `T48_PROGRAMMER_REQUIRE_GTK=1` | Fail the interface tests if GTK is missing, instead of skipping them |
| `MINIPRO_HOME` | Read by minipro itself: the folder holding its chip database |
