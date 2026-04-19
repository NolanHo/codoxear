import json
import tempfile
import unittest
from pathlib import Path

from codoxear.pi_log import pi_model_context_window
from codoxear.pi_log import read_pi_run_settings


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
