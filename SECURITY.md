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
- It makes no network connections. It downloads no ROM images and no updates.
- It needs no privileges. Access to the programmer comes from a udev rule that
  grants it to the user logged in at the machine. Do not run it with sudo.

## Trust boundaries

ROM images and minipro's output are treated as untrusted input. Image
identification reads fixed offsets with bounds checks and never executes or
unpacks anything. Files larger than 64 MB are passed to minipro without being
read into memory.

`T48_PROGRAMMER_MINIPRO` names the program that will be run with your
privileges and access to the programmer. Anyone who can set your environment
can already run programs as you, so it grants nothing new, but do not point it
at a binary you did not build or install.

The Debian package compiles minipro from a release archive pinned by SHA-256 in
`packaging/minipro-source.sha256`. A changed archive fails the build.

## Hardware safety

A wrong chip selection can apply a programming voltage that destroys the chip.
The application selects a chip only by your action: from the search, from the
chip you picked in the guided ROM burn, or from the button offered after an
SPI flash detection that matched exactly one part. It never sets a voltage
other than minipro's default unless you select it.
