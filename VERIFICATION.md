# What has been verified

## Public offline checks

All 45 tests passed on Windows and Linux with Python 3.12. Both jobs also replayed a synthetic 2,001-line read through the plugin hook. The extract contained the delivery decision, and the recovered original matched the full input. These runs used no paid models or signed-in Codex sessions. [Public test run](https://github.com/jpet121/Codex-Token-Mods/actions/runs/45658697476) · [Replay source](examples/replay_read.py)

| Suite | Tests per platform | What it exercises |
| --- | ---: | --- |
| Core integration | 16 | Hook events, local tool server, full source recovery, PDF text, image previews, and usage records |
| Completion checks | 17 | Handoffs, source handling, worker input, usage comparison, and recovery paths |
| Flow checks | 5 | Routing, extraction, image previews, and simulated worker events |
| Easy interface | 7 | Project and chat selection, reversible pause, and settings changed while paused |

The first public run exposed a test fixture that required a Codex executable even though it replaced the worker process. The repaired fixture selects the running Python executable for that simulated process. The production worker still requires the configured Codex CLI. [Initial run](https://github.com/jpet121/Codex-Token-Mods/actions/runs/45658085302)

## Repeat the offline checks

Use a disposable source checkout. The core integration suite writes machine-specific hook paths in its checkout. Install the Python dependencies and the PDF test fixture before running the suites.

```powershell
py -3 -m pip install -r requirements.txt "reportlab>=4,<5"
py -3 examples/replay_read.py
py -3 test_suite.py
py -3 test_completion.py
py -3 plugins/token-mods/test_flow.py
py -3 easy-start/test_easy.py
```

## Released Windows edition

The release record identifies live Windows checks using Codex CLI `0.171.0-alpha.13` and desktop package `26.1117.4957.0`. Those checks cover extraction, PDF text and reuse, sourced research, independent models, effort ownership, image previews, compaction, handoffs, usage reconciliation, and plain-language operation across projects. Hook trust, approval settings, and the sandbox remained active. Live Linux and macOS acceptance is open.

The published Windows installer ZIP has SHA-256 `bc33e35fd110a4db5a33d98d16101a26b96c956d2d3db67a05275cbe14359b45`. A fresh download matched that digest and all 38 entries in the manifest inside the ZIP. The repository's own manifest covers its current source and documentation. [Windows release](https://github.com/jpet121/Codex-Token-Mods/releases/tag/v1.1.0) · [Current source checksums](SHA256SUMS.txt)
