import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.cli import _art
from factory.config import FactoryConfig
from tests.temp_paths import temporary_root


class ArtCliTest(unittest.TestCase):
    def make_config(self, root: Path) -> FactoryConfig:
        return FactoryConfig(
            root=root,
            model_root=root / "models",
            tooling_root=root / ".tooling",
            reports_root=root / "reports",
            bridge_url="http://127.0.0.1:9876",
            blender_candidates=(),
        )

    def write_fixture(self, root: Path) -> tuple[Path, Path, Path]:
        reference = root / "projects" / "fixture" / "reference.png"
        reference.parent.mkdir(parents=True)
        reference.write_bytes(b"reference")
        license_snapshot = root / "projects" / "fixture" / "license.json"
        license_snapshot.write_text('{"license":"Public Domain"}', encoding="utf-8")
        brief = root / "specs" / "assets" / "fixture.json"
        brief.parent.mkdir(parents=True)
        brief.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "asset_id": "fixture_asset",
                    "style_profile": "fixture_style",
                    "intended_use": "test",
                    "required_parts": ["body"],
                    "forbidden_details": [],
                    "budgets": {"triangles_max": 100},
                    "cameras": ["hero"],
                    "retry_budget": {"concept": 1},
                    "references": [
                        {
                            "id": "reference",
                            "kind": "identity_shape",
                            "source_url": "https://example.invalid/reference",
                            "creator": "Fixture",
                            "license": "Public Domain",
                            "license_url": "https://creativecommons.org/publicdomain/mark/1.0/",
                            "license_snapshot_path": str(license_snapshot),
                            "local_path": str(reference),
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        image = root / "projects" / "fixture" / "concept.png"
        image.write_bytes(b"concept")
        metadata = root / "projects" / "fixture" / "metadata.json"
        metadata.write_text(
            json.dumps(
                {
                    "provider": "fixture",
                    "model": "fixture-v1",
                    "prompt_sha256": "1" * 64,
                    "workflow_sha256": "2" * 64,
                    "seed": 7,
                    "license_snapshot": "fixture-terms",
                }
            ),
            encoding="utf-8",
        )
        return brief, image, metadata

    def test_art_cli_initializes_stages_and_approves_a_concept(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            root = Path(temp)
            config = self.make_config(root)
            brief, image, metadata = self.write_fixture(root)
            with patch("factory.config.FactoryConfig.load", return_value=config):
                code, initialized = _art(
                    ["init", "--brief", str(brief), "--run-id", "cli-art-run"]
                )
                self.assertEqual(code, 0)
                self.assertTrue(initialized["ok"])

                code, staged = _art(
                    [
                        "stage-concept",
                        "--run-id",
                        "cli-art-run",
                        "--candidate-id",
                        "concept-01",
                        "--image",
                        str(image),
                        "--metadata",
                        str(metadata),
                    ]
                )
                self.assertEqual(code, 0)
                self.assertEqual(staged["data"]["candidate_id"], "concept-01")

                code, approved = _art(
                    [
                        "approve-concept",
                        "--run-id",
                        "cli-art-run",
                        "--candidate-id",
                        "concept-01",
                        "--approved-by",
                        "user",
                        "--evidence",
                        "explicit visual approval",
                    ]
                )
                self.assertEqual(code, 0)
                self.assertTrue(approved["data"]["concept_approved"])


if __name__ == "__main__":
    unittest.main()
