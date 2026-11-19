# Moect 会话 JSON 与 JSONL 中立导入

使用已授权的 Moect 会话导出，`metadata.application` 为 `Moect`。输入为单个 UTF-8 JSON 或 `.jsonl` 文件，大小不超过 128 MiB。RMFH、`.enc`、原生数据库、收藏和资源报告各自保留，需使用各自的处理入口。

## 公开版本与兼容范围

- 截至 2026-11-19，Moect 最新正式发布为 `v1.3.0`，提交 `7498e9f21ab283edb55a5d6a2e17c7ad696cf168`。会话 JSON 使用 `metadata`、`messages` 和整数 `count`。会话 JSONL 第一物理行只含 `metadata`，其后每个非空行一个消息对象。输入如有空白行，后续位置仍按物理行号记录。重复键、无效行和尾部计数行会中止导入。收藏使用 `category: "favorites"` 和 `items`。 [Moect v1.3.0 正式发布](https://github.com/mofan6/Moect/releases/tag/v1.3.0) · [会话导出代码](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/core/exporting.py#L156-L227) · [收藏导出代码](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/core/favorites.py#L339-L349)
- v1.3.0 可能在 `extra.game_emoji` 保存游戏表情字段并附图，也调整了转发子项、系统提示和语音资源的呈现。逐项定位至 Moect 导出对象，保存其显示文字及资源标称状态。Moect 导出器会筛掉部分内部字段，导出原对象所能证明的范围限于该导出件。v1.2.8 和 v1.3.0 格式用合成样本验证；真实账号提取、媒体回放和完整性需要另行核对。 [导出字段清理](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/core/exporting.py#L43-L46) · [游戏表情与语音资源](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/core/resources.py#L441-L486) · [转发字段映射](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/wx4/forward.py#L20-L31)

## 导入和复核

```
python scripts/main.py --export /path/单个会话.jsonl --out /path/全新目录 neutral-moect
python scripts/main.py --export /path/全新目录/compatible.json validate
```

- 输入只读，新目录必须不存在。`manifest.json` 最后落盘；缺失或命令退出码非零表示本次整理未完成。源码包不读微信进程、不下载资源、不对附件解密。
- 保留原会话文件名和相邻的同批 `<stem>_assets` 目录。例如 `chat.json` 和 `chat.jsonl` 都使用各自同批的 `chat_assets/resource-report.jsonl`。已重命名的归档副本须查回同批布局。`metadata.filters`、`export_options` 和 `demo` 记录导出声明，实际范围须另行复核。`manifest.source_demo` 保留布尔声明，缺失或非布尔时为 `null`。
- 一个输入会话对应一个输出目录。使用导出的 `metadata.session` 作稳定归属，以 `metadata.name` 为本次显示名；当前昵称不证明历史昵称或实名，未知群聊状态不臆填。
- `messages.jsonl` 保留每条原字段和源位置。会话 JSON 使用 `$.messages[i]` 的零基位置。会话 JSONL 使用 `line:N` 的一基物理行号。`compatible.json` 保存 `extra.source_raw`、源位置、原始时间字段及源导出哈希。顶层 `server_id` 重复时，每条保留源编号及位置，均省略兼容 `msg_id`，主张请使用 `idx:N`。旧兼容件保留了首条 `msg_id` 时，主张命令也会拒绝该重复编号。
- `conversation_index.csv` 为浏览用，首字符疑似表格公式会转义，逐字引用须回到原 JSON。`type_summary.csv` 和 `按消息类型/*.csv` 保留来源类型。`nickname_index.csv` 指向以显示名和稳定会话标识衍生的子目录。单会话输出的顶层目录使用 `--out` 提供的名称。
- `attachment_index.jsonl` 分开收录顶层、引用与合并转发子项的资源。每项保留父消息和资源位置，例如 `$.messages[0].forward.messages[0].resources[0]` 或 `line:2.forward.messages[0].resources[0]`。`resource_report_index.jsonl` 保留报告原行及诊断字段，并列出关联消息位置。`manifest.json` 分列顶层消息、顶层附件和内嵌附件数量。`issues.jsonl` 标出缺失、加密、多位置匹配及无法解析的卡片金额。资源状态与文件路径只记录导出所报情况，媒体回放和完整性须另核。
- Moect 带 `￥`/`¥` 的转账卡片只在规则明确时提取供技能检索的 `extra.amount` 数值，并保留 `extra.amount_exact` 原小数字符串、原字段和状态；浮点数不可用于精确金额计算，也不当作实际付款或到账。`metadata.time_zone` 只作原导出声明，原 Unix 秒和显示时间分别保留。
- 完成标记前再次核对源文件与附件报告的字节哈希。文件在运行中变化时命令失败并省略 `manifest.json`，重做时另选新目录。JSONL 只统计实际解析的消息行，范围和完整性须结合源设备核对。
- 争议分析引用的 `idx` 指向兼容件。`anchor`、`extract`、`timeline` 和 `toulmin` 另带原导出哈希和位置供核对。只有导出件时，一致性检查限于导出与整理之间。 [兼容件和分析产物格式](export_schema.md)
