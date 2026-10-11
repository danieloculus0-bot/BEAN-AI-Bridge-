"""Adversarial independent checks for the CAD STEP/STL gate."""
from __future__ import annotations
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import trimesh
from axle_fixture import AxleBlock, export_fixture
from verify import CADReject, validate

class CADPeerGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)

    def export(self, **kwargs):
        return export_fixture(self.folder,**kwargs)

    def test_valid_real_parametric_step_stl(self):
        self.export()
        result=validate(self.folder)
        self.assertEqual(result['status'],'PASSED_GEOMETRIC_CHECKS_NOT_HARDWARE_VALIDATED')
        self.assertEqual(result['bounds_mm'],[38.0,30.0,24.0])
        self.assertLess(abs(result['step_volume_mm3']-result['stl_volume_mm3']),50)
        for key in ('part.step','part.stl','interface.json'):
            self.assertEqual(len(result['sha256'][key]),64)

    def test_blind_axle_bore_is_rejected(self):
        self.export(axle_depth_fraction=0.70)
        with self.assertRaisesRegex(CADReject,'axle minimum diameter'):
            validate(self.folder)

    def test_too_tight_axle_bore_is_rejected(self):
        self.export(spec=replace(AxleBlock(),axle_bore_d_mm=6.2))
        with self.assertRaisesRegex(CADReject,'axle minimum diameter'):
            validate(self.folder)

    def test_axle_bore_too_wide_is_rejected(self):
        self.export(spec=replace(AxleBlock(),axle_bore_d_mm=9.0))
        with self.assertRaisesRegex(CADReject,'axle max diameter'):
            validate(self.folder)

    def test_missing_mount_bolts_are_rejected(self):
        self.export(omit_bolts=True)
        with self.assertRaisesRegex(CADReject,'bolt through-hole'):
            validate(self.folder)

    def test_bolt_bores_too_narrow_are_rejected(self):
        self.export(spec=replace(AxleBlock(),bolt_bore_d_mm=3.7))
        with self.assertRaisesRegex(CADReject,'bolt minimum passage'):
            validate(self.folder)

    def test_oversize_envelope_is_rejected(self):
        self.export(spec=replace(AxleBlock(),length_mm=48.0))
        with self.assertRaisesRegex(CADReject,'exceeds declared build envelope'):
            validate(self.folder)

    def test_corrupted_mesh_does_not_pass_step_parity(self):
        self.export()
        trimesh.creation.box(extents=(38.,30.,24.)).export(self.folder/'part.stl')
        with self.assertRaisesRegex(CADReject,'volume differs'):
            validate(self.folder)

    def test_degenerate_nonmanifold_mesh_is_rejected(self):
        self.export()
        mesh=trimesh.load_mesh(self.folder/'part.stl')
        mesh.update_faces(range(len(mesh.faces)-1))
        mesh.export(self.folder/'part.stl')
        with self.assertRaisesRegex(CADReject,'not watertight'):
            validate(self.folder)

    def test_false_millimetre_declaration_is_rejected(self):
        self.export()
        p=self.folder/'interface.json'
        doc=json.loads(p.read_text())
        doc['units']='inches'
        p.write_text(json.dumps(doc))
        with self.assertRaisesRegex(CADReject,'schema or unit'):
            validate(self.folder)

    def test_step_stl_bounds_mismatch_is_rejected(self):
        self.export()
        mesh=trimesh.load_mesh(self.folder/'part.stl')
        mesh.apply_translation((5,0,0))
        mesh.export(self.folder/'part.stl')
        with self.assertRaises(CADReject):
            validate(self.folder)

if __name__=='__main__':
    unittest.main()
