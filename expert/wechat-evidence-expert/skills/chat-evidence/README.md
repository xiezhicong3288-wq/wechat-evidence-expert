# chat-evidence

微信记录→证据草稿(边界诚实/可复现/可废止论证)。仅本地、不篡改、可溯源。

## 安装

放到 skills 目录（项目级 `.workbuddy/skills/chat-evidence/` 或用户级 skills 目录）即可，仅用 Python 标准库。

## 用法

脚本不依赖当前工作目录，但**必须用绝对路径调用**；`python scripts/main.py` 在其他目录会报 `can't open file`。先跑这条一键自检（可直接复制、不写产物）：

```bash
python "$HOME/.workbuddy/skills/chat-evidence/scripts/main.py" --export "$HOME/.workbuddy/skills/chat-evidence/examples/sample_export.json" validate
M="$HOME/.workbuddy/skills/chat-evidence/scripts/main.py"
python "$M" --export "导出.json" --identity "idmap.json" all
python "$M" --export "导出.json" toulmin            # 无主张：打印可直接保存的 claims 模板
python "$M" --export "导出.json" --claims "主张.json" toulmin
python "$M" reflect --kind worked --note "..."
python "$M" learn --rule "..." --reasoning "..."
python "$M" regress --export "导出.json"
```

Windows PowerShell / cmd 里 `python` 常不在 PATH（跳 Microsoft Store，rc=9009），改用自带解释器：`$PY = (Get-ChildItem "$HOME\.workbuddy\binaries\python\versions\*\python.exe" | Select-Object -First 1).FullName`，再 `& $PY $M ...`。完整说明见 `SKILL.md` 第「二·零」节。

路径含空格或中文必须加引号；`--export/--out/--identity/--claims` 放在子命令前后均可。没有 `主张.json` 时先跑不带 `--claims` 的 `toulmin`，把终端打印的模板（已填好真实 `ref`）存成 JSON 再重跑；不带 claims 的产物会明确标「已降级为证据池」。字段见 `references/export_schema.md` 第 2b 节。

产物是 **UTF-8 无 BOM**：VS Code / 现代记事本直接可读；Windows PowerShell 5.1 默认按 ANSI 读会乱码，须 `Get-Content -Encoding UTF8`。不要给产物加 BOM（会破坏 JSON 可复算）。运行环境另见 `SKILL.md` 第「二·零」节。

产物写到导出同目录：`*.anchor.json`、`*.evidence_index.json`、`*.timeline.md`、`*.toulmin.md`、`*.identity.md`。进化日志在 `vault/`，规则在 `rules/`；退出码非 0 即失败，非法输入给一行中文错误而非 traceback。`--out` 仅单命令有效，且不得指向任一输入文件（导出/claims/identity），否则拒止以保护原始证据。字段异常不会静默跳过，会汇总为产物里的 `reproducibility.structural_warnings` 并在 `validate` 打印。中文 Windows 的 GBK/cp936 终端与重定向已做 UTF-8 兼容，不会因提示符号报错。

产物是证据草稿：只做完整性校验与结构化整理，不证明导出源真实性；未核实项标 `待核实`。引用用原生 `msg_id` 或内容派生 `msg_ref`（不含下标）；产物不写本机时钟，同输入 + 同工具版本 + 同规则集可字节级复现。字段与上游凭证见 `references/export_schema.md`，推演见 `references/multi_role_sandbox.md`。

若同时安装在用户级 skills 与专家包内，部署后须核对 9 个共享文件 sha256 一致，避免漂移。

## 运行环境

Python 3.8+，纯标准库，离线可用。

## 许可

MIT。
