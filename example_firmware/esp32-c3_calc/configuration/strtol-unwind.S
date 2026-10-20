# Debugger-only CFI for strtol in the pinned ESP32-C3 revision 1.1 ROM ELF.
# No instructions from this assembly are loaded onto the target.
# SPDX-License-Identifier: AGPL-3.0

.cfi_sections .debug_frame
.section .text
.global gdbminer_strtol_unwind
.type gdbminer_strtol_unwind, @function
gdbminer_strtol_unwind:
.cfi_startproc simple
.cfi_def_cfa sp, 0
.cfi_same_value ra
.cfi_same_value s0
.space 2                       # 40035286: addi sp,sp,-32
.cfi_def_cfa_offset 32
.space 2                       # 40035288: sw s0,24(sp)
.cfi_offset s0, -8
.space 2                       # 4003528a: sw ra,28(sp)
.cfi_offset ra, -4
.space 16                      # Through 4003529a: lw ra,28(sp)
.cfi_restore ra
.space 6                       # Through 400352a0: lw s0,24(sp)
.cfi_restore s0
.space 2                       # 400352a2: addi sp,sp,32
.cfi_def_cfa_offset 0
.space 2                       # 400352a4: tail jump to _strtol_l.isra.0
.cfi_endproc
.size gdbminer_strtol_unwind, .-gdbminer_strtol_unwind
