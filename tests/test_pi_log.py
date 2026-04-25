import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import codoxear.pi_log as _pi_log
from codoxear.pi_log import pi_model_context_window
from codoxear.pi_log import read_pi_run_settings
from codoxear.pi_messages import read_pi_message_tail_snapshot


class TestPiLogRunSettings(unittest.TestCase):
    def test_pi_model_context_window_prefers_builtin_provider_match(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            models_path = Path(td) / "models.json"
            builtin_models_path = Path(td) / "models.generated.ts"
            models_path.write_text(json.dumps({
                "providers": {
                    "macaron": {"models": [{"id": "gpt-5.4", "contextWindow": 1000000}]},
                    "openai": {"baseUrl": "https://example.invalid/v1", "api": "openai-responses"},
                }
            }), encoding="utf-8")
            builtin_models_path.write_text(
                '"gpt-5.4": { provider: "openai", contextWindow: 272000 } satisfies Model<"openai-responses">,\n',
                encoding="utf-8",
            )

            self.assertEqual(
                pi_model_context_window(
                    "openai",
                    "gpt-5.4",
                    models_path=models_path,
                    builtin_models_path=builtin_models_path,
                ),
                272000,
            )

    def test_pi_model_context_window_applies_model_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            models_path = Path(td) / "models.json"
            builtin_models_path = Path(td) / "models.generated.ts"
            models_path.write_text(json.dumps({
                "providers": {
                    "openai": {
                        "baseUrl": "https://example.invalid/v1",
                        "api": "openai-responses",
                        "modelOverrides": {"gpt-5.4": {"contextWindow": 300000}},
                    }
                }
            }), encoding="utf-8")
            builtin_models_path.write_text(
                '"gpt-5.4": { provider: "openai", contextWindow: 272000 } satisfies Model<"openai-responses">,\n',
                encoding="utf-8",
            )

            self.assertEqual(
                pi_model_context_window(
                    "openai",
                    "gpt-5.4",
                    models_path=models_path,
                    builtin_models_path=builtin_models_path,
                ),
                300000,
            )

    def test_read_pi_run_settings_recovers_early_model_events_from_large_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session.jsonl"
            with path.open("w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "session",
                    "version": 3,
                    "id": "sess-1",
                    "timestamp": "2026-04-16T14:45:09.869Z",
                    "cwd": "/tmp/project",
                }) + "\n")
                f.write(json.dumps({
                    "type": "model_change",
                    "provider": "openai",
                    "modelId": "gpt-5.4",
                }) + "\n")
                f.write(json.dumps({
                    "type": "thinking_level_change",
                    "thinkingLevel": "high",
                }) + "\n")
                filler = "x" * (9 * 1024 * 1024)
                f.write(json.dumps({
                    "type": "message",
                    "message": {"role": "assistant", "content": [{"type": "text", "text": filler}]},
                }) + "\n")

            self.assertEqual(read_pi_run_settings(path), ("openai", "gpt-5.4", "high"))

    def test_read_pi_run_settings_recovers_late_model_events_from_mid_sized_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session.jsonl"
            filler = "x" * (320 * 1024)
            with path.open("w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "session",
                    "version": 3,
                    "id": "sess-1",
                    "timestamp": "2026-04-16T14:45:09.869Z",
                    "cwd": "/tmp/project",
                    "provider": "openai",
                    "modelId": "gpt-5.3-codex",
                    "thinkingLevel": "high",
                }) + "\n")
                f.write(json.dumps({
                    "type": "message",
                    "id": "msg-1",
                    "parentId": None,
                    "timestamp": "2026-04-16T14:46:00.000Z",
                    "message": {
                        "role": "assistant",
                        "provider": "openai",
                        "model": "gpt-5.3-codex",
                        "content": [{"type": "text", "text": filler}],
                    },
                }) + "\n")
                f.write(json.dumps({
                    "type": "model_change",
                    "id": "model-1",
                    "parentId": "msg-1",
                    "timestamp": "2026-04-16T14:47:00.000Z",
                    "provider": "openai",
                    "modelId": "gpt-5.4",
                }) + "\n")

            self.assertEqual(read_pi_run_settings(path), ("openai", "gpt-5.4", "high"))

    def test_read_pi_run_settings_reuses_cached_scan_for_unchanged_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session.jsonl"
            path.write_text(
                "\n".join([
                    json.dumps({
                        "type": "session",
                        "version": 3,
                        "id": "sess-1",
                        "timestamp": "2026-04-16T14:45:09.869Z",
                        "cwd": "/tmp/project",
                        "provider": "openai",
                        "modelId": "gpt-5.4",
                        "thinkingLevel": "high",
                    }),
                    json.dumps({"type": "model_change", "provider": "openai", "modelId": "gpt-5.4"}),
                    "",
                ]),
                encoding="utf-8",
            )
            with patch("codoxear.pi_log._scan_pi_run_settings_range", wraps=_pi_log._scan_pi_run_settings_range) as scan:
                self.assertEqual(read_pi_run_settings(path), ("openai", "gpt-5.4", "high"))
                first_calls = scan.call_count
                self.assertGreater(first_calls, 0)
                self.assertEqual(read_pi_run_settings(path), ("openai", "gpt-5.4", "high"))
                self.assertEqual(scan.call_count, first_calls)

    def test_read_pi_message_tail_snapshot_returns_latest_token_usage(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session.jsonl"
            with path.open("w", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "session",
                    "version": 3,
                    "id": "sess-1",
                    "timestamp": "2026-04-19T18:20:00.000Z",
                    "cwd": "/tmp/project",
                }) + "\n")
                f.write(json.dumps({
                    "type": "message",
                    "timestamp": "2026-04-19T18:20:05.000Z",
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": "hello"}],
                    },
                }) + "\n")
                f.write(json.dumps({
                    "type": "message",
                    "timestamp": "2026-04-19T18:20:08.000Z",
                    "message": {
                        "role": "assistant",
                        "provider": "openai",
                        "model": "gpt-5.4",
                        "usage": {"totalTokens": 196077},
                        "content": [{"type": "text", "text": "done"}],
                    },
                }) + "\n")

            _events, token_update, _off, _scan_bytes, _complete, _diag = read_pi_message_tail_snapshot(
                path,
                min_events=20,
                initial_scan_bytes=4096,
                max_scan_bytes=4096,
            )

            self.assertEqual(token_update["context_window"], 272000)
            self.assertEqual(token_update["tokens_in_context"], 196077)
