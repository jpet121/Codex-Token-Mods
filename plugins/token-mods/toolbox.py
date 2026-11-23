"""Local evidence reader and Codex CLI usage reporter. Python 3.9+."""
import argparse
import json
import os
import sys
from pathlib import Path


def excerpt(args):
    with args.file.open("rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        start = max(0, size - args.limit) if args.tail else args.offset
        if start > size:
            raise ValueError("Offset is beyond the end of the file.")
        stream.seek(start)
        data = stream.read(args.limit)
    if b"\x00" in data:
        raise ValueError("Use a text export for binary or UTF-16 input.")
    print(f"{args.file} | bytes [{start}, {start + len(data)}) of {size}")
    print(data.decode("utf-8", errors="replace"))


def usage(args):
    totals = dict(input_tokens=0, cached_input_tokens=0, output_tokens=0)
    completed = failed = started = 0
    with args.file.open("rb") as raw:
        prefix = raw.read(2)
    encoding = "utf-16" if prefix in (b"\xff\xfe", b"\xfe\xff") else "utf-8-sig"
    with args.file.open(encoding=encoding) as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError(f"Invalid event at line {number}")
            kind = event.get("type")
            if kind == "turn.started":
                started += 1
            if kind == "turn.failed":
                failed += 1
            if kind != "turn.completed":
                continue
            counts = event.get("usage")
            if not isinstance(counts, dict) or any(
                type(counts.get(key)) is not int or counts[key] < 0 for key in totals
            ) or counts["cached_input_tokens"] > counts["input_tokens"]:
                raise ValueError(f"Invalid usage record at line {number}")
            for key in totals:
                totals[key] += counts[key]
            completed += 1
    print(json.dumps(dict(completed_turns=completed, failed_turns=failed,
                          started_turns=started, **totals,
                          uncached_input_tokens=totals["input_tokens"] -
                          totals["cached_input_tokens"]), indent=2))
    if not completed or failed or started != completed:
        raise ValueError("Incomplete or failed run. Exclude from savings comparisons.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("excerpt", help="Read a bounded UTF-8 text excerpt")
    read.add_argument("file", type=Path)
    read.add_argument("--limit", type=int, default=4096)
    position = read.add_mutually_exclusive_group()
    position.add_argument("--offset", type=int, default=0)
    position.add_argument("--tail", action="store_true")
    report = commands.add_parser("usage", help="Read a codex exec --json event file")
    report.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.command == "excerpt":
        if args.limit < 1 or args.limit > 65536 or args.offset < 0:
            parser.error("Use a nonnegative offset and a limit of 1 through 65536 bytes.")
        excerpt(args)
    else:
        usage(args)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        sys.exit(f"Error: {error}")
