# wechat-evidence-expert

Current source: [`skills/chat-evidence`](skills/chat-evidence/SKILL.md). The root `wechat-evidence-expert.zip` packages the same source for import. The original 2026-10-29 archive is retained under `archive/` as a rollback reference.

Version 1.3.1 fixes saving review state in deep Windows folders. The skill imports Moect JSONL directly and carries the original export hash and physical message location into analysis. The [actual-use review workflow](skills/chat-evidence/references/evolution_architecture.md) ties later user corrections to reproducible tests. The [official-source evidence workflow](skills/chat-evidence/references/wechat_evidence_sources.md) covers mainland China civil evidence.

For authorized Moect conversation JSON or JSONL, `neutral-moect` creates a per-message index, nickname and message-type CSVs, attachment and resource-report indexes, and a compatible JSON file. `nickname_index.csv` points to `按昵称/<display-name>_<session-hash>/conversation_index.csv`. Use the session identifier to distinguish identical display names. See the [Moect format and verification scope](skills/chat-evidence/references/moect_export.md). Run dispute analysis commands when the user requests them.

```bash
python skills/chat-evidence/scripts/main.py --export /path/to/Moect-chat.json --out /path/to/new-output neutral-moect
python skills/chat-evidence/scripts/main.py --export /path/to/new-output/compatible.json validate
python skills/chat-evidence/scripts/main.py --export /path/to/new-output/compatible.json --out /path/to/new-anchor.json anchor
python -m unittest discover -s skills/chat-evidence/scripts -p 'test_*.py' -v
```

The source and output paths must refer to authorized local material. Never commit real chat records, attachment files, identity mappings or output directories. Updating this GitHub repository alone does not update an installed personal ChatGPT Skill; installation has its own verification step.
