# Token Mods for Codex — Windows team edition

Install once for your Windows user; use in fresh Codex chats across projects. Ask for the result you want. Codex handles tool arguments and chat selection. If needed, prefix a request with `$token-tools`.

## Install

1. Have Python 3.10+ and an installed, signed-in Codex CLI with plugin/hook support. Check `py -3 --version` and `codex --version` in PowerShell. If needed, run `codex` once and complete its normal sign-in.
2. Extract the ZIP. Open PowerShell inside the extracted Token-Mods-Windows-Team folder and run:

   ```powershell
   py -3 install.py
   ```

3. Review the nine Token Mods hooks in Codex Settings > Hooks or `/hooks` in the CLI. They belong to token-mods@local-token-tools. The installer leaves trust review to you and retains normal approval/sandbox settings. Updates to hook content can require review again.
4. Start a fresh Codex chat in any project. Ask **“Token Mods, status.”** If a new tool needs normal Codex permission, review that request normally.

The installer creates a private Python runtime with Pillow and pypdf, installs the plugin and the token-tools skill, and adds the optional tokenmods launcher to your user PATH. The first install downloads dependencies from PyPI. Open a new terminal once to pick up the launcher. No separate API key is needed for the default local tools or Codex workers; workers use your existing Codex account.

## Everyday requests

- “Give me a handoff for this chat.”
- “Show the full result.”
- “Stop shortening reads in this chat.” / “Resume shortening reads.”
- “Read this report for the decisions and caveats.”
- “Research this deeply.”
- “Get an independent second opinion on this approach.”
- “Show this screenshot at original resolution.”

For ambiguous chats in the same folder, choose by topic. You should not need to find a session UUID or write tool JSON.

## Nine helpers, one interface

| Helper | What it does | How it runs |
|---|---|---|
| Mods | Persistent switches and settings across projects or for one chat. | Ask for status/changes; optional panel. |
| Savings Proof | Reports observed input, cached-input and output counts, plus worker overhead. | Capture is automatic; reports on request. Actual billing/causal savings remain unknown. |
| Handoff | Captures chat material and builds continuation drafts with source/tool/Git evidence where available. | Capture is automatic; ask for a draft. Semantic worker only when requested. |
| Effort Optimizer | Task-based effort advice. | Suggestions by default; desktop picker stays under your control. Explicit workers/owned companion can apply auto effort. |
| Model Router | Runs requested independent workers with configured or explicitly selected models. | Requested worker calls. Native spawn hooks offer advice. |
| Input Router | Shortens supported large file/connector results, retaining originals and paging fields. | Automatic eligible extraction; exact/full/semantic reads on request. |
| Research Router | Bounded research with planning, fetched sources, relevance checks and cited synthesis. | Requested quick or deep research. |
| Efficient Browser Use | Smaller local image previews with original-coordinate mapping. | Ask to preview/describe an image. Some screenshot calls get format advice. |
| Cache Clock | Observes request age and measured cache reads. | Observation automatic; ask for a report. Future expiry unknown; warming disabled. |

Automatic paid notes are off. Research, independent reviews and semantic readers consume account usage when requested. Workers normally have a 90-second timeout and a shared twelve-call budget per supplied session; failed calls also use a slot. No percentage or dollar saving is guaranteed.

## Optional terminal

```powershell
tokenmods
tokenmods handoff
tokenmods full
tokenmods pause
tokenmods resume
tokenmods panel
```

Run from your project folder. Handoff saves a draft; full preserves the next eligible read; pause saves this chat's module choices and resume restores them. Add --everywhere for explicit global pause/resume. You can also use the chat tools without this terminal launcher.

## Data and boundaries

Prompts, final replies, source originals and usage records are stored locally under `%USERPROFILE%\.codex-token-mods` while the corresponding features are enabled. Explicit workers send their task/source material through your Codex account. Handoff exports redact common credential shapes, not every possible secret; review an export before sharing it.

The suite does not take over an existing desktop chat's model/effort picker, transparently intercept all hosted search, or replace arbitrary host-owned image blocks. PDF notes cover the text layer; scanned pages need visual/OCR tools. Cache expiry and actual billed savings are unknown. Optional Firecrawl needs its own installed/authenticated service. A registered-runtime provisioning problem can prevent shell/node helpers in nested CLI sessions; the local MCP paths provide working alternatives without disabling safeguards.

Validated here on Windows with Codex CLI 0.171.0-alpha.13 and desktop package 26.1117.4957.0. A build lacking plugins/hooks is not supported by this installer. Linux/macOS have not received live acceptance testing. Version support is a requirement, not a promise that every Codex build exposes the same interfaces.

## Remove

```powershell
py -3 install.py --uninstall
```

This unregisters the suite and removes owned easy-interface files/PATH entry; it retains core source, runtime, backups and chat records. Unrelated Codex settings remain. To remove only the easy interface, use `py -3 easy-start/install.py --uninstall`.

Official prerequisites: [Codex CLI](https://learn.chatgpt.com/docs/codex/cli) and [Python for Windows](https://www.python.org/downloads/windows/).
