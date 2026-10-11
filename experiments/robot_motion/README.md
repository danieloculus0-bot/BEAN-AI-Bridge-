# BEAN Robot Motion — cross-platform failure-injection laboratory

**Experimental Bridge PR #32, not merged to Core, not physical motor control.** This is a research prototype for the logical state machine that could later sit behind a separately reviewed motor driver. No motor GPIO, power electronics, physical E-stop or external motors are connected to these tests.

## What the revised controller can do

One C state machine (`motion_logic.c/.h`) runs on a native Linux host, real AVR instructions inside simavr (Arduino Nano ATmega328P), and ESP32 firmware under Espressif QEMU. That means the same input rules are tested on multiple CPU targets, not merely reimplemented as Python mockups.

- **Explicit arming:** after initialization or a fault reset, output is *disarmed* until a separate `motion_arm` call confirms healthy interlocks.
- **Live interlocks:** `motion_tick` checks emergency stop, communication link and encoder condition on **every invoked tick**, even with no new command. A rejected reset with unhealthy inputs also zeros output.
- **Command anti-replay:** each PWM command carries a strictly increasing, nonzero `uint32_t` sequence. Duplicate/older sequences latch a fault and stop. Fault reset retains the previous sequence.
- **Logical deadman:** a nonzero PWM command requires a finite TTL no longer than 100 ticks; missing refresh reaches `MOTION_TIMEOUT`, zeros commanded output and disarms. **Ticks are logical, not guaranteed milliseconds**.
- **Reversal interlock:** an attempted direction reversal forces zero output; a later, newer command is needed to move in reverse.
- **Strict inputs:** nonboolean interlock values, invalid PWM or TTL, unsequenced commands and nonzero TTL for zero PWM fail closed.
- **Recovery protocol:** faults stay latched until an explicit healthy reset, and reset alone is not authorization to move.

The common adversarial C selftest runs **on host, AVR and ESP32**. The host job also executes **6,144 deterministic fault-injection state transitions** and UBSan for C undefined behavior. A disposable negative-control build intentionally disables E-stop recognition and must be **rejected** by the same selftest (the mutation is never shipped or executed on MCUs). This proves the test detects at least that particular important regression, not general fault completeness.

ESP32 QEMU has an additional FreeRTOS test: actual `vTaskDelay` calls separate logical ticks, which must expire the watchdog and subsequently stop motion on a simulated E-stop. This is *not* a guarantee a future production host will call motion_tick on time, and no preemptive timer interrupt or real feedback reader has been installed.

## Run and inspect

[CI workflow](../../.github/workflows/bean-robot-motion-emulators.yml) builds each emulator independently, captures UART or native logs, and checks:

| Lane | Required machine-produced evidence | Meaning |
| --- | --- | --- |
| Native C + UBSan | `HOST_MOTION_PASS`, `HOST_MOTION_SWEEP_PASS`, `MOTION_MUTATION_CANARY_PASS` | Same C rules + fault sweep + seeded negative control |
| Arduino Nano/simavr | `AVR_MOTION_PASS`, `AVR_CPU_EMULATION_PASS` | Actual ATmega328P firmware instruction execution |
| ESP32 IDF/QEMU | `ESP32_MOTION_PASS`, `ESP32_FREERTOS_WATCHDOG_PASS`, `ESP32_QEMU_CPU_EMULATION_PASS` | Actual ESP32 QEMU execution plus bounded FreeRTOS scheduling checks |
| Wokwi (optional) | `ESP32_MOTION_PASS` when a token is configured, otherwise `NOT_RUN_MISSING_TOKEN` and `pass:false` | Never count missing token as an emulation pass |

Local (with toolchains installed): `bash experiments/robot_motion/run_host.sh`, `bash experiments/robot_motion/run_avr.sh` and `bash experiments/robot_motion/run_esp32_qemu.sh` (Docker).

**Test-status rule:** only mark a lane passed when its own fresh job includes the correct evidence marker. A green top-level workflow may contain an intentionally skipped Wokwi job. Earlier CI runs are historical until retested against the newest commit.

## Remaining physical-readiness weaknesses (not solved by emulator green)

1. **No real GPIO, encoders, driver PWM, E-stop wiring or independent hardware power removal.** Logical `pwm=0` cannot prove power is removed from a motor.
2. **The logical tick is manually invoked** by test harnesses. No measured scheduling deadline, missed-interrupt detection, interrupt-safe state management or physical timebase guarantee.
3. **Sequence protection is volatile RAM only:** a total MCU power loss resets `last_seq`; anti-replay across reboot requires a new authenticated session/epoch and host handshake.
4. **No serial protocol or bus validation** yet (framing, CRC, timeouts, partial packets, sender authorization, queue flooding).
5. **Encoder is a boolean healthy flag**, not actual speed/position feedback. Stall, overspeed, runaway, stuck-high interlocks and polarity/wiring faults still need real design and test.
6. **No independent system-level recovery test** spanning Jetson/Pi/Arduino, battery brownout, real reset, or actual relay/e-stop behavior.
7. **No release acceptance** for a production motor controller, production privileges, fail-safe hardware review or independent hardware engineering signoff.

BEAN Core's `bean/motion` is a separate simulated host-control research layer. This Bridge lab must not be described as BEAN operating a robot or ready for unassisted physical motion.
