#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "motion_logic.h"
/* ESP32 CPU test entry. Does not drive motor pins. */
void app_main(void) {
    int line=motion_selftest();
    if (line) printf("ESP32_MOTION_FAIL line=%d\n",line);
    else puts("ESP32_MOTION_PASS");
    fflush(stdout);
    while (1) vTaskDelay(pdMS_TO_TICKS(1000));
}
