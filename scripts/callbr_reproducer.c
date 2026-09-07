// Regression reproducer for the LLVM 14 taints port (mimid-llvm14.patch):
// asm goto compiles to CALLBR (opcode 11) on LLVM >= 9, which the LLVM 4-era
// analyzer never saw; before CALLBR was routed to genericOperation, trace-taint
// crashed with UnsupportedOperationException on this source.
// Run via scripts/repro_callbr.sh inside the experiment image.
#include <stdio.h>

int main(void) {
    int c = getchar();
    asm goto ("nop" : : : : overflow);
    if (c == 'A') {
        printf("A\n");
    } else {
        printf("B\n");
    }
    return 0;
overflow:
    printf("X\n");
    return 1;
}
