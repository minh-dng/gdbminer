# GDBMiner: Debugger-driven-Grammar-Mining

This is the companion code for the the paper GDBMiner: Mining Precise Input Grammars on (almost)
any System by Eisele et al. The code allows the users to reproduce and extend the results reported
in the study. Please cite the above paper when reporting, reproducing or extending the results.

## Install local

With `mise` (recommended — pins `python@3.12`, `uv`, `ruff`, `basedpyright`, `jq`,
`shellcheck`/`shfmt` per `mise.toml`):

```sh
mise trust                          # trust mise.toml
mise install                        # python + dev tools
mise run install:dev                # uv sync --group dev → .venv
mise run check                      # lint + format check + typecheck
```

Without `mise`:

```sh
sudo apt install gdb graphviz graphviz-dev pkg-config libcairo2-dev python3-dev
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Formatting (via mise):

```sh
mise run fmt        # ruff format src analyze_experiments.py
mise run fmt:check  # verify formatting (CI)
mise run shfmt      # format shell scripts (shfmt -w)
mise run shfmt:check
```

## Git worktrees

To copy your local Docker notes into new worktrees, create `docs/DOCKER.local.md` in the primary
worktree and install the repository hook once from the repository root:

```sh
git config --local core.hooksPath .githooks
```

The hook copies the file only when it is missing, so it will not overwrite local changes. It runs
for normal `git worktree add` commands; with `--no-checkout`, it runs when the worktree is
checked out later.

## Writing up configuration TOMLs

GDBMiner reads `configuration.toml` with Python's built-in `tomllib`; no extra TOML package is needed. Paths remain relative to the working directory. Table and key names are case-sensitive.

This example configures the desktop JSON target:

```toml
[BASIC]
seed_directory = "./example_programs/json/seeds"
output_directory = "./output/json/"
binary_file = "./example_programs/json/json"
eval_directory = "./example_programs/json/eval"

[GDB]
gdb_path = "/usr/bin/gdb"
instance = "valgrind"
ignore_functions_regex = '@plt|_vgr*'
watchpoint_type = "(char*)"
watchpoint_count = 10000
timeout = 30
entrypoint = "json_parse"
input_buffer = "my_string"

[LOGS]
log_level = "INFO"
```

### Shared fields

All configurations require these fields unless marked optional:

| Table | Field | Type and meaning |
| --- | --- | --- |
| `BASIC` | `seed_directory` | str, directory of seed inputs to trace. |
| `BASIC` | `output_directory` | str, parent of the generated `trial-N` directories. |
| `BASIC` | `binary_file` | str, target executable or firmware ELF with debug symbols. |
| `BASIC` | `eval_directory` | str, directory of inputs used to measure recall. |
| `GDB` | `gdb_path` | str, debugger command with optional arguments. |
| `GDB` | `instance` | str, value from the [`GDBInstance` enum][gdb-instance]. |
| `GDB` | `entrypoint` | str, breakpoint location where tracing starts. |
| `GDB` | `exitpoint` | optional str, breakpoint location; omit or use `""` to stop on return. |
| `GDB` | `input_buffer` | str, input buffer symbol or quoted hexadecimal address. |
| `GDB` | `watchpoint_type` | str, GDB pointer type used to read input, such as `"(char*)"`. |
| `GDB` | `watchpoint_count` | positive int, bytes watched per tracing pass. |
| `GDB` | `timeout` | positive finite int or float, GDB response timeout in seconds. |
| `GDB` | `ignore_functions_regex` | optional str, skip-function regex; defaults to `""`. |
| `LOGS` | `log_level` | str, [Python logging level][logging-levels]. |

Breakpoint locations can be symbols, source locations or quoted hexadecimal addresses.
Commands accept arguments; quote command paths containing spaces inside the TOML str.
TOML literal strings preserve regex backslashes.

[gdb-instance]: src/tracer/instance/sut_instance.py
[input-channel]: src/tracer/connection/sut_connection.py
[logging-levels]: https://docs.python.org/3/library/logging.html#levels

`watchpoint_count = -1` is not supported. The tracer advances through the input by this count, so it must be positive.

### MCU settings

STM32, MSP430 and ESP32-C3 require the following server fields in `[GDB]` and serial fields in
`[Connection]`. Valgrind supplies input through a file and does not require these fields or a
`[Connection]` table.

| Table | Field | Type and meaning |
| --- | --- | --- |
| `GDB` | `gdb_server_path` | str, server command and arguments, using shell quoting rules. |
| `GDB` | `gdb_server_address` | str, GDB remote address, such as `":4242"`. |
| `Connection` | `input_channel` | str, value from the [`InputChannel` enum][input-channel]. |
| `Connection` | `port` | str, serial device path. |
| `Connection` | `baud_rate` | positive int, baud rate; omit for `esp32-usb-serial-jtag`. |

Choose the watchpoint count for your hardware. Only the selected MCU's settings are validated
and read. Board-specific fields and setup instructions live in the
[firmware guides](example_firmware/README.md).

## Generate inputs from a golden grammar

To evaluate GDBMiner, we generate inputs using a grammar. For instance, create 1000 inputs for evaluation:

```sh
uv run src/eval/generate_inputs.py --config ./example_programs/json/configuration/configuration.toml --grammar ./example_programs/json/json.grammar ./example_programs/json/eval 1000
```

## Run local

GDBMiner requires two steps tracing the processing of the seed inputs and the subsequential mining step. Execute with mise tasks (default config is `example_programs/json`):

```sh
mise run trace
mise run mine
mise run eval
# or with an explicit config:
mise run trace -- example_programs/json/configuration/configuration.toml
```

Or without mise:

```sh
uv run src/tracer/trace.py --config ./example_programs/json/configuration/configuration.toml
uv run src/miner/mine.py --config ./example_programs/json/configuration/configuration.toml
```

The following files will be stored to the configured output folder:

- `*.trace` - A trace file for every input
- `parsing_g.json` - The mined grammar

To generate inputs from a mined grammar, use:

```python
from cmimid.fuzz import LimitFuzzer
import json
import pathlib

WORKING_DIRECTORY = pathlib.Path("./output/json/trial-0/")

with open(WORKING_DIRECTORY / "parsing_g.json", "r") as f:
    grammar_file = json.load(f)
    grammar = grammar_file["[grammar]"]
    f = LimitFuzzer(grammar)

    for i in range(10):
        print(f.fuzz(grammar_file["[start]"]))
```

## Calculate precision and recall

Calculate precision and recall values using the eval inputs and the mined grammar

```sh
uv run src/eval/precision_recall.py --config ./example_programs/json/configuration/configuration.toml
```

## Run evaluation experiment in docker

Running a full evaluation can take multiple days. If you want to limit the number of evaluation targets, modify the `run_experiments.py` script.

```sh
docker build . -t gdbminer
docker run --rm  -v $( pwd)/output:/output/ gdbminer /run_experiment.sh
```

## Run multiple trials

```sh
# Start 50 trials
NO_TRIALS=50; for i in  $(seq 1 $NO_TRIALS); do docker run -d --rm  -v $( pwd)/output_$i:/output/ --name gdbminer_$i gdbminer /run_experiment.sh; done

# Average results and  calculate std deviation with Welfords algorithm
for miner in arvada treevada gdbminer mimid
do
    printf "\n$miner precision recall f1-score\n"
    for target in cgi_decode json mjs tinyc calc yxml  calcrs jsonrs calccpp  jsoncpp  xmlcpp
    do
        cat output_*/$target.*$miner.result | jq  .precision,.recall |xargs -n2 echo | awk -v target="$target" '{x1=$1;b1=a1+(x1-a1)/NR;q1+=(x1-a1)*(x1-b1);a1=b1; x2=$2;b2=a2+(x2-a2)/NR;q2+=(x2-a2)*(x2-b2);a2=b2} END {std1 = sqrt(q1/NR); std2 = sqrt(q2/NR); printf("%-10s: %0.2f:%0.2f \t\t| %0.2f:%0.2f \t\t| %0.2f\n", target, a1 * 100, std1 * 100, a2* 100, std2 * 100,  200 * (a1 * a2) / (a1+a2))  } '
    done
done
```

## Execute on new binary

GDBMiner relies on a valid stack layout at every point in execution, which is why the target binary
programs need to be build without optimizations. Also debug symbols are required to name non
terminals in the resulting grammar.

Unfortunately on C++ binaries the compiler generated symbol names are required. This leads to ugly
entrypoint names like
`_ZN8picojson5parseIPKcEET_RNS_5valueERKS3_S7_PNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE`
instead of just `picojson::parse<const_char_*>`

## Run on microcontrollers

See the [firmware overview](example_firmware/README.md) for supported boards and parser targets.
Board-specific wiring, configuration, build and run instructions are in the
[STM32 guide][stm32-setup] and [ESP32-C3 guide][c3-setup].

[stm32-setup]: example_firmware/STM32%20B-L4S5I-IOT01A.md
[c3-setup]: example_firmware/ESP32-C3%20DevKitM-1-N4X.md

## SVGPP

Install dependencies

```sh
sudo apt-get install libboost-all-dev cmake inkscape liblzma-dev
```

Download LibXML2 https://github.com/GNOME/libxml2 and compile statically with debug:

```sh
git clone https://github.com/GNOME/libxml2.git
cd libxml2
git checkout v2.12.4
mkdir build
cd build
cmake -D LIBXML2_WITH_ZLIB=OFF -D LIBXML2_WITH_LZMA=OFF  -DLIBXML2_WITH_ICONV=OFF -DLIBXML2_WITH_THREADS=OFF -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=Debug -DCMAKE_C_FLAGS="-O0" ..
make
sudo make install
sudo ldconfig
```

Tested in commit f460b2c7ceba92a875c0ba5c333826652863b396 from <https://github.com/svgpp/svgpp.git>
Compile SVGPP with the static LibXML2 library and debug:

```sh
cd example_programs/svgcpp/svgpp/src/demo/render/
mkdir build
cd build
cmake -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="-O0 -DDEBUG" ..
make
```

Translate SVGs into PDFs

```sh
inkscape --export-type=pdf --export-area-drawing --export-overwrite <file>.svg
```

Run in Docker Container

```sh
docker run --rm  -v $( pwd)/output:/output/ gdbminer python3 /GDBMiner/src/tracer/trace.py --config /example_programs/svgcpp/configuration_libxml.toml

docker run --rm  -v $( pwd)/output:/output/ gdbminer python3 /GDBMiner/src/miner/mine.py --config /example_programs/svgcpp/configuration_libxml.toml
```

## License

GDBMiner is open-sourced under the AGPL-3.0 license. See the [LICENSE](LICENSE) file for details.

For a list of other open source components included in PROJECT-NAME, see the file
[3rd-party-licenses.txt](3rd-party-licenses.txt).
