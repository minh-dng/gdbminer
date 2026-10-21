// ESP32-S3 port of example_firmware/stm32_cgidecode/src/main.cpp (from esp32-c3_cgidecode).
// Same percent_encode parser, acceptance rule and serial protocol.
// Copyright (c) 2022 Robert Bosch GmbH
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU Affero General Public License as published
// by the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Affero General Public License for more details.
//
// You should have received a copy of the GNU Affero General Public License
// along with this program.  If not, see <https://www.gnu.org/licenses/>.

#include "Arduino.h"

constexpr uint8_t STATUS_LED_PIN = 21; // Waveshare ESP32-S3-Zero WS2812, not generic RGB_BUILTIN.
// Update only outside the parser: no RMT calls or LED delays in the traced region.
// (Line kept so the following lines keep their numbers.)


#define FUZZ_INPUT_SIZE 2048
char buf[FUZZ_INPUT_SIZE + 1]; // One extra byte for the terminating NUL.
size_t input_len = 0;
// The last result stays visible while waiting for the next packet.




#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int hex_values[256];

void init_hex_values() {
  for (int i = 0; i < sizeof(hex_values) / sizeof(int); i++) {
    hex_values[i] = -1;
  }
  hex_values['0'] = 0;
  hex_values['1'] = 1;
  hex_values['2'] = 2;
  hex_values['3'] = 3;
  hex_values['4'] = 4;
  hex_values['5'] = 5;
  hex_values['6'] = 6;
  hex_values['7'] = 7;
  hex_values['8'] = 8;
  hex_values['9'] = 9;

  hex_values['a'] = 10;
  hex_values['b'] = 11;
  hex_values['c'] = 12;
  hex_values['d'] = 13;
  hex_values['e'] = 14;
  hex_values['f'] = 15;

  hex_values['A'] = 10;
  hex_values['B'] = 11;
  hex_values['C'] = 12;
  hex_values['D'] = 13;
  hex_values['E'] = 14;
  hex_values['F'] = 15;
}

int cgi_decode(char *s, char *t) {
  while (*s != '\0') {
    if (*s == '+') {
      *t++ = ' ';
    } else if (*s == '%') {
      int digit_high = *++s;
      int digit_low = *++s;
      if (hex_values[digit_high] >= 0 && hex_values[digit_low] >= 0) {
        *t++ = hex_values[digit_high] * 16 + hex_values[digit_low];
      } else {
        return -1;
      }
    } else {
      *t++ = *s;
    }
    s++;
  }
  *t = '\0';
  return 0;
}

void strip_input(char *my_string) {
  int read = strlen(my_string);
  if (my_string[read - 1] == '\n') {
    my_string[read - 1] = '\0';
  }
}

void setup() {
    rgbLedWrite(STATUS_LED_PIN, 0, 0, 16); // Blue: booted, waiting for the first input.
    // The Arduino core provides the WS2812 driver; no additional library is needed.
    Serial.begin(9600);
    init_hex_values();
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

// This example program reads data from serial and parses it as cgi encoded string.
// Copyright (c) 2023 Robert Bosch GmbH
// SPDX-License-Identifier: AGPL-3.0

#include <arduino_percent.hpp>

int parser(char *input, size_t input_size) {
  
  char result[FUZZ_INPUT_SIZE + 1]; // Decoded bytes plus the terminating NUL.

  //strip_input(input);
  //int ret = cgi_decode(input, result);

  percent::decode(input, result);

  int ret = 0;
  for( int i = 0; result[i] != 0; i++) {
    if (result[i] > 127) {
      ret = -1;
      break;
    }

  }

  return ret;
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
    int ret = parser(buf, (size_t)response_length);
    rgbLedWrite(STATUS_LED_PIN, ret == 0 ? 0 : 16, ret == 0 ? 16 : 0, 0); // Green/red: accept/reject.

    // Send result if parsing was successfully or not
    serial_write_byte((uint8_t)ret);
}
