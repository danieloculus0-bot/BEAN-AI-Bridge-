"""Structural tests, deliberately not presented as physics results."""
import math
import random
import unittest
import xml.etree.ElementTree as ET
from lab import Design, model_xml, gait, mutation, body_registry, inverse_kinematics

class RobotLabTests(unittest.TestCase):
    def test_xml_shape(self):
        xml=model_xml(Design())
        root=ET.fromstring(xml)
        self.assertEqual(len(root.find("actuator")),8)
        self.assertEqual(len(root.findall(".//joint")),8)
    def test_hardware_constraints(self):
        with self.assertRaises(ValueError):
            model_xml(Design(body_length=2.0))
    def test_cpg_and_ik_are_finite(self):
        d=Design()
        for t in (0,.1,.2,.5,1.8,2.6):
            moves=gait(d,t)
            self.assertEqual(len(moves),8)
            self.assertTrue(all(math.isfinite(x) for x in moves))
            self.assertTrue(all(-.80 <= moves[i] <= .92 for i in (0,2,4,6)))
            self.assertTrue(all(-1.68 <= moves[i] <= -.05 for i in (1,3,5,7)))
    def test_candidate_stays_buildable(self):
        d=Design(); rand=random.Random(106)
        for _ in range(100):
            d=mutation(d,rand)
            model_xml(d)
    def test_registry_is_unwired(self):
        reg=body_registry(Design())
        self.assertEqual(len(reg["joints"]),8)
        self.assertTrue(all(j["servo_channel"] is None and not j["hardware_connected"] for j in reg["joints"]))

if __name__ == "__main__":
    unittest.main()
