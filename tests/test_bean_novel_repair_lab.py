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
                "model": "openai/gpt-4.1", "provider": "github_models",
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


    def test_empty_provider_response_is_reported_without_token(self):
        class Reply:
            headers = {"Content-Type": "application/json"}
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self, *_):
                return b""
        with patch.object(lab.request, "urlopen", return_value=Reply()):
            with self.assertRaisesRegex(RuntimeError, "MODEL_EMPTY_BODY_application/json") as c:
                lab.ask_model("def f(): pass", "assert True", token="supersecret", model="openai/gpt-4.1")
        self.assertNotIn("supersecret", str(c.exception))

    def test_nonjson_provider_response_is_classified_without_leaking_body(self):
        class Reply:
            headers = {"Content-Type": "text/html; charset=utf-8"}
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self, *_):
                return b"<html>opaque body should not appear in receipt</html>"
        with patch.object(lab.request, "urlopen", return_value=Reply()):
            with self.assertRaisesRegex(RuntimeError, "MODEL_NON_JSON_text/html") as c:
                lab.ask_model("def f(): pass", "assert True", token="secret", model="openai/gpt-4.1")
        self.assertNotIn("opaque", str(c.exception))


    def test_fallback_uses_openrouter_only_after_provider_failure(self):
        with (patch.object(lab, "ask_model", side_effect=RuntimeError("MODEL_NON_JSON_text/plain_bytes_4")),
              patch.object(lab, "ask_openrouter", return_value=self.fixed) as alt):
            source, provider = lab.peer_model_draft(
                self.original, "sealed", token="github-token",
                model="openai/gpt-4.1", alternate_token="openrouter-token")
        self.assertEqual((source, provider), (self.fixed, "openrouter"))
        self.assertEqual(alt.call_count, 1)

    def test_no_false_fallback_when_no_secondary_provider(self):
        with patch.object(lab, "ask_model", side_effect=RuntimeError("MODEL_NON_JSON_text/plain_bytes_4")):
            with self.assertRaisesRegex(RuntimeError, "MODEL_NON_JSON"):
                lab.peer_model_draft(self.original, "sealed", token="github-token",
                                     model="openai/gpt-4.1", alternate_token="")

    def test_alternate_provider_can_work_without_github_token(self):
        with patch.object(lab, "ask_openrouter", return_value=self.fixed) as alt:
            source, provider = lab.peer_model_draft(
                self.original, "sealed", token="", model="openai/gpt-4.1",
                alternate_token="openrouter-token")
        self.assertEqual(provider, "openrouter")
        self.assertEqual(source, self.fixed)
        self.assertEqual(alt.call_count, 1)

    def test_api_keys_removed_from_subprocess_test_environment(self):
        observed = {}
        def fake_run(args, **kw):
            observed.update(kw.get("env", {}))
            return SimpleNamespace(returncode=0, stderr="Ran 1 test", stdout="")
        with (patch.dict(lab.os.environ, {
                 "BEAN_MODELS_TOKEN": "token_a", "OPENROUTER_API_KEY": "token_b",
                 "GITHUB_TOKEN": "token_c", "GH_TOKEN": "token_d"}),
              patch.object(lab.subprocess, "run", side_effect=fake_run)):
            lab.suite(self.root)
        for name in ("BEAN_MODELS_TOKEN", "OPENROUTER_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"):
            self.assertNotIn(name, observed)

    def test_openrouter_json_source_response_is_real_model_text(self):
        class Reply:
            headers = {"Content-Type": "application/json"}
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, *_):
                return json.dumps({"choices":[{"message":{"content":"def model_fix():\n    return 42"}}]}).encode()
        with patch.object(lab.request, "urlopen", return_value=Reply()) as mocked:
            result = lab.ask_openrouter("def f():pass\n", "assert True", 
                                        token="fake-only-test", model="openai/gpt-4.1")
        self.assertEqual(result, "def model_fix():\n    return 42\n")
        self.assertEqual(mocked.call_count, 1)


if __name__ == "__main__":
    unittest.main()
