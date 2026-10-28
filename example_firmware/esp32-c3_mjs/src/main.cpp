// Paper-compatible packets received through Arduino's native serial API.
// SPDX-License-Identifier: GPL-2.0-only

#include <Arduino.h>

extern "C" int parser(const char *input, size_t length);

constexpr size_t input_capacity = 2048;
char buf[input_capacity + 1];

void setup() {
    Serial.begin(9600);
}

// Native USB (`HWCDC`) skips the flush, as in the calc target (issue #60): `HWCDC::flush` can
// discard the queued ready byte that follows a result. `write` alone queues it for the interrupt.
void send(uint8_t value) {
    Serial.write(value);
#if !(ARDUINO_USB_MODE && ARDUINO_USB_CDC_ON_BOOT)
    Serial.flush();
#endif
}

void receive(char *destination, size_t remaining) {
    while (remaining != 0) {
        size_t received = Serial.readBytes(destination, remaining);
        destination += received;
        remaining -= received;
    }
}

void loop() {
    send('A');
    uint32_t length;
    receive(reinterpret_cast<char *>(&length), sizeof(length));
    // Reuse buf to consume every packet, including rejected oversized payloads.
    for (uint32_t remaining = length; remaining != 0;) {
        size_t chunk = remaining < input_capacity ? remaining : input_capacity;
        receive(buf, chunk);
        remaining -= chunk;
    }
    int result = -1;
    if (length <= input_capacity) {
        buf[length] = 0;
        result = parser(buf, length);
    }
    send(static_cast<uint8_t>(result));
}
