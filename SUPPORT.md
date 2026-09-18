# Support

Search the README, the user guide (F1) and existing issues before opening a
report. Include the application version or commit, Linux distribution,
programmer model and firmware, minipro version, the chip as named in the
application, the operation, and the Diagnostic Log with private paths removed.
Help, About lists the programmer, firmware and minipro version under
Troubleshooting.

Say whether the problem also happens with `T48_PROGRAMMER_DEMO=1`. If it does,
it is in this application. If it happens only with the programmer attached,
run the same operation with `minipro` in a terminal. A failure there belongs to
[minipro](https://gitlab.com/DavidGriffith/minipro), which does all of the work
on the chip.

If the application says it is offline but `sudo minipro -k` finds the
programmer, the udev rules are missing or the programmer has not been replugged
since they were installed. See [docs/INSTALLATION.md](docs/INSTALLATION.md).

For a chip that will not boot a machine, give the machine, the board revision,
the chip, and what the last page of the guide showed. Do not upload ROM images,
a rom.key, credentials, or private paths. Use the issue templates for
reproducible defects and feature requests.

Security reports follow [SECURITY.md](SECURITY.md) and must not be filed as
public support issues. Conduct reports follow
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
