#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build/host
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic \
  motion_logic.c motion_selftest.c host_main.c -o build/host/robot_motion
./build/host/robot_motion | tee build/host/result.log
grep -Fxq HOST_MOTION_PASS build/host/result.log
