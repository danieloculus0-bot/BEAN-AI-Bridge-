#include "motion_logic.h"
/* Identical adversarial contract executes on host, AVR and ESP32 CPUs. */
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
#define APPLY(p,t,id,l,e,s) motion_apply(&state,(p),(t),(id),(l),(e),(s))
#define TICK(l,e,s) motion_tick(&state,(l),(e),(s))
#define RESET() motion_reset(&state,1,1,0)
#define ARM() motion_arm(&state,1,1,0)
int motion_selftest(void) {
    MotionState state;
    motion_init(&state);
    CHECK(state.pwm==0 && state.ticks==0 && state.fault==MOTION_OK);
    CHECK(state.armed==0 && state.seen_seq==0);
    /* Boot and fault clearing never implicitly arm a motor. */
    CHECK(!APPLY(90,3,1,1,1,0));
    CHECK(state.fault==MOTION_UNARMED && state.pwm==0 && state.armed==0);
    CHECK(RESET());
    CHECK(state.armed==0 && state.fault==MOTION_OK);
    CHECK(ARM());
    CHECK(state.armed==1);
    CHECK(APPLY(100,3,1,1,1,0));
    CHECK(state.pwm==100 && state.ticks==3 && state.last_seq==1);
    TICK(1,1,0);
    CHECK(state.pwm==100 && state.ticks==2);
    /* A replay or out-of-order command latches a non-moving fault. */
    CHECK(!APPLY(150,3,1,1,1,0));
    CHECK(state.fault==MOTION_SEQUENCE && state.pwm==0 && state.armed==0);
    CHECK(RESET());
    CHECK(state.last_seq==1 && state.seen_seq==1 && !state.armed);
    CHECK(ARM());
    CHECK(!APPLY(100,3,1,1,1,0));
    CHECK(state.fault==MOTION_SEQUENCE);
    CHECK(RESET() && ARM());
    CHECK(APPLY(90,3,3,1,1,0));
    CHECK(!APPLY(90,3,2,1,1,0));
    CHECK(state.pwm==0 && state.fault==MOTION_SEQUENCE);
    CHECK(RESET() && ARM());

    /* Reversal consumes a fresh command but requires an intervening zero. */
    CHECK(APPLY(120,5,4,1,1,0));
    CHECK(!APPLY(-120,5,5,1,1,0));
    CHECK(state.pwm==0 && state.ticks==0 && state.fault==MOTION_OK);
    CHECK(state.last_seq==5);
    CHECK(APPLY(-120,5,6,1,1,0));
    CHECK(state.pwm==-120);
    CHECK(APPLY(0,0,7,1,1,0));
    CHECK(state.pwm==0 && state.ticks==0 && state.fault==MOTION_OK);
    TICK(1,1,0);
    CHECK(state.fault==MOTION_OK);

    /* Negative sensor inputs must not be interpreted as true/healthy. */
    CHECK(APPLY(110,4,8,1,1,0));
    TICK(-1,1,0);
    CHECK(state.fault==MOTION_INVALID && state.pwm==0);
    CHECK(RESET()); /* clearing the fault never re-arms */
    CHECK(!state.armed && state.fault==MOTION_OK);
    CHECK(ARM());

    /* Emergency stop takes effect during tick, without a new command. */
    CHECK(APPLY(100,10,9,1,1,0));
    TICK(1,1,1);
    CHECK(state.fault==MOTION_ESTOP && state.pwm==0 && state.armed==0);
    CHECK(!motion_reset(&state,1,1,1));
    CHECK(!ARM());
    CHECK(RESET() && ARM());

    /* Link and encoder loss are sampled on each tick too. */
    CHECK(APPLY(100,10,10,1,1,0));
    TICK(0,1,0);
    CHECK(state.fault==MOTION_LINK && state.pwm==0 && !state.armed);
    CHECK(!motion_reset(&state,0,1,0));
    CHECK(RESET() && ARM());
    CHECK(APPLY(100,10,11,1,1,0));
    TICK(1,0,0);
    CHECK(state.fault==MOTION_ENCODER && state.pwm==0);
    CHECK(!motion_reset(&state,1,0,0));
    CHECK(RESET() && ARM());

    /* TTL is a logical duration bound; zero does not energize. */
    CHECK(!APPLY(20,0,12,1,1,0));
    CHECK(state.fault==MOTION_INVALID && state.pwm==0);
    CHECK(RESET() && ARM());
    CHECK(!APPLY(10,MOTION_TTL_MAX_TICKS+1,13,1,1,0));
    CHECK(state.fault==MOTION_INVALID);
    CHECK(RESET() && ARM());
    CHECK(!APPLY(0,1,14,1,1,0));
    CHECK(state.fault==MOTION_INVALID);
    CHECK(RESET() && ARM());
    CHECK(!APPLY(256,2,15,1,1,0));
    CHECK(state.fault==MOTION_INVALID);
    CHECK(RESET() && ARM());
    CHECK(!APPLY(-256,2,16,1,1,0));
    CHECK(state.fault==MOTION_INVALID);
    CHECK(RESET() && ARM());
    CHECK(!APPLY(25,2,0,1,1,0));
    CHECK(state.fault==MOTION_SEQUENCE);
    CHECK(RESET() && ARM());

    /* No fresh command means the logical deadman expires, fault latched. */
    CHECK(APPLY(80,2,17,1,1,0));
    TICK(1,1,0);
    CHECK(state.pwm==80 && state.ticks==1);
    TICK(1,1,0);
    CHECK(state.pwm==0 && state.ticks==0 && state.fault==MOTION_TIMEOUT);
    CHECK(!APPLY(80,2,18,1,1,0));
    CHECK(RESET());
    CHECK(!state.armed);
    CHECK(ARM());
    CHECK(APPLY(80,MOTION_TTL_MAX_TICKS,18,1,1,0));
    CHECK(state.pwm==80 && state.ticks==MOTION_TTL_MAX_TICKS);
    CHECK(APPLY(0,0,19,1,1,0));
    CHECK(state.pwm==0 && state.fault==MOTION_OK);
    /* A reset called while the motor is active must brake on lost link. */
    CHECK(APPLY(80,3,20,1,1,0));
    CHECK(!motion_reset(&state,0,1,0));
    CHECK(state.fault==MOTION_LINK && state.pwm==0 && !state.armed);
    CHECK(RESET() && ARM());
    CHECK(APPLY(90,4,21,1,1,0));
    CHECK(!motion_reset(&state,1,1,1));
    CHECK(state.fault==MOTION_ESTOP && state.pwm==0);
    CHECK(RESET() && ARM());
    CHECK(APPLY(90,4,22,1,1,0));
    CHECK(!motion_reset(&state,1,0,0));
    CHECK(state.fault==MOTION_ENCODER && state.pwm==0);
    CHECK(RESET() && ARM());
    CHECK(APPLY(0,0,23,1,1,0));
    return 0;
}
