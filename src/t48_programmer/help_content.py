"""User-focused technical content for the in-application guide."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HelpSection:
    heading: str
    paragraphs: tuple[str, ...]
    steps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HelpTopic:
    slug: str
    title: str
    summary: str
    sections: tuple[HelpSection, ...]


HELP_TOPICS = (
    HelpTopic(
        "overview",
        "Getting Started",
        "The workspace, the programmer, and the rules the application keeps to.",
        (
            HelpSection(
                "Workspace layout",
                (
                    "The start page reads from top to bottom in the order of the job: the programmer, the chip, the image, the options, and then the buttons that act on them. File, Chip, Device, Programmer and Help hold the complete command set. Progress, results, the guided ROM burn and this guide all appear in the same window, and the Back button in the header returns to the start page.",
                    "All of the work on the chip is done by minipro. This application chooses the arguments, shows the progress, and explains the result. Anything minipro supports for your programmer is available here, and the chip list is whatever the installed minipro reports.",
                ),
            ),
            HelpSection(
                "What is safe and what is not",
                (
                    "Reading, verifying, blank checking and reading the chip ID never change the chip. Writing and erasing do, and both ask for confirmation first, naming the chip and the image.",
                    "The most expensive mistake is selecting the wrong chip. The programming voltage follows the selection, and 21 V into a part made for 12.5 V will destroy it. Read the part number from the chip, not from the socket it came out of.",
                ),
            ),
            HelpSection(
                "Offline mode",
                (
                    "When no programmer answers, the application works offline and says so in a banner across the top of every page. Only the commands that need the hardware are disabled. You can still open and identify images, check them against a chip, take a ROM through the guide and save its parts, search the chip database and read what minipro knows about a chip, and read this guide.",
                    "On the last page of the guided ROM burn the Burn buttons are disabled while offline, and Save All Parts writes the prepared files to a folder so that they can be burned later or with another tool.",
                    "The application looks for the programmer again every few seconds while the start page is showing, and the Reconnect button in the banner looks at once. When a programmer answers, the banner goes and the commands come back, with the chip and the image still selected.",
                    "The chip database belongs to minipro. If minipro itself is not installed, chips cannot be listed, and the banner says so. Images and ROM sets still work.",
                ),
            ),
        ),
    ),
    HelpTopic(
        "chips",
        "Choosing a Chip",
        "Finding the right entry among many thousands, and what the details mean.",
        (
            HelpSection(
                "Searching",
                (
                    "Choose Chip opens a search over every device minipro lists for your programmer. Type any part of the name. Several words narrow the search, so 27C256 DIP finds the DIP packages of every 27C256. Press Enter to take the first match.",
                    "Names have the form PART@PACKAGE. The package matters: a PLCC or TSOP part needs the matching adapter, and minipro checks for the adapter on the packages that have an identifiable one.",
                ),
                (
                    "Read the full part number from the top of the chip, including the maker's prefix.",
                    "Search for it. If the exact part is missing, look for the same part from another maker and check the data sheet before trusting the equivalence.",
                    "Choose the entry whose package matches the chip in your hand.",
                ),
            ),
            HelpSection(
                "Chip details",
                (
                    "Once a chip is chosen the start page shows its memory size and package, taken from minipro. Chip, Chip Information shows everything minipro prints, including the programming voltages it will use and the ones it allows.",
                    "Chip, Read Chip ID asks the chip in the socket to identify itself. Flash and most EPROMs from the late 1980s onward can. Older EPROMs and most parallel EEPROMs cannot, and minipro says so.",
                ),
            ),
            HelpSection(
                "SPI flash detection",
                (
                    "For 25-series SPI flash, Chip, Detect 8-Pin SPI Flash reads the JEDEC ID and lists the parts that share it. When exactly one part matches, the result page offers to select it.",
                ),
            ),
        ),
    ),
    HelpTopic(
        "reading",
        "Reading a Chip",
        "Saving the contents of a chip and checking what came out.",
        (
            HelpSection(
                "Making a read",
                (
                    "A read saves the whole chip to a file. The default is a raw binary image, which is what emulators and other tools expect. Intel HEX and Motorola S-record are available under Options, Memory and Files.",
                    "For a microcontroller, a read with the default memory section saves the code, the data EEPROM and the fuses as three files beside each other. Choose one section to read only that.",
                ),
                (
                    "Choose the chip and seat it in the socket with pin 1 by the lever.",
                    "Press Read and choose where to save the image.",
                    "When the read finishes, the result page identifies the image. Use as Current Image loads it, ready to be verified or written to another chip.",
                ),
            ),
            HelpSection(
                "Trusting a read",
                (
                    "Read an old chip twice and compare the CRC-32 values. A chip with failing cells or dirty legs often reads differently each time. A Kickstart image reports whether its checksum is valid, which is a stronger test still.",
                ),
            ),
        ),
    ),
    HelpTopic(
        "writing",
        "Writing a Chip",
        "What happens during a write, and how to tell that it worked.",
        (
            HelpSection(
                "The sequence",
                (
                    "minipro reads the chip ID, erases the chip if it can be erased electrically, writes the image, and reads it back to verify. Each stage appears on the progress page. A write that verifies has been read back from the chip byte for byte, so it is done.",
                    "The image must be the same size as the chip. When it is not, the start page says so before you begin, and minipro stops rather than guess. For a ROM smaller than its chip, use the guided ROM burn so that it is repeated to fill the chip, or allow the mismatch under Options, Writing.",
                ),
                (
                    "Choose the chip, then open the image. Check the identification and the size line.",
                    "Press Write and read the confirmation. It names the chip and the image.",
                    "Leave the chip alone until the result page appears.",
                ),
            ),
            HelpSection(
                "UV EPROMs",
                (
                    "A UV EPROM, the kind with a quartz window, cannot be erased by the programmer. It is erased under an ultraviolet lamp, typically for 10 to 20 minutes. Run Blank Check before writing one. Programming can only change a 1 to a 0, so writing over old data gives a mixture of the two images and a failed verify.",
                    "Cover the window with an opaque label after programming. Daylight erases an EPROM slowly, and a camera flash can upset a read.",
                ),
            ),
            HelpSection(
                "Cancelling",
                (
                    "Cancelling a read or a verify is harmless. Cancelling a write or an erase leaves the chip partly programmed, and the application asks before it does so. minipro is stopped where it stands, so reconnect the programmer afterwards if it does not answer.",
                ),
            ),
        ),
    ),
    HelpTopic(
        "rom-sets",
        "ROM Sets for Retro Computers",
        "Splitting, swapping and filling an image for Amiga, Atari ST and Acorn boards.",
        (
            HelpSection(
                "Why an image cannot always be written as it is",
                (
                    "A ROM image is one file in the order the processor sees it. The chips on the board often hold it differently. Two 8-bit chips serve a 16-bit bus by taking alternate bytes. A large ROM is cut across several smaller chips. A 16-bit EPROM is numbered by the programmer in the opposite byte order to a 68000. A small ROM in a larger chip must be repeated, because the spare address pins are tied high or left to float by the board.",
                    "File, Guided ROM Burn does this work, and the Start button on the start page opens it too. It asks five things in order: which ROM, which machine, which chip, which image or images, and then it burns. Each answer becomes a crumb at the top of the page. Press a crumb to go back and change that answer. Whatever the change does not invalidate is kept, so choosing a different chip does not lose the image.",
                    "The last page lists every chip of the set with its label and checksum. Burn and Verify writes the next chip that is still waiting, reads it back, compares it, and marks it done. The guide always verifies, whatever the Options say. Take each chip out and label it before putting the next blank one in. A chip that fails stays waiting, with the reason beside it, and can be burned again. Save All Parts writes the prepared files to a folder instead, for another tool or another day.",
                ),
            ),
            HelpSection(
                "Commodore Amiga",
                (
                    "The A500, A500 Plus, A600, A2000 and CDTV take one 40-pin ROM, and a 27C400 EPROM fits the socket. The image is byte-swapped for the programmer. A 256 KB Kickstart, 1.3 and earlier, is written twice to fill the 512 KB chip.",
                    "The A1200, A3000 and A4000 take two ROMs, HI and LO, which supply the upper and lower halves of the 32-bit bus. The image is dealt out a 16-bit word at a time, each half is byte-swapped, and each is written twice to fill a 27C400.",
                    "The A600 has one ROM, like the A500. The A1000 loads Kickstart from disk and has no ROM socket to fill.",
                    "The start page reports the Kickstart version and whether the checksum is valid. An image that has already been byte-swapped is recognised and is not swapped again.",
                    "An encrypted Kickstart from Amiga Forever is decrypted with its rom.key. The key beside the ROM is used without asking. Otherwise you are asked for it. A key is accepted only if the result is a Kickstart whose checksum adds up, so a wrong key cannot produce a chip full of noise. The ROM file is left as it is, and the decrypted copy lives in a private folder that is removed when the window closes.",
                ),
            ),
            HelpSection(
                "Atari ST and STE",
                (
                    "TOS 1.00 to 1.04 is 192 KB. Early boards hold it in six 32 KB chips, for which 27C256 EPROMs are a direct fit. The HI chips hold the even bytes and the LO chips the odd bytes, in three pairs numbered from the bottom of the ROM. Later STF and STFM boards hold it in two 1 Mbit mask ROMs, which need a pin adapter to take a 27C010.",
                    "The STE and Mega STE hold 256 KB of TOS, versions 1.06 to 2.06, in two 32-pin sockets that take a 27C010 directly.",
                ),
            ),
            HelpSection(
                "Acorn BBC Micro, Master and Electron",
                (
                    "The MOS, BASIC and sideways ROMs are 8 KB or 16 KB each, and the machine pages them in 16 KB banks. The guide offers chips from 8 KB to 256 KB. A 27128 is the original fit. The 128 KB and 256 KB parts have 32 pins and need an adapter in a 28-pin socket.",
                    "One image in a larger chip is repeated into every bank. That works in any socket, because a plain socket holds the upper address pins high and so reads the top bank, where a copy is.",
                    "A chip larger than 16 KB can also hold a different ROM in each bank, the first image in the lowest. Those appear only where something drives the upper address pins: a switch, a ROM board, or a Master socket linked for 32 KB, which presents both banks as two ROM slots. The last page shows what each bank holds from the top of the chip down, and marks the one a plain socket reads. If that bank is empty, the ROM will not be seen in a plain socket.",
                    "A 128 KB Master MOS image is eight banks and fills a 128 KB chip. A sideways ROM is recognised by its header, and its own title is shown beside the file name, which is the easy way to tell sixteen files called rom apart.",
                ),
            ),
        ),
    ),
    HelpTopic(
        "options",
        "Options",
        "Every minipro option, and when it is worth changing.",
        (
            HelpSection(
                "How options apply",
                (
                    "Each option is passed only to the operations that accept it. A programming voltage set for a write is not passed to a read. Options stay as set until you change them, choose Reset Options from the File menu, or close the application. Choosing a different chip resets the voltages, since the allowed values belong to the chip.",
                ),
            ),
            HelpSection(
                "Voltages and timing",
                (
                    "The Voltages and Timing section appears only for chips that allow them, mainly EPROMs and programmable logic. The lists come from minipro for the chosen chip. The default is right for a genuine part. A lower VPP is sometimes needed for a relabelled or second-source chip whose data sheet calls for it. Raising VPP above the data sheet value destroys chips.",
                ),
            ),
            HelpSection(
                "Chip checks",
                (
                    "Ignore a Chip ID Mismatch lets a write proceed when the chip identifies as a different part. It is the right choice for a known equivalent and the wrong one for a chip you have not identified. minipro has no pin contact test for the T48. The option is there for the TL866II+ and T76, and on a T48 minipro reports that the test is not supported and carries on.",
                ),
            ),
        ),
    ),
    HelpTopic(
        "testing",
        "Testing Devices and the Programmer",
        "Logic ICs, static RAM, and the programmer's own self test.",
        (
            HelpSection(
                "Logic ICs and RAM",
                (
                    "Device, Test Logic IC or RAM runs minipro's test vectors against 74-series and 4000-series logic and common static RAM. Choose the device by its plain number, such as 7400 or 74245. The result lists every vector, and a pin that read wrongly is marked with a minus sign.",
                ),
            ),
            HelpSection(
                "Programmer self test",
                (
                    "Programmer, Self Test checks the pin drivers of the programmer itself. The socket must be empty, because the test drives every pin with every supply in turn, and a chip left in the socket may not survive it.",
                ),
            ),
        ),
    ),
    HelpTopic(
        "troubleshooting",
        "Troubleshooting",
        "The problems that come up, and what each one usually means.",
        (
            HelpSection(
                "The programmer is not found",
                (
                    "Check the cable, then Programmer, Reconnect. If minipro works with sudo in a terminal but not here, the udev rules are missing. The package installs them. For a minipro built by hand, sudo make install puts its rules in place. Either way, unplug the programmer and plug it in again, because the rules are applied when the device appears.",
                    "Only one program can hold the programmer at a time. Close any other copy of minipro.",
                ),
            ),
            HelpSection(
                "The chip ID does not match",
                (
                    "Either the wrong chip is selected, the chip is seated badly, or the chip is not what its label says. Relabelled flash and EPROMs are common in low-cost listings. Read Chip ID shows what the chip reports, and searching for that part is often the quickest way to the truth.",
                ),
            ),
            HelpSection(
                "Verification fails",
                (
                    "On a UV EPROM the chip was probably not blank, so run Blank Check and erase it for longer. On any chip, a failure at the same address every time points to a worn cell, and a failure that moves points to contact. Clean the legs and reseat the chip.",
                ),
            ),
            HelpSection(
                "Overcurrent protection",
                (
                    "The programmer cuts the power when the chip draws too much. The usual causes are a chip inserted the wrong way round or offset by a row, the wrong chip selected, or a dead chip. Remove the chip before trying again.",
                ),
            ),
            HelpSection(
                "Reporting a problem",
                (
                    "Help, Diagnostic Log holds the exact output of minipro for every operation in this session. Copy it into a report. It contains chip names and file names but nothing else about your computer.",
                ),
            ),
        ),
    ),
)
