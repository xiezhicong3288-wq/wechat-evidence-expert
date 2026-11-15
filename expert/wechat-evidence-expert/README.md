# 微信证据整理专家（铁证 / Ironclad）

把已解密的微信导出整理为**可复核、边界清晰的证据草稿**，并在使用中自我进化；不证明导出源真实性，不出具鉴定意见。Agent 型专家，分类：法务安全（11-SecurityCompliance）。

## 安装

已注册到 `~/.workbuddy/plugins/marketplaces/my-experts/.codebuddy-plugin/marketplace.json`，专家中心可见。迁移到其它机器时，把本目录拷到 `~/.workbuddy/plugins/marketplaces/my-experts/plugins/` 后重跑：

```bash
python scripts/register_expert.py <expert-dir>
```

## 用法

专家中心搜「铁证」或「微信证据整理专家」。首次对话可发：
> 先审查这份导出的证据能力与上游凭证缺口，再整理证据草稿；标清能证明/不能证明的边界、对方最强替代解释和可复现锚点

常用：①按第11条第一款六项做证据能力审查，列待核实项与上游凭证清单；②用可废止推演检验主张（反驳是否成立、Ground 能否定位、对方会怎样解释同一批消息）；③核对所引法条与标准现行版本，给出复现三元组和证据缺口清单。

内置 `skills/chat-evidence`：证据整理与进化脚本、参考文档、合成样本。**能力清单、边界声明、合规铁律、法条/标准现行版本与废止状态**详见 `skills/chat-evidence/SKILL.md` 与 `skills/chat-evidence/references/export_schema.md` 附录。

头像 `avatars/expert.png` 已内置：512×512、271.8KB 的 AI 插画（圆眼镜取证专家持带锁盾牌，聊天气泡与天平图标，深灰蓝背景）。由 ImageGen 生成（约 5–10 积分）后，用标准库裁去工具水印、重采样到 512²、去掉 eXIf 元数据重编码；sha256 `dfdb4ea1b287aa5616842c6d69b440b35dde7ca4e3d1bdd111e9bf96b9981291`，无随机性与时间戳字段。需要更小体积时可用标准库确定性重建几何徽章版（约 16.8KB；本包不另存副本）。

## 运行环境

Python 3.8+，仅标准库，全程本地离线作业，不上传聊天数据。

## 许可

MIT。
