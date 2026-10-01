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

## Config file

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
ignore_functions_regex = '@plt|_vgr'
watchpoint_type = "(char*)"
watchpoint_count = 10000 # Positive number of available watchpoints.
timeout = 30 # GDB response timeout in seconds.
entrypoint = "json_parse" # Symbol name or quoted hexadecimal address.
exitpoint = "" # Empty means stop after leaving the entry function.
input_buffer = "my_string" # Symbol name or quoted hexadecimal address.

[LOGS]
log_level = "INFO" # DEBUG, INFO, WARNING, ERROR, or CRITICAL.
```

### MCU-specific settings

Shared debugger settings stay in `[GDB]`. Only the selected backend reads its MCU table: `[stm32]` or `[msp430]`. Desktop targets do not need either table. Both MCU backends use `[Connection]` for serial input.

For an STM32 target, set `GDB.instance = "stm32"`, update the binary, symbols and watchpoint count for your firmware, and add:

```toml
[stm32]
gdb_server_path = "st-util -p 4243"
gdb_server_address = ":4243"
dwt_function_reg = "0xe0001028" # Keep addresses as strings for GDB commands.
dwt_watchpoint_workaround = true # Defaults to true for ARMv7 DWT single-stepping.

[Connection]
input_channel = "serial"
port = "/dev/ttyACM0"
baud_rate = 9600
```

MSP430 uses a `[msp430]` table containing `gdb_server_path` and `gdb_server_address`; it does not read STM32's DWT settings.

### Migrating an existing INI file

Rename GDBMiner configs to `.toml`, quote strings (including empty values and addresses), and leave numbers and booleans unquoted. Move `gdb_server_path` and `gdb_server_address` from `[GDB]` into the selected MCU table; move `dwt_function_reg` and `dwt_watchpoint_workaround` into `[stm32]`. Update commands that pass `--config`. The old INI format is no longer supported; PlatformIO's `platformio.ini` files are unchanged.

The loader returns ordinary dictionaries rather than a config class or a global schema that would require every MCU's settings. Malformed TOML raises `TOMLDecodeError`, missing required keys raise `KeyError` when read, and invalid logging levels retain Python logging's `ValueError`. Values must use the types shown above; the loader does not coerce quoted numbers or strings such as `"false"`. Two checks prevent silent misbehaviour: tracing requires a positive integer `watchpoint_count`, and STM32 requires a boolean `dwt_watchpoint_workaround`.

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
