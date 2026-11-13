#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build/avr
avr-gcc -mmcu=atmega328p -DF_CPU=16000000UL -Os -Wall -Wextra -Werror \
  motion_logic.c motion_selftest.c avr_main.c -o build/avr/robot_motion.elf
avr-size build/avr/robot_motion.elf
set +e
timeout 20s simavr -m atmega328p -f 16000000 build/avr/robot_motion.elf > build/avr/simavr.log 2>&1
status=$?
set -e
cat build/avr/simavr.log
if [[ "$status" != 0 && "$status" != 124 ]]; then echo "Unexpected simavr exit: $status" >&2; exit 1; fi
grep -Fq 'AVR_MOTION_PASS' build/avr/simavr.log
if grep -Fq 'AVR_MOTION_FAIL' build/avr/simavr.log; then exit 1; fi
echo 'AVR_CPU_EMULATION_PASS'
