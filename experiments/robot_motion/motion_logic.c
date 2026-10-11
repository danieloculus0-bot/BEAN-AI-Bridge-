#include "motion_logic.h"
/* Logical CPU state machine only, no hardware I/O or safety certification. */
static void trip(MotionState *s, MotionFault f) {
    s->pwm=0; s->ticks=0; s->armed=0; s->fault=f;
}
static int interlocks(MotionState *s, int link, int encoder, int estop) {
    /* Reject non-boolean sensor states, including negative/error codes. */
    if ((link!=0 && link!=1) || (encoder!=0 && encoder!=1) ||
        (estop!=0 && estop!=1)) {
        trip(s,MOTION_INVALID); return 0;
    }
    if (estop) { trip(s,MOTION_ESTOP); return 0; }
    if (!link) { trip(s,MOTION_LINK); return 0; }
    if (!encoder) { trip(s,MOTION_ENCODER); return 0; }
    return 1;
}
void motion_init(MotionState *s) {
    s->pwm=0; s->ticks=0; s->fault=MOTION_OK;
    s->last_seq=0; s->seen_seq=0; s->armed=0;
}
/* Clearing a fault is NEVER arming. Sequence protection survives reset. */
int motion_reset(MotionState *s, int link, int encoder, int estop) {
    if (link!=1 || encoder!=1 || estop!=0) return 0;
    s->pwm=0; s->ticks=0; s->fault=MOTION_OK; s->armed=0;
    return 1;
}
int motion_arm(MotionState *s, int link, int encoder, int estop) {
    if (s->fault!=MOTION_OK) return 0;
    if (!interlocks(s,link,encoder,estop)) return 0;
    /* Explicit separate operator/host-controlled logical arm step. */
    if (s->pwm!=0 || s->ticks!=0) return 0;
    s->armed=1;
    return 1;
}
int motion_apply(MotionState *s, int16_t pwm, uint16_t ttl, uint32_t seq,
                 int link, int encoder, int estop) {
    if (!interlocks(s,link,encoder,estop)) return 0;
    if (s->fault!=MOTION_OK) return 0;
    if (!s->armed) { trip(s,MOTION_UNARMED); return 0; }
    if (seq==0 || (s->seen_seq && seq<=s->last_seq)) {
        trip(s,MOTION_SEQUENCE); return 0;
    }
    if (pwm < -255 || pwm > 255 || ttl > MOTION_TTL_MAX_TICKS ||
        (pwm!=0 && ttl==0) || (pwm==0 && ttl!=0)) {
        trip(s,MOTION_INVALID); return 0;
    }
    /* Consume a valid sequence even when reversal is neutralized. */
    s->last_seq=seq; s->seen_seq=1;
    if ((s->pwm>0 && pwm<0) || (s->pwm<0 && pwm>0)) {
        s->pwm=0; s->ticks=0;
        return 0;
    }
    s->pwm=pwm; s->ticks=(pwm==0)?0:ttl;
    return 1;
}
/* Called by a trusted periodic driver; all sensors rechecked EVERY tick. */
void motion_tick(MotionState *s, int link, int encoder, int estop) {
    if (!interlocks(s,link,encoder,estop)) return;
    if (s->fault!=MOTION_OK || s->pwm==0) return;
    if (s->ticks>0) --s->ticks;
    if (s->ticks==0) trip(s,MOTION_TIMEOUT);
}
