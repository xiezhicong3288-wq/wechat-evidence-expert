#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chat-evidence：微信导出 JSON → 证据草稿 + 自我进化。

输入是二手派生材料；只做完整性校验与结构化整理，不证明导出源真实性。
产物不写本机时钟（无效力且破坏字节级复现）。边界见 SKILL.md 第零节。

铁律：只读导出；只归类不篡改；全程本地；未核实项标「待核实」；法律结论由律师定稿。
异常输入一律显式告警或友好拒止，绝不静默漏证。
命令：validate / anchor / extract / timeline / toulmin / identity / all / reflect / learn / regress
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime, timedelta, timezone

EXPORT_SCHEMA_VERSION = "1.2"
TOOL_VERSION = "2.2.2"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.path.join(SKILL_DIR, "vault")
LEARNINGS = os.path.join(VAULT, "learnings")
HISTORY = os.path.join(VAULT, "config-history")
BASELINES = os.path.join(VAULT, "baselines")
RULES_DIR = os.path.join(SKILL_DIR, "rules")

# 外部依据单一来源：references/export_schema.md 附录
REVIEW_BASIS_REF = "references/export_schema.md 附录「外部核验依据」"
PROVENANCE_FIELDS = (
    "original_device", "forensic_image_sha256", "export_tool_and_version",
    "export_operator", "export_process_record", "chain_of_custody",
    "third_party_deposit_or_notarization",
)

# 仅粗筛，命中后须人工复核；单字关键词（如「前」「周」）假阳性过高，已移除。
CATEGORY_RULES = {
    "合同协议": ["合同", "协议", "签约", "约定", "条款", "起草", "书面", "盖章", "签署", "意向书", "框架"],
    "承诺确认": ["承诺", "保证", "确认", "没问题", "可以", "同意", "负责", "包在", "一定", "收到", "好的", "明白"],
    "金额价格": ["元", "万", "费用", "价格", "报价", "金额", "付款", "收款", "结算", "欠款", "尾款", "定金", "总价", "预付款", "首付款"],
    "转账支付": ["转账", "支付", "打款", "汇款", "收款码", "支付宝", "微信支付", "发票"],
    "验收交付": ["验收", "交付", "交货", "完工", "合格", "交付标准", "进度", "节点", "进场", "施工"],
    "违约责任": ["违约", "逾期", "延期", "赔偿", "责任", "纠纷", "起诉", "投诉", "未按", "拖延", "追究", "返工"],
    "期限时间": ["截止", "期限", "之前完成", "日内", "月底前", "工期", "交付期"],
    "质量标准": ["质量", "标准", "规格", "不合格", "返工", "检测", "验收标准", "国标"],
}
AMBIGUOUS = {"可以", "没问题", "好的", "收到", "同意", "明白"}


_PROTECTED = {}  # normcase(realpath) -> (名称, 原路径)：所有输入文件，任何写操作都不得覆盖


def _fail(msg):
    raise SystemExit("错误：" + msg)


def _setup_stdio():
    """中文 Windows 重定向/管道常为 GBK，⚠ 等符号会触发 UnicodeEncodeError。
    产物本就全是 UTF-8，终端输出统一 UTF-8 且用 replace 兜底。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def _protect(args):
    for label, q in (("导出文件", getattr(args, "export", None)),
                     ("主张清单", getattr(args, "claims", None)),
                     ("身份映射", getattr(args, "identity", None))):
        if q:
            _PROTECTED[os.path.normcase(os.path.realpath(q))] = (label, q)


def _scan_bad(obj):
    """输入合法性扫描：孤立代理、非有限数值、极深嵌套一律在写入前拒止。

    只归类不篡改——不能编码的字符绝不静默替换，否则证据产物会与原文不符。
    用迭代栈而非递归，避免深嵌套在这里再次触发 RecursionError。
    """
    stack = [(obj, "root")]
    while stack:
        o, p = stack.pop()
        if isinstance(o, str):
            try:
                o.encode("utf-8")
            except UnicodeEncodeError:
                return p, "无法用 UTF-8 表示的字符（损坏的 emoji / 孤立代理）"
        elif isinstance(o, float) and not math.isfinite(o):
            return p, "非有限数值 NaN/Infinity（RFC 8259 不允许）"
        elif isinstance(o, dict):
            for k, v in o.items():
                stack.append((v, p + "." + str(k)))
                if isinstance(k, str):
                    try:
                        k.encode("utf-8")
                    except UnicodeEncodeError:
                        return p, "字段名含无法用 UTF-8 表示的字符"
        elif isinstance(o, (list, tuple)):
            for i, v in enumerate(o):
                stack.append((v, "%s[%d]" % (p, i)))
    return None


def _read_json(path, what):
    """友好读取：兼容 BOM，捕获非法 JSON / 编码 / IO / 深嵌套，不抛 traceback。"""
    if not path or not os.path.isfile(path):
        _fail("%s不存在或不是文件：%s" % (what, path))
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            obj = json.load(f)
    except json.JSONDecodeError as e:
        _fail("%s不是合法 JSON（第%d行第%d列：%s）：%s" % (what, e.lineno, e.colno, e.msg, path))
    except RecursionError:
        _fail("%s嵌套过深，超出 JSON 解析器上限；请回查导出工具：%s" % (what, path))
    except (UnicodeDecodeError, OSError) as e:
        _fail("无法读取%s（%s）：%s" % (what, e, path))
    hit = _scan_bad(obj)
    if hit:
        where, why = hit
        _fail("%s含%s（位置 %s）；工具不擅自改写原文，请回查：%s" % (what, why, where, path))
    return obj


def _check_write(path):
    key = os.path.normcase(os.path.realpath(path))
    if key in _PROTECTED:
        label, q = _PROTECTED[key]
        _fail("拒绝写入：目标与输入%s相同（%s）。只读导出是铁律，请换一个 --out 路径。" % (label, q))


def _write(path, text):
    _check_write(path)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        _fail("无法写入 %s：%s（检查目录是否存在、是否有写权限）" % (path, e))


def _dump(path, obj):
    _write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def _text(v):
    """字段保真：非字符串按 JSON 原样展开，绝不丢弃内容。"""
    if v is None:
        return ""
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)


def _extra(m):
    x = m.get("extra")
    return x if isinstance(x, dict) else {}


def _tz_offset(tz):
    if tz is None or isinstance(tz, bool):
        return None
    try:
        v = float(tz)
    except (TypeError, ValueError):
        return None
    return v if -24 < v < 24 else None


def _ts_seconds(ts):
    """返回 (秒, 单位推定说明) 或 (None, 原因)。单位属上游事实，推定一律标待核实。"""
    if ts is None or isinstance(ts, bool):
        return None, "时间不可判定"
    if isinstance(ts, str):
        if not re.fullmatch(r"\d{10,15}", ts.strip()):
            return None, "时间不可判定"
        ts = int(ts)
    if not isinstance(ts, (int, float)):
        return None, "时间不可判定"
    v = float(ts)
    if abs(v) >= 1e14:
        return None, "数值超出可表示范围"
    if abs(v) >= 1e11:
        return v / 1000.0, "毫秒推定/待核实"
    return v, ""


def ts_to_iso(ts, tz_offset=None):
    """Unix 秒（或疑似毫秒）→ 可读时间。未声明时区时显式标「待核实」，绝不擅自假定。"""
    sec, note = _ts_seconds(ts)
    if sec is None:
        return "?(%s/待核实)" % note
    try:
        utc = datetime.fromtimestamp(sec, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return "?(时间超出系统可表示范围/待核实)"
    off = _tz_offset(tz_offset)
    if off is None:
        s = utc.strftime("%Y-%m-%dT%H:%M:%SZ") + "(UTC展示/时区未声明-待核实)"
    else:
        s = utc.astimezone(timezone(timedelta(hours=off))).strftime("%Y-%m-%d %H:%M:%S") + "(UTC%+g)" % off
    return s + ("(" + note + ")" if note else "")


def msg_text(m):
    """非 text 类型也把 content/extra 全带上：未知类型不再静默漏证。"""
    t = m.get("type", "text")
    t = t if isinstance(t, str) else str(t)
    body = _text(m.get("content"))
    if t == "text":
        return body
    parts = ["[%s]" % t]
    if body:
        parts.append(body)
    for k in sorted(_extra(m)):
        v = _text(_extra(m)[k])
        if v:
            parts.append("%s=%s" % (k, v))
    if len(parts) == 1:
        parts.append("原文未导出(待核实)")
    return " ".join(parts)


def msg_ref(m):
    """原生 msg_id 优先，否则用 时间+发送者+类型+内容 哈希；不含数组下标。

    完全相同的消息共用锚点；idx 仅作定位辅助，须与输入 sha256 一起给出。
    """
    if m.get("msg_id"):
        return str(m["msg_id"])
    raw = json.dumps({k: m.get(k) for k in
                      ("timestamp", "sender", "sender_id", "type", "content", "extra")},
                     ensure_ascii=False, sort_keys=True)
    return "m-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _md_cell(v, limit=None):
    """表格单元：折叠空白/控制符/双向控制符，转义管道与尖括号，截断必留标记。

    双向控制符（U+202A–202E、U+2066–2069）能伪造显示顺序，证据展示层必须先净化；
    只改展示，不回写原文，原始内容仍完整保存在导出与 JSON 产物中。
    """
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u202a-\u202e\u2066-\u2069\ufeff]", " ", _text(v))
    s = re.sub(r"\s+", " ", s).replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
    if limit and len(s) > limit:
        s = s[:limit] + "…(截断)"
    return s


def load_export(path):
    """结构校验 + 归一化告警。异常消息拒止而非跳过，避免静默漏证。"""
    data = _read_json(path, "导出文件")
    if not isinstance(data, dict) or "messages" not in data:
        _fail("导出文件缺少 messages 字段，不符合 chat-evidence 导出格式")
    msgs = data["messages"]
    if not isinstance(msgs, list):
        _fail("messages 必须是数组，实际为 %s" % type(msgs).__name__)
    counts, first = {}, {}
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            _fail("messages[%d] 不是对象（%s）；拒绝处理以免静默漏证，请回查导出工具" % (i, type(m).__name__))
        def bump(tag):
            counts[tag] = counts.get(tag, 0) + 1
            first.setdefault(tag, i)
        if not isinstance(m.get("type", "text"), str):
            bump("type 非字符串，按字符串解释")
        c = m.get("content")
        if c is not None and not isinstance(c, str):
            bump("content 非字符串，按 JSON 原样展开")
        x = m.get("extra")
        if x is not None and not isinstance(x, dict):
            bump("extra 非对象，已忽略")
        s = m.get("sender")
        if s is not None and not isinstance(s, str):
            bump("sender 非字符串，按字符串解释")
        _, note = _ts_seconds(m.get("timestamp"))
        if note:
            bump("timestamp " + note)
    w = ["%s：%d 条（首见 messages[%d]）" % (tag, n, first[tag]) for tag, n in sorted(counts.items())]
    sv = data.get("schema_version")
    if sv is None:
        w.append("未声明 schema_version：按 v%s 结构解释，待核实" % EXPORT_SCHEMA_VERSION)
    elif str(sv) != EXPORT_SCHEMA_VERSION:
        w.append("schema_version=%s 与工具 v%s 不一致：按工具结构解释，须回查导出工具" % (sv, EXPORT_SCHEMA_VERSION))
    tz = data.get("tz_offset_hours")
    if tz is not None and _tz_offset(tz) is None:
        w.append("tz_offset_hours=%r 非法或超出 ±24，按未声明处理" % tz)
    if not msgs:
        w.append("messages 为空：可能是截取或导出失败，须核对原始载体")
    seen, dup = set(), set()
    for m in msgs:
        if m.get("msg_id"):
            x = str(m["msg_id"])
            if x in seen:
                dup.add(x)
            seen.add(x)
    if dup:
        w.append("原生 msg_id 重复 %d 个：ref 不唯一，须回查（%s…）" % (len(dup), "、".join(sorted(dup)[:3])))
    sp = data.get("source_provenance")
    if isinstance(sp, dict) and sp:
        w.append("source_provenance 仅填写 %d/%d 项，其余一律待核实" %
                 (sum(1 for k in PROVENANCE_FIELDS if sp.get(k)), len(PROVENANCE_FIELDS)))
    elif not sp:
        w.append("未附 source_provenance：属二手派生材料，真实性依赖上游")
    data["_warnings"] = w
    return data


def ensure_dir(d):
    os.makedirs(d, exist_ok=True)


def now_iso():
    """仅用于进化日志，不写入证据产物。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _input_hash(args):
    if not args.export or not os.path.exists(args.export):
        return None
    with open(args.export, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _ruleset_hash():
    return hashlib.sha256(
        json.dumps(CATEGORY_RULES, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]


def _repro(data, args):
    """同输入 + 同工具版本 + 同规则集 → 字节级一致；故意不写本机时钟。"""
    return {
        "input_sha256": _input_hash(args),
        "tool_version": TOOL_VERSION,
        "ruleset_sha256": _ruleset_hash(),
        "tz_offset_hours_declared": data.get("tz_offset_hours"),
        "structural_warnings": data.get("_warnings") or [],
        "clock_note": "本机时钟无效力且破坏可复现性，不写入产物；可信时间须第三方 TSA 签发",
    }


def _md_header(title, data, args):
    r = _repro(data, args)
    tz = r["tz_offset_hours_declared"] if r["tz_offset_hours_declared"] is not None else "未声明(待核实)"
    md = ["# %s（证据草稿，非鉴定意见）\n" % title,
          "> 复现锚点：输入 sha256 `%s` ｜ 工具 v%s ｜ 规则集 %s ｜ 时区 %s" % (
              r["input_sha256"], r["tool_version"], r["ruleset_sha256"], tz),
          "> 边界：不证明导出源真实性；未核实项标「待核实」。\n"]
    ws = r["structural_warnings"]
    for x in ws[:5]:
        md.append("> ⚠ 结构告警：%s" % x)
    if len(ws) > 5:
        md.append("> ⚠ 另有 %d 项结构告警，见 anchor/extract 产物" % (len(ws) - 5))
    if ws:
        md.append("")
    return md


def categorize(text):
    return [cat for cat, kws in CATEGORY_RULES.items() if any(kw in text for kw in kws)]


def _rows(data):
    rows = []
    tz = data.get("tz_offset_hours")
    for i, m in enumerate(data["messages"]):
        text = msg_text(m)
        cats = categorize(text)
        t = m.get("type", "text")
        if t == "transfer":
            cats.append("转账支付")
        ts = m.get("timestamp")
        sec, _ = _ts_seconds(ts)
        rows.append({
            "idx": i, "ref": msg_ref(m), "ts": ts, "sec": sec if sec is not None else 0,
            "iso": ts_to_iso(ts, tz), "sender": _text(m.get("sender")) or "未知",
            "sender_id": _text(m.get("sender_id")) or _text(m.get("sender")) or "未知",
            "type": t, "cats": cats, "text": text,
            "amount": _extra(m).get("amount") if t == "transfer" else None,
        })
    return rows


def cmd_validate(args):
    data = load_export(args.export)
    tz = data.get("tz_offset_hours")
    senders, types, tmin, tmax = {}, {}, None, None
    for m in data["messages"]:
        s = _text(m.get("sender")) or "未知"
        senders[s] = senders.get(s, 0) + 1
        ty = _text(m.get("type", "text")) or "text"
        types[ty] = types.get(ty, 0) + 1
        sec, _ = _ts_seconds(m.get("timestamp"))
        if sec is not None:
            tmin = sec if tmin is None else min(tmin, sec)
            tmax = sec if tmax is None else max(tmax, sec)
    print("校验通过：结构合法（仅结构，不校验真实性）")
    print("会话：%s（%s）" % (data.get("chat", "?"), "群聊" if data.get("is_group") else "单聊"))
    print("消息总数：%d" % len(data["messages"]))
    print("日期范围：%s ~ %s" % (ts_to_iso(tmin, tz) if tmin is not None else "?(无可用时间/待核实)",
                              ts_to_iso(tmax, tz) if tmax is not None else "?(无可用时间/待核实)"))
    print("发言人：%s" % "、".join("%s:%d" % kv for kv in sorted(senders.items(), key=lambda x: -x[1])))
    print("类型：%s" % "、".join("%s:%d" % kv for kv in sorted(types.items(), key=lambda x: -x[1])))
    ws = data["_warnings"]
    if ws:
        print("⚠ 结构告警 %d 项（不影响结构合法性，但影响举证可用性）：" % len(ws))
        for x in ws[:20]:
            print("   - " + x)
        if len(ws) > 20:
            print("   - …其余 %d 项见 anchor/extract 产物" % (len(ws) - 20))
    print("⚠ 结构合法 ≠ 证据可采：见 SKILL.md 第零节。")
    return 0


def cmd_anchor(args):
    data = load_export(args.export)
    msgs = data["messages"]
    sp = data.get("source_provenance") if isinstance(data.get("source_provenance"), dict) else {}
    prov = {k: sp.get(k) for k in PROVENANCE_FIELDS}
    for k, v in sp.items():
        prov.setdefault(k, v)
    prov["status"] = "已填写 %d/%d 项；未填项一律待核实，不得声称真实性已锚定" % (
        sum(1 for k in PROVENANCE_FIELDS if sp.get(k)), len(PROVENANCE_FIELDS))
    manifest = {
        "schema": EXPORT_SCHEMA_VERSION,
        "reproducibility": _repro(data, args),
        "chat": data.get("chat"),
        "exported_at": data.get("exported_at"),
        "message_count": len(msgs),
        "file_sha256": _input_hash(args),
        "timestamp": {
            "trusted_timestamp_status": "not_obtained",
            "tsa_service": None,
            "note": "可信时间戳须第三方 TSA（RFC 3161 / GB/T 20520—2006）或存证平台签发",
        },
        "what_this_proves": "自本次计算起，若文件字节未变，file_sha256 与 chain_sha256 可复算一致；仅用于完整性比对。",
        "what_this_does_not_prove": [
            "不证明导出内容等于手机原始聊天记录（源真实性依赖上游取证）",
            "不证明导出未被截取或删减（须以原始载体/公证核对上下文）",
            "不证明消息生成时间真实（设备时钟可改，须外部时间源）",
            "不构成第11条第二款意义上的可信时间戳或存证平台认证",
            "不构成鉴定意见或公证；真实性由法院依第93条综合判断",
        ],
        # 上游凭证由取证人/律师填写，工具不核实、不代作声明；局部填写也显式标缺口
        "source_provenance": prov,
        "review_basis_ref": REVIEW_BASIS_REF,
        "messages": [],
    }
    chain = hashlib.sha256()
    for i, m in enumerate(msgs):
        h = hashlib.sha256(json.dumps(m, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        chain.update(h.encode("utf-8"))
        manifest["messages"].append({"idx": i, "ref": msg_ref(m), "msg_sha256": h})
    manifest["chain_sha256"] = chain.hexdigest()
    out = args.out or (os.path.splitext(args.export)[0] + ".anchor.json")
    _dump(out, manifest)
    print("完整性锚定：%s" % out)
    print("file_sha256：%s" % manifest["file_sha256"])
    print("chain_sha256：%s" % manifest["chain_sha256"])
    print("⚠ 仅证明「自此刻起未改动」，不证明导出源真实性；上游凭证 %s。" % prov["status"])
    print("⚠ 可信时间戳 status=not_obtained，须第三方 TSA / 存证平台签发。")
    return 0


def cmd_extract(args):
    data = load_export(args.export)
    index = []
    for i, m in enumerate(data["messages"]):
        text = msg_text(m)
        cats = categorize(text)
        if m.get("type", "text") == "transfer":
            cats.append("转账支付")
        if not cats:
            continue
        stripped = text.strip()
        index.append({
            "idx": i, "ref": msg_ref(m), "ts": m.get("timestamp"),
            "sender": _text(m.get("sender")) or "未知", "categories": cats,
            "snippet": text[:120], "snippet_truncated": len(text) > 120,
            "need_review": len(stripped) <= 12 and any(a in stripped for a in AMBIGUOUS),
        })
    out = args.out or (os.path.splitext(args.export)[0] + ".evidence_index.json")
    _dump(out, {"reproducibility": _repro(data, args),
                "note": "关键词粗筛，命中不等于事实成立；snippet 为摘录，须回查原始导出；"
                        "snippet_truncated=true 表示摘录不完整。",
                "items": index})
    print("要素抽取：命中 %d 条（粗筛，非事实认定）→ %s" % (len(index), out))
    cat_count = {}
    for it in index:
        for c in it["categories"]:
            cat_count[c] = cat_count.get(c, 0) + 1
    print("类别：%s" % "、".join("%s:%d" % kv for kv in sorted(cat_count.items(), key=lambda x: -x[1])))
    flagged = [it for it in index if it["need_review"]]
    if flagged:
        print("⚠ %d 条短确认须人工复核，勿直接作承诺证据" % len(flagged))
    print("⚠ 未命中不等于不存在：须人工通读补漏。")
    return 0


def cmd_timeline(args):
    data = load_export(args.export)
    rows = _rows(data)
    rows.sort(key=lambda r: r["sec"])
    md = _md_header("微信聊天记录时间线", data, args)
    md += ["会话：%s（%s）\n" % (data.get("chat", "?"), "群聊" if data.get("is_group") else "单聊"),
           "## 一、关键记录\n",
           "> ref 为稳定锚点（不含下标）；idx 仅定位，引用须附原始导出与输入 sha256。\n",
           "| # | 时间 | 发言人 | 类别 | 内容摘要 | ref |", "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        if r["cats"]:
            md.append("| %d | %s | %s | %s | %s | %s |" %
                      (r["idx"], _md_cell(r["iso"]), _md_cell(r["sender"]),
                       _md_cell("/".join(r["cats"])), _md_cell(r["text"], 60), _md_cell(r["ref"])))
    md.append("\n## 二、金额/转账清单（不等于款项已支付）\n")
    amounts = [r for r in rows if r["amount"] or "转账支付" in r["cats"] or "金额价格" in r["cats"]]
    if amounts:
        md += ["| # | 时间 | 发言人 | 金额/说明 | ref |", "| --- | --- | --- | --- | --- |"]
        for r in amounts:
            md.append("| %d | %s | %s | %s | %s |" %
                      (r["idx"], _md_cell(r["iso"]), _md_cell(r["sender"]),
                       _md_cell(r["amount"] if r["amount"] else "见内容"), _md_cell(r["ref"])))
    else:
        md.append("（未发现金额/转账标记；金额陈述须以支付机构原始凭证印证）\n")
    md.append("\n> 聊天为片段式记录，不反映被删消息与上下文；须以原始载体核对。\n")
    out = args.out or (os.path.splitext(args.export)[0] + ".timeline.md")
    _write(out, "\n".join(md) + "\n")
    print("时间线：%s（关键 %d 条，金额相关 %d 条）" %
          (out, sum(1 for r in rows if r["cats"]), len(amounts)))
    return 0


def _claim_template(rows):
    picks = [r["ref"] for r in rows if r["cats"]][:2] or [r["ref"] for r in rows[:1]]
    return [{
        "claim": "（填一句可被反驳的事实主张）",
        "ground_msg_ids": picks,
        "warrant": "（这些消息为何能推出该主张）",
        "backing": "（法条/合同条款/官方凭证，须标现行版本与来源）",
        "qualifier": "按现有导出材料",
        "rebuttal": "（对方最可能的相反主张）",
        "rebuttal_test": "（反驳成立时：撤回 / 降级为待核实）",
        "alternative_explanation": "（对方对同一批消息的最强解释）",
        "evidence_gap": "（还缺哪份原始凭证：支付回单/原始载体/外部时间源）",
    }]


def cmd_toulmin(args):
    """可废止推理：反驳成立则主张降级，Ground 须可定位，须写竞争解释与缺口。"""
    data = load_export(args.export)
    rows = _rows(data)
    refs = {r["ref"] for r in rows}
    claims = []
    if args.claims:
        claims = _read_json(args.claims, "主张清单")
        if not isinstance(claims, list):
            _fail("主张清单必须是数组 [...]；字段见 references/export_schema.md 第 4 节")
        for i, c in enumerate(claims):
            if not isinstance(c, dict):
                _fail("claims[%d] 必须是对象；直接跑一次不带 --claims 的 toulmin 可得到模板" % i)
    md = _md_header("图尔敏论证结构", data, args)
    md += ["会话：%s\n" % data.get("chat", "?"),
           "> 六要素：主张/根据/保证/支撑/限定/反驳。反驳成立 → 撤回或降级；保证无支撑 → 推论不成立。",
           "> 只归位与校验引用，不判断真伪；法律结论由律师定稿。\n"]
    total_g, invalid = 0, 0
    if not claims:
        md += ["## ⚠ 已降级为证据池（未提供 claims）\n",
               "> 本产物**未生成六要素论证**，不能当作可废止推演结果使用。",
               "> 把 `toulmin` 终端输出的模板存成 JSON，再以 `--claims` 重跑。\n",
               "| # | 时间 | 发言人 | 内容 | 要素 | ref |", "| --- | --- | --- | --- | --- | --- |"]
        for r in rows:
            if r["cats"]:
                md.append("| %d | %s | %s | %s | %s | %s |" %
                          (r["idx"], _md_cell(r["iso"]), _md_cell(r["sender"]),
                           _md_cell(r["text"], 50), _md_cell("/".join(r["cats"])), _md_cell(r["ref"])))
    else:
        fields = [
            ("warrant", "保证(Warrant)", "待补：事实为何能推出主张"),
            ("backing", "支撑(Backing)", "待补：法条/合同/官方凭证，须标版本"),
            ("qualifier", "限定(Qualifier)", "待补：如'按现有证据'"),
            ("rebuttal", "反驳(Rebuttal)", "待补：对方的相反主张"),
            ("rebuttal_test", "反驳检验", "待判定：反驳成立时撤回还是降级"),
            ("alternative_explanation", "竞争解释", "待补：对方对同一批消息的最强解释"),
            ("evidence_gap", "证据缺口", "待补：还缺哪份原始凭证"),
        ]
        for c in claims:
            md.append("## 主张：%s\n" % _md_cell(c.get("claim", "?")))
            gids = c.get("ground_msg_ids") or []
            if isinstance(gids, str):
                gids = [gids]
            if not isinstance(gids, list):
                gids = []
            gids = [_text(g) for g in gids]
            bad = [g for g in gids if g not in refs]
            total_g += len(gids)
            invalid += len(bad)
            md.append("- **根据(Ground)**：%s%s" % (
                "、".join(_md_cell(g) for g in gids) if gids else "待补（无 Ground 则推论不成立）",
                "　⚠ 无法定位：" + "、".join(_md_cell(g) for g in bad) if bad else ""))
            for key, label, hint in fields:
                md.append("- **%s**：%s" % (label, _md_cell(c.get(key)) or hint))
            md.append("")
    out = args.out or (os.path.splitext(args.export)[0] + ".toulmin.md")
    _write(out, "\n".join(md) + "\n")
    print("论证结构：%s" % out)
    if not claims:
        print("⚠ 未提供 --claims：已降级为「证据池」，未生成六要素论证，不能作为可废止推演结果。")
        print("   把下面这段存为 主张.json，再用 `--claims 主张.json toulmin` 重跑：")
        print(json.dumps(_claim_template(rows), ensure_ascii=False, indent=2))
    else:
        print("   %d 条主张；Ground 引用 %d 个，无法定位 %d 个。" % (len(claims), total_g, invalid))
        if not total_g:
            print("⚠ 所有主张均无 Ground 引用：推论不成立，须填 ground_msg_ids。")
        elif invalid:
            print("⚠ 有 Ground 无法定位：须回查 ref，不得据此下结论。")
        else:
            print("   Ground 引用已校验可定位。")
    return 0


def cmd_identity(args):
    data = load_export(args.export)
    idmap = {}
    if args.identity:
        idmap = _read_json(args.identity, "身份映射")
        if not isinstance(idmap, dict):
            _fail("身份映射必须是对象 {\"sender_id\": {...}}")
    senders = {}
    for m in data["messages"]:
        sid = _text(m.get("sender_id")) or _text(m.get("sender")) or "未知"
        senders.setdefault(sid, {"count": 0})
        senders[sid]["count"] += 1
    md = _md_header("身份印证链", data, args)
    md += ["> 填写的姓名/手机号只是主张；附可核验外部凭证才可能印证。",
           "> 门槛：real_name/phone/org 三项齐全 + evidence 含 verifiable=true，才标「有可核验凭证」。\n",
           "| 标识 | 次数 | 实名 | 手机号 | 所属方 | 凭证 | 状态 |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    skipped = 0
    for sid, info in sorted(senders.items(), key=lambda x: -x[1]["count"]):
        meta = idmap.get(sid, {})
        if not isinstance(meta, dict):
            meta, skipped = {}, skipped + 1
        ev_all = meta.get("evidence") or []
        if not isinstance(ev_all, list):
            ev_all = []
        ev_ok, ev_desc = [], []
        for e in ev_all:
            if isinstance(e, dict):
                if e.get("verifiable") is True:
                    ev_ok.append(e)
                ev_desc.append(_text(e.get("type", "?")))
            else:
                skipped += 1
        missing = [k for k in ("real_name", "phone", "org") if not meta.get(k)]
        if missing:
            status = "待核实：缺" + "/".join(missing)
        elif ev_ok:
            status = "有可核验凭证，待核验原件（不等同已印证）"
        elif ev_all:
            status = "仅列凭证线索且不可核验，属待补"
        else:
            status = "仅当事人填写，属主张，未印证"
        md.append("| %s | %d | %s | %s | %s | %s | %s |" % (
            _md_cell(sid), info["count"], _md_cell(meta.get("real_name")) or "—",
            _md_cell(meta.get("phone")) or "—", _md_cell(meta.get("org")) or "—",
            _md_cell("、".join(ev_desc)) or "—", _md_cell(status)))
    if skipped:
        md.append("\n> ⚠ 身份映射中 %d 项结构不合法已跳过，须回查补齐。\n" % skipped)
    md.append("\n> 印证路径：支付机构实名回单/对方自认/官方注册信息/公证/司法鉴定，须写清来源与可核验性；微信非实名制。\n")
    out = args.out or (os.path.splitext(args.export)[0] + ".identity.md")
    _write(out, "\n".join(md) + "\n")
    print("身份印证链：%s（%d 人，未附凭证一律为「主张」）" % (out, len(senders)))
    return 0


# ───────────────────── 自我进化运行时 ─────────────────────

def _append_log(path, entry):
    _check_write(path)
    ensure_dir(os.path.dirname(path))
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry + "\n")
    except OSError as e:
        _fail("无法写入进化日志 %s：%s" % (path, e))


def _one_line(s):
    return re.sub(r"\s+", " ", s or "").strip()


def cmd_reflect(args):
    """阶1：写进化日志（vault/），不写证据产物。"""
    ts = now_iso()
    note = _one_line(args.note)
    if args.kind == "correction":
        _append_log(os.path.join(VAULT, "corrections.md"), "- [%s] %s" % (ts, note))
        print("已记录纠正 → vault/corrections.md")
    else:
        fn = "what-worked.md" if args.kind == "worked" else "what-failed.md"
        _append_log(os.path.join(LEARNINGS, fn), "- [%s] %s" % (ts, note))
        print("已记录%s → vault/learnings/%s" % ("经验" if args.kind == "worked" else "失败", fn))
    print("提示：复现 ≥3 次且过质量门才晋升（见 learn）。")
    return 0


def cmd_learn(args):
    """阶2：起草规则，status=proposed 待人工审批。"""
    ensure_dir(RULES_DIR)
    rule = {"rule": _one_line(args.rule), "reasoning": _one_line(args.reasoning),
            "promoted_at": now_iso(), "status": "proposed"}
    print("质量门：真改进？可复用？够具体？够通用？是否触碰证据铁律？")
    slug = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", rule["rule"])[:30] or "rule"
    path = os.path.join(RULES_DIR, slug + ".json")
    _dump(path, rule)
    _append_log(os.path.join(HISTORY, now_iso()[:10] + ".md"),
                "- [%s] 提议规则：%s（status=proposed）" % (now_iso(), rule["rule"]))
    print("已起草（待审批）：%s" % path)
    print("⚠ 未审批不生效；规则不得改证据能力边界。")
    return 0


def cmd_regress(args):
    """阶3前：基线须绑定同一输入 + 同一工具/规则版本，否则拒绝比较。"""
    data = load_export(args.export)
    current = {}
    for r in _rows(data):
        for c in r["cats"]:
            current[c] = current.get(c, 0) + 1
    ensure_dir(BASELINES)
    base_path = os.path.join(BASELINES, "baseline.json")
    if os.path.exists(base_path):
        base = _read_json(base_path, "回归基线")
        if "counts" in base:
            if base.get("input_sha256") != _input_hash(args):
                print("⚠ 基线与当前输入不同，拒绝比较（须同一份已锚定样本）。")
                return 1
            if base.get("tool_version") != TOOL_VERSION or base.get("ruleset_sha256") != _ruleset_hash():
                print("⚠ 工具/规则集版本已变，命中数不可直接比较。")
            bcounts = base["counts"]
        else:
            bcounts = base
            print("⚠ 旧基线未绑定输入哈希与版本，仅供参考。")
        print("回归检测：基线 vs 当前（类别命中数）")
        regressed = []
        for c in sorted(set(list(bcounts) + list(current))):
            b, n = bcounts.get(c, 0), current.get(c, 0)
            flag = ""
            if b > 0 and n == 0:
                flag = " ⚠ 骤降为0"
                regressed.append(c)
            elif n < b * 0.5:
                flag = " ⚠ 下降过半"
                regressed.append(c)
            print("  %s：%d → %d%s" % (c, b, n, flag))
        if regressed:
            print("⚠ 疑似退化：%s，建议回滚。" % "、".join(regressed))
            return 1
        print("回归通过（仅覆盖词表粗筛，不替代人工通读）。")
    else:
        _dump(base_path, {"input_sha256": _input_hash(args), "tool_version": TOOL_VERSION,
                          "ruleset_sha256": _ruleset_hash(), "counts": current})
        print("首次运行：已建立基线（输入哈希 + 工具版本 + 规则集版本）")
    return 0


def cmd_all(args):
    # 同一 --out 传给六个命令会互相覆盖，此处隔离。
    saved = args.out
    if saved:
        print("提示：all 模式忽略 --out，产物按各自默认后缀生成。")
    args.out = None
    try:
        for fn in (cmd_anchor, cmd_validate, cmd_extract, cmd_timeline, cmd_toulmin, cmd_identity):
            print("\n=== %s ===" % fn.__name__.replace("cmd_", ""))
            rc = fn(args)
            if rc:
                return rc
    finally:
        args.out = saved
    return 0


def main(argv=None):
    _setup_stdio()
    p = argparse.ArgumentParser(prog="chat-evidence", description="微信记录 → 证据草稿 + 自我进化")
    flags = (("--export", "导出 JSON（只读，属二手派生材料）"),
             ("--out", "输出路径（仅单命令有效）"),
             ("--identity", "身份映射 JSON（须含 evidence 数组）"),
             ("--claims", "主张清单 JSON（toulmin 用；缺省会打印模板）"))
    for flag, help_ in flags:
        p.add_argument(flag, help=help_)
    sub = p.add_subparsers(dest="cmd")
    cmds = [("validate", cmd_validate), ("anchor", cmd_anchor), ("extract", cmd_extract),
            ("timeline", cmd_timeline), ("toulmin", cmd_toulmin), ("identity", cmd_identity),
            ("all", cmd_all), ("regress", cmd_regress)]
    for name, fn in cmds:
        sp = sub.add_parser(name)
        for flag, _ in flags:
            sp.add_argument(flag, default=argparse.SUPPRESS)  # 前置/后置两种顺序皆可，且不覆盖根值
        sp.set_defaults(func=fn)
    sp = sub.add_parser("reflect")
    sp.add_argument("--kind", choices=["worked", "failed", "correction"], required=True)
    sp.add_argument("--note", required=True)
    sp.set_defaults(func=cmd_reflect)
    sp = sub.add_parser("learn")
    sp.add_argument("--rule", required=True)
    sp.add_argument("--reasoning", required=True)
    sp.set_defaults(func=cmd_learn)

    args = p.parse_args(argv)
    if not getattr(args, "cmd", None):
        p.error("请指定子命令")
    if args.cmd not in ("reflect", "learn") and not args.export:
        p.error("该命令需要 --export")
    _protect(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
