# wechat-evidence-expert

Current source: [`skills/chat-evidence`](skills/chat-evidence/SKILL.md). The root `wechat-evidence-expert.zip` packages the same source for import. The original 2026-10-29 archive is retained under `archive/` as a rollback reference.

This skill reads authorized JSON chat exports. For Moect 1.2.8 JSON, its `neutral-moect` command creates a full per-message index, nickname and message-type CSVs, attachment and resource-report indexes, and a compatible JSON file. `nickname_index.csv` points to `按昵称/<display-name>_<session-hash>/conversation_index.csv`; a nickname is a display label, not a verified identity. It does not log in to WeChat, decrypt a backup, recover unavailable media, verify the original database, or draw legal conclusions. Later legal analysis commands run only when explicitly requested.

```bash
python skills/chat-evidence/scripts/main.py --export /path/to/Moect-chat.json --out /path/to/new-output neutral-moect
python skills/chat-evidence/scripts/main.py --export /path/to/new-output/compatible.json validate
python skills/chat-evidence/scripts/main.py --export /path/to/new-output/compatible.json --out /path/to/new-anchor.json anchor
python -m unittest discover -s skills/chat-evidence/scripts -p 'test_*.py' -v
```

The source and output paths must refer to authorized local material. Never commit real chat records, attachment files, identity mappings or output directories. Updating this GitHub repository alone does not update an installed personal ChatGPT Skill; installation has its own verification step.
