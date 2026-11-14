# 聊天导出与辅助材料格式

核心脚本接受一个 UTF-8 JSON 对象，`messages` 为消息对象列表。只处理用户合法取得并授权的导出；本包没有微信备份读取或解密能力，不保证任何第三方导出工具默认兼容。

```json
{
  "chat": "合成示例会话",
  "is_group": false,
  "exported_at": "2026-01-01T00:00:00Z",
  "messages": [
    {
      "msg_id": "example-001",
      "timestamp": 1767225600,
      "sender": "合成参与者甲",
      "sender_id": "synthetic_a",
      "type": "text",
      "content": "请核对约定金额。",
      "extra": {}
    }
  ]
}
```

## 字段

- `timestamp`：有限数值的 Unix 秒时间戳，代表时间点。不能把本地钟表时间直接当作 Unix 秒；毫秒导出需经明确的格式转换。
- `sender`：非空显示名称；`sender_id` 为可选稳定标识，缺少时显示名称只是线索。
- `msg_id`：可选原生消息编号，原样保留。缺少时使用源文件哈希和零基 `idx` 定位；不能把 `idx` 包装成原生编号。
- `type`：字符串，如 text、image、voice、video、file、transfer、system。`content` 为文本字符串，非文字消息可以为空；`extra` 为对象。
- `extra.amount`：转账消息提供的金额值，不代表收款已完成。原币种、支付状态及凭证需另行核实。
- 图片、语音、视频与附件的占位文字不是其内容；本脚本没有 OCR、语音识别或附件真实性鉴别能力。

身份映射是按 `sender_id`（缺省时按 `sender`）索引的对象，例如：

```json
{"synthetic_a": {"real_name": "合成姓名", "phone": "合成号码", "org": "合成机构"}}
```

这些值是输入线索，填齐后仍需外部证据核验。

主张文件为对象列表，可填写 `claim`、`ground_msg_ids`、`warrant`、`backing`、`qualifier`、`rebuttal`。`ground_msg_ids` 使用消息中存在且唯一的原生 `msg_id`，或用明确的 `idx:0`、`idx:1` 形式引用源数组位置；不要使用裸序号混淆原生编号。主张与推理文本均属于用户或分析者的陈述，不是导出记录本身。
