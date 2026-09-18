## Summary

Describe the user-visible result and the technical boundary changed.

## Risk and compatibility

- Chips, boards and programmers affected:
- Whether a destructive operation, a voltage or a chip selection is touched:
- Changes to how minipro is invoked or how its output is read:
- GNOME accessibility implications:

## Verification

- [ ] Python regressions pass, with ResourceWarning as an error.
- [ ] Python compilation and script syntax checks pass.
- [ ] Wrong size, wrong key, cancellation, unplugged and failure cases are covered where relevant.
- [ ] No ROM image, rom.key or other copyrighted fixture has been added.
- [ ] Destructive operations require explicit confirmation and fail closed.

List exact commands and relevant real-hardware evidence, with the programmer,
firmware, minipro version and chip:

## Engineering review

- [ ] minipro arguments remain a list, and no chip or file name reaches a shell.
- [ ] Facts about chips still come from minipro at run time.
- [ ] A new board states where its pinout and layout facts come from.
- [ ] Changed controls remain keyboard-operable and clearly labelled.
- [ ] The user guide and documentation use current terminology.
