#!/usr/bin/env python3
"""Synthetic, offline checks for the Moect entry point. No real chats."""

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from moect_adapter import normalize


SCRIPT = Path(__file__).with_name("main.py")


class MoectAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wechat-moect-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "Sample_abc.json"
        self.assets = self.root / "Sample_abc_assets"
        self.assets.mkdir()
        self.data = {
            "metadata": {"application": "Moect", "version": "1.2.8",
                         "name": "合成昵称", "session": "wxid_synthetic",
                         "exported_at": "2026-11-12T22:51:26", "time_zone": "Asia/Shanghai"},
            "messages": [
                {"server_id": "id1", "local_id": 1, "create_time": 1767225600,
                 "time_str": "2026-01-01 08:00:00", "sender": "合成甲",
                 "sender_wxid": "wxid_a", "kind": "text", "text": "=2+2",
                 "extra": {}, "resources": []},
                {"server_id": "id2", "local_id": 2, "create_time": 1767225660,
                 "sender": "合成乙", "sender_wxid": "wxid_b", "kind": "transfer",
                 "text": "[转账]", "extra": {"transfer": {"amount": "￥12.30", "state": "unknown"}},
                 "resources": []},
                {"server_id": "id3", "local_id": 3, "create_time": 1767225720,
                 "sender": "合成甲", "sender_wxid": "wxid_a", "kind": "image",
                 "text": "[图片]", "extra": {},
                 "resources": [{"path": "Sample_abc_assets/resources/unused.dat",
                                "kind": "original", "status": "encrypted"}]},
                {"server_id": "id4", "local_id": 4, "create_time": 1767225780,
                 "sender": "合成乙", "sender_wxid": "wxid_b", "kind": "quote",
                 "text": "[引用]", "extra": {}, "resources": [],
                 "quote": {"server_id": "embedded", "kind": "file", "text": "[文件]",
                           "resources": [{"kind": "file", "status": "missing", "path": ""}]}},
                {"server_id": "id5", "local_id": 5, "create_time": 1767225840,
                 "sender": "系统", "sender_wxid": "", "kind": "appmsg",
                 "text": "[应用消息]", "extra": {}, "resources": []},
            ],
            "count": 5,
        }
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        self.report = self.assets / "resource-report.jsonl"
        self.report.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in [
            {"message_id": "id3", "kind": "image", "status": "encrypted", "resources": []},
            {"message_id": "embedded", "kind": "file", "status": "missing", "resources": []},
        ]) + "\n", encoding="utf-8")
        self.source_bytes, self.report_bytes = self.source.read_bytes(), self.report.read_bytes()

    def run_cli(self, *parts, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, parts)],
                                capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def test_neutral_data_and_followup_commands(self):
        dest = self.root / "out"
        self.run_cli("--export", self.source, "--out", dest, "neutral-moect")
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["message_count"], 5)
        self.assertEqual(manifest["resource_report_rows"], 2)
        self.assertEqual(manifest["mapped_transfer_amounts"], 1)
        self.assertEqual(manifest["top_level_attachment_references"], 1)
        self.assertEqual(manifest["embedded_attachment_references"], 1)
        self.assertEqual(manifest["source_database_audit"], "not_provided")
        compatible = json.loads((dest / "compatible.json").read_text(encoding="utf-8"))
        self.assertEqual(len(compatible["messages"]), 5)
        self.assertEqual(compatible["messages"][1]["extra"]["amount"], 12.3)
        self.assertEqual(compatible["messages"][1]["extra"]["amount_exact"], "12.30")
        self.assertEqual(compatible["messages"][4]["type"], "appmsg")
        self.assertNotIn("sender_id", compatible["messages"][4])
        self.run_cli("--export", dest / "compatible.json", "validate")
        self.run_cli("--export", dest / "compatible.json", "--out",
                     self.root / "anchor.json", "anchor")
        reports = [json.loads(line) for line in
                   (dest / "resource_report_index.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(reports[1]["matched_positions"], ["$.messages[3].quote"])
        self.assertEqual(reports[1]["raw_report"]["status"], "missing")
        attachments = [json.loads(line) for line in
                       (dest / "attachment_index.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(attachments[1]["source_pointer"], "$.messages[3].quote.resources[0]")
        self.assertEqual(attachments[1]["record_role"], "embedded")
        self.assertEqual(len(list((dest / "按消息类型").glob("*.csv"))), 5)
        with (dest / "conversation_index.csv").open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["content_display"], "'=2+2")
        nickname_path = manifest["nickname_index_file"]
        self.assertTrue(nickname_path.startswith("按昵称/"))
        with (dest / nickname_path).open(encoding="utf-8-sig", newline="") as f:
            nickname_rows = list(csv.DictReader(f))
        self.assertEqual(nickname_rows, rows)
        with (dest / "nickname_index.csv").open(encoding="utf-8-sig", newline="") as f:
            nickname_table = list(csv.DictReader(f))
        self.assertEqual(nickname_table[0]["index_file"], nickname_path)
        self.assertEqual(nickname_table[0]["session"], "wxid_synthetic")
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(self.report.read_bytes(), self.report_bytes)

    def test_rejects_existing_output_without_overwriting(self):
        dest = self.root / "occupied"
        dest.mkdir()
        marker = dest / "keep.txt"
        marker.write_text("unchanged", encoding="utf-8")
        self.run_cli("--export", self.source, "--out", dest, "neutral-moect", ok=False)
        self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")

    def test_rejects_count_mismatch_before_writing(self):
        self.data["count"] = 4
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        dest = self.root / "bad"
        self.run_cli("--export", self.source, "--out", dest, "neutral-moect", ok=False)
        self.assertFalse(dest.exists())

    def test_rejects_duplicate_json_keys_before_writing(self):
        self.source.write_text('{"metadata":{},"messages":[],"messages":[],"count":0}', encoding="utf-8")
        dest = self.root / "bad"
        self.run_cli("--export", self.source, "--out", dest, "neutral-moect", ok=False)
        self.assertFalse(dest.exists())

    def test_unknown_type_is_preserved_and_overlong_type_rejected(self):
        self.data["messages"][4]["kind"] = "new_exporter_type"
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        dest = self.root / "unknown"
        self.run_cli("--export", self.source, "--out", dest, "neutral-moect")
        self.assertEqual(json.loads((dest / "compatible.json").read_text(encoding="utf-8"))
                         ["messages"][4]["type"], "new_exporter_type")
        self.data["messages"][4]["kind"] = "x" * 81
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        failed = self.root / "invalid"
        self.run_cli("--export", self.source, "--out", failed, "neutral-moect", ok=False)
        self.assertFalse((failed / "manifest.json").exists())

    def test_reused_export_id_keeps_both_records_without_forging_unique_id(self):
        self.data["messages"][4]["server_id"] = "id1"
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        dest = self.root / "reused"
        self.run_cli("--export", self.source, "--out", dest, "neutral-moect")
        messages = json.loads((dest / "compatible.json").read_text(encoding="utf-8"))["messages"]
        self.assertEqual(len(messages), 5)
        self.assertNotIn("msg_id", messages[4])
        self.assertEqual(messages[4]["extra"]["source_raw"]["server_id"], "id1")
        self.assertEqual(json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
                         ["issue_counts"]["duplicate_server_id"], 1)

    def test_source_change_does_not_write_success_manifest(self):
        original_read = Path.read_bytes
        source_reads = 0

        def changed_second_read(path):
            nonlocal source_reads
            value = original_read(path)
            if path == self.source:
                source_reads += 1
                if source_reads > 1:
                    return value + b" "
            return value

        dest = self.root / "changed"
        with mock.patch.object(Path, "read_bytes", changed_second_read):
            with self.assertRaisesRegex(ValueError, "发生变化"):
                normalize(self.source, dest)
        self.assertFalse((dest / "manifest.json").exists())

    def test_missing_server_id_still_indexes_attachments(self):
        self.data["messages"][2].pop("server_id")
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        dest = self.root / "no-id"
        self.run_cli("--export", self.source, "--out", dest, "neutral-moect")
        attachments = [json.loads(line) for line in
                       (dest / "attachment_index.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(attachments[0]["source_pointer"], "$.messages[2].resources[0]")
        self.assertIsNone(attachments[0]["server_id"])
        self.assertEqual(json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
                         ["top_level_attachment_references"], 1)

    def test_nickname_folder_is_safe_and_uses_stable_session(self):
        self.data["metadata"]["name"] = "../CON\\:*?"
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        dest = self.root / "safe-nickname"
        self.run_cli("--export", self.source, "--out", dest, "neutral-moect")
        relative = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))["nickname_index_file"]
        self.assertEqual(Path(relative).parts[0], "按昵称")
        self.assertEqual(len(Path(relative).parts), 3)
        self.assertTrue((dest / relative).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
