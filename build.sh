#!/bin/sh
# Builds floppy.img (1.44 MB) = boot sector + program.
# Needs: GNU as + ld (binutils) and dd.   Usage: ./build.sh [program-file]
set -e

PROG=${1:-prog.cmc}
SIZE=$(wc -c < "$PROG")
SECTORS=$(( (SIZE + 511) / 512 ))

# The loader does one INT 13h read from track 0, so it must fit on one track (17 sectors after the boot sector).
[ "$SECTORS" -le 17 ] || { echo "program too big for the 1-track loader (max 8704 bytes)"; exit 1; }

as --32 --defsym SECTORS="$SECTORS" -o boot.o boot.S
ld -m elf_i386 -nostdlib -Ttext 0x7C00 --oformat binary -o boot.bin boot.o
[ "$(wc -c < boot.bin)" -eq 512 ] || { echo "boot sector is not exactly 512 bytes"; exit 1; }

dd if=/dev/zero of=floppy.img bs=512 count=2880 2>/dev/null          # blank 1.44 MB floppy
dd if=boot.bin  of=floppy.img bs=512 seek=0 conv=notrunc 2>/dev/null  # sector 1
dd if="$PROG"   of=floppy.img bs=512 seek=1 conv=notrunc 2>/dev/null  # sector 2...

echo "OK: floppy.img  (program: $SIZE bytes = $SECTORS sectors)"
