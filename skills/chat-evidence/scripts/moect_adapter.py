#!/usr/bin/env python3
"""Loss-aware, offline Moect JSON -> neutral index and evidence-schema input.

No account access, database decryption, OCR, transcription, or legal inference.
All original message objects remain in the source file and messages.jsonl.
"""

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re


MAX_INPUT_BYTES = 128 * 1024 * 1024
AMOUNT = re.compile(r"^[¥￥]\s*([0-9]+(?:\.[0-9]{1,2})?)$")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 中出现重复字段：" + key)
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError("JSON 含非有限数值：" + value)


def _parse(raw):
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_unique,
                      parse_constant=_bad_constant)


def _csv_safe(value):
    text = "" if value is None else str(value)
    return "'" + text if re.match(r"^\s*[=+@-]", text) else text


def _nickname_folder(display_name, session):
    """Human-readable contact label plus stable, collision-resistant session suffix."""
    label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", display_name).strip(" .")[:40].rstrip(" .")
    label = label or "未命名会话"
    if label.upper() in {"CON", "PRN", "AUX", "NUL"} | {"COM" + str(i) for i in range(1, 10)} | {"LPT" + str(i) for i in range(1, 10)}:
        label = "_" + label
    suffix = hashlib.sha256(session.encode("utf-8")).hexdigest()[:12]
    return label + "_" + suffix


def _record_nodes(node, pointer, depth=0):
    if depth > 16:
        raise ValueError("嵌套引用过深，无法安全定位")
    if isinstance(node, dict):
        # A message with no server_id still has a real array position and may
        # carry resources. Never make attachment indexing depend on an ID.
        yield node, pointer
        for key in ("quote", "forward"):
            if key in node:
                yield from _record_nodes(node[key], pointer + "." + key, depth + 1)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _record_nodes(item, pointer + "[" + str(i) + "]", depth + 1)


def _write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def _write_jsonl(path, values):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        for value in values:
            stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")


def _write_csv(path, fields, rows):
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_safe(row.get(key)) for key in fields})


def normalize(source, output, skill_storage=None):
    # On restricted Windows mounts, opening the user-authorized file can be
    # permitted while pathlib.resolve() (GetFinalPathNameByHandle) is denied.
    # Use an absolute path for reading and reject a direct reparse-file input.
    src = Path(os.path.abspath(source))
    dst = Path(output).absolute()
    resolved_dst = dst.resolve()
    if src.is_symlink() or not src.is_file() or src.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("输入必须是小于 128 MiB 的普通 JSON 文件")
    if dst.exists() or dst.is_symlink():
        raise ValueError("拒绝覆盖已有输出目录")
    if not dst.parent.is_dir() or resolved_dst == src:
        raise ValueError("输出目录须位于已有父目录且不得覆盖原始输入")
    if skill_storage:
        storage = str(Path(skill_storage).resolve())
        try:
            inside_skill = os.path.commonpath((str(resolved_dst), storage)) == storage
        except ValueError:  # Separate Windows drives have no common path.
            inside_skill = False
        if inside_skill:
            raise ValueError("运行产物不得写入技能目录")

    raw = src.read_bytes()
    data = _parse(raw)
    if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict) or not isinstance(data.get("messages"), list):
        raise ValueError("输入不是 Moect JSON 导出")
    meta, source_messages = data["metadata"], data["messages"]
    if meta.get("application") != "Moect":
        raise ValueError("未识别的导出程序，不能猜测字段语义")
    if not isinstance(meta.get("name"), str) or not isinstance(meta.get("session"), str):
        raise ValueError("缺少显示名或稳定会话标识")
    if data.get("count") != len(source_messages):
        raise ValueError("导出 count 与实际顶层消息数量不符")
    source_hash = hashlib.sha256(raw).hexdigest()
    compatible = {"chat": meta.get("name", ""), "exported_at": meta.get("exported_at", ""),
                  "source_time_zone": meta.get("time_zone"), "source_metadata": meta,
                  "messages": []}
    if str(meta.get("session", "")).endswith("@chatroom"):
        compatible["is_group"] = True
    index, originals, attachments, issues, ids = [], [], [], [], {}
    type_counts, senders = {}, {}
    mapped_amounts = 0
    for i, msg in enumerate(source_messages):
        ptr = "$.messages[%d]" % i
        if not isinstance(msg, dict):
            raise ValueError(ptr + " 不是消息对象")
        sender, kind, stamp = msg.get("sender"), msg.get("kind"), msg.get("create_time")
        if not isinstance(sender, str) or not sender.strip() or not isinstance(kind, str) or not kind.strip():
            raise ValueError(ptr + " 缺发言人或类型")
        if isinstance(stamp, bool) or not isinstance(stamp, int):
            raise ValueError(ptr + " 的 create_time 不是 Unix 秒整数")
        content = msg.get("text", "")
        if not isinstance(content, str):
            raise ValueError(ptr + " 的 text 不是字符串")
        if not isinstance(msg.get("extra", {}), dict):
            raise ValueError(ptr + " 的 extra 不是对象")
        mid = msg.get("server_id")
        if mid is not None and (isinstance(mid, bool) or not isinstance(mid, (str, int))):
            raise ValueError(ptr + " 的 server_id 类型异常")
        mid = str(mid).strip() if mid is not None else ""
        extra = {"source_pointer": ptr, "source_json_sha256": source_hash,
                 "source_local_id": msg.get("local_id"), "source_time_str": msg.get("time_str"),
                 "source_raw_type": msg.get("raw_type"), "source_raw": msg}
        item = {"timestamp": stamp, "sender": sender, "type": kind,
                "content": content, "extra": extra}
        if mid and mid not in ids:
            item["msg_id"] = mid
        elif mid:
            issues.append({"kind": "duplicate_server_id", "source_pointer": ptr, "server_id": mid,
                           "note": "保留原字段，以数组位置区分；未冒充唯一编号"})
        if mid:
            ids.setdefault(mid, []).append(ptr)
        sid = msg.get("sender_wxid")
        if isinstance(sid, str) and sid.strip():
            item["sender_id"] = sid
        elif sid not in (None, ""):
            raise ValueError(ptr + " 的 sender_wxid 类型异常")
        if kind == "transfer":
            transfer = (msg.get("extra") or {}).get("transfer")
            raw_amount = transfer.get("amount") if isinstance(transfer, dict) else None
            match = AMOUNT.fullmatch(raw_amount) if isinstance(raw_amount, str) else None
            if match:
                try:
                    amount = Decimal(match.group(1))
                except InvalidOperation as exc:
                    raise ValueError(ptr + " 金额字段格式异常") from exc
                item["extra"]["amount"] = int(amount) if amount == int(amount) else float(amount)
                item["extra"]["amount_exact"] = match.group(1)
                item["extra"]["amount_source"] = ptr + ".extra.transfer.amount"
                mapped_amounts += 1
            else:
                issues.append({"kind": "unparsed_transfer_amount", "source_pointer": ptr,
                               "note": "保留原字段，不猜测数值或支付结果"})
        compatible["messages"].append(item)
        originals.append({"source_pointer": ptr, "raw_message": msg})
        resources = msg.get("resources", [])
        if not isinstance(resources, list):
            raise ValueError(ptr + " 的 resources 不是数组")
        for record, record_ptr in _record_nodes(msg, ptr):
            record_resources = record.get("resources", [])
            if not isinstance(record_resources, list):
                raise ValueError(record_ptr + " 的 resources 不是数组")
            for j, resource in enumerate(record_resources):
                if not isinstance(resource, dict):
                    raise ValueError(record_ptr + ".resources[%d] 不是对象" % j)
                attachments.append({"source_pointer": record_ptr + ".resources[%d]" % j,
                                    "parent_pointer": ptr, "record_pointer": record_ptr,
                                    "record_role": "top_level" if record_ptr == ptr else "embedded",
                                    "server_id": record.get("server_id"),
                                    "resource": resource, "inspection": "not_opened"})
        type_counts[kind] = type_counts.get(kind, 0) + 1
        senders[sender] = senders.get(sender, 0) + 1
        index.append({"seq": i + 1, "source_pointer": ptr, "server_id": mid,
                      "local_id": msg.get("local_id"), "sender": sender,
                      "sender_id": sid, "timestamp": stamp, "time_str": msg.get("time_str"),
                      "type": kind, "content_display": content,
                      "resource_status": msg.get("resource_status"),
                      "resource_count": len(resources), "source_sha256": source_hash})

    report_path = src.parent / (src.stem + "_assets") / "resource-report.jsonl"
    report_rows, report_hash = [], None
    positions = {}
    for i, msg in enumerate(source_messages):
        for record, pointer in _record_nodes(msg, "$.messages[%d]" % i):
            key = record.get("server_id")
            if key is not None and str(key).strip():
                positions.setdefault(str(key), []).append(pointer)
    if report_path.is_file():
        report_bytes = report_path.read_bytes()
        report_hash = hashlib.sha256(report_bytes).hexdigest()
        for i, line in enumerate(report_bytes.decode("utf-8-sig").splitlines(), 1):
            report = _parse(line.encode("utf-8"))
            if not isinstance(report, dict):
                raise ValueError("资源报告第 %d 行不是对象" % i)
            refs = positions.get(str(report.get("message_id", "")), [])
            row = {"line": i, "message_id": report.get("message_id"),
                   "kind": report.get("kind"), "status": report.get("status"),
                   "notice": report.get("notice"), "matched_positions": refs,
                   "report_file": str(report_path), "raw_report": report}
            report_rows.append(row)
            if not refs:
                issues.append({"kind": "unmatched_resource_report", "report_line": i,
                               "message_id": row["message_id"]})
            elif len(refs) > 1:
                issues.append({"kind": "multiple_message_appearances", "report_line": i,
                               "matched_positions": refs,
                               "note": "同一导出编号同时出现在顶层消息和引用中，不计为独立缺失"})
            if report.get("status") in ("missing", "encrypted"):
                issues.append({"kind": "resource_" + report["status"], "report_line": i,
                               "matched_positions": refs, "message_id": row["message_id"]})
    else:
        issues.append({"kind": "resource_report_not_provided", "note": "仅整理消息内附件字段"})

    # Exclusive new directory; manifest is written last so interrupted runs
    # cannot be mistaken for a complete result.
    dst.mkdir()
    _write_json(dst / "compatible.json", compatible)
    # The skill's own validator checks the generated file before manifest is
    # written. On a failure the new directory remains diagnostically incomplete.
    from main import load_export
    load_export(str(dst / "compatible.json"))
    _write_jsonl(dst / "messages.jsonl", originals)
    _write_csv(dst / "conversation_index.csv", list(index[0]) if index else ["seq", "source_pointer"], index)
    # A display nickname is a browsing label, not an identity claim. Keep the
    # session-derived suffix to avoid merging same-name contacts across exports.
    nickname_path = "按昵称/" + _nickname_folder(meta["name"], meta["session"]) + "/conversation_index.csv"
    nickname_dir = dst / "按昵称" / _nickname_folder(meta["name"], meta["session"])
    nickname_dir.mkdir(parents=True)
    _write_csv(nickname_dir / "conversation_index.csv", list(index[0]) if index else ["seq", "source_pointer"], index)
    _write_csv(dst / "nickname_index.csv", ["display_name", "session", "message_count", "index_file"],
               [{"display_name": meta["name"], "session": meta["session"],
                 "message_count": len(index), "index_file": nickname_path}])
    _write_csv(dst / "type_summary.csv", ["type", "count"],
               [{"type": key, "count": count} for key, count in sorted(type_counts.items())])
    type_directory = dst / "按消息类型"
    type_directory.mkdir()
    filenames = {}
    for kind in sorted(type_counts):
        safe = re.sub(r"[^0-9A-Za-z_-]+", "_", kind).strip("_") or "type"
        suffix = hashlib.sha256(kind.encode("utf-8")).hexdigest()[:8]
        filename = safe[:40] + "_" + suffix + ".csv"
        filenames[kind] = "按消息类型/" + filename
        _write_csv(type_directory / filename, list(index[0]) if index else ["seq", "source_pointer"],
                   (row for row in index if row["type"] == kind))
    _write_jsonl(dst / "attachment_index.jsonl", attachments)
    _write_jsonl(dst / "resource_report_index.jsonl", report_rows)
    _write_jsonl(dst / "issues.jsonl", issues)
    issue_counts = {}
    for item in issues:
        issue_counts[item["kind"]] = issue_counts.get(item["kind"], 0) + 1
    if hashlib.sha256(src.read_bytes()).hexdigest() != source_hash:
        raise ValueError("原导出在整理过程中发生变化，结果目录未写完成标记")
    if report_hash is not None and hashlib.sha256(report_path.read_bytes()).hexdigest() != report_hash:
        raise ValueError("附件报告在整理过程中发生变化，结果目录未写完成标记")
    top_resources = sum(a["record_role"] == "top_level" for a in attachments)
    manifest = {"normalization": "success", "source_file": str(src),
                "source_sha256": source_hash, "resource_report_sha256": report_hash,
                "account_scope": "unverified", "session": meta.get("session"),
                "display_name": meta.get("name"), "time_zone": meta.get("time_zone"),
                "exported_at": meta.get("exported_at"), "message_count": len(source_messages),
                "type_counts": type_counts, "sender_counts": senders,
                "nickname_index_file": nickname_path,
                "category_files": filenames,
                "attachment_references": len(attachments),
                "top_level_attachment_references": top_resources,
                "embedded_attachment_references": len(attachments) - top_resources,
                "resource_report_rows": len(report_rows),
                "issues": len(issues), "issue_counts": issue_counts,
                "mapped_transfer_amounts": mapped_amounts,
                "source_database_audit": "not_provided",
                "media_content_inspection": "not_performed",
                "limitations": "哈希与导出整理不证明原微信完整性、账号实名、附件内容或法律采信"}
    _write_json(dst / "manifest.json", manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="本机 Moect JSON 中立整理")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = normalize(args.input, args.out, skill_storage=Path(__file__).resolve().parent.parent)
    except (ValueError, OSError, TypeError, OverflowError) as exc:
        parser.exit(2, "未完成：%s\n" % exc)
    print("中立整理完成：%d 条；资源报告 %d 行；状态详见 manifest.json" %
          (result["message_count"], result["resource_report_rows"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
