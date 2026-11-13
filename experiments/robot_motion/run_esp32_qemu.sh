#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build/esp32
set +e
timeout 840s docker run --rm -v "$PWD":/workspace -w /workspace/esp32_idf \
  -e IDF_GIT_SAFE_DIR=/workspace espressif/idf:v5.4 \
  bash -c 'idf.py set-target esp32 && idf.py build && timeout 100s idf.py qemu' \
  > build/esp32/qemu.log 2>&1
status=$?
set -e
tail -n 120 build/esp32/qemu.log
if [[ "$status" != 0 && "$status" != 124 ]]; then echo "ESP32 compile/QEMU exited unexpectedly: $status" >&2; exit 1; fi
grep -Fq 'ESP32_MOTION_PASS' build/esp32/qemu.log
grep -Fq 'ESP32_FREERTOS_WATCHDOG_PASS' build/esp32/qemu.log
if grep -Fq 'ESP32_MOTION_FAIL' build/esp32/qemu.log; then exit 1; fi
if grep -Fq 'ESP32_FREERTOS_WATCHDOG_FAIL' build/esp32/qemu.log; then exit 1; fi
echo 'ESP32_QEMU_CPU_EMULATION_PASS'
