#include <avr/io.h>
#include <stdint.h>
#include "motion_logic.h"
/* Arduino Nano ATmega328P, 16MHz UART TX; motor GPIO deliberately unused. */
static void serial_init(void) {
    UBRR0H=0; UBRR0L=103; UCSR0B=(1U<<TXEN0);
    UCSR0C=(1U<<UCSZ01)|(1U<<UCSZ00);
}
static void putc_uart(char c) { while (!(UCSR0A & (1U<<UDRE0))) {} UDR0=(uint8_t)c; }
static void puts_uart(const char *p) { while (*p) putc_uart(*p++); }
int main(void) {
    serial_init();
    if (motion_selftest()==0) puts_uart("AVR_MOTION_PASS\n");
    else puts_uart("AVR_MOTION_FAIL\n");
    for (;;) {}
}
