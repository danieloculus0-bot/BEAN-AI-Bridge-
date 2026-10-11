#include "motion_logic.h"
static void trip(MotionState *s, MotionFault f) { s->pwm=0; s->ticks=0; s->fault=f; }
void motion_init(MotionState *s) { s->pwm=0; s->ticks=0; s->fault=MOTION_OK; }
int motion_reset(MotionState *s, int link, int encoder, int estop) {
    if (!link || !encoder || estop) return 0;
    motion_init(s); return 1;
}
int motion_apply(MotionState *s, int16_t pwm, uint16_t ttl, int link, int encoder, int estop) {
    if (estop) { trip(s,MOTION_ESTOP); return 0; }
    if (!link) { trip(s,MOTION_LINK); return 0; }
    if (!encoder) { trip(s,MOTION_ENCODER); return 0; }
    if (s->fault!=MOTION_OK) return 0;
    if (pwm < -255 || pwm > 255 || (pwm!=0 && ttl==0)) { trip(s,MOTION_INVALID); return 0; }
    /* Reversal requires a separate zero-output transition. */
    if ((s->pwm>0 && pwm<0) || (s->pwm<0 && pwm>0)) {
        s->pwm=0; s->ticks=0; return 0;
    }
    s->pwm=pwm; s->ticks=(pwm==0)?0:ttl; return 1;
}
void motion_tick(MotionState *s) {
    if (s->fault!=MOTION_OK || s->pwm==0) return;
    if (s->ticks>0) --s->ticks;
    if (s->ticks==0) trip(s,MOTION_TIMEOUT);
}
