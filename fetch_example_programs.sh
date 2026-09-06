#! /bin/bash

# This script fetches example programs that cannot be distributed because of license conflicts.
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

set -euo pipefail

tmpdir=""
cleanup() {
    if [ -n "$tmpdir" ]; then
        rm -rf "$tmpdir"
    fi
}
trap cleanup EXIT

if [ -d /mimid/Cmimid/examples ]; then
    mimid_repo=/mimid
else
    tmpdir="$(mktemp -d)"
    mimid_repo="$tmpdir/mimid_repo"
    git clone --depth=1 --single-branch https://github.com/vrthra/mimid.git "$mimid_repo"
fi

cp "$mimid_repo"/Cmimid/examples/mjs.h "$mimid_repo"/Cmimid/examples/mjs.c "$mimid_repo"/Cmimid/examples/mjs_extra.h ./example_programs/mjs/
cd ./example_programs/mjs/ && clang -g -O0 -o  mjs mjs.c && cd ../../

cp "$mimid_repo"/Cmimid/examples/tiny.c ./example_programs/tinyc/
cd ./example_programs/tinyc/ && clang -g -O0 -o  tinyc tiny.c && cd ../../

cd ./example_programs/calc && wget -O rdp.c https://raw.githubusercontent.com/fbuihuu/parser/master/rdp.c && patch rdp.c < ./calc.diff && mv rdp.c calc.c && clang -g -O0 -o calc calc.c && cd ../../

# Rebuild checked-in benchmark binaries for the container architecture
# (the checked-in ones are x86-64).
clang++ -std=c++17 -g -O0 -D_GLIBCXX_DEBUG -o example_programs/calccpp/calccpp example_programs/calccpp/calc.cpp
clang -g -O0 -o example_programs/cgi_decode/cgi_decode example_programs/cgi_decode/cgi_decode.c
clang -g -O0 -o example_programs/json/json example_programs/json/json.c
clang++ -g -O0 -D_GLIBCXX_DEBUG -o example_programs/jsoncpp/jsoncpp example_programs/jsoncpp/json.cpp
clang -g -O0 -o example_programs/yxml/yxml example_programs/yxml/yxml.c
clang++ -g -O0 -o example_programs/xmlcpp/xmlcpp example_programs/xmlcpp/xml.cpp
rustc -g -C opt-level=0 -C target-feature=+crt-static -C overflow-checks=off -o example_programs/calcrs/calcrs example_programs/calcrs/calc.rs
rustc -g -C opt-level=0 -C target-feature=+crt-static -o example_programs/jsonrs/jsonrs example_programs/jsonrs/json.rs
