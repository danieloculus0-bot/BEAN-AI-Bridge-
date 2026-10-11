#include "motion_logic.h"
/* Same adversarial contract executed by host, AVR CPU and ESP32 CPU. */
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
int motion_selftest(void) {
    MotionState s;
    motion_init(&s);
    CHECK(s.pwm==0 && s.ticks==0 && s.fault==MOTION_OK);
    CHECK(motion_apply(&s,100,3,1,1,0));
    CHECK(s.pwm==100 && s.ticks==3);
    motion_tick(&s);
    CHECK(s.pwm==100 && s.ticks==2);
    CHECK(!motion_apply(&s,-90,3,1,1,0));
    CHECK(s.pwm==0 && s.fault==MOTION_OK);
    CHECK(motion_apply(&s,-90,3,1,1,0));
    CHECK(s.pwm==-90);
    CHECK(!motion_apply(&s,50,2,1,1,1));
    CHECK(s.pwm==0 && s.fault==MOTION_ESTOP);
    CHECK(!motion_apply(&s,50,2,1,1,0));
    CHECK(!motion_reset(&s,1,1,1));
    CHECK(s.fault==MOTION_ESTOP);
    CHECK(motion_reset(&s,1,1,0));
    CHECK(motion_apply(&s,110,2,1,1,0));
    CHECK(!motion_apply(&s,110,2,0,1,0));
    CHECK(s.pwm==0 && s.fault==MOTION_LINK);
    CHECK(!motion_reset(&s,0,1,0));
    CHECK(motion_reset(&s,1,1,0));
    CHECK(motion_apply(&s,110,2,1,1,0));
    CHECK(!motion_apply(&s,110,2,1,0,0));
    CHECK(s.fault==MOTION_ENCODER && s.pwm==0);
    CHECK(motion_reset(&s,1,1,0));
    CHECK(!motion_apply(&s,256,2,1,1,0));
    CHECK(s.fault==MOTION_INVALID);
    CHECK(motion_reset(&s,1,1,0));
    CHECK(!motion_apply(&s,-256,2,1,1,0));
    CHECK(s.fault==MOTION_INVALID);
    CHECK(motion_reset(&s,1,1,0));
    CHECK(!motion_apply(&s,20,0,1,1,0));
    CHECK(s.fault==MOTION_INVALID);
    CHECK(motion_reset(&s,1,1,0));
    CHECK(motion_apply(&s,80,2,1,1,0));
    motion_tick(&s);
    CHECK(s.pwm==80 && s.ticks==1);
    motion_tick(&s);
    CHECK(s.pwm==0 && s.fault==MOTION_TIMEOUT);
    CHECK(!motion_apply(&s,70,1,1,1,0));
    CHECK(motion_reset(&s,1,1,0));
    CHECK(motion_apply(&s,50,2,1,1,0));
    CHECK(motion_apply(&s,0,0,1,1,0));
    CHECK(s.pwm==0 && s.ticks==0);
    motion_tick(&s);
    CHECK(s.fault==MOTION_OK);
    return 0;
}
