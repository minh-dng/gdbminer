// Regression reproducer for the LLVM 14 taints port (mimid-llvm14.patch):
// unary float negation compiles to FNEG (opcode 12) on LLVM 14, which the
// trace-taint analyzer must handle. On LLVM 4 the same source compiled to a
// binary FSUB instruction, so the LLVM 4-era analyzer never saw this opcode.
// Run via scripts/repro_fneg.sh inside the experiment image.
#include <stdio.h>

int main(void) {
    int c = getchar();
    double x = (double)c;
    if (-x == -65.0) {
        printf("A\n");
    } else {
        printf("B\n");
    }
    return 0;
}
