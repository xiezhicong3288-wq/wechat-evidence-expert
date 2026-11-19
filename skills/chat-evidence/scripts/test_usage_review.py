"""Round-trip checks for feedback records using synthetic receipts."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from usage_review import load_record, save_record


SCRIPT = Path(__file__).with_name("main.py")


class UsageReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="wechat-review-test-")
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        self.receipt = directory / "receipt.json"
        self.state = directory / "state"

    def invoke(self, receipt, *opts, origin="synthetic", code=0):
        raw = json.dumps(receipt, ensure_ascii=False).encode("utf-8")
        self.receipt.write_bytes(raw)
        command = [sys.executable, str(SCRIPT), "--state-dir", str(self.state),
                   "review-use", "--receipt", str(self.receipt), "--origin", origin, *opts]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(self.receipt.read_bytes(), raw)
        return json.loads(result.stdout) if code == 0 else None

    def test_archive_receipt_keeps_only_safe_counts_and_is_repeatable(self):
        receipt = {"schema": "moect-neutral-archive/1", "completed": True, "status": "partial", "exit_code": 1,
                   "counts": {"top_level_messages": 7, "warnings": 2, "private_count": 12},
                   "account_scope": "synthetic-private-account", "originals": ["synthetic-private-file"]}
        first = self.invoke(receipt, "--skill-version", "0.3.0")
        self.assertEqual(first, self.invoke(receipt, "--skill-version", "0.3.0"))
        self.invoke(receipt, "--skill-version", "0.4.0", code=2)
        self.assertEqual(first["counts"], {"top_level_messages": 7, "warnings": 2})
        self.assertEqual(first["next_step"], "check_source_scope_or_reproduce")
        self.assertEqual(first["receipt_sha256"], hashlib.sha256(self.receipt.read_bytes()).hexdigest())
        paths = list(self.state.rglob("*.json"))
        self.assertEqual(len(paths), 1)
        self.assertNotIn("synthetic-private", paths[0].read_text(encoding="utf-8"))

    def test_demo_and_inconsistent_receipts_are_rejected(self):
        demo = {"normalization": "success", "source_database_audit": "not_provided",
                "source_demo": True, "message_count": 1, "issues": 0}
        self.invoke(demo, origin="actual", code=2)
        self.invoke(demo, "--feedback", "confirmed", code=2)
        observation = {"schema": "wechat-use-observation/1", "stage": "analysis", "status": "success", "exit_code": 2}
        self.invoke(observation, code=2)
        self.assertFalse(self.state.exists())

    def test_observed_operator_feedback_has_a_separate_record(self):
        # Exercise declared-origin mechanics without claiming the fixture is a real run.
        receipt = {"schema": "wechat-use-observation/1", "stage": "analysis", "status": "success", "exit_code": 0}
        first = self.invoke(receipt, origin="actual")
        second = self.invoke(receipt, origin="actual")
        self.assertEqual(first["next_step"], "await_feedback")
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.invoke(receipt, "--feedback", "corrected", origin="actual", code=2)
        correction = self.invoke(receipt, "--feedback", "corrected", "--run-id", first["run_id"], origin="actual")
        self.assertEqual(correction["command"], "observed-analysis")
        self.assertEqual(correction["next_step"], "reproduce_feedback")
        self.assertEqual(len(list(self.state.rglob("*.json"))), 3)

    def test_attachment_notes_keep_successful_conversion_status(self):
        receipt = {"normalization": "success", "source_database_audit": "not_provided",
                   "message_count": 1, "issues": 2}
        record = self.invoke(receipt)
        self.assertEqual(record["result"], "success")
        self.assertEqual(record["next_step"], "review_reported_scope")

    def test_waylon_preflight_maps_status_without_copying_details(self):
        receipt = {"schema": "moect-input-inspection/1", "status": "blocked", "exit_code": 2,
                   "input_count": 1, "inputs": [{"input_index": 1, "ignored": "synthetic-detail"}]}
        record = self.invoke(receipt)
        self.assertEqual((record["command"], record["result"]), ("waylon-inspect", "failed"))
        self.assertEqual(record["counts"], {"input_count": 1})

    def test_failed_publication_can_be_retried_without_partial_record(self):
        self.state.mkdir()
        output = self.state / "test-record"
        expected = {"schema": "wechat-use-review/1"}
        with patch.object(Path, "rename", side_effect=OSError("synthetic interruption")):
            with self.assertRaises(OSError):
                save_record(output, expected)
        self.assertEqual(list(self.state.iterdir()), [])
        save_record(output, expected)
        self.assertEqual(load_record(output), expected)
