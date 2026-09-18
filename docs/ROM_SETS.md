# ROM sets

A ROM image is published as one file, in the order the processor reads it. The
chips on a board rarely hold it that way. This document explains the four
transformations that get from the file to the chips, which boards need which,
and how to add a board.

All of it is implemented in `src/t48_programmer/rom_sets.py`. Every supported
board is one row of the `LAYOUTS` table, and `prepare()` is the one routine
that carries them all out.

## The four transformations

### Splitting into lanes

A 68000 has a 16-bit data bus. When the ROMs are 8 bits wide, two of them sit
side by side: one supplies data lines D15 to D8 and the other D7 to D0. The
68000 is big-endian, so the byte at an even address is the high byte. The HI
chip therefore holds every even byte of the image and the LO chip every odd
byte.

The A1200 and A4000 have a 32-bit bus served by two 16-bit ROMs. The principle
is the same with a wider unit: HI holds the first 16-bit word of every 32-bit
long, data lines D31 to D16, and LO holds the second.

In the table this is `lanes`, the names of the chips that share a bus word in
the order their data appears in the image, and `lane_bytes`, how many bytes
each takes per turn.

### Cutting into banks

TOS 1.0x is 192 KB. Split into HI and LO it is two lanes of 96 KB. Early ST
boards hold each lane in three 32 KB chips, which gives six chips in three
pairs. Pair 0 is the lowest 64 KB of TOS, at 0xFC0000.

In the table this is `segmented`. Without it, a lane larger than the chip is an
error, which is what stops a 16 KB Acorn ROM being cut across two 2764s that
the machine has no means of joining.

### Byte swapping

A 27C400 is a 16-bit EPROM. A programmer reads an image file as a stream of
bytes and takes each pair as the low byte and then the high byte of a word. A
Kickstart file is in the 68000's order, high byte first. Written as it stands,
every word in the chip would have its halves exchanged. The image is swapped
before it is written so that the chip comes out right.

This applies only to 16-bit chips. The 8-bit chips of an Atari or a BBC Micro
are written byte for byte.

An image that someone has already swapped is recognised when it is opened, and
the application refuses to prepare it, because a second swap would undo the
first and the result would be written as though it were correct.

### Filling the chip

When the image is smaller than the chip, the spare address pins of the chip
are connected to something on the board, and which part of the chip the machine
reads depends on what. The BBC Micro holds pins 1 and 27 of a ROM socket high.
On a 27128 those are VPP and PGM, which is as it should be. On a 27C256 pin 27
is A14, on an AT28C256 pin 1 is A14, and on a W27C512 they are A15 and A14. In
each case the machine reads the top of the chip.

The image is therefore repeated to fill the chip, so that a copy is wherever
the machine looks. The same is done with a 256 KB Kickstart in a 512 KB
27C400.

When the chip is not a whole multiple of the image, repetition is not possible
and the remainder is left at 0xFF, the erased state. This is the case for 96 KB
of TOS in a 128 KB 27C010.

## Banks

Acorn machines page their ROMs. The MOS, BASIC and every sideways ROM occupy
the same 16 KB of the address map, and the machine selects one at a time. A
chip larger than 16 KB is therefore not one big ROM but room for several, each
in its own 16 KB bank.

`join_banks()` lines the chosen images up on bank boundaries, the first in the
lowest bank. An 8 KB image is repeated to fill its bank. An image of several
banks, such as a 128 KB Master MOS, takes that many. The result then goes
through `prepare()` like any other image, so one image in a large chip is still
repeated to fill it, and a set that does not divide the chip leaves the rest
erased.

Which bank a machine sees depends on the socket. A plain BBC Micro socket holds
the upper address pins high and reads the top bank. Different ROMs in one chip
appear only where something drives those pins: a switch, a ROM board, or a
Master socket linked for 32 KB, which presents both banks as two ROM slots.
With three images in a 64 KB chip the top bank is empty, and a plain socket
would see nothing. The guide shows the bank map so that this is visible before
the chip is burned.

In the table this is `bank_bytes`.

## Boards

| Layout | Image | Lanes | Lane width | Swap | Banks | Chip |
| --- | --- | --- | --- | --- | --- | --- |
| Amiga, one ROM | 256 KB or 512 KB | 1 | 16-bit | yes | no | 512 KB |
| Amiga, HI and LO | 512 KB | 2 | 16-bit | yes | no | 512 KB |
| Atari ST, six sockets | 192 KB | 2 | 8-bit | no | yes | 32 KB |
| Atari ST, two sockets | 192 KB | 2 | 8-bit | no | no | 128 KB |
| Atari STE | 256 KB | 2 | 8-bit | no | no | 128 KB |
| Acorn | 8 KB or 16 KB each, in 16 KB banks | 1 | 8-bit | no | no | 8 KB to 256 KB |

Notes that matter at the bench:

- A500 boards at revision 3 and 5 need a wire modification before they can
  address a 512 KB ROM.
- A 27C400 has 40 pins and an A1200 socket has 42. The chip sits at the end of
  the socket away from the notch, leaving socket pins 1 and 42 empty.
- The two-socket ST boards have 28-pin sockets made for 1 Mbit mask ROMs. No
  28-pin EPROM has that pinout, so a 27C010 needs a pin adapter in each.
- Kickstart images are specific to a model. The layout arranges the bytes. It
  cannot make an A500 image boot an A1200.
- Fit HI and LO chips to the sockets that the originals of the same name came
  from. Board revisions differ in how the sockets are numbered, and the labels
  on the original chips are the reliable guide.

## How the result is checked

The tests rebuild the image from the prepared chips, by undoing each step in
reverse, for every layout, every image size and every chip option, and require
the original back. They also pin down the details that a mirror-image bug in
both directions would hide: that the first bytes of a 512 KB Kickstart,
`11 14 4E F9`, come out as `14 11` at the start of HI and `F9 4E` at the start
of LO, that HI 0 of a TOS set starts with bytes 0 and 2 of the image, and that
a 27C256 prepared for a BBC Micro ends with the ROM.

## Adding a board

Add a `RomLayout` to `LAYOUTS`. For example, the Atari TT holds 512 KB of TOS
3.06 in four 8-bit chips that serve a 32-bit bus:

```python
RomLayout(
    "atari-tt",
    "tos",
    ("TT030",),
    "TOS 3.06 in four 27C010.",
    (512 * KIB,),
    _EPROM_27C010,
    lanes=("D31-D24", "D23-D16", "D15-D8", "D7-D0"),
),
```

Check each chip name against `minipro -l`, confirm the socket's pinout against
the chip's data sheet, and add a test of the first bytes of each lane. The
round-trip test picks the new row up by itself.
