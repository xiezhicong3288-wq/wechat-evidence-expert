#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chat-evidence: 微信聊天记录整理草稿与可审核的改进建议。

证据铁律（不可破坏）：
  - 只读取导出文件，绝不修改、删除、外传原始数据。
  - 只归类、不篡改：以原生 msg_id（若有）及零基 idx 定位原文。
  - 脚本不调用网络；执行宿主是否在云端由使用环境决定。
  - 不替用户做法律判断，结论由律师定稿。

子命令（证据链）：
  validate   校验导出文件结构（不打印私人聊天内容）
  anchor     记录文件哈希；不证明来源、真实性或第三方时间戳
  extract    抽取法律语义要素（合同/承诺/金额/转账/验收/违约…）
  timeline   生成时间线 + 金额清单
  toulmin    生成图尔敏论证结构（主张/根据/保证/支撑/限定/反驳）
  identity   生成身份印证链
  all        依次执行上述全部

子命令（需显式 --state-dir，必须位于技能目录之外）：
  reflect    记录去标识化经验，不写入技能目录
  learn      只起草规则建议，不加载或自动激活分类规则
  regress    比较同一输入哈希的类别数量；不是准确率评估
"""
import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
from datetime import datetime, timezone

# Windows consoles may default to GBK, which cannot encode some diagnostic
# symbols. Keep CLI output deterministic without changing the input bytes.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

EXPORT_SCHEMA_VERSION = "1.1"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_skill_parent = os.path.dirname(SKILL_DIR)
_git_marker = os.path.join(_skill_parent, ".git")
_parent_is_worktree = os.path.isfile(_git_marker) or os.path.isfile(os.path.join(_git_marker, "HEAD"))
SKILLS_STORAGE = _skill_parent if os.path.basename(_skill_parent) == "remote-skills" or _parent_is_worktree else SKILL_DIR
OUTPUT_SUFFIXES = {
    "anchor": ".anchor.json", "extract": ".evidence_index.json",
    "timeline": ".timeline.md", "toulmin": ".toulmin.md",
    "identity": ".identity.md",
}

# 法律语义要素分类规则（关键词 → 类别）。仅粗筛，命中后需人工复核。
CATEGORY_RULES = {
    "合同协议": ["合同", "协议", "签约", "约定", "条款", "起草", "书面", "盖章", "签署", "意向书", "框架"],
    "承诺确认": ["承诺", "保证", "确认", "没问题", "可以", "同意", "负责", "包在", "一定", "收到", "好的", "明白"],
    "金额价格": ["元", "万", "费用", "价格", "报价", "金额", "付款", "收款", "结算", "欠款", "尾款", "定金", "总价", "预付款", "首付款"],
    "转账支付": ["转账", "支付", "打款", "汇款", "收款码", "支付宝", "微信支付", "发票"],
    "验收交付": ["验收", "交付", "交货", "完工", "合格", "交付标准", "进度", "节点", "进场", "施工", "完工"],
    "违约责任": ["违约", "逾期", "延期", "赔偿", "责任", "纠纷", "起诉", "投诉", "未按", "拖延", "追究", "返工"],
    "期限时间": ["截止", "期限", "之前完成", "日内", "月底前", "周", "前", "工期", "交付期", "延期"],
    "质量标准": ["质量", "标准", "规格", "不合格", "返工", "检测", "验收标准", "国标"],
}

AMBIGUOUS = {"可以", "没问题", "好的", "收到", "同意", "明白"}  # 短确认需人工复核


def load_export(path, with_hash=False):
    with open(path, "rb") as f:
        raw = f.read()
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        raise ValueError("导出文件必须是对象，且 messages 必须是数组")
    for key in ("chat", "username", "exported_at"):
        if key in data and not isinstance(data[key], str):
            raise ValueError("导出字段 %s 必须是字符串" % key)
    if "is_group" in data and not isinstance(data["is_group"], bool):
        raise ValueError("is_group 必须是布尔值")
    ids = set()
    for i, m in enumerate(data["messages"]):
        prefix = "messages[%d]" % i
        if not isinstance(m, dict):
            raise ValueError(prefix + " 必须是对象")
        ts = m.get("timestamp")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts):
            raise ValueError(prefix + ".timestamp 必须是有限的 Unix 秒数")
        try:
            datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            raise ValueError(prefix + ".timestamp 超出可表示范围")
        if not isinstance(m.get("sender"), str) or not m["sender"].strip():
            raise ValueError(prefix + ".sender 必须是非空字符串")
        if "sender_id" in m and (not isinstance(m["sender_id"], str) or not m["sender_id"].strip()):
            raise ValueError(prefix + ".sender_id 必须是非空字符串")
        ty = m.get("type", "text")
        # Exporters can introduce additional types (for example, quote or
        # miniprogram). Preserve their original label instead of discarding
        # messages or pretending that they were ordinary text.
        if (not isinstance(ty, str) or not ty.strip() or len(ty) > 80
                or ty != ty.strip() or any(ord(char) < 32 for char in ty)):
            raise ValueError(prefix + ".type 必须是非空且不含控制字符的类型名称")
        if (ty == "text" or "content" in m) and not isinstance(m.get("content"), str):
            raise ValueError(prefix + ".content 必须是字符串")
        extra = m.get("extra", {})
        if not isinstance(extra, dict):
            raise ValueError(prefix + ".extra 必须是对象")
        if "desc" in extra and not isinstance(extra["desc"], str):
            raise ValueError(prefix + ".extra.desc 必须是字符串")
        if "amount" in extra:
            amount = extra["amount"]
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
                raise ValueError(prefix + ".extra.amount 必须是有限数值")
        if "msg_id" in m:
            mid = m["msg_id"]
            if isinstance(mid, bool) or not isinstance(mid, (str, int)) or not str(mid).strip():
                raise ValueError(prefix + ".msg_id 必须是非空字符串或整数")
            if str(mid) in ids:
                raise ValueError(prefix + ".msg_id 重复或存在字符串/整数歧义")
            ids.add(str(mid))
    return (data, hashlib.sha256(raw).hexdigest()) if with_hash else data


def _export(args):
    if not hasattr(args, "_data"):
        args._data, args._source_sha256 = load_export(args.export, with_hash=True)
    return args._data


def _reference(i, message):
    ref = {"idx": i, "source_location": "messages[%d]" % i}
    if "msg_id" in message:
        ref["msg_id"] = message["msg_id"]
    return ref


def _ref_label(row):
    label = "idx:%d" % row["idx"]
    if "msg_id" in row:
        label += "; msg_id=" + json.dumps(row["msg_id"], ensure_ascii=False)
    return label


def _md(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _inside(path, directory):
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(directory)]) == os.path.realpath(directory)
    except ValueError:
        return False


def _check_output(path, args, must_be_new=True):
    if _inside(path, SKILLS_STORAGE):
        raise ValueError("运行产物不得写入技能集合目录：" + str(path))
    for source in (args.export, args.identity, args.claims):
        if source and os.path.realpath(path) == os.path.realpath(source):
            raise ValueError("输出路径与输入材料冲突：" + str(path))
        if source and os.path.exists(path) and os.path.exists(source) and os.path.samefile(path, source):
            raise ValueError("输出路径指向输入材料的同一文件：" + str(path))
    if must_be_new and os.path.lexists(path):
        raise ValueError("拒绝覆盖已有输出（包括链接）：" + str(path))


def _write_output(path, args, value, as_json=False):
    _check_output(path, args)
    # x 模式使用排他创建；即使预检后目标出现，也不会覆盖。
    with open(path, "x", encoding="utf-8") as f:
        if as_json:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        else:
            f.write(value)


def _output_path(args, command):
    if hasattr(args, "_outputs"):
        return args._outputs[command]
    return args.out or os.path.splitext(args.export)[0] + OUTPUT_SUFFIXES[command]


def _load_claims(args, data):
    if not args.claims:
        return []
    with open(args.claims, "r", encoding="utf-8-sig") as f:
        claims = json.load(f)
    if not isinstance(claims, list):
        raise ValueError("主张文件必须是数组")
    ids = {str(m["msg_id"]): i for i, m in enumerate(data["messages"]) if "msg_id" in m}
    for ci, c in enumerate(claims):
        if not isinstance(c, dict) or not isinstance(c.get("claim"), str) or not c["claim"].strip():
            raise ValueError("claims[%d] 必须包含非空 claim 字符串" % ci)
        for key in ("warrant", "backing", "qualifier", "rebuttal"):
            if key in c and not isinstance(c[key], str):
                raise ValueError("claims[%d].%s 必须是字符串" % (ci, key))
        refs = c.get("ground_msg_ids", [])
        if not isinstance(refs, list):
            raise ValueError("ground_msg_ids 必须是数组")
        resolved, seen = [], set()
        for ref in refs:
            if isinstance(ref, bool) or not isinstance(ref, (str, int)):
                raise ValueError("根据引用必须是原生 msg_id 或明确的 idx:<零基序号>")
            key = str(ref)
            positional = re.fullmatch(r"idx:(0|[1-9][0-9]*)", key)
            if positional and key in ids:
                raise ValueError("根据引用同时匹配原生 msg_id 和 idx，存在歧义：" + key)
            idx = int(positional.group(1)) if positional else ids.get(key)
            if idx is None or idx >= len(data["messages"]):
                raise ValueError("根据引用在原始 messages 中不存在：" + key)
            if idx in seen:
                raise ValueError("同一主张的根据重复引用了同一消息：" + key)
            seen.add(idx)
            resolved.append(_reference(idx, data["messages"][idx]))
        c["_resolved_grounds"] = resolved
    return claims


def _load_identity(args):
    if not args.identity:
        return {}
    with open(args.identity, "r", encoding="utf-8-sig") as f:
        idmap = json.load(f)
    if not isinstance(idmap, dict):
        raise ValueError("身份映射必须是对象")
    for sid, meta in idmap.items():
        if not isinstance(meta, dict):
            raise ValueError("身份映射每个条目必须是对象")
        for key in ("real_name", "phone", "org"):
            if key in meta and not isinstance(meta[key], str):
                raise ValueError("身份映射的 %s 必须是字符串" % key)
    return idmap


def msg_text(m):
    t = m.get("type", "text")
    if t == "text":
        return m.get("content", "") or ""
    if t == "transfer":
        return "[转账] " + str(m.get("extra", {}).get("amount", ""))
    if t == "image":
        return "[图片] " + (m.get("extra", {}).get("desc", "") or "")
    return "[" + t + "]"


def ts_to_iso(ts):
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return str(ts)


def ensure_dir(d):
    os.makedirs(d, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def categorize(text):
    cats = []
    for cat, kws in CATEGORY_RULES.items():
        if any(kw in text for kw in kws):
            cats.append(cat)
    return cats


def _rows(data):
    rows = []
    for i, m in enumerate(data["messages"]):
        text = msg_text(m)
        cats = categorize(text)
        if m.get("type") == "transfer" and "转账支付" not in cats:
            cats.append("转账支付")
        rows.append({
            **_reference(i, m),
            "ts": m.get("timestamp"),
            "iso": ts_to_iso(m.get("timestamp")) if isinstance(m.get("timestamp"), (int, float)) else "?",
            "sender": m.get("sender"),
            "sender_id": m.get("sender_id") or m.get("sender"),
            "type": m.get("type", "text"),
            "cats": cats,
            "text": text,
            "amount": m.get("extra", {}).get("amount") if m.get("type") == "transfer" else None,
        })
    return rows


def cmd_validate(args):
    data = _export(args)
    msgs = data["messages"]
    senders, types, tmin, tmax = {}, {}, None, None
    for m in msgs:
        s = m.get("sender", "未知")
        senders[s] = senders.get(s, 0) + 1
        ty = m.get("type", "text")
        types[ty] = types.get(ty, 0) + 1
        ts = m.get("timestamp")
        if isinstance(ts, (int, float)):
            tmin = ts if tmin is None else min(tmin, ts)
            tmax = ts if tmax is None else max(tmax, ts)
    print("格式校验通过；不代表内容、身份或取证来源已经核验")
    group_status = ("群聊" if data["is_group"] else "单聊") if "is_group" in data else "类型未标明"
    print("会话：%s（%s）" % (data.get("chat", "?"), group_status))
    print("消息总数：%d" % len(msgs))
    print("日期范围：%s ~ %s" % (ts_to_iso(tmin) if tmin is not None else "?", ts_to_iso(tmax) if tmax is not None else "?"))
    print("发言人分布：%s" % "、".join("%s:%d" % (k, v) for k, v in sorted(senders.items(), key=lambda x: -x[1])))
    print("类型分布：%s" % "、".join("%s:%d" % (k, v) for k, v in sorted(types.items(), key=lambda x: -x[1])))
    return 0


def cmd_neutral_moect(args):
    if not args.out:
        raise ValueError("Moect 中立整理须指定不存在的新目录 --out")
    from moect_adapter import normalize
    result = normalize(args.export, args.out, skill_storage=SKILLS_STORAGE)
    print("中立整理完成：%d 条消息；%d 条资源报告；缺失 %d、加密 %d、多位置引用 %d" %
          (result["message_count"], result["resource_report_rows"],
           result["issue_counts"].get("resource_missing", 0),
           result["issue_counts"].get("resource_encrypted", 0),
           result["issue_counts"].get("multiple_message_appearances", 0)))
    return 0


def cmd_anchor(args):
    data = _export(args)
    msgs = data["messages"]
    manifest = {
        "schema": EXPORT_SCHEMA_VERSION,
        "chat": data.get("chat"),
        "exported_at": data.get("exported_at"),
        "message_count": len(msgs),
        "anchored_at": now_iso(),
        "file_sha256": args._source_sha256,
        "scope": "仅记录本次读取字节的指纹；不验证导出来源、导出前完整性、内容真实性或法律效力",
        "index_basis": "idx 为原始 messages 数组的零基位置；msg_id 仅在输入中存在时保留",
        "trusted_timestamp": {
            "status": "unavailable",
            "note": "未接入或签发第三方可信时间戳；anchored_at 仅为运行环境时钟",
        },
        "pre_chain_declaration": {
            "status": "unverified",
            "clean_env": None,
            "source": None,
            "statement": None,
            "note": "没有核验来源或取证过程，不自动生成当事人声明",
        },
        "messages": [],
    }
    chain = hashlib.sha256()
    for i, m in enumerate(msgs):
        canonical = json.dumps(m, ensure_ascii=False, sort_keys=True)
        h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        chain.update(h.encode("utf-8"))
        manifest["messages"].append({**_reference(i, m), "msg_sha256": h})
    manifest["chain_sha256"] = chain.hexdigest()
    out = _output_path(args, "anchor")
    _write_output(out, args, manifest, as_json=True)
    print("文件指纹记录已生成：%s" % out)
    print("文件指纹(file_sha256)：%s" % manifest["file_sha256"])
    print("链式指纹(chain_sha256)：%s" % manifest["chain_sha256"])
    print("可信时间戳不可用；来源与取证过程未核验。")
    print("消息 %d 条；指纹用于后续字节一致性比较，不证明导出前真实性。" % len(msgs))
    return 0


def cmd_extract(args):
    data = _export(args)
    index = []
    for i, m in enumerate(data["messages"]):
        text = msg_text(m)
        cats = categorize(text)
        if m.get("type") == "transfer" and "转账支付" not in cats:
            cats.append("转账支付")
        if not cats:
            continue
        need_review = any(phrase in text for phrase in AMBIGUOUS)
        index.append({
            **_reference(i, m), "ts": m.get("timestamp"), "sender": m.get("sender"),
            "categories": cats, "snippet": text[:120], "need_review": need_review,
        })
    out = _output_path(args, "extract")
    _write_output(out, args, index, as_json=True)
    print("法律要素抽取完成：命中 %d 条" % len(index))
    print("输出：%s" % out)
    cat_count = {}
    for it in index:
        for c in it["categories"]:
            cat_count[c] = cat_count.get(c, 0) + 1
    print("类别分布：%s" % "、".join("%s:%d" % (k, v) for k, v in sorted(cat_count.items(), key=lambda x: -x[1])))
    flagged = [it for it in index if it["need_review"]]
    if flagged:
        print("⚠ %d 条短确认(如'可以/没问题/好的')需人工复核语义，勿直接作承诺证据" % len(flagged))
    return 0


def cmd_timeline(args):
    data = _export(args)
    rows = _rows(data)
    rows.sort(key=lambda r: r["ts"] if isinstance(r["ts"], (int, float)) else 0)
    md = ["# 微信聊天记录时间线（证据草稿）\n",
          "会话：%s（%s）\n" % (data.get("chat", "?"), "群聊" if data.get("is_group") else "单聊"),
          "## 一、按时间排序的关键记录\n",
          "> idx 为原始 messages 数组的零基位置；msg_id 为输入原生标识（如有）。\n",
          "| 原文位置 | 时间(UTC) | 发言人 | 类别 | 内容摘要 |",
          "| --- | --- | --- | --- | --- |"]
    for r in rows:
        if r["cats"]:
            snippet = re.sub(r"\s+", " ", r["text"])[:60]
            md.append("| %s | %s | %s | %s | %s |" % tuple(_md(v) for v in (_ref_label(r), r["iso"], r["sender"], "/".join(r["cats"]), snippet)))
    md += ["\n## 二、金额/转账事实清单（供诉讼/谈判核验）\n"]
    amounts = [r for r in rows if r["amount"] or "转账支付" in r["cats"] or "金额价格" in r["cats"]]
    if amounts:
        md += ["| 原文位置 | 时间 | 发言人 | 金额/说明 |", "| --- | --- | --- | --- |"]
        for r in amounts:
            md.append("| %s | %s | %s | %s |" % tuple(_md(v) for v in (_ref_label(r), r["iso"], r["sender"], r["amount"] if r["amount"] is not None else "见内容")))
    else:
        md.append("（本导出未发现明确金额/转账标记，请结合微信官方电子支付凭证补全）\n")
    out = _output_path(args, "timeline")
    _write_output(out, args, "\n".join(md))
    print("时间线已生成：%s" % out)
    print("含法律要素的关键记录 %d 条；金额/转账相关 %d 条" % (sum(1 for r in rows if r["cats"]), len(amounts)))
    return 0


def cmd_toulmin(args):
    """图尔敏论证结构：主张/根据/保证/支撑/限定/反驳。"""
    data = _export(args)
    rows = _rows(data)
    claims = getattr(args, "_claims", None)
    if claims is None:
        claims = _load_claims(args, data)
    md = ["# 图尔敏论证结构（证据链）\n",
          "会话：%s\n" % data.get("chat", "?"),
          "> 六要素：主张(Claim) / 根据(Ground) / 保证(Warrant) / 支撑(Backing) / 限定(Qualifier) / 反驳(Rebuttal)。",
          "> 由律师定稿；本工具只把证据归位到要素，不做价值判断。",
          "> idx 为原始 messages 数组的零基位置；msg_id 为输入原生标识（如有）。\n"]
    if not claims:
        md += ["（未提供 claims.json，以下为证据池，供律师挑选归位）\n", "## 证据池（按要素粗筛）\n"]
        md += ["| 原文位置 | 时间 | 发言人 | 内容 | 可归位要素 |", "| --- | --- | --- | --- | --- |"]
        for r in rows:
            if not r["cats"]:
                continue
            snippet = re.sub(r"\s+", " ", r["text"])[:50]
            md.append("| %s | %s | %s | %s | %s |" % tuple(_md(v) for v in (_ref_label(r), r["iso"], r["sender"], snippet, "/".join(r["cats"]))))
    else:
        for c in claims:
            md.append("## 主张：%s\n" % _md(c["claim"]))
            md.append("- **根据(Ground)**：%s" % ("、".join(_md(_ref_label(r)) for r in c["_resolved_grounds"]) or "待补：没有提供消息引用"))
            md.append("- **保证(Warrant)**：%s" % c.get("warrant", "待补：为何这些事实能推出该主张"))
            md.append("- **支撑(Backing)**：%s" % c.get("backing", "待补：法律条文/合同条款/官方凭证等更强依据"))
            md.append("- **限定(Qualifier)**：%s" % c.get("qualifier", "待补：如'很可能/按现有证据/除非有相反证据'"))
            md.append("- **反驳(Rebuttal)**：%s" % c.get("rebuttal", "待补：对方可能提出的相反主张及应对"))
            md.append("")
    out = _output_path(args, "toulmin")
    _write_output(out, args, "\n".join(md))
    print("图尔敏论证结构已生成：%s" % out)
    print("提示：六要素中 主张/根据/保证 为必备，其余按需；请律师据此定稿。")
    return 0


def cmd_identity(args):
    data = _export(args)
    idmap = getattr(args, "_identity", None)
    if idmap is None:
        idmap = _load_identity(args)
    senders = {}
    for m in data["messages"]:
        sid = m.get("sender_id") or m.get("sender")
        senders.setdefault(sid, {"display": m.get("sender"), "count": 0})
        senders[sid]["count"] += 1
    md = ["# 身份印证链（草图）\n", "| 标识 | 出现次数 | 实名 | 手机号 | 所属方 | 状态 |",
          "| --- | --- | --- | --- | --- | --- |"]
    for sid, info in sorted(senders.items(), key=lambda x: -x[1]["count"]):
        meta = idmap.get(sid, {})
        missing = [k for k in ("real_name", "phone", "org") if not meta.get(k)]
        status = "字段齐全；身份未核验" if not missing else "字段缺" + "/".join(missing) + "；身份未核验"
        md.append("| %s | %d | %s | %s | %s | %s |" % (
            _md(sid), info["count"], _md(meta.get("real_name", "—")), _md(meta.get("phone", "—")), _md(meta.get("org", "—")), status))
    md.append("\n此表仅整理用户提供的身份信息；字段完整不代表已核验或司法认可。")
    md.append("请另附可追溯的身份凭证，并核对同昵称、借用账号等可能性。\n")
    out = _output_path(args, "identity")
    _write_output(out, args, "\n".join(md))
    print("身份印证链已生成：%s" % out)
    print("参与者 %d 个账号/显示名；身份真实性均待独立核验。" % len(senders))
    return 0


# ───────────────────── 自我进化运行时 ─────────────────────

def _state_file(args, *parts):
    if not args.state_dir:
        raise ValueError("此命令必须显式指定 --state-dir")
    root = os.path.realpath(os.path.expanduser(args.state_dir))
    if _inside(root, SKILLS_STORAGE):
        raise ValueError("--state-dir 必须位于技能集合目录之外")
    ensure_dir(root)
    parent = root
    for part in parts[:-1]:
        parent = os.path.join(parent, part)
        if os.path.lexists(parent):
            if os.path.islink(parent) or not os.path.isdir(parent):
                raise ValueError("状态子目录不得是链接或非目录：" + parent)
        else:
            os.mkdir(parent)
    path = os.path.join(parent, parts[-1])
    _check_output(path, args, must_be_new=False)
    if os.path.lexists(path):
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("状态文件必须是无符号链接、无硬链接的普通文件：" + path)
    return path


def _append_log(path, entry, args):
    _check_output(path, args, must_be_new=False)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("日志必须是无硬链接的普通文件：" + path)
        f.write(entry.replace("\r", "\\r").replace("\n", "\\n") + "\n")


def cmd_reflect(args):
    """阶1：捕获可教时刻。"""
    kind = args.kind  # worked / failed / correction
    note = args.note
    ts = now_iso()
    if kind == "correction":
        path = _state_file(args, "vault", "corrections.md")
    else:
        fn = "what-worked.md" if kind == "worked" else "what-failed.md"
        path = _state_file(args, "vault", "learnings", fn)
    _append_log(path, "- [%s] %s" % (ts, note), args)
    print("已记录经验（请确认已去标识化）：%s" % path)
    print("此记录不会改变分类规则；请勿在经验日志中写入案件原文或个人身份信息。")
    return 0


def cmd_learn(args):
    """仅起草规则建议；不激活、不加载规则，也不验证复现次数。"""
    rule = {
        "rule": args.rule,
        "reasoning": args.reasoning,
        "proposed_at": now_iso(),
        "status": "proposed",  # 待人工审批后才转 active
    }
    print("规则建议核对项（程序不自动证明其满足）：")
    print("  1) 是否真改进？ 2) 能否跨任务复用？ 3) 够具体？ 4) 够通用？ 5) 是否触碰证据铁律？")
    slug = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", args.rule)[:30]
    digest = hashlib.sha256(json.dumps(rule, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    path = _state_file(args, "rules", (slug or "proposal") + "-" + digest + ".json")
    _write_output(path, args, rule, as_json=True)
    print("已起草规则（待审批）：%s" % path)
    print("理由：%s" % args.reasoning)
    print("规则仅为 proposed 建议；本脚本不会读取规则文件，改成 active 也不会改变分类结果。")
    print("实际升级需要另行修改实现、验证并保存；此命令不执行该升级。")
    return 0


def cmd_regress(args):
    """仅比较同一输入字节哈希的类别计数，不评价准确率或法律效力。"""
    data = _export(args)
    rows = _rows(data)
    current = {}
    for r in rows:
        for c in r["cats"]:
            current[c] = current.get(c, 0) + 1
    base_path = _state_file(args, "vault", "baselines", args._source_sha256 + ".json")
    if os.path.exists(base_path):
        with open(base_path, "r", encoding="utf-8") as f:
            baseline = json.load(f)
        if not isinstance(baseline, dict) or baseline.get("input_sha256") != args._source_sha256:
            raise ValueError("基线与当前输入文件哈希不匹配")
        base = baseline.get("categories")
        if not isinstance(base, dict) or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in base.values()):
            raise ValueError("基线类别计数格式不合法")
        print("同一输入哈希的基线 vs 当前（类别命中数，不是准确率）")
        all_cats = sorted(set(list(base.keys()) + list(current.keys())))
        regressed = []
        for c in all_cats:
            b, n = base.get(c, 0), current.get(c, 0)
            flag = ""
            if b > 0 and n == 0:
                flag = " ⚠ 骤降为0，疑似退化"
                regressed.append(c)
            elif n < b * 0.5:
                flag = " ⚠ 下降过半，关注"
                regressed.append(c)
            print("  %s：%d → %d%s" % (c, b, n, flag))
        if regressed:
            print("⚠ 类别计数显著下降：%s。请检查实际实现与预期；不自动回滚。" % "、".join(regressed))
            return 1
        print("类别计数检查通过：未发现设定阈值的显著下降；仍需核对准确性。")
    else:
        _write_output(base_path, args, {"input_sha256": args._source_sha256, "categories": current}, as_json=True)
        print("此输入哈希首次运行：已建立类别计数基线，不代表回归通过。")
        print("基线：%s" % base_path)
    return 0


def cmd_all(args):
    data = _export(args)
    args._claims = _load_claims(args, data)
    args._identity = _load_identity(args)
    stem = os.path.splitext(args.export)[0]
    if args.out:
        # all 的 --out 是新目录；先完成所有内容与目标检查，再创建目录。
        _check_output(args.out, args)
        if not os.path.isdir(os.path.dirname(os.path.abspath(args.out))):
            raise ValueError("新输出目录的父目录必须已存在")
        stem = os.path.join(args.out, os.path.basename(stem))
    args._outputs = {name: stem + suffix for name, suffix in OUTPUT_SUFFIXES.items()}
    for path in args._outputs.values():
        _check_output(path, args)
        if not args.out and not os.path.isdir(os.path.dirname(os.path.abspath(path))):
            raise ValueError("输出文件的父目录必须已存在")
    if args.out:
        os.mkdir(args.out)
    for fn in (cmd_anchor, cmd_validate, cmd_extract, cmd_timeline, cmd_toulmin, cmd_identity):
        print("\n=== %s ===" % fn.__name__.replace("cmd_", ""))
        rc = fn(args)
        if rc:
            return rc
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="chat-evidence", description="微信聊天记录整理草稿与可审核的改进建议")
    p.add_argument("--export", help="已解密的聊天记录导出 JSON 路径（只读）")
    p.add_argument("--out", help="单命令为新文件；all 为新目录；拒绝覆盖已有路径")
    p.add_argument("--identity", help="身份映射 JSON（可选）")
    p.add_argument("--claims", help="主张清单 JSON（toulmin 用，可选）")
    p.add_argument("--state-dir", help="reflect/learn/regress 必填，位于技能集合目录之外")
    sub = p.add_subparsers(dest="cmd")

    # 证据链
    for name, fn in [("validate", cmd_validate), ("neutral-moect", cmd_neutral_moect),
                     ("anchor", cmd_anchor), ("extract", cmd_extract),
                     ("timeline", cmd_timeline), ("toulmin", cmd_toulmin), ("identity", cmd_identity),
                     ("all", cmd_all)]:
        sp = sub.add_parser(name)
        sp.set_defaults(func=fn)
    # 自我进化
    sp = sub.add_parser("reflect")
    sp.add_argument("--state-dir", default=argparse.SUPPRESS)
    sp.add_argument("--kind", choices=["worked", "failed", "correction"], required=True)
    sp.add_argument("--note", required=True)
    sp.set_defaults(func=cmd_reflect)
    sp = sub.add_parser("learn")
    sp.add_argument("--state-dir", default=argparse.SUPPRESS)
    sp.add_argument("--rule", required=True)
    sp.add_argument("--reasoning", required=True)
    sp.set_defaults(func=cmd_learn)
    sp = sub.add_parser("regress")
    sp.add_argument("--state-dir", default=argparse.SUPPRESS)
    sp.add_argument("--export", default=argparse.SUPPRESS, help="导出 JSON 路径（用于计算当前类别命中）")
    sp.set_defaults(func=cmd_regress)

    args = p.parse_args(argv)
    if not args.cmd:
        p.error("请选择子命令")
    if args.cmd not in ("reflect", "learn") and not args.export:
        p.error("该命令需要 --export")
    if args.cmd in ("reflect", "learn", "regress") and not args.state_dir:
        p.error("该命令需要 --state-dir（技能集合目录之外）")
    try:
        return args.func(args)
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        print("未完成：%s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
