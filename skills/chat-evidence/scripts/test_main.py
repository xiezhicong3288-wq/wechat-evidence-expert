#!/usr/bin/env python3
"""Synthetic acceptance checks for the installed evidence helper.

Run with Python's standard library. Inputs and outputs remain in a temporary
directory outside the skill. No real chat records or network calls are used.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().with_name("main.py")


class EvidenceAcceptance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="wechat-evidence-acceptance-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = {
            "chat": "合成材料",
            "is_group": False,
            "messages": [
                {"msg_id": "m-contract", "timestamp": 1767225660,
                 "sender": "合成人甲", "sender_id": "synthetic-a", "type": "text",
                 "content": "合同金额 50000 元，是否付款另核凭证。", "extra": {}},
                {"msg_id": "m-ack", "timestamp": 1767225600,
                 "sender": "合成人乙", "sender_id": "synthetic-b", "type": "text",
                 "content": "好的。", "extra": {}},
                {"msg_id": "m-denial", "timestamp": 1767225720,
                 "sender": "合成人甲", "sender_id": "synthetic-a", "type": "text",
                 "content": "我只是收到方案，尚未同意合同。", "extra": {}},
                {"msg_id": "m-transfer", "timestamp": 1767225780,
                 "sender": "合成人乙", "sender_id": "synthetic-b", "type": "transfer",
                 "content": "", "extra": {"amount": 10000, "status": "unknown"}},
            ],
        }
        self.export = self.write("input.json", self.data)
        self.identity = self.write("identity.json", {
            "synthetic-a": {"real_name": "合成姓名", "phone": "synthetic-phone", "org": "合成机构"}
        })
        self.claims = self.write("claims.json", [{
            "claim": "存在合同金额讨论", "ground_msg_ids": ["m-contract", "idx:2"]
        }])
        self.originals = {p: p.read_bytes() for p in (self.export, self.identity, self.claims)}

    def write(self, name, value):
        p = self.root / name
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def call(self, *args, ok=True):
        proc = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              capture_output=True, text=True, encoding="utf-8", timeout=15)
        if ok:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        else:
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def assert_originals(self):
        for p, original in self.originals.items():
            self.assertEqual(p.read_bytes(), original, str(p))

    def test_complete_workflow_and_hash_scope(self):
        out = self.root / "bundle"
        self.call("--export", self.export, "--identity", self.identity,
                  "--claims", self.claims, "--out", out, "all")
        expected = {"input.anchor.json", "input.evidence_index.json", "input.timeline.md",
                    "input.toulmin.md", "input.identity.md"}
        self.assertEqual({p.name for p in out.iterdir()}, expected)
        anchor = json.loads((out / "input.anchor.json").read_text(encoding="utf-8"))
        self.assertEqual(anchor["file_sha256"], hashlib.sha256(self.originals[self.export]).hexdigest())
        self.assertEqual(anchor["message_count"], 4)
        self.assertNotEqual(anchor["trusted_timestamp"]["status"], "issued")
        declaration = anchor["pre_chain_declaration"]
        self.assertIsNone(declaration["source"])
        self.assertIsNone(declaration["statement"])
        self.assertIsNone(declaration["clean_env"])
        self.assertEqual(anchor["messages"][0]["msg_id"], "m-contract")
        timeline = (out / "input.timeline.md").read_text(encoding="utf-8")
        self.assertLess(timeline.index("idx:1;"), timeline.index("idx:0;"))
        self.assertIn("UTC", timeline)
        self.assert_originals()

    def test_short_confirmations_are_reviewed(self):
        out = self.root / "index.json"
        self.call("--export", self.export, "--out", out, "extract")
        rows = {r["idx"]: r for r in json.loads(out.read_text(encoding="utf-8"))}
        self.assertTrue(rows[1]["need_review"])
        self.assertTrue(rows[2]["need_review"])
        self.assertEqual(rows[1]["msg_id"], "m-ack")
        self.assertEqual(rows[1]["source_location"], "messages[1]")

    def test_identity_fields_never_imply_verification(self):
        out = self.root / "identity.md"
        self.call("--export", self.export, "--identity", self.identity, "--out", out, "identity")
        report = out.read_text(encoding="utf-8")
        self.assertIn("身份未核验", report)
        self.assertNotIn("已印证", report)

    def test_inputs_cannot_be_output_targets(self):
        for source in self.originals:
            with self.subTest(source=source.name):
                self.call("--export", self.export, "--identity", self.identity,
                          "--claims", self.claims, "--out", source, "anchor", ok=False)
                self.assert_originals()

    def test_existing_file_and_links_are_not_overwritten(self):
        existing = self.root / "existing.json"
        existing.write_bytes(b"preserve")
        self.call("--export", self.export, "--out", existing, "anchor", ok=False)
        self.assertEqual(existing.read_bytes(), b"preserve")

    def test_hardlink_is_not_overwritten_when_permitted(self):
        hardlink = self.root / "hardlink.json"
        try:
            os.link(self.export, hardlink)
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) in (5, 1314):
                self.skipTest("Windows hardlink privilege unavailable")
            raise
        self.call("--export", self.export, "--out", hardlink, "anchor", ok=False)

    def test_symlinks_are_not_overwritten_when_permitted(self):
        symlink = self.root / "symlink.json"
        dangling = self.root / "dangling.json"
        try:
            symlink.symlink_to(self.export)
            dangling.symlink_to(self.root / "absent.json")
        except OSError as exc:
            if os.name == "nt" and getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows symlink privilege unavailable")
            raise
        for out in (symlink, dangling):
            with self.subTest(path=out.name):
                self.call("--export", self.export, "--out", out, "anchor", ok=False)
        self.assertFalse((self.root / "absent.json").exists())
        self.assert_originals()

    def test_all_refuses_existing_directory_and_preflights(self):
        out = self.root / "existing"
        out.mkdir()
        self.call("--export", self.export, "--out", out, "all", ok=False)
        self.assertEqual(list(out.iterdir()), [])
        collision = self.root / "input.identity.md"
        collision.write_bytes(b"preserve")
        self.call("--export", self.export, "all", ok=False)
        self.assertFalse((self.root / "input.anchor.json").exists())
        self.assertEqual(collision.read_bytes(), b"preserve")

    def test_invalid_structure_fails_before_output(self):
        cases = [{}, {"messages": {}}, {"messages": ["bad-row"]}]
        for field, value in [("timestamp", True), ("timestamp", float("nan")),
                             ("timestamp", "2026-01-01"), ("sender", ""),
                             ("content", []), ("extra", [])]:
            data = copy.deepcopy(self.data)
            data["messages"][0][field] = value
            cases.append(data)
        duplicate = copy.deepcopy(self.data)
        duplicate["messages"][1]["msg_id"] = duplicate["messages"][0]["msg_id"]
        cases.append(duplicate)
        for i, data in enumerate(cases):
            with self.subTest(case=i):
                source = self.write("invalid-%d.json" % i, data)
                out = self.root / ("invalid-output-%d" % i)
                self.call("--export", source, "--out", out, "all", ok=False)
                self.assertFalse(out.exists())

    def test_unknown_and_duplicate_claim_refs_fail_before_output(self):
        for i, refs in enumerate([["missing-message"], ["m-contract", "idx:0"], ["idx:500"]]):
            with self.subTest(refs=refs):
                claims = self.write("bad-claims-%d.json" % i, [{"claim": "合成主张", "ground_msg_ids": refs}])
                out = self.root / ("bad-claims-output-%d" % i)
                self.call("--export", self.export, "--claims", claims, "--out", out, "all", ok=False)
                self.assertFalse(out.exists())

    def test_positional_and_native_ambiguity_is_rejected(self):
        data = copy.deepcopy(self.data)
        data["messages"][1]["msg_id"] = "idx:0"
        source = self.write("ambiguous.json", data)
        claims = self.write("ambiguous-claims.json", [{"claim": "合成主张", "ground_msg_ids": ["idx:0"]}])
        self.call("--export", source, "--claims", claims, "--out", self.root / "ambiguous.md",
                  "toulmin", ok=False)

    def test_missing_native_ids_are_not_fabricated(self):
        data = copy.deepcopy(self.data)
        for row in data["messages"]:
            row.pop("msg_id")
        source = self.write("no-native-id.json", data)
        out = self.root / "no-native-id.anchor.json"
        self.call("--export", source, "--out", out, "anchor")
        rows = json.loads(out.read_text(encoding="utf-8"))["messages"]
        self.assertEqual([r["idx"] for r in rows], list(range(4)))
        self.assertTrue(all("msg_id" not in r for r in rows))

    def test_runtime_state_requires_external_explicit_directory(self):
        self.call("reflect", "--kind", "correction", "--note", "合成反馈", ok=False)
        blocked = SCRIPT.parent.parent / "acceptance-must-not-exist"
        self.call("--state-dir", blocked, "reflect", "--kind", "correction", "--note", "合成反馈", ok=False)
        self.assertFalse(blocked.exists())
        state = self.root / "state"
        self.call("--state-dir", state, "reflect", "--kind", "correction", "--note", "合成反馈")
        self.assertIn("合成反馈", (state / "vault" / "corrections.md").read_text(encoding="utf-8"))

    def test_rule_proposals_do_not_claim_activation(self):
        state = self.root / "state"
        result = self.call("--state-dir", state, "learn", "--rule", "合成规则", "--reasoning", "合成理由")
        proposals = list((state / "rules").glob("*.json"))
        self.assertEqual(len(proposals), 1)
        self.assertEqual(json.loads(proposals[0].read_text(encoding="utf-8"))["status"], "proposed")
        self.assertIn("不会读取规则文件", result.stdout)

    def test_regression_is_bound_to_exact_input(self):
        state = self.root / "state"
        first = self.call("--export", self.export, "--state-dir", state, "regress")
        self.assertIn("不代表回归通过", first.stdout)
        second = self.call("--export", self.export, "--state-dir", state, "regress")
        self.assertIn("同一输入哈希", second.stdout)
        changed = copy.deepcopy(self.data)
        changed["messages"][0]["content"] = "另一份合成输入"
        other = self.write("changed.json", changed)
        self.call("--export", other, "--state-dir", state, "regress")
        bases = list((state / "vault" / "baselines").glob("*.json"))
        self.assertEqual(len(bases), 2)
        expected = {hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.export, other)}
        self.assertEqual({json.loads(p.read_text(encoding="utf-8"))["input_sha256"] for p in bases}, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
