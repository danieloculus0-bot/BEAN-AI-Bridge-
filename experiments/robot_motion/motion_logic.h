#ifndef BEAN_ROBOT_MOTION_LOGIC_H
#define BEAN_ROBOT_MOTION_LOGIC_H
#include <stdint.h>
/* Portable logical interlock. NEVER connected directly to motor pins. */
#define MOTION_TTL_MAX_TICKS 100U
typedef enum {
    MOTION_OK=0, MOTION_ESTOP=1, MOTION_LINK=2, MOTION_ENCODER=3,
    MOTION_INVALID=4, MOTION_TIMEOUT=5, MOTION_SEQUENCE=6, MOTION_UNARMED=7
} MotionFault;
typedef struct {
    int16_t pwm;
    uint16_t ticks;
    MotionFault fault;
    uint32_t last_seq;
    uint8_t seen_seq;
    uint8_t armed;
} MotionState;
void motion_init(MotionState *s);
int motion_reset(MotionState *s, int link, int encoder, int estop);
int motion_arm(MotionState *s, int link, int encoder, int estop);
int motion_apply(MotionState *s, int16_t pwm, uint16_t ttl, uint32_t seq,
                 int link, int encoder, int estop);
void motion_tick(MotionState *s, int link, int encoder, int estop);
int motion_selftest(void);
#endif
