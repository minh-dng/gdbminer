#!/usr/bin/env bash
# Add debugger-only strtol CFI to a copy of the pinned ESP32-C3 v1.1 ROM symbols.
# SPDX-License-Identifier: AGPL-3.0

set -euo pipefail

rom=${ROM_ELF:-$HOME/.espressif/tools/esp-rom-elfs/20241011/esp32c3_rev101_rom.elf}
# arduino-cli runs only when TOOLCHAIN_BIN is unset.
toolchain=${TOOLCHAIN_BIN:-$(arduino-cli config get directories.data)/packages/esp32/tools/esp-rv32/2601/bin}
bin=$toolchain/riscv32-esp-elf
here=$(cd "$(dirname "$0")" && pwd)
debug_rom=$here/build/debug/esp32c3_rev101_rom.elf
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# The CFI matches only this ROM revision's strtol instructions.
echo "9495e1453f36f7eec4112714ea1dca22d77808776adffa93dda7dda4393e8336  $rom" | shasum -a 256 -c

"$bin-as" -march=rv32imc -mabi=ilp32 "$here/configuration/strtol-unwind.S" -o "$tmp/unwind.o"
"$bin-ld" -Ttext=0x40035286 -e gdbminer_strtol_unwind "$tmp/unwind.o" -o "$tmp/unwind.elf"
"$bin-objcopy" --dump-section ".debug_frame=$tmp/cfi.bin" "$tmp/unwind.elf"
mkdir -p "$(dirname "$debug_rom")"
"$bin-objcopy" --add-section ".debug_frame=$tmp/cfi.bin" "$rom" "$debug_rom"

# The copy keeps every ROM symbol and gains only the strtol frame description.
diff <("$bin-nm" "$rom") <("$bin-nm" "$debug_rom")
"$bin-readelf" --debug-dump=frames-interp "$debug_rom" | grep -q "pc=40035286..400352a6"
echo "Created $debug_rom"
