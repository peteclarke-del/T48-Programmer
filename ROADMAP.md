# Roadmap

## Done in 0.1.0

- Every minipro operation on a chip, with every option.
- Chip search over the full database, and chip information.
- Image identification for Kickstart, TOS and Acorn ROMs.
- A guided ROM burn with breadcrumbs for Amiga Kickstart, Atari TOS in six
  chips or two, and Acorn ROMs in chips from 8 KB to 256 KB.
- Several Acorn ROMs in one chip, in 16 KB banks, with a bank map.
- Encrypted Amiga Forever Kickstarts, decrypted with rom.key.
- Logic and RAM tests, chip ID, SPI flash detection, programmer self test.
- Offline mode.
- A simulator, a user guide, and a Debian package that bundles minipro.

## Next

1. **Validation on a physical T48.** Read a known chip and compare it, then
   write and verify an EEPROM, a UV EPROM and a 27C400, and record the firmware
   and the results. Correct whatever the real output shows that the captured
   text did not.
2. **More boards.** Atari TT (four 8-bit chips on a 32-bit bus, which
   `prepare()` already handles), the Acorn Atom, whose 24-pin socket pinout has
   to be confirmed against a board first, the BBC Master 128K MOS, and
   multi-Kickstart images for 27C800 and 27C160 switchers. Each needs its
   pinout confirmed against a board before it is offered.
3. **TOS images that are already split.** The guide takes one whole image and
   splits it. Taking a file per chip as well means deciding which file is HI,
   and a wrong guess burns a set that does not boot, so it needs a careful
   design and not a filename convention.
4. **Reordering banks** by dragging, where today an image is removed and added
   again.
5. **Compare two images.** Show the first difference and the count, for
   deciding between two reads of a doubtful chip.
6. **Read twice and compare**, as one command, for old EPROMs.
7. **A hex view** of the open image.
8. **Fuse editing** for microcontrollers. minipro exchanges fuses as a text
   file, which the application can already read and write. An editor with the
   fuse names is a better interface than a file chooser.
9. **Check for Application Updates**, as in Greaseweazle-GUI, once there are
   releases to check for.

## Left out on purpose

- **Firmware update.** minipro can flash the programmer's firmware. A failure
  part way leaves the programmer in its bootloader, and the operation asks a
  question on standard input that this application deliberately keeps closed.
  It is better done in a terminal, by someone reading what minipro says.
- **A built-in chip database.** Sizes and voltages come from minipro at run
  time. A second copy here would be wrong as soon as minipro was updated.
- **Downloading ROM images.** They belong to their owners.
- **T56 and T76 algorithm files.** Those programmers need bitstreams extracted
  from XGecu's software. minipro provides a script for that, and the result is
  picked up without any help from this application.
