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
instance = "valgrind" # valgrind, stm32, or msp430
# Ignore function names matching this Python regular expression.
# Literal strings preserve backslashes without TOML escape sequences.
ignore_functions_regex = '@plt|_vgr*'
watchpoint_type = "(char*)"
watchpoint_count = 10000 # Positive number of available watchpoints.
timeout = 30 # GDB response timeout in seconds.
entrypoint = "json_parse" # Symbol name or quoted hexadecimal address.
input_buffer = "my_string" # Symbol name or quoted hexadecimal address.

[LOGS]
log_level = "INFO" # DEBUG, INFO, WARNING, ERROR, or CRITICAL.
```

### Shared fields

All configurations require these fields unless marked optional:

| Table | Field | Type and meaning |
| --- | --- | --- |
| `BASIC` | `seed_directory` | String, directory of seed inputs to trace. |
| `BASIC` | `output_directory` | String, parent of the generated `trial-N` directories. |
| `BASIC` | `binary_file` | String, target executable or firmware ELF with debug symbols. |
| `BASIC` | `eval_directory` | String, directory of inputs used to measure recall. |
| `GDB` | `gdb_path` | String, debugger command with optional arguments. Quote command paths containing spaces inside the TOML string. |
| `GDB` | `instance` | String, `"valgrind"`, `"stm32"`, or `"msp430"`. |
| `GDB` | `entrypoint` | String, symbol, source location, or quoted hexadecimal address where tracing starts. |
| `GDB` | `exitpoint` | Optional string. Omit or use `""` to stop after leaving the entry function; otherwise give a breakpoint location. |
| `GDB` | `input_buffer` | String, input buffer symbol or quoted hexadecimal address. |
| `GDB` | `watchpoint_type` | String, GDB pointer type used to read the input buffer, such as `"(char*)"`. |
| `GDB` | `watchpoint_count` | Positive integer, number of bytes watched per tracing pass. Use the hardware limit for MCUs. Valgrind can use a large count. |
| `GDB` | `timeout` | Positive finite number, GDB response timeout in seconds; fractions are allowed. |
| `GDB` | `ignore_functions_regex` | Optional string, Python regex for functions to skip; defaults to `""`. TOML literal strings preserve regex backslashes. |
| `LOGS` | `log_level` | String, Python logging level such as `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, or `"CRITICAL"`. |

`watchpoint_count = -1` is not supported. The tracer advances through the input by this count, so it must be positive.

### MCU settings

STM32 and MSP430 both require the following server fields in `[GDB]` and serial fields in `[Connection]`. Valgrind supplies input through a file and does not require these fields or a `[Connection]` table.

| Table | Field | Type and meaning |
| --- | --- | --- |
| `GDB` | `gdb_server_path` | String, server command and arguments, split using shell quoting rules. |
| `GDB` | `gdb_server_address` | String, GDB remote address, such as `":4242"`. |
| `Connection` | `input_channel` | String, `"serial"`. |
| `Connection` | `port` | String, serial device path. |
| `Connection` | `baud_rate` | Positive integer, serial baud rate. |
| `GDB.stm32` | `dwt_watchpoint_workaround` | Optional boolean, defaults to `true`. Read DWT registers while stepping on ARMv7 targets. |
| `GDB.stm32` | `dwt_function_reg` | String, quoted hexadecimal address of the first DWT comparator function register. Required when the workaround is enabled. |

For STM32, change `instance` to `"stm32"` and add the server fields to the existing `[GDB]` table:

```toml
# Inside the existing [GDB] table:
gdb_server_path = "st-util -p 4243"
gdb_server_address = ":4243"

[GDB.stm32]
dwt_function_reg = "0xe0001028"
dwt_watchpoint_workaround = true

[Connection]
input_channel = "serial"
port = "/dev/ttyACM0"
baud_rate = 9600
```

Choose the binary, symbols, register address and watchpoint count for your firmware and MCU. MSP430 uses `instance = "msp430"` with its server command and address in `[GDB]`. It needs no MCU subtable because it currently has no additional settings. Only the selected MCU's settings are validated and read.

### Migrating an existing INI file

Rename GDBMiner configs to `.toml`, quote strings and addresses, and leave numbers and booleans unquoted. Keep `gdb_server_path` and `gdb_server_address` in `[GDB]`. Move `dwt_function_reg` and `dwt_watchpoint_workaround` into `[GDB.stm32]`. Update commands that pass `--config`. The old INI format is no longer supported. PlatformIO's `platformio.ini` files are unchanged.

The loader uses ordinary dictionaries and checks shared fields plus the selected backend's fields before creating trial directories or starting a target. It does not coerce numbers or strings such as `"false"`. Malformed TOML raises `TOMLDecodeError`, missing required keys raise `KeyError`, wrong types raise `TypeError`, and invalid ranges or misplaced STM32 settings raise `ValueError`. The loader also validates log levels through Python logging before creating a trial directory, preserving logging's own `ValueError` message.

`scripts/repro_json.sh` writes TOML using a Bash heredoc with literal strings. Its `OUT_DIR` supports spaces, double quotes, backslashes and UTF-8 text, but must not contain apostrophes or newlines.

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

## GDBMiner on STM32 B-L4S5I-IOT01A board

In this case the B-L4S5I-IOT01A and its on-board debugger are used. This on-board debugger sets up
a GDB server via the 'st-util' program, and enables access to this GDB server via localhost:4242.

- Install the STLINK driver [link](https://www.st.com/content/st_com/en/products/development-tools/software-development-tools/stm32-software-development-tools/stm32-utilities/stsw-link009.html)
- Connect MCU board and PC via USB (on MCU board, connect to the USB connector that is labeled as 'USB STLINK')

```sh
sudo apt-get install stlink-tools gdb-multiarch libusb-dev
```

Build and flash a firmware for the STM32 B-L4S5I-IOT01A, for example the arduinojson project.

Prerequisite: Install [platformio (pio)](https://docs.platformio.org/en/latest//core/installation.html#super-quick-mac-linux)

```sh
cd ./example_firmware/stm32_arduinojson/
pio run --target upload
```

If a `LIBUSB_ERROR_ACCESS` occurs, put

```sh
# STLink v2
ATTRS{idVendor}=="0483", ATTRS{idProduct}=="374b", MODE="664", GROUP="plugdev"
```

into `/etc/udev/rules.d/90-stm32.rules`and run `sudo udevadm control --reload` to reload. Ensure that your user belongs to the `plugdev`group.

For your info: platformio stored an .elf file of the SUT here: ./example_firmware/stm32_arduinojson/.pio/build/disco_l4s5i_iot01a/firmware.elf

Check the config at `./example_firmware/stm32_arduinojson/configuration/configuration.toml` and start tracing and mining:

```sh
uv run src/tracer/trace.py --config ./example_firmware/stm32_arduinojson/configuration/configuration.toml

uv run src/miner/mine.py --config ./example_firmware/stm32_arduinojson/configuration/configuration.toml
```

## GDBMiner on the ESP32-C3 DevKitM-1-N4X board

Ports of the three STM32 examples (`esp32-c3_json`, `esp32-c3_cgidecode`, `esp32-c3_xml`) run on
an ESP32-C3. For the wiring, build, debugger and run commands, see
[`example_firmware/ESP32-C3 DevKitM-1-N4X.README.md`](example_firmware/ESP32-C3%20DevKitM-1-N4X.README.md).

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
