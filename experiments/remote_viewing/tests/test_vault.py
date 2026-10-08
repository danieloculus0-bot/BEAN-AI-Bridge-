import tempfile
import unittest
from pathlib import Path

from experiments.remote_viewing.rv_protocol import (
    initialize, observation, close_trial, reveal, json_read, canonical, digest
)
from experiments.remote_viewing.gate import blind_packet, judge, final_result, binomial_tail

PASSWORD = "correct-horse-battery-staple-not-a-production-secret"

class BlindVaultTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "trial"
        self.manifest = initialize(self.root, PASSWORD)

    def test_secrecy_and_immutable_trial(self):
        public = (self.root / "challenge.json").read_text()
        self.assertNotIn("candidates", public)
        self.assertNotIn("target_index", public)
        self.assertEqual(self.manifest["candidate_count"], 4)
        with self.assertRaises(PermissionError):
            reveal(self.root, PASSWORD)
        with self.assertRaises(PermissionError):
            blind_packet(self.root, PASSWORD)
        with self.assertRaises(FileExistsError):
            initialize(self.root, PASSWORD)

    def test_all_gates(self):
        sealed = observation(self.root, "cold spiraling metallic object, oddly bright", "chat-123")
        with self.assertRaises(FileExistsError):
            observation(self.root, "edited to cheat", "chat-123")
        with self.assertRaises(ValueError):
            close_trial(self.root, "0"*64, True)
        with self.assertRaises(ValueError):
            close_trial(self.root, sealed["observation_sha256"], False)
        closed = close_trial(self.root, sealed["observation_sha256"], True)
        self.assertTrue(closed["operator_attests_chat_closed"])
        packet = blind_packet(self.root, PASSWORD)
        self.assertEqual(len(packet["candidates"]), 4)
        self.assertNotIn("target_index", str(packet))
        with self.assertRaises(PermissionError):
            final_result(self.root, PASSWORD)
        response = judge(self.root, 0, "judge-one")
        self.assertTrue(response["locked"])
        with self.assertRaises(FileExistsError):
            judge(self.root, 1, "judge-one")
        result = final_result(self.root, PASSWORD)
        self.assertTrue(result["verified"])
        self.assertEqual(result["target"], result["bundle"]["candidates"][result["bundle"]["target_index"]])
        self.assertEqual(result["hit"], result["bundle"]["target_index"] == 0)

    def test_tampered_commitment_fails(self):
        sealed = observation(self.root, "blue crystal", "chat-xyz")
        close_trial(self.root, sealed["observation_sha256"], True)
        modified = json_read(self.root / "challenge.json")
        modified["commitment_sha256"] = "f"*64
        (self.root / "challenge.json").write_bytes(canonical(modified))
        with self.assertRaises(ValueError):
            blind_packet(self.root, PASSWORD)

    def test_tampered_observation_fails(self):
        sealed = observation(self.root, "blue crystal", "chat-xyz")
        close_trial(self.root, sealed["observation_sha256"], True)
        modified = json_read(self.root / "observation.lock.json")
        modified["observation"]["description"] = "replaced after commit"
        (self.root / "observation.lock.json").write_bytes(canonical(modified))
        # This emphasizes verification at externally timestamped observation hash,
        # performed by independent auditors, not only a local mutable file.
        self.assertNotEqual(digest(canonical(modified["observation"])), modified["observation_sha256"])
        with self.assertRaises(ValueError):
            blind_packet(self.root, PASSWORD)

    def test_blind_judge_input_validation(self):
        sealed = observation(self.root, "square metal", "chat-abc")
        close_trial(self.root, sealed["observation_sha256"], True)
        for index in (-1, 4, True, "0"):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    judge(self.root, index, "judge-one")

    def test_exact_null_probability(self):
        self.assertAlmostEqual(binomial_tail(1, 1), 0.25)
        self.assertAlmostEqual(binomial_tail(4, 4), 0.25**4)
        self.assertEqual(binomial_tail(0, 1618), 1.0)
        self.assertLess(binomial_tail(700, 1618), 1e-30)

if __name__ == "__main__":
    unittest.main()
