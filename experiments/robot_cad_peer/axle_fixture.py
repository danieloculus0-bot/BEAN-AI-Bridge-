"""Neutral CadQuery CAD reference fixture (not BEAN's chosen robot body).

Dimensions are experimental interface assumptions in millimetres. This file
exists solely to exercise the independent checker. BEAN's own CAD exporter
may generate wholly different geometry if it satisfies a declared interface.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import cadquery as cq

@dataclass(frozen=True)
class AxleBlock:
    length_mm: float = 38.0
    width_mm: float = 30.0
    height_mm: float = 24.0
    nominal_axle_d_mm: float = 6.35
    axle_bore_d_mm: float = 6.65
    bolt_bore_d_mm: float = 4.30
    bolt_x_mm: float = 12.0
    bolt_y_mm: float = 10.0


def make_model(spec: AxleBlock, *, axle_depth_fraction=1.0,
               omit_bolts=False) -> cq.Workplane:
    """Export a real CAD solid; the checker NEVER reads these parameters as truth."""
    length, width, height = spec.length_mm, spec.width_mm, spec.height_mm
    part = cq.Workplane("XY").box(length, width, height,
                                    centered=(True, True, False))
    depth = length * axle_depth_fraction
    hole = (cq.Workplane("YZ").workplane(offset=-length/2)
            .center(0,height/2).circle(spec.axle_bore_d_mm / 2).extrude(depth))
    part = part.cut(hole)
    if not omit_bolts:
        mounts = (cq.Workplane("XY")
                  .pushPoints([(-spec.bolt_x_mm,-spec.bolt_y_mm),
                               (spec.bolt_x_mm,spec.bolt_y_mm)])
                  .circle(spec.bolt_bore_d_mm/2).extrude(height))
        part=part.cut(mounts)
    return part


def interface_contract(spec: AxleBlock):
    """Declared *experimental* mechanical mating constraints, not CAD proof."""
    return {
        "schema":"bean.cad.axle-interface.v1",
        "units":"mm",
        "interface":"replaceable_quarter_inch_axle_block",
        "nominal_axle_d_mm": spec.nominal_axle_d_mm,
        "bore_diameter_range_mm":[6.50, 7.10],
        "bolt_diameter_range_mm":[4.15, 4.80],
        "axle_axis_y_mm":0.0,
        "axle_axis_z_mm":spec.height_mm/2,
        "axle_axis":"X",
        "mounts_xy_mm":[[-spec.bolt_x_mm,-spec.bolt_y_mm],
                        [spec.bolt_x_mm,spec.bolt_y_mm]],
        "max_envelope_mm":[44.0,36.0,29.0],
        "minimum_nominal_web_mm":2.0,
        "status":"synthetic_fixture_no_physical_fit_claim",
    }


def export_fixture(out: Path, *, spec=AxleBlock(),
                   axle_depth_fraction=1.0, omit_bolts=False):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    cad=make_model(spec,axle_depth_fraction=axle_depth_fraction,
                   omit_bolts=omit_bolts)
    cq.exporters.export(cad,str(out/'part.step'))
    cq.exporters.export(cad,str(out/'part.stl'), tolerance=0.05,
                        angularTolerance=0.15)
    (out/'interface.json').write_text(json.dumps(interface_contract(spec),indent=2)+'\n')
    return out


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,default=Path('robot-cad-results'))
    args=p.parse_args()
    print(export_fixture(args.out))
