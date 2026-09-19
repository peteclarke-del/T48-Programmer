# Security policy

## Supported versions

| Version | Security fixes |
| --- | --- |
| Current `main` branch | Yes |
| Latest published release | Yes |
| Older tags and unmaintained branches | No |

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use GitHub's private
[Report a vulnerability](https://github.com/peteclarke-del/T48-Programmer/security/advisories/new)
workflow. If that workflow is unavailable, contact the repository owner
privately using the address on the maintainer's GitHub profile. Include the
affected version or commit, host distribution, a minimal reproduction using
files you may lawfully share, and sanitised logs.

You should receive an acknowledgement within five working days. Disclosure
timing will be coordinated with the reporter. These are response targets, not
a service-level agreement.

Reports are especially useful for command or argument injection through a chip
or file name, unsafe image parsing, path traversal, unintended host-file
access, a write or erase that happens without confirmation, a voltage or chip
selected without the user's action, and vulnerable dependencies.

Use blank or disposable chips for research. This project does not operate a bug
bounty.

## What this application does and does not do

- It runs `minipro` as a child process, with arguments passed as a list and
  never through a shell. A chip name or file name cannot become a command.
- It reads the files you open and writes only where you choose: the image from
  a read, the parts of a ROM set, and a private temporary folder that is removed
  when the window closes. A Kickstart decrypted with your rom.key is held in
  memory and in that folder only. The encrypted file and the key are never
  changed, and neither is sent anywhere.
- It uses the network for one thing, and only when you ask: Check for
  Application Updates sends a request to api.github.com, and an update you
  accept is downloaded from GitHub, checked against the SHA256SUMS published
  with the release, and installed by apt after the system asks for your
  password. A package that does not match is deleted. Nothing is sent when the
  application starts, and no ROM image is ever downloaded or uploaded. See
  Installing an update, below, for how the package is protected on its way in.
- It needs no privileges of its own. Installing an update is done by
  `pkexec apt-get`, which asks for your password each time. Access to the programmer comes from a udev rule that
  grants it to the user logged in at the machine. Do not run it with sudo.

## Trust boundaries

ROM images, keys and minipro's output are treated as untrusted input.

- Image identification reads fixed offsets with bounds checks and never
  executes or unpacks anything. Only a regular file is opened. A FIFO or a
  device, which reports no size and never stops giving bytes, is refused, and
  every read stops at a limit of its own instead of trusting the size the file
  system reported: 64 MB for an image and 64 KB for a key. The Kickstart
  checksum and decryption are attempted only on files of 2 MB or less.
- minipro is given the path of the image and reads the file itself. If the
  file has changed since it was opened, the application reads it again and
  does not write, so what is burned is what was identified and confirmed.
- minipro's output is parsed with string operations and with regular
  expressions that cannot backtrack badly, and each line is cut at 2 KB. A
  listing is taken from standard output alone and only when minipro succeeds,
  so an error message cannot become the name of a chip.
- The worker that runs minipro never raises. Whatever happens, the window is
  told that the operation is over, so it cannot be left refusing every command.

`T48_PROGRAMMER_MINIPRO` names the program that will be run with your
privileges and access to the programmer. Anyone who can set your environment
can already run programs as you, so it grants nothing new, but do not point it
at a binary you did not build or install.

The Debian package compiles minipro from a release archive pinned by SHA-256 in
`packaging/minipro-source.sha256`. A changed archive fails the build.

## Installing an update

The package is downloaded to your cache folder and checked against the
release's `SHA256SUMS`. That check is made as you, in a folder you can write
to, and the password prompt can then stay open for any length of time. A
program running as you could replace the file in that gap, and its maintainer
scripts would run as root on the strength of a password given for something
else.

So the check that counts is made as root. pkexec runs
`/usr/lib/t48-programmer/bin/install-update`, which the package installs and
only root can change, with the package's path and the checksum it must have.
The helper copies the package into a folder only root can write to, hashes the
copy, refuses it if the checksum differs, and gives the copy to apt. The file
that was checked is the file that is installed.

The simulator used by the demonstration mode keeps its imaginary chips in a
private folder under your runtime directory, and refuses a folder that is not
yours, so that another user of the machine cannot leave a link there for a
write to follow.

## Hardware safety

A wrong chip selection can apply a programming voltage that destroys the chip.
The application selects a chip only by your action: from the search, from the
chip you picked in the guided ROM burn, or from the button offered after an
SPI flash detection that matched exactly one part. It never sets a voltage
other than minipro's default unless you select it.
