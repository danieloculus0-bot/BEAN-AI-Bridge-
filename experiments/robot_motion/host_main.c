#include <stdio.h>
#include "motion_logic.h"
int motion_fault_sweep(void);
int main(void) {
    int line=motion_selftest();
    if (line) { fprintf(stderr,"HOST_MOTION_FAIL line=%d\n",line); return 1; }
    puts("HOST_MOTION_PASS");
    line=motion_fault_sweep();
    if (line) { fprintf(stderr,"HOST_MOTION_SWEEP_FAIL line=%d\n",line); return 1; }
    puts("HOST_MOTION_SWEEP_PASS");
    return 0;
}
