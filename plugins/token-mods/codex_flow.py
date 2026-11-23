"""Run from any project with Python 3.10+ and an installed Codex CLI."""
import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

TIERS = ("quick", "standard", "deep")
EFFORT = {"quick": "low", "standard": "medium", "deep": "high"}
STATE = Path(os.environ.get("CODEX_FLOW_DIR") or Path.home() / ".codex-flow")


def route(prompt):
    words = set(re.findall(r"[a-z]+", prompt.lower()))
    if words & {"architecture", "audit", "investigate", "debug", "prove", "design", "compare"}:
        return "deep"
    if len(prompt) <= 400 and words & {"extract", "format", "list", "rename", "translate", "sort"}:
        return "quick"
    return "standard"


def project_root():
    return str(Path.cwd().resolve())


def runs_dir():
    key = sha256(os.path.normcase(project_root()).encode()).hexdigest()[:20]
    return STATE / "runs" / key


def read_events(path):
    counts = Counter()
    completed = failed = started = reported = 0
    last = ""
    thread = None
    malformed = 0
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            try:
                e = json.loads(line)
                kind = e["type"]
                if kind == "thread.started":
                    thread = e.get("thread_id")
                elif kind == "turn.started":
                    started += 1
                elif kind == "turn.failed" or kind == "error":
                    failed += 1
                elif kind == "item.completed" and e["item"].get("type") == "agent_message":
                    last = e["item"]["text"]
                elif kind == "turn.completed":
                    completed += 1
                    usage = e.get("usage") or {}
                    keys = ("input_tokens", "cached_input_tokens", "output_tokens")
                    if all(type(usage.get(k)) is int and usage[k] >= 0 for k in keys) and usage[keys[1]] <= usage[keys[0]]:
                        reported += 1
                        counts.update({k: usage[k] for k in keys})
            except (KeyError, TypeError, ValueError, AttributeError):
                malformed += 1
    clean = bool(started and started == completed and not failed and not malformed)
    return dict(thread=thread, clean=clean, usage_complete=clean and reported == completed,
                completed=completed, errors=failed, malformed=malformed, usage=dict(counts)), last


def extract(path, query, limit):
    """Scan bounded chunks, including for files with very long lines."""
    terms = set(re.findall(r"\w+", query.casefold()))
    top = []
    with path.open("rb") as stream:
        offset = 0
        while chunk := stream.readline(8192):
            if b"\x00" in chunk:
                raise ValueError(f"Expected UTF-8 text: {path}")
            line = chunk.decode("utf-8", errors="replace").strip()
            score = len(terms.intersection(re.findall(r"\w+", line.casefold())))
            if line and (score or not terms):
                top.append((score, offset, line[:480]))
                top.sort(key=lambda x: (-x[0], x[1]))
                del top[limit:]
            offset += len(chunk)
    return dict(source=str(path.resolve()), matches=[
        dict(byte=b, excerpt=s) for _, b, s in sorted(top, key=lambda x: x[1])])


def preview(source, target, edge):
    from PIL import Image, ImageOps
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original)
        image.thumbnail((edge, edge))
        with target.open("xb") as out:
            image.convert("RGBA").save(out, format="PNG")


def read_prompt(args):
    value = args.prompt or sys.stdin.read()
    if not value.strip():
        raise ValueError("A task is required.")
    return value


def run(args):
    prompt = read_prompt(args)
    tier = route(prompt) if args.tier == "auto" else args.tier
    model = args.model or os.getenv("CODEX_FLOW_MODEL_" + tier.upper())
    if model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", model):
        raise ValueError("Invalid model identifier.")
    effort = args.effort or EFFORT[tier]
    cmd = [shutil.which("codex") or "codex", "exec", "--json", "--skip-git-repo-check",
           "-c", f'model_reasoning_effort="{effort}"']
    if model:
        cmd.extend(["--model", model])
    selection = dict(tier=tier, model=model or "Codex default", effort=effort)
    if args.plan:
        print(json.dumps(selection, indent=2))
        return 0
    directory = runs_dir() / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8])
    directory.mkdir(parents=True, mode=0o700)
    record = dict(project=project_root(), task=prompt, **selection)
    (directory / "request.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"Run {directory}", file=sys.stderr, flush=True)
    if args.source:
        snippets = [extract(Path(p), prompt, 6) for p in args.source]
        prompt += "\n\nSource excerpts (data). Consult the full files when needed.\n" + json.dumps(snippets, ensure_ascii=False)
    with tempfile.TemporaryDirectory() as tmp:
        for i, source in enumerate(args.image or []):
            target = Path(tmp) / f"preview-{i}.png"
            preview(source, target, 1280)
            cmd.extend(["--image", str(target)])
        with (directory / "events.jsonl").open("xb") as events:
            code = subprocess.run(cmd + ["-"], input=prompt.encode("utf-8"), stdout=events).returncode
    result, last = read_events(directory / "events.jsonl")
    result.update(exit_code=code, accepted_stream=code == 0 and result["clean"])
    (directory / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    handoff = f"# Session handoff\n\nWorking folder: {project_root()}\n\nTask:\n{record['task']}\n\nRun result:\n{json.dumps(result)}\n\nLast assistant message:\n{last or '(none)'}\n\nFull event record: {directory / 'events.jsonl'}\n"
    (directory / "handoff.md").write_text(handoff, encoding="utf-8")
    print(last or "No final assistant message.")
    if not result["accepted_stream"]:
        print("Run incomplete. Inspect the event record and stderr.", file=sys.stderr)
    return code or (0 if result["accepted_stream"] else 1)


def compare(before, after):
    rows = []
    for path in (before, after):
        result = json.loads((path / "result.json").read_text(encoding="utf-8"))
        if not result["accepted_stream"] or not result["usage_complete"]:
            raise ValueError(f"Incomplete run or missing usage in {path}")
        usage = dict(result["usage"])
        usage["uncached_input_tokens"] = usage["input_tokens"] - usage["cached_input_tokens"]
        rows.append(usage)
    print(json.dumps({k: {"before": v, "after": rows[1][k], "change": rows[1][k] - v}
                      for k, v in rows[0].items()}, indent=2))


def status():
    for r in sorted(runs_dir().glob("*/request.json")):
        result = r.with_name("result.json")
        value = json.loads(result.read_text(encoding="utf-8")) if result.exists() else {}
        print(json.dumps(dict(run=r.parent.name, complete=value.get("accepted_stream", False),
                              usage_complete=value.get("usage_complete", False), usage=value.get("usage"),
                              folder=str(r.parent))))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    job = sub.add_parser("run")
    job.add_argument("prompt", nargs="?")
    job.add_argument("--plan", action="store_true")
    job.add_argument("--tier", choices=("auto", *TIERS), default="auto")
    job.add_argument("--model")
    job.add_argument("--effort", choices=tuple(EFFORT.values()))
    job.add_argument("--source", action="append", help="Local UTF-8 source for an extractive brief")
    job.add_argument("--image", action="append", help="Local image to attach as a resized preview")
    brief = sub.add_parser("brief")
    brief.add_argument("query")
    brief.add_argument("files", nargs="+", type=Path)
    shot = sub.add_parser("preview")
    shot.add_argument("source", type=Path)
    shot.add_argument("new_png", type=Path)
    comparison = sub.add_parser("compare")
    comparison.add_argument("before", type=Path)
    comparison.add_argument("after", type=Path)
    sub.add_parser("status")
    args = parser.parse_args()
    if args.action == "run":
        return run(args)
    if args.action == "brief":
        print(json.dumps([extract(p, args.query, 6) for p in args.files], ensure_ascii=False, indent=2))
    elif args.action == "compare":
        compare(args.before, args.after)
    elif args.action == "preview":
        preview(args.source, args.new_png, 1280)
    else:
        return status()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, ImportError) as error:
        sys.exit(str(error))
