// Serial protocol shared with esp32-c3_json; the parser is the desktop jsonrs one, built from Rust.
// build/libjsonrs.a comes from rust/lib.rs, which includes example_programs/jsonrs/json.rs.
// SPDX-License-Identifier: AGPL-3.0

#include "Arduino.h"

extern "C" int jsonrs_parse(const uint8_t *data, size_t length);

int parser(char *input, size_t length) {
    return jsonrs_parse((const uint8_t *)input, length);
}

// Parsing is recursive and the parser runs in Arduino's loop task, so give it more than the default
// 8 KiB stack, as the calc target does.
SET_LOOP_TASK_STACK_SIZE(32 * 1024);

#ifndef LED_BUILTIN
#define LED_BUILTIN 8
#endif

#define FUZZ_INPUT_SIZE 2048
uint8_t buf[FUZZ_INPUT_SIZE + 1]; // One extra byte for the terminating NUL.
int led_state = 0;

void setup() {
    pinMode(LED_BUILTIN, OUTPUT);
    digitalWrite(LED_BUILTIN, HIGH);
    Serial.begin(9600);
}

// Native USB (`HWCDC`) skips the flush: `write` queues the byte and the driver's interrupt sends it
// once the host has collected the previous packet. `HWCDC::flush` discards the queue instead when
// the driver sees no connection or the TX ring stays unchanged for 100 one-millisecond checks. The
// ready byte follows a result at once, so it can still be in the queue that such a flush discards.
void serial_write_byte(uint8_t value) {
    Serial.write(value);
#if !(ARDUINO_USB_MODE && ARDUINO_USB_CDC_ON_BOOT) // The condition for `HWCDC` in HWCDC.h.
    Serial.flush();
#endif
}

void serial_read_bytes(uint8_t *buf, size_t length) {
    size_t bytes_read = 0;
    while (bytes_read < length) {
        if (!Serial.available()) {
            delay(1); // Yield to the ESP32 runtime while waiting for input.
            continue;
        }
        char byte = Serial.read();
        buf[bytes_read] = byte;
        bytes_read += 1;
    }
}

void loop() {
    if (led_state == 0) {
        digitalWrite(LED_BUILTIN, HIGH);
        led_state = 1;
    } else {
        digitalWrite(LED_BUILTIN, LOW);
        led_state = 0;
    }

    serial_write_byte('A');

    uint32_t response_length = 0;
    serial_read_bytes((uint8_t*)&response_length, 4);
    if (response_length > FUZZ_INPUT_SIZE) {
        // Reject oversized packets without overflowing or losing packet alignment.
        uint8_t discard[64];
        while (response_length > 0) {
            size_t chunk = response_length < sizeof(discard) ? response_length : sizeof(discard);
            serial_read_bytes(discard, chunk);
            response_length -= chunk;
        }
        serial_write_byte(0xff);
        return;
    }

    serial_read_bytes(buf, response_length);
    buf[response_length] = 0;
    int res = parser((char*)buf, response_length);
    serial_write_byte((uint8_t)res);
}
