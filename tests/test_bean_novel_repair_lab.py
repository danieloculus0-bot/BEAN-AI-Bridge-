"""Independent safety/contract tests for BEAN's novel self-repair path.

No hosted model or external network required. These are protocol tests, not
proof that an LLM can solve the unknown issue.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools import bean_novel_repair as lab


class NovelRepairLabTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name) / "root"
        self.challenge = Path(self.work.name) / "challenge"
        (self.root / lab.SOURCE.parent).mkdir(parents=True)
        (self.root / lab.ORACLE.parent).mkdir(parents=True)
        (self.challenge / lab.ORACLE.parent).mkdir(parents=True)
        (self.root / lab.SOURCE).write_text("def f():\n    return 0\n")
        (self.challenge / lab.ORACLE).write_text("def test_synthetic():\n    assert True\n")
        self.fixed = "def f():\n    return 1\n"
        self.original = (self.root / lab.SOURCE).read_text()
        self.head = "a"*40

    def head_for(self, root):
        return lab.CHALLENGE_SHA if Path(root) == self.challenge else self.head

    def candidate(self):
        return {"schema": "bean.novel-repair.v1",
                "base_commit": self.head,
                "challenge_commit": lab.CHALLENGE_SHA,
                "path": lab.SOURCE.as_posix(),
                "source_sha256": lab.sha(self.original),
                "oracle_sha256": lab.sha((self.challenge/lab.ORACLE).read_text()),
                "replacement_sha256": lab.sha(self.fixed),
                "changed_lines": 2,
                "model": "openai/gpt-4.1",
                "replacement": self.fixed}

    def test_rejects_unchanged_source(self):
        with self.assertRaisesRegex(ValueError, "unchanged"):
            lab.difference("pass\n", "pass\n")

    def test_rejects_invalid_python(self):
        with self.assertRaises(SyntaxError):
            lab.difference("x=1\n", "def broken(:\n")

    def test_rejects_oversized_changes(self):
        with self.assertRaisesRegex(ValueError, "100-line"):
            lab.difference("pass\n", "\n".join("x%d=%d" % (i,i) for i in range(120)))

    def test_denies_unknown_target(self):
        record = self.candidate()
        record["path"] = "tools/bean_novel_repair.py"
        with patch.object(lab, "git_head", side_effect=self.head_for):
            with self.assertRaisesRegex(ValueError, "unauthorized"):
                lab.check(record, self.root, self.challenge)

    def test_source_integrity_catches_stale_revision(self):
        record = self.candidate()
        (self.root / lab.SOURCE).write_text("def new(): pass\n")
        with patch.object(lab, "git_head", side_effect=self.head_for):
            with self.assertRaisesRegex(ValueError, "source digest"):
                lab.check(record, self.root, self.challenge)

    def test_oracle_integrity_catches_changes(self):
        record = self.candidate()
        (self.challenge / lab.ORACLE).write_text("def tampered(): pass\n")
        with patch.object(lab, "git_head", side_effect=self.head_for):
            with self.assertRaisesRegex(ValueError, "oracle digest"):
                lab.check(record, self.root, self.challenge)

    def test_model_without_token_fails(self):
        with self.assertRaisesRegex(RuntimeError, "NO_MODEL_TOKEN"):
            lab.ask_model("x=1\n", "assert True", token="", model="openai/gpt-4.1")

    def test_candidate_requires_actual_change(self):
        with patch.object(lab, "git_head", side_effect=self.head_for):
            result = lab.check(self.candidate(), self.root, self.challenge)
        self.assertEqual(result["changed_lines"], 2)

    def test_generate_does_not_write_untested_model_source_to_tree(self):
        receipt = self.root / ".bean-peer" / "gen.json"
        candidate = self.root / ".bean-peer" / "candidate.json"
        with (patch.object(lab, "git_head", side_effect=self.head_for),
              patch.object(lab, "witness", return_value={"normal_passed": True, "oracle_red": True}),
              patch.object(lab, "ask_model", return_value=self.fixed)):
            result = lab.produce(self.root, self.challenge, candidate, receipt,
                                 "openai/gpt-4.1", "fake")
        self.assertEqual(result, 0)
        self.assertEqual((self.root / lab.SOURCE).read_text(), self.original)
        self.assertEqual(json.loads(receipt.read_text())["result"], "drafted_not_verified")

    def test_validator_only_keeps_verified_artifact_and_restores_source(self):
        candidate = self.root / ".bean-peer" / "candidate.json"
        receipt = self.root / ".bean-peer" / "validate.json"
        lab.save(candidate, self.candidate())
        with (patch.object(lab, "git_head", side_effect=self.head_for),
              patch.object(lab, "witness", return_value={"normal_passed": True, "oracle_red": True}),
              patch.object(lab, "suite", return_value=SimpleNamespace(returncode=0, stderr="", stdout="OK"))):
            code = lab.verify(self.root, self.challenge, candidate, receipt, self.root/"validated")
        self.assertEqual(code, 0)
        self.assertEqual((self.root / lab.SOURCE).read_text(), self.original)
        self.assertFalse((self.root / lab.ORACLE).exists())
        self.assertEqual((self.root/"validated"/lab.SOURCE).read_text(), self.fixed)
        self.assertEqual(json.loads(receipt.read_text())["result"], "validated_on_one_platform")

    def test_failed_validator_restores_source_without_publishing(self):
        candidate = self.root / ".bean-peer" / "candidate.json"
        receipt = self.root / ".bean-peer" / "validate.json"
        lab.save(candidate, self.candidate())
        with (patch.object(lab, "git_head", side_effect=self.head_for),
              patch.object(lab, "witness", return_value={"normal_passed": True, "oracle_red": True}),
              patch.object(lab, "suite", return_value=SimpleNamespace(returncode=1, stderr="FAILED", stdout=""))):
            code = lab.verify(self.root, self.challenge, candidate, receipt, self.root/"validated")
        self.assertEqual(code, 1)
        self.assertEqual((self.root / lab.SOURCE).read_text(), self.original)
        self.assertFalse((self.root / lab.ORACLE).exists())
        self.assertFalse((self.root/"validated"/lab.SOURCE).exists())
        self.assertEqual(json.loads(receipt.read_text())["result"], "rejected")


if __name__ == "__main__":
    unittest.main()
