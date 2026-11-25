# Install Token Mods on Windows

## Before you install

Use Python 3.10 or later and a signed-in Codex CLI with plugin and hook support. Check `py -3 --version` and `codex --version` in PowerShell. If needed, start `codex` once and sign in. [Codex CLI](https://developers.openai.com/codex/cli/) · [Python for Windows](https://www.python.org/downloads/windows/)

1. Download the [Windows installer ZIP](https://github.com/jpet121/Codex-Token-Mods/releases/download/v1.1.0/Token-Mods-Windows-Team.zip).
2. Check the ZIP against the SHA-256 on the [release page](https://github.com/jpet121/Codex-Token-Mods/releases/tag/v1.1.0). In PowerShell, use `Get-FileHash .\Token-Mods-Windows-Team.zip -Algorithm SHA256`.
3. Extract the ZIP. Open PowerShell in the folder that contains `install.py`.
4. Run `py -3 install.py`. The first install downloads Python dependencies for the private runtime and adds the optional `tokenmods` launcher to your user PATH.
5. Review the nine hooks for `token-mods@local-token-tools` in **Settings → Hooks** or with `/hooks`. Updated hook content can require a new review.
6. Start a fresh Codex chat in a project folder. Ask **“Token Mods, status.”** If Codex needs help selecting the skill, prefix the request with `$token-tools`.

## Use it across projects

Open a new terminal for the PATH change to take effect. Run these commands in the project folder. When several captured chats share that folder, the launcher may ask you to select one by topic.

| Command | Result |
| --- | --- |
| `tokenmods` | Show chat status, enabled helpers, and available usage counts. |
| `tokenmods handoff` | Save a draft for continuing this chat. Review it before sharing. |
| `tokenmods full` | Keep the next eligible read in full. |
| `tokenmods pause` / `tokenmods resume` | Pause or restore this chat's module choices. Add `--everywhere` for a global change. |
| `tokenmods panel` | Open the settings panel. |

Ordinary local tools use no separate API key. Requested workers use your Codex account. Workers normally have a 90-second timeout and a shared 12-call budget per supplied session. Failed calls also use a slot. Optional Firecrawl needs its own configured service. PDF reading uses the text layer. Scans need a separate visual or text-recognition step.

## Remove the tools

From the extracted folder, run `py -3 install.py --uninstall`. This unregisters the plugin and removes the easy-interface files and its PATH entry. Core source, runtime, backups, and captured chat records remain on disk. To remove only the easy interface, run `py -3 easy-start/install.py --uninstall`.

[Project overview](README.md) · [Verification and tested versions](VERIFICATION.md)
