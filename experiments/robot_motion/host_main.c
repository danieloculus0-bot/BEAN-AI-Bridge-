#include <stdio.h>
#include "motion_logic.h"
int main(void) {
    int line=motion_selftest();
    if (line) { fprintf(stderr,"HOST_MOTION_FAIL line=%d\n",line); return 1; }
    puts("HOST_MOTION_PASS"); return 0;
}
