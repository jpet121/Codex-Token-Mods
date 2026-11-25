"""Run a synthetic Token Mods read through its real hook and check the saved original."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "token-mods" / "mods.py"
SESSION = "sample-delivery-review"
DECISION = "DECISION: delivery date 2026-12-03 café"


def replay():
    source = "irrelevant background\n" * 1000 + DECISION + "\n" + "other text\n" * 1000
    with tempfile.TemporaryDirectory(prefix="token-mods-demo-") as temp:
        work = Path(temp)
        (work / "report.txt").write_bytes(source.encode("utf-8"))
        env = {**os.environ, "TOKEN_MODS_DIR": str(work / "state"), "PYTHONUTF8": "1"}

        def call(args, event=None):
            result = subprocess.run(
                [sys.executable, str(PLUGIN), *args], cwd=work, env=env,
                input=json.dumps(event) if event is not None else None,
                check=True, capture_output=True, encoding="utf-8",
            )
            return json.loads(result.stdout)

        def hook(kind, **fields):
            return call(["hook"], dict(hook_event_name=kind, session_id=SESSION,
                                       turn_id="sample-turn", **fields))

        hook("SessionStart", cwd=str(work), model="offline-example")
        hook("UserPromptSubmit", prompt="Find the delivery date.")
        result = hook("PostToolUse", tool_name="Bash",
                      tool_input={"command": "Get-Content report.txt"}, tool_response=source)
        if result.get("decision") != "block" or DECISION not in result.get("reason", ""):
            raise RuntimeError("The hook did not return an extract with the delivery decision.")
        events = call(["events"])
        record = next(e for e in events if e["action"] == "extracted")
        saved = json.loads(Path(record["detail"]["source"]).read_text(encoding="utf-8"))
        if saved != source:
            raise RuntimeError("The saved original differs from the supplied tool result.")

        print(f"Source: {len(source.splitlines()):,} lines")
        print(f"Extract: {DECISION}")
        print("Saved original: exact match")
        print("Original SHA-256:", hashlib.sha256(saved.encode("utf-8")).hexdigest())


if __name__ == "__main__":
    replay()
