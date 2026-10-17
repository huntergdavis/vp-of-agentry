"""Claude session usage counts each API message once in an explicit trial."""

import json
import tempfile
import unittest
from pathlib import Path

from claude_usage import anchors, usage_between


def message(message_id, model, read, write, uncached, output):
    return {"type": "assistant", "timestamp": "2026-10-16T00:00:00Z",
            "message": {"id": message_id, "model": model,
                        "usage": {"input_tokens": uncached,
                                  "cache_creation_input_tokens": write,
                                  "cache_read_input_tokens": read,
                                  "output_tokens": output}}}


class ClaudeUsageTests(unittest.TestCase):
    def test_repeated_message_records_are_counted_once(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.jsonl"
            events = [message("before", "opus", 1, 2, 3, 4),
                      message("trial-1", "opus", 10, 20, 30, 40),
                      message("trial-1", "opus", 10, 20, 30, 40),
                      {"type": "user", "message": {"content": "ignored"}},
                      message("trial-2", "opus", 100, 200, 300, 400)]
            path.write_text("".join(json.dumps(event) + "\n" for event in events))
            points = anchors(path)
        self.assertEqual(len(points), 3)
        self.assertEqual(points[1]["last_line"], 3)
        result = usage_between(points, 0, 2)
        self.assertEqual(result["message_count"], 2)
        self.assertEqual(result["tokens"]["total_input_tokens"], 660)
        self.assertEqual(result["tokens"]["output_tokens"], 440)

    def test_conflicting_duplicate_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.jsonl"
            events = [message("same", "opus", 1, 2, 3, 4),
                      message("same", "opus", 1, 2, 3, 5)]
            path.write_text("".join(json.dumps(event) + "\n" for event in events))
            with self.assertRaisesRegex(ValueError, "conflicting repeated"):
                anchors(path)

    def test_mixed_model_trial_is_rejected(self):
        points = [{"model": model, "tokens": dict.fromkeys(
            ("input_tokens", "cache_creation_input_tokens",
             "cache_read_input_tokens", "output_tokens"), 1)}
            for model in ("opus", "opus", "sonnet")]
        with self.assertRaisesRegex(ValueError, "mixed Claude models"):
            usage_between(points, 0, 2)


if __name__ == "__main__":
    unittest.main()
