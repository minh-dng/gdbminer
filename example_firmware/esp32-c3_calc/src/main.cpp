// Serial protocol shared with esp32-c3_json; parser comes from the desktop calc target.
// src/calc.c links to the desktop example_programs/calc/calc.c from fetch_example_programs.sh.
// Copyright (c) 2023 Robert Bosch GmbH
// SPDX-License-Identifier: AGPL-3.0

#include "Arduino.h"
#include <setjmp.h>

extern "C" {
extern jmp_buf env;
void strip_input(char *my_string);
int rdp_parse_expression(const char *exp, int *result);
}

// The desktop main() without its file input; its exit statuses become -1.
int parser(char *input) {
    if (input[0] == '\0') {
        return -1; // The desktop exits before strip_input() on an empty file.
    }
    strip_input(input);
    int res = 0;
    if (setjmp(env)) {
        return -1;
    }
    return rdp_parse_expression(input, &res);
}

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
    int res = parser((char*)buf);
    serial_write_byte((uint8_t)res);
}
