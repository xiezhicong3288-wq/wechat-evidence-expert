# Moect JSON 中立导入

使用已授权的 Moect JSON 导出（`metadata.application=Moect`、`messages` 数组、`count`），不要把 RMFH、`.enc` 或原生微信数据库直接传给这个命令。

```
python scripts/main.py --export /path/单个会话.json --out /path/全新目录 neutral-moect
python scripts/main.py --export /path/全新目录/compatible.json validate
```

- 输入只读，新目录必须不存在。`manifest.json` 最后落盘；缺失或命令退出码非零表示本次整理未完成。源码包不读微信进程、不下载资源、不对附件解密。
- 一个输入会话对应一个输出目录。使用导出的 `metadata.session` 作稳定归属，以 `metadata.name` 为本次显示名；当前昵称不证明历史昵称或实名，未知群聊状态不臆填。
- `messages.jsonl` 每条保存原字段及 `$.messages[i]` 定位；`compatible.json` 留下 `extra.source_raw` 和原始时间字段。规范化后的 `msg_id` 来自导出的 `server_id`，仍需原数据库核验真实性；相同编号重复时仅首次作为规范化唯一 ID，其余保留原值及位置并列问题。
- `conversation_index.csv` 为浏览用，首字符疑似表格公式会转义；逐字引用必须回到原 JSON。`type_summary.csv` 和 `按消息类型/*.csv` 保留所有消息类型，未知类型不改成普通文字；系统消息不补虚假 wxid。单会话输出目录以用户指定的新目录为准，建议用显示名和稳定会话 ID 命名，脚本目前不自动改名。
- `attachment_index.jsonl` 分开收录顶层及引用内嵌资源，每项含父消息、原记录和资源 JSON 指针；manifest 分列两种数量。`resource_report_index.jsonl` 收录每行原报告及诊断字段，并定位顶层/引用中的编号；`issues.jsonl` 分列缺失、加密、多位置引用及无法解析的转账金额。资源报告行数不等于消息数，文件路径与标称状态不证明媒体已被回放或内容完整。
- Moect 带 `￥`/`¥` 的转账卡片只在规则明确时提取供技能检索的 `extra.amount` 数值，并保留 `extra.amount_exact` 原小数字符串、原字段和状态；浮点数不可用于精确金额计算，也不当作实际付款或到账。`metadata.time_zone` 只作原导出声明，原 Unix 秒和显示时间分别保留。
- 完成标记前再次核对源 JSON 与附件报告的字节哈希；如果运行中变化，命令失败且不写 `manifest.json`，保留新目录供诊断，重做时另选新目录。
- 输入若只有 JSON 而无原数据库独立行清单，仅能验证“导出件→整理件”的一致性；不能宣称微信源记录全量、账号控制权或司法采信。
