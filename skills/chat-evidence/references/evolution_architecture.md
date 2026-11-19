# 基于反馈的受控改进

每次能够核对结果的实际使用结束后，记录一次观察。只把可重现、会影响下一次同类任务的问题转成修复。Waylon 的采集、预检和整理可以用同一流程复盘。

## 从运行结果登记

在获授权的运行环境中打开本次回执，先核对使用范围、产物和已知缺失。`--receipt` 可用 Waylon 预检 JSON、Waylon 归档 `manifest.json`、本技能中立整理 `manifest.json` 或分析 `*.anchor.json`。分析指纹只覆盖文件指纹和消息索引。如果要复盘 `all` 整体，逐项查看所有产物后再登记整个操作的观察。

```bash
python3 "$SCRIPT" --state-dir "$STATE" review-use --receipt "$RECEIPT" --origin actual --skill-version 1.3.0
python3 "$SCRIPT" --state-dir "$STATE" review-use --receipt "$RECEIPT" --origin actual --skill-version 1.3.0 --run-id "$RUN_ID" --feedback corrected
```

- `actual` 由调用者按确实发生的使用填写。用已知测试材料时填 `synthetic`，演示材料有明确标记时也进入这一路径。实际版本不可核实时填 `unknown`。
- `pending` 表示尚无用户反馈，`confirmed` 表示用户确认具体结果，`corrected` 表示用户指出了具体差异。初次实际使用生成独立 `run_id`。补录或重试时将输出的编号作为 `$RUN_ID`，使用同一回执和技能版本。未回应时保留 `pending`。
- 采集、提前失败或整流程没有单一机器回执时，可将观察到的结果另存为 `wechat-use-observation/1`。仅填写 `stage`（`acquisition`、`intake`、`organize`、`analysis`），`status` 和对应 `exit_code`（`success/0`、`partial/1`、`failed/2`，按观察归一化）；例如 `{"schema":"wechat-use-observation/1","stage":"acquisition","status":"partial","exit_code":1}`。它是操作者观察，复查原日志时一并记录适用范围。
- 改进记录只写回执 SHA-256、阶段、状态、允许的聚合计数、版本与反馈状态，不复制材料路径、账号、原文、附件名及源材料哈希。状态放在技能目录以外的授权目录，材料和改进记录按各自范围保存。两者都留在授权环境。

## 复现与修复

回执显示 `check_source_scope_or_reproduce` 或 `review_reported_scope` 时，先区分缺附件、筛选范围或客户端差异与程序缺陷。`reproduce_feedback` 时，将用户指出的差异抽象成最小脱敏问题。只有证据足以复现时才动手。

```bash
python3 "$SCRIPT" --state-dir "$STATE" reflect --kind correction --note "脱敏的识别纠正"
python3 "$SCRIPT" --state-dir "$STATE" learn --rule "候选规则" --reasoning "适用范围和依据"
python3 "$SCRIPT" --export "$SYNTHETIC_FIXTURE" --state-dir "$STATE" regress
```

`reflect` 追加反馈；`learn` 只生成 `status=proposed` 提案，分类器不会读取这些提案，也不会因手动改为 `active` 自动改变行为。没有 `promote` 子命令。

`regress` 将基线与样本文件哈希绑定，对同一输入比较类别命中数量。首次建立基线不等于回归通过；数量没有下降也不等于分类准确、证据充分或法律正确。应另用带人工标注的合成样本检查漏判、误判、短确认、否认、转述、条件限制、身份歧义和不利证据。

1. 记录旧版本、脱敏输入的哈希、命令和环境、预期与实际差异。先修会造成缺失、错配、误判或无法复核的问题。源材料不完整时保留缺口，无法复现时保留线索。
2. 用单个合成或授权脱敏用例稳定复现，再做最小修改。用同一用例检验修复，并做与风险相邻的回归。效率主张使用相同输入、机器、参数和计时边界复测，记录耗时及产物是否一致。
3. 将通过复测的修改、适用版本、结果和回退标记写入原技能的版本记录。区分代码提交、安装、实际调用和用户确认。正式发布沿用现有授权与宿主入口。

此流程在实际使用结束、本次反馈明确到达或相应复测发生时触发。规则提案等待实现和复测，调用不会启动后台任务或自动应用提案。
