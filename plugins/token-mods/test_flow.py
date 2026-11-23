"""Offline checks. A fake subprocess produces deterministic Codex-style events."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import codex_flow as flow


class FlowChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.events = [dict(type="turn.started"),
                       dict(type="item.completed", item=dict(type="agent_message", text="Sample reply")),
                       dict(type="turn.completed", usage=dict(input_tokens=30, cached_input_tokens=10, output_tokens=4))]

    def test_routing(self):
        for prompt, tier in [("List the colors", "quick"), ("Design a garden", "deep"),
                             ("Write a letter", "standard")]:
            self.assertEqual(flow.route(prompt), tier)

    def test_brief(self):
        source = self.root / "source.txt"
        source.write_bytes(b"oranges\ngreen apples\n")
        result = flow.extract(source, "green apples", 6)
        self.assertEqual(result["matches"], [dict(byte=8, excerpt="green apples")])
        self.assertFalse(flow.extract(source, "banana", 6)["matches"])

    def test_preview(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Install Pillow for image checks")
        original, small = self.root / "a.png", self.root / "b.png"
        Image.new("RGB", (1800, 900)).save(original)
        flow.preview(original, small, 1280)
        with Image.open(small) as out:
            self.assertEqual(out.size, (1280, 640))
        with self.assertRaises(FileExistsError):
            flow.preview(original, small, 1280)

    def test_incomplete_usage(self):
        f = self.root / "events"
        f.write_text('{"type":"turn.started"}\n', encoding="utf-8")
        self.assertFalse(flow.read_events(f)[0]["clean"])
        f.write_text('{"type":"turn.started"}\n{"type":"turn.completed"}\n', encoding="utf-8")
        self.assertFalse(flow.read_events(f)[0]["usage_complete"])

    def test_workflow(self):
        from argparse import Namespace
        from subprocess import CompletedProcess
        args = Namespace(prompt="List the colors", tier="auto", effort=None, model=None,
                         plan=False, source=[], image=[])
        def simulate(cmd, input, stdout):
            self.assertEqual(input, b"List the colors")
            self.assertIn("chosen-model", cmd)
            stdout.write("\n".join(map(json.dumps, self.events)).encode())
            return CompletedProcess(cmd, 0)
        with patch.object(flow, "STATE", self.root), patch.dict(os.environ, CODEX_FLOW_MODEL_QUICK="chosen-model"), patch.object(flow.subprocess, "run", simulate), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(flow.run(args), 0)
            folder = next(flow.runs_dir().iterdir())
            self.assertIn("Sample reply", (folder / "handoff.md").read_text())
            self.assertIn("cached_input_tokens", (folder / "result.json").read_text())
            flow.status()
            flow.compare(folder, folder)
            self.events.append(dict(type="turn.failed"))
            self.assertNotEqual(flow.run(args), 0)

if __name__ == "__main__":
    unittest.main()
