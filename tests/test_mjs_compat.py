"""Check the libc bridge independently of the downloaded benchmark source."""

import shutil
import signal
import subprocess
from pathlib import Path

import pytest

HEADER = Path(__file__).resolve().parents[1] / "example_firmware/esp32-c3_mjs/src/cmimid_compat.h"


def compile_check(tmp_path: Path, code: str) -> Path:
    cc = shutil.which("cc")
    if cc is None:
        pytest.skip("A C compiler is required for the mJS libc compatibility checks")
    binary = tmp_path / "check"
    subprocess.run(
        [
            cc,
            "-std=c11",
            "-DNDEBUG",
            "-include",
            str(HEADER),
            "-x",
            "c",
            "-",
            "-lm",
            "-o",
            str(binary),
        ],
        input=code,
        text=True,
        capture_output=True,
        check=True,
    )
    return binary


def test_ctype_matches_c_locale_and_signed_byte_indices(tmp_path: Path):
    binary = compile_check(
        tmp_path,
        r"""
int main(void) {
    const unsigned short *table = *cmimid_ctype_b_loc();
    for (int c = -128; c <= 255; c++) {
        unsigned char u = (unsigned char)c;
        int alnum = (u >= '0' && u <= '9') || (u >= 'a' && u <= 'z') || (u >= 'A' && u <= 'Z');
        int xdigit = (u >= '0' && u <= '9') || (u >= 'a' && u <= 'f') || (u >= 'A' && u <= 'F');
        int space = u == ' ' || (u >= '\t' && u <= '\r');
        int print = u >= ' ' && u <= '~';
        unsigned short expected = c == EOF ? 0 :
            (alnum ? 0x0008 : 0) | (xdigit ? 0x1000 : 0) |
            (space ? 0x2000 : 0) | (print ? 0x4000 : 0);
        if (table[c] != expected) return 1;
#ifdef __GLIBC__
        if (table[c] != ((*__ctype_b_loc())[c] & 0x7008)) return 2;
#endif
    }
    return 0;
}
""",
    )
    subprocess.run([binary], check=True)


def test_expanded_assertions_still_abort_with_ndebug(tmp_path: Path):
    binary = compile_check(
        tmp_path,
        r"""
int main(void) { cmimid_assert_fail("kept", "benchmark.c", 12, "parser"); }
""",
    )
    result = subprocess.run([binary], capture_output=True, text=True, check=False)
    assert result.returncode == -signal.SIGABRT
    assert "Assertion `kept' failed" in result.stderr
