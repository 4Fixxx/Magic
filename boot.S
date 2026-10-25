# boot.S - tiny floppy boot sector: BIOS -> real mode -> 32-bit protected mode -> run program
#
# Floppy layout:   sector 1 (LBA 0)    = this boot sector
#                  sector 2.. (LBA 1+) = the raw program (prog.cmc)
#
# The program is loaded to physical 0x7E00 (directly after this sector) and
# entered at its first byte, in 32-bit ring-0 protected mode with flat
# 4 GB code/data segments (base 0), interrupts off.
#
# SECTORS (how many sectors of program to read) is passed by build.sh.

        .intel_syntax noprefix

        .equ    LOAD,   0x7E00          # where the program is loaded / entered
        .equ    STACK,  0x7C00          # initial stack top (grows down, below this sector)

        .text
        .code16
        .globl  _start
_start:
        .byte   0xEA                    # jmp 0x0000:start  (some BIOSes enter at 07C0:0000,
        .word   start, 0                #  this normalises CS to 0 so our offsets are right)

start:
        cli
        xor     ax, ax
        mov     ds, ax
        mov     es, ax                  # ES:BX = 0000:7E00 is the read buffer
        mov     ss, ax
        mov     sp, STACK
        sti                             # BIOS floppy code waits for IRQ6, so IRQs must be on
        mov     [drive], dl             # BIOS passes the boot drive in DL
        mov     BYTE PTR [tries], 5

.Lretry:
        xor     ax, ax                  # INT 13h AH=0: reset disk system
        mov     dl, [drive]
        int     0x13
        mov     ax, 0x0200 + SECTORS    # INT 13h AH=2: read AL sectors
        mov     bx, LOAD
        mov     cx, 0x0002              # cylinder 0, sector 2 (sectors count from 1)
        xor     dh, dh                  # head 0
        mov     dl, [drive]
        int     0x13
        jnc     .Lloaded
        dec     BYTE PTR [tries]        # floppies are flaky: retry a few times
        jnz     .Lretry

        mov     ax, 0x0E45              # give up: print 'E' and stop
        xor     bx, bx
        int     0x10
.Lstop16:
        hlt
        jmp     .Lstop16

.Lloaded:
        mov     ax, 0x0003              # 80x25 colour text mode (text RAM at 0xB8000)
        int     0x10

        mov     dx, 0x3F2               # floppy controller: motor off. With IRQs about to
        mov     al, 0x0C                # be disabled the BIOS timer can't do it for us.
        out     dx, al

        cli
        lgdt    [gdtr]
        mov     eax, cr0
        or      al, 1                   # CR0.PE = 1
        mov     cr0, eax
        .byte   0xEA                    # far jmp 0x08:pmode  (flushes prefetch, loads 32-bit CS)
        .word   pmode, 0x08

# ---------------------------------------------------------------------------
        .code32
pmode:
        mov     eax, 0x10               # flat 4 GB data selector
        mov     ds, ax
        mov     es, ax
        mov     fs, ax
        mov     gs, ax
        mov     ss, ax
        mov     esp, STACK
        mov     eax, LOAD
        call    eax                     # run the program (it never returns, but just in case:)
.Lstop32:
        cli
        hlt
        jmp     .Lstop32

# ---------------------------------------------------------------------------
drive:  .byte   0
tries:  .byte   0

        .align  8
gdt:
        .quad   0                       # 0x00  null descriptor
        .quad   0x00CF9A000000FFFF      # 0x08  code: base 0, limit 4 GB, 32-bit, ring 0, exec/read
        .quad   0x00CF92000000FFFF      # 0x10  data: base 0, limit 4 GB, 32-bit, ring 0, read/write
gdtr:
        .word   gdtr - gdt - 1
        .long   gdt

        .org    510
        .word   0xAA55                  # boot signature
