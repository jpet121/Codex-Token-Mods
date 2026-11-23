---
name: token-tools
description: "Use installed Token Mods in plain language for status, handoffs, full results, large sources, screenshots and requested independent research/reviews. Handle session lookup and tool arguments internally. Load this skill through token_mods input_router action full when shell access is unavailable."
---

Make the nine Token Mods feel like normal Codex capabilities. The user supplies a task; choose the existing token_mods MCP tools and handle their arguments. Return the useful result in plain language. Keep IDs, JSON, interpreter paths and setup instructions out of routine replies.

## Find this chat internally

Use the current chat ID when the environment supplies it. Otherwise call mods_status action sessions, match the current working folder, and inspect handoff_read for candidate chats until the latest captured user request matches this conversation. A worker's prompt is not the user's chat. Folder alone is insufficient when several chats share it. If the match remains ambiguous, offer short topic descriptions for the person to choose, never require a UUID.

Pass the resolved session to session reports, handoffs, worker budgets and local changes. A user request about this chat is session-scoped. Apply global settings when the user says everywhere, across projects or from now on. SessionStart hooks already enable ordinary use; installation is per Windows user.

## Choose the task, not a module tutorial

| User intent | Existing capability |
|---|---|
| “Token Mods status” / “Are the token tools working?” | mods_status list; use the current session when known. Resolve a session only for a chat-specific question. Add savings_proof/cache_clock when requested. Present enabled/paused behavior and any real failure in a few lines. |
| “Give me a handoff” / “Help me continue in a fresh chat” | handoff_read for this chat, then write a concise continuation from the captured facts. For a saved draft use handoff action draft. Use a semantic worker only when requested. Show the saved file or copyable handoff, not an ID. |
| “Show the full result” / “Don't shorten this read” | mods action full, module input-router, this session. Recover an already-shortened result from its saved original using input_router range; expand bounded ranges until the requested evidence is covered. |
| “Stop shortening reads” / “Resume shortening reads” | mods action off/on, module input-router, this session. Keep other module preferences. |
| “Read this large report for the decisions” | input_router brief with path and task; expand exact ranges for quotes, edits and missing evidence. It returns selected extracts. An explicitly requested independent/semantic read uses action worker. |
| “Research X” / “Research X deeply” | research_router run with mode quick, or action deep. Supply the question and this session. Let configured models apply; honor a model/effort the user names. Report sources and material gaps. |
| “Get an independent second opinion on this” | model_router run with sufficient task/source context and this session. Independent workers do not inherit the full chat. |
| “Show this screenshot” / “Show original resolution” | image_preview with path and optional full true; use its native image and coordinate mapping. |
| “Use less/more effort” | Honor the desktop's user-owned effort choice. effort_optimizer plan is advice; configured auto applies to explicit workers or companion-owned sessions. |

Usage/capture/compaction logging and supported large-read extraction already run through trusted hooks. Effort advice is automatic in suggest mode. Model switching, research and image replacement are not universal background interception. Cache expiry is unknown and warming remains disabled.

Workers consume real account usage. Start them for requested research, independent review or semantic reading; keep ordinary status, handoff inspection and extraction free of extra worker calls. Automatic paid notes stay off unless explicitly enabled. Preserve full sources and name incomplete coverage. Read-only failures retain the original evidence. Use normal Codex permissions.

## Terminal fallback

The installed `tokenmods` launcher offers status, handoff, full, pause/resume and panel without Python paths or JSON. It selects the chat from its current project and shows topic choices when several match. `pause` saves this chat's enabled-module choices; `resume` restores them. `--everywhere` explicitly changes global scope. Use it when a terminal is available, with the MCP routes above when nested CLI shell execution is unavailable. Existing desktop-owned model/effort control stays with the host picker.
