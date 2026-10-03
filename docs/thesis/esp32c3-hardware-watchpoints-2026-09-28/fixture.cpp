// Standalone validation target, NOT linked into any parser firmware.
// No input tracking/logging instrumentation: only ordinary volatile test accesses.
#include <Arduino.h>

alignas(4) uint8_t buf[8];
volatile uint32_t result;

extern "C" __attribute__((noinline)) uint8_t nested_read(volatile uint8_t *p) {
    return *p;
}

extern "C" __attribute__((noinline)) uint32_t byte_fixture(volatile uint8_t *p) {
    uint32_t a = p[0];
    a += p[0];
    a += nested_read(p + 1);
    p[2] = 90;  // A read-only trigger must not report this store.
    if (a & 1) {
        a += 3;
    }
    return a + p[3];  // Last read immediately before return.
}

extern "C" __attribute__((noinline)) uint32_t word_fixture(volatile uint8_t *p) {
    return *reinterpret_cast<volatile uint32_t *>(p);
}

void read_bytes(uint8_t *p, size_t count) {
    for (size_t i = 0; i < count; ++i) {
        while (!Serial.available()) {
            delay(1);
        }
        p[i] = Serial.read();
    }
}

void setup() {
    Serial.begin(115200);
}

void loop() {
    Serial.write((uint8_t)0xa5);
    Serial.flush();
    uint32_t size;
    read_bytes(reinterpret_cast<uint8_t *>(&size), 4);
    if (size != 4) {
        uint8_t discard;
        while (size--) {
            read_bytes(&discard, 1);
        }
        Serial.write((uint8_t)0xff);
        return;
    }
    read_bytes(buf, 4);
    result = byte_fixture(buf);
    result = word_fixture(buf);
    Serial.write((uint8_t)0);
    Serial.flush();
}
