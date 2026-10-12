# Arduino CLI setup

The ESP32-C3 and ESP32-S3 firmware examples share the Arduino CLI toolchain and parser-library
versions below. Install each library once per Arduino CLI user environment, not once per board.
If you use separate CLI configurations or user directories, install the libraries in each one.
The STM32 examples use PlatformIO and declare their dependencies in `platformio.ini` instead.

Board options, build paths and upload ports differ. After setup, follow the
[C3 build guide](ESP32-C3%20DevKitM-1-N4X.md#build-and-upload) or the
[S3 build guide](ESP32-S3-Zero.md#build-and-upload).

## Toolchain

Use [Arduino CLI 1.5.1](https://github.com/arduino/arduino-cli/releases/tag/v1.5.1) and Espressif's
official Arduino-ESP32 distribution. Install the core before building:

```sh
arduino-cli core update-index \
  --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.12 \
  --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core list
```

Confirm core 3.3.12 before building. The official package index selects matching compiler and
runtime versions for both boards.

## Parser libraries

Install only the library for the parser you want to build, or all three if you use all targets.
These exact versions are the base versions declared by the STM32 references' PlatformIO ranges:
`^0.2.0` for `stm32_arduinojson`, `^2.0.1` for `stm32_cgidecode`, and `^1.0.2` for
`stm32_libyxml`. The commands are identical for the C3 and S3.

### JSON

```sh
arduino-cli lib install 'Arduino_JSON@0.2.0'
```

### CGI

```sh
arduino-cli lib install 'percent_encode@2.0.1'
```

### XML

```sh
arduino-cli lib install 'LibYxml@1.0.2'
```

### Verify installed versions

```sh
arduino-cli lib list
```

Confirm the selected library's version matches the pin above before building. `lib list` only
lists installed libraries; it does not install them.

## Apple Silicon host prerequisite

Arduino CLI 1.5.1 installs an Intel-only `ctags` 5.8-arduino11
([upstream issue](https://github.com/arduino/ctags/issues/20)). On a Mac without Rosetta, compile
the same unmodified upstream release natively:

```sh
curl -fL -o /tmp/arduino-ctags.tar.xz \
  https://github.com/arduino/ctags/releases/download/5.8-arduino11/ctags-5.8-arduino11.tar.xz
PREFIX="$HOME/.local/opt/arduino-ctags/5.8-arduino11"
mkdir -p "$PREFIX/source"
tar -xf /tmp/arduino-ctags.tar.xz -C "$PREFIX/source" --strip-components=1
(cd "$PREFIX/source" && ./configure --prefix="$PREFIX" && \
  make -j4 CFLAGS='-O2 -include dirent.h' && make install)
```

Pre-including the system header avoids the old `ctags` `__unused__` macro colliding with the
current macOS SDK header. No ctags source or installed Arduino package is patched. The board
build commands select this native executable with `runtime.tools.ctags.path`; omit that build
property on hosts where the packaged executable works.

## Upstream sources

- [Arduino-ESP32 3.3.12](https://github.com/espressif/arduino-esp32/releases/tag/3.3.12)
- [Official installation instructions](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html)
- [Official package index](https://espressif.github.io/arduino-esp32/package_esp32_index.json)
