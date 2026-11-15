---
name: chat-evidence
description: "将已解密的微信聊天记录导出(JSON)整理为诉讼/谈判可用的证据草稿，并随使用自我迭代进化。能力：完整性哈希锚定+上游溯源待填槽位+能力边界声明、时间线、角色名单、法律要素抽取、可废止图尔敏论证(反驳成立即降级)、身份印证强度分级；异常输入显式告警或友好拒止，绝不静默漏证；自我进化：反思日志→经验晋升为规则→阶3须人工审批后手工沉淀(脚本不自动 promote)，含绑定输入哈希的回归检测。只做完整性校验与结构化整理，不证明导出源真实性；全程本地、不篡改原文、可溯源。用于微信证据整理、聊天记录举证、证据索引、时间线、谈判材料、与政府及职能部门对接。"
description_zh: "微信记录→证据草稿(边界诚实/可复现/可废止论证)"
description_en: "WeChat evidence drafting skill: explicit proof limits, reproducible outputs, defeasible Toulmin reasoning"
---

# 微信聊天记录证据级整理（边界诚实 / 可复核 / 可废止）

把已解密的微信导出（JSON）整理为**证据草稿**；只归类、不篡改、可溯源，并在使用中自我迭代。

## 何时使用 / 何时不用

- 用：诉讼举证、谈判准备、与政府/职能部门对接，需要时间线、要素索引、论证结构、印证缺口。
- 输入须是已解密导出 JSON；解密、取证镜像、公证、鉴定不在范围内。
- 不用：出具鉴定意见/公证书/TSA 证书、胜诉预测，或对导出源真实性下结论——交第三方机构或执业律师。

## 零、能力边界（先读，再看任何产物）

输入是从原始载体派生的**二手材料**。

| 能证明 | 不能证明 |
| --- | --- |
| 自锚定起文件字节未变则哈希可复算一致 | 导出内容等于手机原始记录 |
| 同输入+同工具版本+同规则集可复现**字节级一致**产物（不写本机时钟） | 导出未被截取、删减或脱离上下文 |
| 结论可回指稳定锚点 `msg_ref` | 消息生成时间真实（设备时钟可改） |
| 哪些事项尚待核实 | 主体身份真实、款项实际支付、法律关系成立 |

本机时钟不是可信时间戳。任何「已证明真实性」「已印证」「未剪辑」须有外部凭证，否则写「待核实」；工具不代取证人作清洁性声明。

## 一、工作流（顺序不可颠倒）

1. **证据能力审查**：按法释〔2018〕16号第11条第一款六项与《民事诉讼证据的若干规定》第93条逐项标 `已核实`/`待核实`（生成主体与时间、保管介质、提取工具与方式、**过程是否可重现**、有无增删、能否验证）。缺上游凭证先补。
2. **溯源与锚定**：`anchor` 记输入哈希、链式指纹、复现三元组，保留 `source_provenance` 待填槽位（原始载体/镜像哈希/导出工具与版本/操作人/过程留痕/保管链/第三方存证）。可信时间戳由 TSA 或存证平台签发，工具只标 `not_obtained`。
3. **结构化**：`validate`（仅结构）→ `extract`（粗筛）→ `timeline` → `identity`（分级）。
4. **可废止论证**：`toulmin` 不是六格填空。反驳成立则撤回/降级；保证无支撑则推论不成立；Ground 须可定位；每主张写对方最强替代解释与证据缺口。
5. **找己方弱点**：产出缺口清单（单方陈述、聊天转述无支付凭证、短确认含糊、消息脱上下文、对方质证角度）。只挑有利事实不能定稿。
6. **自我进化**：`reflect` → 复现≥3 次且过质量门 `learn`（proposed 待审批）→ `regress`（绑定同一输入与版本）。

## 二·零、零门槛起步（先读这一节）

脚本内部用 `__file__` 定位技能目录，**不依赖当前工作目录**；但 `python scripts/main.py` 这种相对写法只在 cwd 恰好是技能目录时才有效，在其他目录会报 `can't open file`（rc=2）。因此**必须用脚本绝对路径调用**。下面这条是一键自检，完全自足、可直接复制、不写任何产物：

```bash
python "$HOME/.workbuddy/skills/chat-evidence/scripts/main.py" --export "$HOME/.workbuddy/skills/chat-evidence/examples/sample_export.json" validate
```

为缩短后续命令，先定义一次（Bash / Git Bash / WorkBuddy 终端）：

```bash
M="$HOME/.workbuddy/skills/chat-evidence/scripts/main.py"
```

- **Windows PowerShell / cmd**：`python` 常不在 PATH（会跳 Microsoft Store，rc=9009），`py -3` 也可能没有。改用 WorkBuddy 自带解释器，不写死版本号：
  ```powershell
  $PY = (Get-ChildItem "$HOME\.workbuddy\binaries\python\versions\*\python.exe" | Select-Object -First 1).FullName
  $M  = "$HOME\.workbuddy\skills\chat-evidence\scripts\main.py"
  & $PY $M --export "导出.json" validate
  ```
- 若只装在专家包副本里，把路径换成 `.../my-experts/plugins/wechat-evidence-expert/skills/chat-evidence/scripts/main.py`。
- **AI / 专家调用约定**：直接用本 `SKILL.md` 所在目录拼出的绝对路径，不要假设 cwd，也不要用相对 `scripts/main.py`。
- 产物为 **UTF-8 无 BOM**。VS Code、现代记事本直接正常；Windows PowerShell 5.1 默认按 ANSI 读会乱码，须 `Get-Content -Encoding UTF8`，勿因此给产物加 BOM（会破坏 JSON 可复算与产物一致性）。中文终端/重定向的 GBK 编码问题已由脚本统一 UTF-8 输出解决。

## 二、命令映射

下表的 `$M` 来自上一节；若未定义 `$M`，把每条里的 `"$M"` 换成上面一键自检中的完整路径。

| 目的 | 运行 |
| --- | --- |
| 校验导出 | `python "$M" --export "<导出.json>" validate` |
| 完整性锚定 | `python "$M" --export "<导出.json>" anchor` |
| 抽取法律要素 | `python "$M" --export "<导出.json>" extract` |
| 生成时间线 | `python "$M" --export "<导出.json>" timeline` |
| 可废止论证 | `python "$M" --export "<导出.json>" --claims "<主张.json>" toulmin` |
| 身份印证链 | `python "$M" --export "<导出.json>" --identity "<idmap.json>" identity` |
| 全部执行 | `python "$M" --export "<导出.json>" --identity "<idmap.json>" all` |
| 记录可教时刻 | `python "$M" reflect --kind worked --note "..."`（`--kind` 三选一：`worked` / `failed` / `correction`） |
| 晋升经验为规则 | `python "$M" learn --rule "..." --reasoning "..."` |
| 回归检测 | `python "$M" regress --export "<导出.json>"` |

路径含空格或中文必须加引号。`--export/--out/--identity/--claims` 放在子命令前后均可。`--out` 仅单命令有效；`all` 六份产物按默认后缀分别生成。产物带 `reproducibility`（输入 sha256 / 工具版本 / 规则集版本 / 时区声明 / 结构告警）；不写本机时钟是「字节级一致」的前提。

**没有 `主张.json` 也能起步**：先跑 `toulmin`（不带 `--claims`），终端会打印一份填好本导出真实 `ref` 的 claims 模板，存成 JSON 再重跑即可。不带 `--claims` 时产物明确标「已降级为证据池」，不得当作可废止推演结果。

## 三、输入与引用

- 字段、上游凭证、**claims 模板**、异常输入兼容口径见 [references/export_schema.md](references/export_schema.md)：`chat`、`is_group`、`schema_version`、`tz_offset_hours`、`source_provenance`、`messages[]`。
- 未声明 `tz_offset_hours` 时只按 UTC 展示并标待核实，不得直接用于举证。时间戳疑似毫秒时按 /1000 推定并显式标「毫秒推定/待核实」——单位属上游事实，工具不擅自认定。
- 原生 `msg_id` 优先作引用；否则用 时间+发送者+类型+内容 派生的 `msg_ref`（不含下标）。`idx` 仅定位，引用须附输入 sha256；完全相同消息共用锚点；原生 `msg_id` 重复会告警，此时 ref 不唯一。
- `identity_map.json` 的 `evidence` 数组列凭证类型/来源/可核验性；填写的姓名手机号是主张，不自动标已印证。「有可核验凭证」须 `real_name/phone/org` 三项齐全且 `evidence` 含 `verifiable: true`。
- 非 text 类型会连同 `content`/`extra` 一并展开，避免语音、链接、文件消息静默漏证；表格单元转义管道符与尖括号，截断一律留 `(截断)` 标记。

## 四、外部标准

对错由外部标准判定：法释〔2018〕16号第11条（第一款六项）、《民事诉讼证据的若干规定》第14/15/93/94条；技术侧现行 GB/T 29360/29361/29362—2023、GA/T 756—2021、GB/T 20520—2006、SF/T 0076—2020、ISO/IEC 27037:2012、NIST SP 800-86 / 800-101 Rev.1。**版本、废止状态、核验日期、名称核验脚注与降级路径统一见 [references/export_schema.md](references/export_schema.md) 附录**；引用前逐条核现行版本，废止版本不得引用；优先用本机 `chinalaw-waylon-expert` 回到法条原文，不可用时到官方站点核验。

## 五、多角色推演

详见 [references/multi_role_sandbox.md](references/multi_role_sandbox.md)。触发词：多角色分析、立场推演、对抗推演、律师/公安/法院/政府/监督视角、运筹决策、博弈沙盘。只推演依法路径；「施压」仅限法定监督渠道且真实有据；禁止捏造、诬告、裹挟司法、贿赂；不给胜诉率等无依据预测；结论由律师定稿。

## 六、自我进化

详见 [references/evolution_architecture.md](references/evolution_architecture.md)。阶 1 自动记日志、阶 2 起草 `proposed` 规则待审批、**阶 3 需人工审批后手工创建子 skill，脚本不提供自动 promote 命令**。`regress` 基线绑定输入哈希、工具版本、规则集版本，样本或版本不一致拒绝比较。

## 七、失败处理

- 非法 JSON / BOM / 路径不存在 / 输出目录不可写 → 一行中文错误 + 非 0 退出，不抛 traceback。
- 中文 Windows 的 GBK/cp936 终端或 `> 日志.txt` 重定向 → 输出统一 UTF-8，不因 ⚠ 等符号触发 `UnicodeEncodeError`。
- `--out` 指向任一输入文件（导出/claims/identity，含大小写与 `..` 路径变体）→ **拒止并保住原文**；只读导出是铁律，须换输出路径。
- 孤立代理字符（损坏的 emoji）、`NaN`/`Infinity`（含 `1e400` 溢出）、JSON 嵌套过深 → **友好拒止并指出位置**，不静默改写原文、不产出非标准 JSON。
- 双向控制符（U+202A–202E / U+2066–2069）与 C0 控制符 → 仅在 Markdown 表格展示层折叠，防止显示顺序被伪造；JSON 产物与原始导出保持原样。
- `messages` 不是数组、或某条消息不是对象 → **拒止并指出下标**，不静默跳过（跳过会造成看不见的漏证）。
- 字段类型异常（毫秒时间戳、`extra=null`、非字符串 `content`/`sender`/`type`、非法时区、schema 版本不符、`msg_id` 重复、空导出）→ 汇总为「结构告警」写入 `reproducibility`，并在 `validate` 终端逐条打印；不影响结构合法性，但举证前须核实。
- 上游凭证缺失或局部填写 → 继续整理，缺项一律标「待核实」，不代作清洁性声明。
- `need_review` 或 Ground 无法定位 → 人工复核，不代下法律结论。
- `regress` 报退化 → 回滚最近规则变更；报「基线与当前输入不同，拒绝比较」→ 属预期保护，换样本或工具升级后先删 `vault/baselines/baseline.json` 再重跑重建基线。

## Invariants

- 只读导出，绝不修改/删除/外传；全程本地，不上传聊天内容。
- 只归类不篡改：引用 `msg_ref` 并注明摘录，不改写原文。
- **边界诚实**：不把完整性校验说成真实性证明，不把主张说成已印证，不把本机时钟说成可信时间戳。
- 未经上游凭证支持标 `待核实`，不代作清洁性声明。
- 证据产物不含本机时钟，同三元组下字节级可复现。
- 进化只改识别/论证规则，不触碰原始内容、哈希锚定与能力边界；不下法律结论。
