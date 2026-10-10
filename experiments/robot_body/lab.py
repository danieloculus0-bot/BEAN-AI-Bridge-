"""BEAN Robotics Lab 001: reproducible low-cost servo robot morphology experiments.
Actual dynamics require MuJoCo. Nothing in this module commands hardware.
"""
import argparse, csv, json, math, random, sqlite3, sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path

TORQUE = .60  # N.m assumed available per servo; NOT a verified servo curve
SPEED = 3.1  # rad/s software command-speed cap
LEGS = ("FL", "FR", "RL", "RR")

@dataclass(frozen=True)
class Design:
    body_length: float = .27
    body_width: float = .15
    upper: float = .105
    lower: float = .117
    stride: float = .045
    clearance: float = .028
    frequency: float = 1.
    stance: float = .62

RANGES = dict(body_length=(.23,.32), body_width=(.12,.19),
              upper=(.085,.125), lower=(.095,.145), stride=(.02,.07),
              clearance=(.012,.042), frequency=(.6,1.55), stance=(.52,.73))

def model_xml(d):
    """Construct an inertial/contact-dynamics model using ONLY eight servos."""
    for key,(lo,hi) in RANGES.items():
        if not lo <= getattr(d,key) <= hi:
            raise ValueError("unbuildable parameter: " + key)
    root_h = (d.upper + d.lower)*.91 + .019
    hip_x = d.body_length/2-.043
    hip_y = d.body_width/2+.010
    limbs, motors = [], []
    for i,name in enumerate(LEGS):
        x = hip_x if i < 2 else -hip_x
        y = hip_y if i%2==0 else -hip_y
        limbs.append(f'''<body name="{name}_upper" pos="{x:.5f} {y:.5f} 0">
          <joint name="{name}_hip" type="hinge" axis="0 1 0" range="-.80 .92" damping=".035" armature=".002"/>
          <geom type="capsule" fromto="0 0 0 0 0 {-d.upper:.5f}" size=".014" mass=".074"/>
          <body name="{name}_lower" pos="0 0 {-d.upper:.5f}">
            <joint name="{name}_knee" type="hinge" axis="0 1 0" range="-1.68 -.05" damping=".030" armature=".002"/>
            <geom type="capsule" fromto="0 0 0 0 0 {-d.lower:.5f}" size=".011" mass=".055"/>
            <geom name="{name}_foot" type="sphere" pos="0 0 {-d.lower:.5f}" size=".018" mass=".008" friction="1.3 .01 .0001"/>
          </body></body>''')
        motors += [f'<position joint="{name}_{joint}" kp="9" kv=".4" forcerange="-.60 .60"/>'
                   for joint in ("hip","knee")]
    body_mass = .44*(d.body_length*d.body_width)/(.27*.15)
    return f'''<mujoco model="BEAN_Lab001">
      <compiler angle="radian"/>
      <option timestep=".005" gravity="0 0 -9.81" integrator="implicitfast"/>
      <worldbody>
        <geom name="ground" type="plane" size="3 3 .1" friction="1.3 .01 .0001"/>
        <body name="base" pos="0 0 {root_h:.5f}">
          <freejoint/>
          <geom name="chassis" type="box" size="{d.body_length/2:.5f} {d.body_width/2:.5f} .027" mass="{body_mass:.5f}"/>
          {''.join(limbs)}
        </body>
      </worldbody>
      <actuator>{''.join(motors)}</actuator>
    </mujoco>'''

def inverse_kinematics(d,x,down):
    c=(x*x+down*down-d.upper*d.upper-d.lower*d.lower)/(2*d.upper*d.lower)
    knee=-math.acos(max(-1,min(1,c)))
    hip=math.atan2(-x,down)-math.atan2(d.lower*math.sin(knee),d.upper+d.lower*math.cos(knee))
    return max(-.78,min(.90,hip)),max(-1.65,min(-.07,knee))

def gait(d,t):
    down=.91*(d.upper+d.lower)
    commands=[]
    for i in range(4):
        phase=(t*d.frequency+(0 if i in (0,3) else .5))%1.
        if phase<d.stance:
            p=phase/d.stance
            x=d.stride*(.5-p)
            lift=0
        else:
            p=(phase-d.stance)/(1-d.stance)
            x=d.stride*(p-.5)
            lift=d.clearance*math.sin(math.pi*p)
        commands+=inverse_kinematics(d,x,down-lift)
    return commands

def run_physics(d,duration=3.0):
    import mujoco
    m=mujoco.MjModel.from_xml_string(model_xml(d))
    data=mujoco.MjData(m)
    mujoco.mj_resetData(m,data)
    neutral=gait(d,0)
    data.qpos[7:15]=neutral
    data.ctrl[:]=neutral
    mujoco.mj_forward(m,data)
    start_x,start_y=float(data.qpos[0]),float(data.qpos[1])
    cmd=list(neutral)
    energy=0; saturation=0; motors=0; upright=0; fallen=False; steps=0; tilt=0
    dt=float(m.opt.timestep)
    for step in range(int(duration/dt)):
        t=step*dt
        desired=neutral if t<.5 else gait(d,t-.5)
        for j,angle in enumerate(desired):
            cmd[j]+=max(-SPEED*dt,min(SPEED*dt,angle-cmd[j]))
            data.ctrl[j]=cmd[j]
        mujoco.mj_step(m,data)
        steps+=1
        w,x,y,z=[float(v) for v in data.qpos[3:7]]
        roll=math.atan2(2*(w*x+y*z),1-2*(x*x+y*y))
        pitch=math.asin(max(-1,min(1,2*(w*y-z*x))))
        tilt=max(tilt,abs(roll),abs(pitch))
        if data.qpos[2]<.10 or abs(roll)>.90 or abs(pitch)>.90:
            fallen=True
            break
        if abs(roll)<.35 and abs(pitch)<.35: upright+=1
        for j in range(8):
            force=float(data.actuator_force[j])
            energy+=abs(force*float(data.qvel[6+j]))*dt
            saturation+=abs(force)>.97*TORQUE
            motors+=1
    forward=float(data.qpos[0])-start_x
    lateral=abs(float(data.qpos[1])-start_y)
    upright_fraction=upright/max(1,steps)
    survival=steps/max(1,int(duration/dt))
    saturated=saturation/max(1,motors)
    score=15*forward+1.5*upright_fraction+.5*survival-3*int(fallen)-3*lateral-.02*energy-saturated
    return dict(score=round(score,4),forward_m=round(forward,4),
                lateral_m=round(lateral,4),fell=fallen,
                upright_fraction=round(upright_fraction,4),
                survival_fraction=round(survival,4),energy_j=round(energy,4),
                saturation_fraction=round(saturated,4),
                max_tilt_rad=round(tilt,4),body_mass_kg=round(float(sum(m.body_mass)),4))

def mutation(d,rng):
    patches={}
    for key in rng.sample(list(RANGES),rng.randint(2,4)):
        lo,hi=RANGES[key]
        patches[key]=round(max(lo,min(hi,getattr(d,key)+rng.gauss(0,(hi-lo)/5))),5)
    return replace(d,**patches)

def body_registry(d):
    """Existing BEAN BodyRegistry JSON contract; not connected to real servos."""
    joints=[]; limbs=[]
    baseline=inverse_kinematics(d,0,.91*(d.upper+d.lower))
    for i,leg in enumerate(LEGS):
        ids=[]
        for j,part in enumerate(("hip","knee")):
            ident=f"{leg.lower()}_{part}"; ids.append(ident)
            offset=90 if j==0 else 120
            lo,hi=((-0.8,.92) if j==0 else (-1.68,-.05))
            deg=lambda x: round(offset+math.degrees(x),2)
            joints.append(dict(joint_id=ident,label=ident.replace("_"," ").title(),
                servo_channel=None,hardware_connected=False,neutral_pos=deg(baseline[j]),
                notes="SIMULATION ONLY. Explicit hardware calibration and approval required.",
                limits=dict(min_pos=deg(lo),max_pos=deg(hi),safe_min=deg(lo+.03),
                            safe_max=deg(hi-.03),max_speed=round(math.degrees(SPEED),2),
                            forbidden_ranges=[])))
        limbs.append(dict(limb_id=leg.lower(),label=leg,joint_ids=ids))
    return dict(_version="0.1.0",_comment="Simulated BEAN body, eight unwired servos",joints=joints,limbs=limbs)

def register_governed_proposal(core_dir,out,baseline,winner):
    sys.path.insert(0,str(core_dir.resolve()))
    from bean.optimization import init_self_optimization
    conn=sqlite3.connect(out/"bean_proposals.sqlite")
    conn.row_factory=sqlite3.Row
    gov=init_self_optimization(conn)
    prop=gov.create_proposal(session_uuid="robot-lab001",title="Low-cost printable BEAN body",
        problem_statement="Unverified low-cost robotic embodiment design.",
        proposed_change="Review best measured simulation candidate and simulated registry.",
        target_layer="embodiment",proposal_type="experiment",
        expected_benefit="Measured candidate improvement over the fixed baseline, if any.",
        expected_cost="Eight servos, 3D printing, driver and power: BOM to be priced and bench-tested.",
        risk_level="medium",validation_plan="Multiple terrain/seed trials and real motor bench measurements.",
        rollback_plan="Keep current disconnected body registry; never auto-enable hardware.",
        evidence_refs=["robot-results/results.json:baseline","robot-results/results.json:winner"],
        alternatives=["six legs","wheels","stationary arms"])
    (out/"governor_proposal.json").write_text(json.dumps(prop,indent=2))
    conn.close()
    return prop["proposal_id"]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--trials",type=int,default=24)
    p.add_argument("--seed",type=int,default=106)
    p.add_argument("--out",type=Path,default=Path("robot-results"))
    p.add_argument("--core-dir",type=Path)
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    if not 1<=a.trials<=150: p.error("trials must be 1..150")
    a.out.mkdir(parents=True,exist_ok=True)
    baseline_design=Design()
    (a.out/"baseline.xml").write_text(model_xml(baseline_design))
    if a.dry_run:
        print("XML generated; NO PHYSICS TEST RUN")
        return
    import mujoco
    rng=random.Random(a.seed)
    baseline=dict(id=0,design=asdict(baseline_design),metrics=run_physics(baseline_design))
    best=baseline; records=[baseline]
    for i in range(1,a.trials+1):
        parent=baseline_design if i%4==0 else Design(**best["design"])
        candidate=mutation(parent,rng)
        try: outcome=run_physics(candidate)
        except Exception as exc:
            records.append(dict(id=i,design=asdict(candidate),error=str(exc)))
            continue
        result=dict(id=i,design=asdict(candidate),metrics=outcome)
        records.append(result)
        if outcome["score"]>best["metrics"]["score"]: best=result
    report=dict(engine="MuJoCo",engine_version=mujoco.__version__,seed=a.seed,
        servo_count=8,assumed_continuous_torque_Nm=TORQUE,
        assumed_command_speed_rad_s=SPEED,baseline=baseline,winner=best,
        trials=records,warning="Flat-floor model assumptions; not physical verification")
    (a.out/"results.json").write_text(json.dumps(report,indent=2))
    (a.out/"winner.json").write_text(json.dumps(best,indent=2))
    (a.out/"winner.xml").write_text(model_xml(Design(**best["design"])))
    (a.out/"body_registry_candidate.json").write_text(json.dumps(body_registry(Design(**best["design"])),indent=2))
    with (a.out/"ranked.csv").open("w",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(["id","score","forward_m","lateral_m","fell","energy_j","saturation_fraction"])
        for r in sorted((z for z in records if "metrics" in z),key=lambda z:z["metrics"]["score"],reverse=True):
            m=r["metrics"]
            writer.writerow([r["id"]]+[m[k] for k in ("score","forward_m","lateral_m","fell","energy_j","saturation_fraction")])
    if a.core_dir: print("BEAN governor proposal:",register_governed_proposal(a.core_dir,a.out,baseline,best))
    print(json.dumps(dict(baseline=baseline,winner=best,valid_trials=sum("metrics" in r for r in records)),indent=2))

if __name__=="__main__":
    main()
