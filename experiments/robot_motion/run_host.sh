#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build/host
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic \
  -fsanitize=undefined -fno-sanitize-recover=all \
  motion_logic.c motion_selftest.c motion_fault_sweep.c host_main.c \
  -o build/host/robot_motion
./build/host/robot_motion | tee build/host/result.log
grep -Fxq HOST_MOTION_PASS build/host/result.log
grep -Fxq HOST_MOTION_SWEEP_PASS build/host/result.log
# Negative-control test: deliberately remove E-stop detection from the
# disposable copy and demand that the unchanged adversarial tests reject it.
python3 - <<'PY'
from pathlib import Path
src=Path('motion_logic.c').read_text()
needle='if (estop) { trip(s,MOTION_ESTOP); return 0; }'
assert src.count(needle)==1, "canary patch target changed"
Path('build/host/mutated_motion_logic.c').write_text(
    src.replace(needle,'if (estop) { /* intentionally broken test canary */ }'))
PY
cc -I. -std=c11 -O2 -Wall -Wextra -Werror -pedantic \
  -fsanitize=undefined -fno-sanitize-recover=all \
  build/host/mutated_motion_logic.c motion_selftest.c motion_fault_sweep.c host_main.c \
  -o build/host/mutated_motion
set +e
./build/host/mutated_motion > build/host/canary.log 2>&1
status=$?
set -e
cat build/host/canary.log
if [[ "$status" -eq 0 ]]; then
  echo 'MOTION_MUTATION_CANARY_FAIL: broken E-stop passed' >&2
  exit 1
fi
grep -Fq 'HOST_MOTION_FAIL' build/host/canary.log
echo 'MOTION_MUTATION_CANARY_PASS: independent selftest rejected broken E-stop'
