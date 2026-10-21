// ESP32-S3 port of stm32_libyxml/src/main.ino; lines 1-54 keep their numbers.
// Copyright (c) 2023 Robert Bosch GmbH
// SPDX-License-Identifier: AGPL-3.0

#include "Arduino.h"

constexpr uint8_t STATUS_LED_PIN = 21; // Waveshare ESP32-S3-Zero WS2812, not generic RGB_BUILTIN.
// Update only outside the parser: no RMT calls or LED delays in the traced region.
// Keep these lines so XML's source-line breakpoints remain unchanged.

#define FUZZ_INPUT_SIZE 2048
char buf[FUZZ_INPUT_SIZE + 1]; // One extra byte for the terminating NUL.
size_t input_len = 0;
// The last result stays visible while waiting for the next packet.


void setup()
{
    rgbLedWrite(STATUS_LED_PIN, 0, 0, 16); // Blue: booted, waiting for the first input.
    // The Arduino core provides the WS2812 driver; no additional library is needed.
    Serial.begin(9600); 
}

void serial_read_bytes(uint8_t *buf, size_t length) {
    size_t bytes_read = 0;

    while (bytes_read < length) {
        if (!Serial.available()) { delay(1); continue; } // Yield to the ESP32 runtime.
        char byte = Serial.read();
        buf[bytes_read] = byte;
        bytes_read += 1;
    }
}



#include <yxml.h>

uint8_t xmlbuf[4096];

int parser(uint8_t *input, size_t input_size)
{
    yxml_t x;
    int ret_val = 0;
    yxml_init(&x, xmlbuf, 4096);
    for (int i = 0; i < input_size; i++) {
        yxml_ret_t ret = yxml_parse(&x, input[i]);
        if (ret < 0) {
            ret_val = -1;
            break;
        }
    }
    return ret_val;
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

void loop() {
    // Do not overwrite the previous result while waiting for a new input.

    // Notify that we request a new input
    serial_write_byte('A');

    uint32_t response_length = 0;
    serial_read_bytes((uint8_t*)&response_length, 4);
    rgbLedWrite(STATUS_LED_PIN, 16, 8, 0); // Amber: receiving the payload.

    if (response_length > FUZZ_INPUT_SIZE) {
        rgbLedWrite(STATUS_LED_PIN, 16, 0, 16); // Magenta: oversized packet, draining.
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
    //socket_read_bytes(connection_fd, (void *)buf, response_length);
    serial_read_bytes((uint8_t*)buf, (size_t)response_length);
    buf[response_length] = 0; //nullify string
    rgbLedWrite(STATUS_LED_PIN, 0, 16, 16); // Cyan: parsing (also while halted in GDB).
    int ret = parser((uint8_t*) buf, (size_t)response_length);
    rgbLedWrite(STATUS_LED_PIN, ret == 0 ? 0 : 16, ret == 0 ? 16 : 0, 0); // Green/red: accept/reject.
    // Send result if parsing was successfully or not
    serial_write_byte((uint8_t)ret);
}



