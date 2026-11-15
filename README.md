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

## Branch-only: hardened WorkBuddy expert package

This branch adds [`expert/wechat-evidence-expert/`](expert/wechat-evidence-expert/) — a complete WorkBuddy expert package (13 files, including `.codebuddy-plugin/plugin.json`, the agent persona and the avatar). It is a **separate evolution line**, not a replacement for `skills/chat-evidence/`:

| | `skills/chat-evidence/` (main source) | `expert/wechat-evidence-expert/` (this branch) |
| --- | --- | --- |
| Skill name / schema | `wechat-evidence-expert`, schema 1.1 | `chat-evidence`, schema 1.2, tool 2.2.2 |
| Commands | includes `neutral-moect` (Moect 1.2.8 import) | 10 evidence commands, no Moect adapter |
| Focus | neutral per-message indexing, CSV reports, tests + CI | explicit proof limits, upstream provenance slots, byte-reproducible outputs, defeasible Toulmin reasoning, four-tier identity corroboration |
| Inputs | Moect JSON + compatible JSON | authorized decrypted-export JSON only |
| Robustness | unittest + GitHub Actions | 300 randomized stress rounds (0 defects), 52/52 regression, GBK/cp936 console support, read-only input guard, friendly rejection of malformed Unicode / NaN / Infinity / deep nesting |

`skills/chat-evidence/`, its tests, `moect_adapter.py`, `.github/workflows/` and `archive/` are **untouched** on this branch, so the existing CI stays green. The CI does **not** cover the new package, and the two lines have not been merged. Do not treat this directory as a drop-in replacement for the main source.

To use it, copy `expert/wechat-evidence-expert/` into WorkBuddy's `plugins/marketplaces/my-experts/plugins/` and re-register, or copy `expert/wechat-evidence-expert/skills/chat-evidence/` as a user-level skill. If both are installed, the 9 shared files must be byte-identical. Reproducibility tuple: input sha256 + tool version + ruleset sha256; evidence products never contain the local clock. Outputs are evidence drafts, not proof of authenticity — upstream chain of custody, a third-party TSA timestamp, identity documents and current versions of cited laws/standards still require human and third-party verification, and legal conclusions are for a licensed lawyer.
