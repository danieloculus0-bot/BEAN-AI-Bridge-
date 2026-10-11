#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "motion_logic.h"
/* QEMU-only logical state machine; no motor GPIO or PWM is used. */
void app_main(void) {
    MotionState s;
    int line=motion_selftest();
    if (line) {
        printf("ESP32_MOTION_FAIL line=%d\n",line);
        fflush(stdout);
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    puts("ESP32_MOTION_PASS");

    /* Independently exercise task-delayed watchdog sampling under FreeRTOS. */
    motion_init(&s);
    if (!motion_arm(&s,1,1,0) ||
        !motion_apply(&s,80,2,1,1,1,0)) {
        puts("ESP32_FREERTOS_WATCHDOG_FAIL setup");
    } else {
        vTaskDelay(pdMS_TO_TICKS(10));
        motion_tick(&s,1,1,0);
        if (s.pwm!=80 || s.ticks!=1) {
            puts("ESP32_FREERTOS_WATCHDOG_FAIL first-tick");
        } else {
            vTaskDelay(pdMS_TO_TICKS(10));
            motion_tick(&s,1,1,0);
            if (s.pwm!=0 || s.fault!=MOTION_TIMEOUT || s.armed!=0) {
                puts("ESP32_FREERTOS_WATCHDOG_FAIL timeout");
            } else if (!motion_reset(&s,1,1,0) ||
                       !motion_arm(&s,1,1,0) ||
                       !motion_apply(&s,70,10,2,1,1,0)) {
                puts("ESP32_FREERTOS_WATCHDOG_FAIL recovery");
            } else {
                vTaskDelay(pdMS_TO_TICKS(10));
                motion_tick(&s,1,1,1);
                if (s.pwm!=0 || s.fault!=MOTION_ESTOP || s.armed!=0)
                    puts("ESP32_FREERTOS_WATCHDOG_FAIL estop");
                else
                    puts("ESP32_FREERTOS_WATCHDOG_PASS");
            }
        }
    }
    fflush(stdout);
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
