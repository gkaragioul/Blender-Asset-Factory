import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from factory.config import FactoryConfig
from factory.learning import (
    LearningPolicyError,
    promote_candidate,
    record_candidate,
)


class LearningPolicyTest(unittest.TestCase):
    def config(self, root: Path) -> FactoryConfig:
        return FactoryConfig(
            root,
            Path(r"G:\LLMs"),
            root / ".tooling",
            root / "reports",
            "http://127.0.0.1:9876",
            (),
        )

    def test_candidate_does_not_become_lesson_without_evidence(self):
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
            root = Path(temp)
            path = record_candidate(
                self.config(root),
                {
                    "lesson_id": "localized-wear-001",
                    "scope": "profile",
                    "title": "Localize functional wear",
                    "statement": "Wear follows handling and mechanisms.",
                    "source_projects": ["m42"],
                },
            )
            self.assertIn("candidates", path.parts)
            with self.assertRaises(LearningPolicyError):
                promote_candidate(
                    self.config(root), "localized-wear-001", {}
                )

    def test_user_approval_promotes_profile_lesson(self):
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
            root = Path(temp)
            config = self.config(root)
            record_candidate(
                config,
                {
                    "lesson_id": "localized-wear-001",
                    "scope": "profile",
                    "title": "Localize wear",
                    "statement": "Wear follows contact zones.",
                    "source_projects": ["m42"],
                },
            )
            promoted = promote_candidate(
                config,
                "localized-wear-001",
                {
                    "type": "user_approval",
                    "reference": "conversation-2026-07-18",
                },
            )
            self.assertEqual(promoted.parent.name, "profile")

    def test_learning_cli_records_candidate_from_g_path(self):
        root = Path(__file__).resolve().parents[1]
        output = (
            root
            / "knowledge"
            / "lessons"
            / "candidates"
            / "cli-candidate-001.json"
        )
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
            path = Path(temp) / "candidate.json"
            path.write_text(
                json.dumps(
                    {
                        "lesson_id": "cli-candidate-001",
                        "scope": "asset",
                        "title": "CLI candidate",
                        "statement": "CLI inputs are explicit.",
                        "source_projects": ["fixture"],
                    }
                ),
                encoding="utf-8",
            )
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "factory",
                        "learn",
                        "candidate",
                        "--input",
                        str(path),
                        "--json",
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                )
            finally:
                output.unlink(missing_ok=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["ok"])

    def test_learning_cli_rejects_input_outside_g_with_structured_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "candidate.json"
            path.write_text("{}", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "factory",
                    "learn",
                    "candidate",
                    "--input",
                    str(path),
                    "--json",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(completed.returncode, 0)
        result = json.loads(completed.stdout)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["code"], "command_failed")


if __name__ == "__main__":
    unittest.main()
