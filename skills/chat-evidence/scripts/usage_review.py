"""Project a local run receipt into a record without chat or identity fields."""

import hashlib
import json
import os
import re
from pathlib import Path
from tempfile import TemporaryDirectory


RECEIPT_LIMIT = 16 * 1024 * 1024
RESULTS = {"success": 0, "partial": 1, "failed": 2}


def load_record(directory):
    path = directory / "record.json"
    if directory.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("复盘记录不存在或文件类型不安全")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields)


def save_record(directory, record):
    if not os.path.lexists(directory):
        with TemporaryDirectory(dir=directory.parent, prefix=".review-") as temporary:
            staging = Path(temporary)
            payload = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)
            (staging / "record.json").write_text(payload, encoding="utf-8")
            try:
                staging.rename(directory)
                return
            except OSError:
                if not os.path.lexists(directory):
                    raise
    if load_record(directory) != record:
        raise ValueError("同一运行和反馈状态已有不同记录")


def _unique_fields(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError("运行回执包含重复字段")
        fields[key] = value
    return fields


def _metrics(source, fields):
    if not isinstance(source, dict):
        raise ValueError("运行回执缺少计数对象")
    values = {name: source[name] for name in fields if name in source}
    if any(type(value) is not int or value < 0 for value in values.values()):
        raise ValueError("运行回执计数无效")
    return values


def _status(source, codes=RESULTS):
    value, code = source.get("status"), source.get("exit_code")
    if not isinstance(value, str) or value not in codes or type(code) is not int or code != codes[value]:
        raise ValueError("运行回执状态与退出码不一致")
    return value


def _summarize(source):
    kind = source.get("schema")
    if kind == "moect-input-inspection/1":
        counts = _metrics(source, ("input_count",))
        inputs = source.get("inputs")
        status = _status(source, {"ready": 0, "review": 1, "blocked": 2})
        stopped_before_inspection = status == "blocked" and inputs == [] and isinstance(source.get("error_code"), str)
        if ("input_count" not in counts or not isinstance(inputs, list)
                or (counts["input_count"] != len(inputs) and not stopped_before_inspection)):
            raise ValueError("预检回执与输入数不符")
        result = {"ready": "success", "review": "partial", "blocked": "failed"}[status]
        demo = any(isinstance(item, dict) and item.get("demo") is True for item in inputs)
        return "waylon-inspect", result, counts, demo
    if kind == "moect-neutral-archive/1" and source.get("completed") is True:
        counts = _metrics(source.get("counts"), ("top_level_messages", "nested_messages", "warnings", "errors"))
        if "top_level_messages" not in counts:
            raise ValueError("Waylon 回执缺少顶层消息数")
        inputs = source.get("sources", [])
        if not isinstance(inputs, list):
            raise ValueError("Waylon 回执来源列表无效")
        demo = any(isinstance(item, dict) and isinstance(item.get("metadata"), dict)
                   and item["metadata"].get("demo") is True for item in inputs)
        return "waylon-normalize", _status(source), counts, demo
    if source.get("normalization") == "success" and source.get("source_database_audit") == "not_provided":
        counts = _metrics(source, ("message_count", "issues", "attachment_references", "resource_report_rows"))
        if "message_count" not in counts or "issues" not in counts:
            raise ValueError("Moect 中立回执缺少消息数或问题数")
        return "evidence-neutral", "success", counts, source.get("source_demo") is True
    if kind == "1.1" and isinstance(source.get("messages"), list) and isinstance(source.get("file_sha256"), str):
        counts = _metrics(source, ("message_count",))
        if counts.get("message_count") != len(source["messages"]) or not re.fullmatch(r"[0-9a-f]{64}", source["file_sha256"]):
            raise ValueError("分析指纹回执与消息数或摘要格式不符")
        return "evidence-anchor", "success", counts, source.get("source_demo") is True
    if kind == "wechat-use-observation/1" and set(source) <= {"schema", "stage", "status", "exit_code"}:
        stage = source.get("stage")
        if stage in ("acquisition", "intake", "organize", "analysis"):
            return "observed-" + stage, _status(source), {}, False
    raise ValueError("无法识别运行回执，请使用明示的受支持结构")


def review(receipt, origin, feedback, version):
    if not re.fullmatch(r"(?:[0-9]+\.[0-9]+\.[0-9]+(?:[-.][A-Za-z0-9.-]+)?|unknown)", version) or len(version) > 40:
        raise ValueError("技能版本应为版本号或 unknown")
    if origin == "synthetic" and feedback != "pending":
        raise ValueError("合成测试不能登记为用户反馈")
    receipt_path = Path(receipt)
    if not receipt_path.is_file():
        raise ValueError("运行回执须为本地普通文件")
    with receipt_path.open("rb") as stream:
        raw = stream.read(RECEIPT_LIMIT + 1)
    if len(raw) > RECEIPT_LIMIT:
        raise ValueError("运行回执超过 16 MiB，请使用脱敏观察记录")
    try:
        source = json.loads(raw, object_pairs_hook=_unique_fields)
    except (UnicodeError, RecursionError, json.JSONDecodeError):
        raise ValueError("运行回执不是有效的 JSON 对象") from None
    if not isinstance(source, dict):
        raise ValueError("运行回执不是 JSON 对象")
    command, result, counts, demo = _summarize(source)
    if demo and origin == "actual":
        raise ValueError("回执声明为演示数据，不能登记为实际使用")
    if feedback == "corrected":
        next_step = "reproduce_feedback"
    elif result != "success":
        next_step = "check_source_scope_or_reproduce"
    elif counts.get("issues"):
        next_step = "review_reported_scope"
    elif feedback == "pending" and origin == "actual":
        next_step = "await_feedback"
    else:
        next_step = "keep_as_observation"
    return {"schema": "wechat-use-review/1", "receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "command": command, "result": result, "counts": counts, "declared_origin": origin,
            "feedback": feedback, "skill_version": version, "next_step": next_step}
