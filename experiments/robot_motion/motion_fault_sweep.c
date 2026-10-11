#include "motion_logic.h"
#include <stdint.h>
/* Deterministic adversarial sequences, native-host only. No real motor pins. */
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
static uint32_t random_state=0x9e3779b9U;
static uint32_t draw(void) {
    random_state=random_state*1664525U+1013904223U;
    return random_state;
}
int motion_fault_sweep(void) {
    unsigned episode, step;
    for (episode=0; episode<128U; ++episode) {
        MotionState s;
        uint32_t next_seq=1U;
        motion_init(&s);
        CHECK(s.fault==MOTION_OK && !s.armed && s.pwm==0);
        for (step=0; step<48U; ++step) {
            uint32_t r=draw();
            int link=((r>>3)&15U)==0U ? 0 : 1;
            int encoder=((r>>9)&15U)==0U ? 0 : 1;
            int estop=((r>>15)&31U)==0U ? 1 : 0;
            unsigned action=r%6U;
            uint32_t old_seq=s.last_seq;
            uint8_t old_seen=s.seen_seq;
            if (action==0U) {
                motion_reset(&s,link,encoder,estop);
            } else if (action==1U) {
                motion_arm(&s,link,encoder,estop);
            } else if (action==2U) {
                motion_tick(&s,link,encoder,estop);
            } else {
                int16_t pwm=(int16_t)((int)(draw()%601U)-300);
                uint16_t ttl=(uint16_t)(draw()%107U);
                uint32_t seq=next_seq++;
                /* One fifth of requests are replayed/out of order. */
                if ((draw()%5U)==0U && old_seen) seq=old_seq;
                motion_apply(&s,pwm,ttl,seq,link,encoder,estop);
            }
            if (s.fault!=MOTION_OK || !s.armed) {
                CHECK(s.pwm==0 && s.ticks==0);
            }
            if (s.pwm!=0) {
                CHECK(s.armed && s.fault==MOTION_OK);
                CHECK(s.pwm>=-255 && s.pwm<=255);
                CHECK(s.ticks>0 && s.ticks<=MOTION_TTL_MAX_TICKS);
            } else {
                CHECK(s.ticks==0);
            }
            CHECK(!old_seen || (s.seen_seq && s.last_seq>=old_seq));
        }
    }
    return 0;
}
