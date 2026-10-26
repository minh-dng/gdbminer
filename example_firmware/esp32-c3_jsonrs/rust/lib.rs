// Firmware entry point for the desktop jsonrs parser (tinyjson) on the ESP32-C3.
// SPDX-License-Identifier: AGPL-3.0
//
// The desktop json.rs is included unchanged apart from its std-only main(). Every `std::` path in
// it resolves to the `std` module below, which re-exports core and alloc, so the parser code that
// is traced is the code of the desktop target.

#![no_std]

#[macro_use]
extern crate alloc;

use core::alloc::{GlobalAlloc, Layout};
use core::str::FromStr;

/// The subset of std that json.rs uses.
mod std {
    pub use core::{char, convert, error, fmt, iter, ops, str};

    pub mod collections {
        // json.rs only needs insertion, lookup and iteration, which BTreeMap also offers; core
        // has no hash map. Key order does not change which inputs are accepted.
        pub use alloc::collections::BTreeMap as HashMap;
    }

    pub mod io {
        use alloc::string::String;
        use alloc::vec::Vec;
        use core::fmt;

        #[derive(Debug)]
        pub enum ErrorKind {
            Other,
        }

        #[derive(Debug)]
        pub struct Error(String);

        impl Error {
            pub fn new(_kind: ErrorKind, msg: &str) -> Self {
                Error(String::from(msg))
            }
        }

        impl fmt::Display for Error {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str(&self.0)
            }
        }

        pub type Result<T> = core::result::Result<T, Error>;

        pub trait Write {
            fn write_all(&mut self, buf: &[u8]) -> Result<()>;

            fn write_fmt(&mut self, args: fmt::Arguments<'_>) -> Result<()> {
                struct Adapter<'a, W: ?Sized>(&'a mut W, Option<Error>);
                impl<W: Write + ?Sized> fmt::Write for Adapter<'_, W> {
                    fn write_str(&mut self, s: &str) -> fmt::Result {
                        self.0.write_all(s.as_bytes()).map_err(|e| {
                            self.1 = Some(e);
                            fmt::Error
                        })
                    }
                }
                let mut adapter = Adapter(self, None);
                match fmt::write(&mut adapter, args) {
                    Ok(()) => Ok(()),
                    Err(_) => Err(adapter.1.unwrap_or(Error(String::from("formatter error")))),
                }
            }
        }

        impl Write for Vec<u8> {
            fn write_all(&mut self, buf: &[u8]) -> Result<()> {
                self.extend_from_slice(buf);
                Ok(())
            }
        }

        impl<W: Write + ?Sized> Write for &mut W {
            fn write_all(&mut self, buf: &[u8]) -> Result<()> {
                (**self).write_all(buf)
            }
        }
    }
}

#[allow(dead_code, unused_imports)]
mod json {
    use super::std;
    use alloc::borrow::ToOwned;
    use alloc::boxed::Box;
    use alloc::string::{String, ToString};
    use alloc::vec::Vec;

    include!("../../../example_programs/jsonrs/json.rs");
}

/// Newlib's heap, the one the rest of the Arduino firmware uses.
struct CHeap;

extern "C" {
    fn memalign(alignment: usize, size: usize) -> *mut u8;
    fn free(ptr: *mut u8);
    fn abort() -> !;
}

unsafe impl GlobalAlloc for CHeap {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        // malloc aligns to 4 bytes on ESP-IDF, but JsonValue holds an f64.
        memalign(layout.align(), layout.size())
    }

    unsafe fn dealloc(&self, ptr: *mut u8, _layout: Layout) {
        free(ptr)
    }
}

#[global_allocator]
static HEAP: CHeap = CHeap;

#[panic_handler]
fn panic(_info: &core::panic::PanicInfo) -> ! {
    unsafe { abort() }
}

/// The desktop read_to_string() check: whether the input is UTF-8. It runs before the traced entry
/// point, as the desktop checks the file before it parses, so its reads of the input are not traced.
/// The desktop accepts input that is not UTF-8: read_to_string() fails and main() still exits with
/// status 0.
#[no_mangle]
pub extern "C" fn utf8_valid(data: *const u8, length: usize) -> bool {
    core::str::from_utf8(unsafe { core::slice::from_raw_parts(data, length) }).is_ok()
}

/// The desktop main() on UTF-8 input: 0 when it exits normally, -1 when it would panic.
///
/// The desktop untyped_example() panics on a parse error or an unprintable number; here those
/// become -1 so the firmware can answer instead of aborting. Any other panic aborts the firmware.
///
/// # Safety
/// `data` must be `length` bytes of UTF-8, as checked by `utf8_valid`.
#[no_mangle]
pub unsafe extern "C" fn jsonrs_parse(data: *const u8, length: usize) -> i32 {
    let data = core::str::from_utf8_unchecked(core::slice::from_raw_parts(data, length));
    match json::JsonValue::from_str(data) {
        Ok(value) => match value.stringify() {
            Ok(_) => 0,
            Err(_) => -1,
        },
        Err(_) => -1,
    }
}
