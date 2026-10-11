# BEAN Robot Motion — Emulator Lab

This is an experimental Bridge subproject. No physical motor pins are driven.

The same portable C control-state machine and adversarial test vectors run in three environments:

- Native C on GitHub Actions, a reference test (not a microcontroller).
- Arduino Nano (ATmega328P) machine instructions with avr-gcc + simavr, checked by the `AVR_MOTION_PASS` UART marker.
- ESP32 IDF firmware in Espressif QEMU, checked by the `ESP32_MOTION_PASS` UART marker.
- Optional ESP32 Wokwi simulation using that firmware and the same marker. This requires the GitHub secret `WOKWI_CLI_TOKEN`; missing token is explicitly recorded as `NOT_RUN_MISSING_TOKEN`.

Interlock cases cover reverse direction, emergency stop, link loss, encoder failure, invalid commands, fault latching and logical watchdog expiry. This tests control software, not physical electrical protection or real-time safety.

GitHub workflow: `.github/workflows/bean-robot-motion-emulators.yml`.

Run host tests with `bash experiments/robot_motion/run_host.sh`, AVR with `bash experiments/robot_motion/run_avr.sh` after installing `simavr gcc-avr avr-libc`, and ESP32 with `bash experiments/robot_motion/run_esp32_qemu.sh` using Docker.

BEAN Core continues to own `bean/motion` and its simulated joint-state implementation. The Bridge maintains independent research and reproducible external-controller test evidence. This lab is unmerged experimental code; no claims of real robot movement or independent review are implied.
