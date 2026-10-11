"""Independent STEP + STL QA gate for robotics axle-module CAD.

Checks actual model geometry, not only model-declared dimensions. Uses OCC
for STEP point occupancy and trimesh for exported STL manifold/volume parity.
No structural FEA, printability or certified fit claims are possible here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import cadquery as cq
import numpy as np
import trimesh

class CADReject(ValueError):
    pass


def sha256(path:Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_contract(spec):
    if spec.get('schema') != 'bean.cad.axle-interface.v1' or spec.get('units')!='mm':
        raise CADReject('interface schema or unit mismatch')
    if spec.get('axle_axis')!='X':
        raise CADReject('this dedicated axle-block fixture verifier expects an X-oriented axle')
    for k in ('nominal_axle_d_mm','axle_axis_y_mm','axle_axis_z_mm','minimum_nominal_web_mm'):
        if not isinstance(spec.get(k),(int,float)) or not math.isfinite(spec[k]):
            raise CADReject(f'invalid numeric constraint: {k}')
    if abs(spec['nominal_axle_d_mm']-6.35)>1e-6:
        raise CADReject('quarter-inch axle nominal must be 6.35 mm')
    for key in ('bore_diameter_range_mm','bolt_diameter_range_mm','max_envelope_mm'):
        limits=spec.get(key)
        length=3 if key=='max_envelope_mm' else 2
        if not isinstance(limits,list) or len(limits)!=length or not all(isinstance(v,(float,int)) and math.isfinite(v) and v>0 for v in limits):
            raise CADReject(f'invalid {key}')
    if spec['bore_diameter_range_mm'][0]>=spec['bore_diameter_range_mm'][1] or spec['bolt_diameter_range_mm'][0]>=spec['bolt_diameter_range_mm'][1]:
        raise CADReject('invalid bore limits')
    holes=spec.get('mounts_xy_mm')
    if not isinstance(holes,list) or len(holes)<2 or len(holes)>8:
        raise CADReject('expected 2-8 declared mounting holes')
    for xy in holes:
        if not isinstance(xy,list) or len(xy)!=2 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in xy):
            raise CADReject('invalid mounting hole center')


def body_occupies(part, xyz):
    return any(s.isInside(cq.Vector(*xyz),1e-4) for s in part.Solids())


def require_open(part,xyz,label):
    if body_occupies(part,xyz):
        raise CADReject(f'{label}: expected passage is filled at {xyz}')


def require_solid(part,xyz,label):
    if not body_occupies(part,xyz):
        raise CADReject(f'{label}: missing material at {xyz}')


def validate(folder:Path):
    folder=Path(folder)
    step, stl, manifest=folder/'part.step',folder/'part.stl',folder/'interface.json'
    for p in (step,stl,manifest):
        if p.is_symlink() or not p.is_file() or p.stat().st_size>15_000_000:
            raise CADReject(f'missing/invalid CAD file {p.name}')
    spec=json.loads(manifest.read_text())
    check_contract(spec)
    part=cq.importers.importStep(str(step)).val()
    solids=part.Solids()
    if len(solids)!=1 or not part.isValid():
        raise CADReject('STEP is not one valid closed solid')
    solid=solids[0]
    step_volume=float(solid.Volume())
    if not 1.0<step_volume<1e6:
        raise CADReject('STEP volume invalid')
    bb=part.BoundingBox()
    span=[bb.xlen,bb.ylen,bb.zlen]
    for n,maximum in zip(span,spec['max_envelope_mm']):
        if n>maximum+0.05:
            raise CADReject('physical part exceeds declared build envelope')
    if min(span)<4.0:
        raise CADReject('unexpected degenerate part extent')
    mesh=trimesh.load_mesh(str(stl),force='mesh',process=True)
    if not isinstance(mesh,trimesh.Trimesh) or not mesh.is_watertight or not mesh.is_winding_consistent:
        raise CADReject('STL is not watertight with consistent winding')
    if not math.isfinite(mesh.volume) or mesh.volume<=0:
        raise CADReject('STL volume must be positive')
    if abs(mesh.volume-step_volume)/step_volume > 0.015:
        raise CADReject('STEP-to-STL volume differs by more than 1.5 percent')
    step_bounds=np.array([[bb.xmin,bb.ymin,bb.zmin],
                          [bb.xmax,bb.ymax,bb.zmax]],dtype=float)
    if float(np.max(np.abs(step_bounds-mesh.bounds))) > 0.2:
        raise CADReject('STEP-to-STL absolute bounds differ by >0.2 mm')
    cy,cz=spec['axle_axis_y_mm'],spec['axle_axis_z_mm']
    bmin,bmax=spec['bore_diameter_range_mm']
    for x in np.linspace(bb.xmin+1.0,bb.xmax-1.0,7):
        for direction in ((1,0),(-1,0),(0,1),(0,-1)):
            # Slightly smaller than the declared minimum accepted bore
            # radius MUST remain air, at every interior location.
            radius=bmin/2 - 0.08
            y=cy+direction[0]*radius
            z=cz+direction[1]*radius
            require_open(part,(float(x),float(y),float(z)),'axle minimum diameter')
    # The central cross-section contains material beyond the max permitted bore.
    for dy,dz in ((1,0),(-1,0),(0,1),(0,-1)):
        radius=bmax/2 + 0.18
        require_solid(part,(0.,cy+dy*radius,cz+dz*radius),'axle max diameter / solid web')
    bolmin,bolmax=spec['bolt_diameter_range_mm']
    for mx,my in spec['mounts_xy_mm']:
        for z in np.linspace(bb.zmin+1.,bb.zmax-1.,5):
            require_open(part,(mx,my,float(z)),'bolt through-hole')
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                rad=bolmin/2-0.08
                require_open(part,(mx+dx*rad,my+dy*rad,float(z)), 'bolt minimum passage')
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            rad=bolmax/2+spec['minimum_nominal_web_mm']
            require_solid(part,(mx+dx*rad,my+dy*rad,(bb.zmin+bb.zmax)/2),'bolt local web')
    return {
        'schema':'bean.cad.independent-qa.v1',
        'status':'PASSED_GEOMETRIC_CHECKS_NOT_HARDWARE_VALIDATED',
        'checks':['one_valid_step_solid','stl_manifold_positive_volume',
                  'step_stl_volume_and_envelope_parity','nominal_6_35mm_axle_passage',
                  'axle_max_bore_and_web','through_bolt_passages_and_web'],
        'step_volume_mm3':round(step_volume,3),
        'stl_volume_mm3':round(float(mesh.volume),3),
        'bounds_mm':[round(float(x),3) for x in span],
        'sha256':{x.name:sha256(x) for x in (step,stl,manifest)},
        'limits':{'not_structural_FEA':True,'not_motor_interface_certification':True,
                  'not_verified_printability':True,'synthetic_reference_only':True}
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--folder',type=Path,default=Path('robot-cad-results'))
    p.add_argument('--receipt',type=Path,default=None)
    args=p.parse_args()
    try:
        r=validate(args.folder)
        exitcode=0
    except (CADReject,ValueError,RuntimeError,OSError,KeyError,TypeError) as e:
        r={'schema':'bean.cad.independent-qa.v1','status':'REJECTED',
           'reason':type(e).__name__+': '+str(e)[:200]}
        exitcode=1
    path=args.receipt or args.folder/'cad_qa.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    print(json.dumps(r,indent=2,sort_keys=True))
    return exitcode

if __name__=='__main__':
    raise SystemExit(main())
