"""Exact token anchors reject missing or reset Codex counters."""

import json
import tempfile
import unittest
from pathlib import Path

from codex_usage import anchors, usage_delta


def token_event(timestamp, input_tokens, output_tokens):
    totals = {"input_tokens": input_tokens, "cached_input_tokens": input_tokens // 2,
              "cache_write_input_tokens": 0, "output_tokens": output_tokens,
              "reasoning_output_tokens": output_tokens // 2,
              "total_tokens": input_tokens + output_tokens}
    return {"timestamp": timestamp, "type": "event_msg",
            "payload": {"type": "token_count", "info": {"total_token_usage": totals}}}


class CodexUsageTests(unittest.TestCase):
    def test_explicit_anchors_count_only_the_selected_interval(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.jsonl"
            events = [token_event("t0", 100, 10), {"type": "response_item", "payload": {}},
                      token_event("t1", 250, 25), token_event("t2", 400, 50)]
            path.write_text("".join(json.dumps(event) + "\n" for event in events))
            points = anchors(path)
        self.assertEqual([point["line"] for point in points], [1, 3, 4])
        result = usage_delta(points, 0, 1)
        self.assertEqual(result["tokens"]["input_tokens"], 150)
        self.assertEqual(result["tokens"]["output_tokens"], 15)
        self.assertEqual(result["end"]["timestamp"], "t1")

    def test_counter_reset_inside_interval_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.jsonl"
            events = [token_event("t0", 100, 10), token_event("t1", 80, 20),
                      token_event("t2", 150, 30)]
            path.write_text("".join(json.dumps(event) + "\n" for event in events))
            points = anchors(path)
        with self.assertRaisesRegex(ValueError, "reset"):
            usage_delta(points, 0, 2)


if __name__ == "__main__":
    unittest.main()
