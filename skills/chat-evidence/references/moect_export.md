# Moect JSON 中立导入

使用已授权的 Moect JSON 导出（`metadata.application=Moect`、`messages` 数组、`count`），不要把 RMFH、`.enc` 或原生微信数据库直接传给这个命令。

## 公开版本与兼容范围

- 截至 2026-11-19，Moect 最新正式发布为 `v1.3.0`，提交 `7498e9f21ab283edb55a5d6a2e17c7ad696cf168`。会话 JSON 仍使用 `metadata`、`messages`、`count`。`neutral-moect` 读取单个会话 JSON。若现有文件为 JSONL 且仍能读取同一会话，可另导出 JSON 并记录范围。若只有 JSONL，保留原件及逐行定位，待有可追溯的格式转换后再做兼容分析。收藏 `data.json` 使用 `category: "favorites"` 和 `items`，属于独立材料。 [Moect v1.3.0 正式发布](https://github.com/mofan6/Moect/releases/tag/v1.3.0) · [会话导出代码](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/core/exporting.py#L156-L227) · [收藏导出代码](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/core/favorites.py#L339-L349)
- v1.3.0 可能在 `extra.game_emoji` 保存游戏表情字段并附图，也调整了转发子项、系统提示和语音资源的呈现。逐项定位至 Moect 导出对象，保存其显示文字及资源标称状态。Moect 导出器会筛掉部分内部字段，导出原对象所能证明的范围限于该导出件。现有 v1.2.8 合成用例和基于 v1.3.0 源码形状的合成样本验证 JSON 整理，不覆盖真实账号的提取、媒体回放或完整性。 [导出字段清理](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/core/exporting.py#L43-L46) · [游戏表情与语音资源](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/core/resources.py#L441-L486) · [转发字段映射](https://github.com/mofan6/Moect/blob/7498e9f21ab283edb55a5d6a2e17c7ad696cf168/wx4/forward.py#L20-L31)

## 导入和复核

```
python scripts/main.py --export /path/单个会话.json --out /path/全新目录 neutral-moect
python scripts/main.py --export /path/全新目录/compatible.json validate
```

- 输入只读，新目录必须不存在。`manifest.json` 最后落盘；缺失或命令退出码非零表示本次整理未完成。源码包不读微信进程、不下载资源、不对附件解密。
- 保留原会话 JSON 文件名和相邻的同批 `<stem>_assets` 目录。CLI 以该布局发现 `<stem>_assets/resource-report.jsonl`，例如 `chat.json` 对应 `chat_assets/resource-report.jsonl`。已重命名的归档副本须查回原导出布局，找不到同批报告时注明未提供。只从 `metadata.filters`、`export_options` 和 `demo` 报告导出声称的范围、过滤和演示状态，实际覆盖范围须另行复核。
- 一个输入会话对应一个输出目录。使用导出的 `metadata.session` 作稳定归属，以 `metadata.name` 为本次显示名；当前昵称不证明历史昵称或实名，未知群聊状态不臆填。
- `messages.jsonl` 每条保存原字段及 `$.messages[i]` 定位；`compatible.json` 留下 `extra.source_raw` 和原始时间字段。规范化后的 `msg_id` 来自导出的 `server_id`，仍需原数据库核验真实性；相同编号重复时仅首次作为规范化唯一 ID，其余保留原值及位置并列问题。
- `conversation_index.csv` 为浏览用，首字符疑似表格公式会转义，逐字引用须回到原 JSON。`type_summary.csv` 和 `按消息类型/*.csv` 保留来源类型。`nickname_index.csv` 指向以显示名和稳定会话标识衍生的子目录。单会话输出的顶层目录使用 `--out` 提供的名称。
- `attachment_index.jsonl` 分开收录顶层、引用与合并转发子项的资源。每项保留父消息和资源 JSON 指针，例如 `$.messages[i].forward.messages[j].resources[k]`。`resource_report_index.jsonl` 保留报告原行及诊断字段，并列出关联消息位置。`manifest.json` 分列顶层消息、顶层附件和内嵌附件数量。`issues.jsonl` 标出缺失、加密、多位置匹配及无法解析的卡片金额。资源状态与文件路径只记录导出所报情况，媒体回放和完整性须另核。
- Moect 带 `￥`/`¥` 的转账卡片只在规则明确时提取供技能检索的 `extra.amount` 数值，并保留 `extra.amount_exact` 原小数字符串、原字段和状态；浮点数不可用于精确金额计算，也不当作实际付款或到账。`metadata.time_zone` 只作原导出声明，原 Unix 秒和显示时间分别保留。
- 完成标记前再次核对源 JSON 与附件报告的字节哈希；如果运行中变化，命令失败且不写 `manifest.json`，保留新目录供诊断，重做时另选新目录。
- 输入若只有 JSON 而无原数据库独立行清单，仅能验证“导出件→整理件”的一致性；不能宣称微信源记录全量、账号控制权或司法采信。
