// Standalone hardware-validation firmware, never linked into a parser target.
// Volatile ordinary reads/stores keep the diagnostic accesses in the executable.
#include <Arduino.h>

alignas(4) uint8_t buf[16];
volatile uint32_t result;

extern "C" __attribute__((noinline)) uint8_t nested_read(volatile uint8_t *p) {
    return *p;
}

extern "C" __attribute__((noinline)) uint32_t byte_fixture(volatile uint8_t *p) {
    uint32_t value = p[0] + p[0];
    for (size_t i = 1; i < 8; ++i) {
        value += nested_read(p + i);
    }
    p[2] = 90;  // Must not generate an extra read event.
    if (value & 1) {
        value += 3;
    }
    return value + p[8];  // Read in the partial window immediately before return.
}

extern "C" __attribute__((noinline)) uint32_t word_fixture(volatile uint8_t *p) {
    return *reinterpret_cast<volatile uint32_t *>(p);
}

extern "C" __attribute__((noinline)) uint32_t unaligned_fixture(volatile uint8_t *p) {
    uint32_t value;
    // Explicit machine access, not an undefined misaligned C++ dereference.
    asm volatile("lw %0, 1(%1)" : "=r"(value) : "r"(p) : "memory");
    return value;
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
    if (size != 9) {
        uint8_t discard;
        while (size--) {
            read_bytes(&discard, 1);
        }
        Serial.write((uint8_t)0xff);
        return;
    }
    read_bytes(buf, 9);
    result = byte_fixture(buf);
    result = word_fixture(buf);
    result = unaligned_fixture(buf);
    Serial.write((uint8_t)0);
    Serial.flush();
}
