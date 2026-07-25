import json
import tempfile
import unittest
from pathlib import Path

from factory.art_runs import (
    ArtRunError,
    approve_concept,
    create_art_run,
    stage_concept_candidate,
)
from factory.config import FactoryConfig
from factory.io import sha256_file
from tests.temp_paths import temporary_root


class ArtRunTest(unittest.TestCase):
    def make_config(self, root: Path) -> FactoryConfig:
        return FactoryConfig(
            root=root,
            model_root=root / "models",
            tooling_root=root / ".tooling",
            reports_root=root / "reports",
            bridge_url="http://127.0.0.1:9876",
            blender_candidates=(),
        )

    def write_brief(self, root: Path) -> tuple[Path, Path]:
        reference = root / "projects" / "benchmark" / "shotgun-side.png"
        reference.parent.mkdir(parents=True)
        reference.write_bytes(b"rights-cleared-reference")
        license_snapshot = root / "projects" / "benchmark" / "shotgun-side-license.json"
        license_snapshot.write_text('{"license":"Public Domain"}', encoding="utf-8")
        brief = root / "specs" / "assets" / "benchmark-shotgun.json"
        brief.parent.mkdir(parents=True)
        brief.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "asset_id": "benchmark_shotgun",
                    "style_profile": "ps1_ww2_frontline",
                    "intended_use": "static Three.js hero prop",
                    "required_parts": ["stock", "receiver", "two_barrels", "fore_end", "trigger_guard"],
                    "forbidden_details": ["logos", "extremist_symbols"],
                    "budgets": {"triangles_max": 1200, "materials_max": 3, "texture_max_px": 512},
                    "cameras": ["hero", "left", "right", "front", "rear", "top"],
                    "retry_budget": {"concept": 3, "reconstruction": 2, "repair": 2},
                    "references": [
                        {
                            "id": "shotgun_side",
                            "kind": "identity_shape",
                            "source_url": "https://example.invalid/public-domain-shotgun",
                            "creator": "Fixture Museum",
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
        return brief, reference

    def test_create_art_run_freezes_brief_references_and_initial_gates(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            root = Path(temp)
            brief, reference = self.write_brief(root)
            result = create_art_run(self.make_config(root), brief, run_id="benchmark-run")
            run_root = root / "reports" / "art-runs" / "benchmark-run"

            self.assertEqual(Path(result["run_root"]), run_root)
            self.assertEqual(sha256_file(run_root / "brief.json"), sha256_file(brief))
            frozen_reference = run_root / "references" / "shotgun_side.png"
            self.assertEqual(frozen_reference.read_bytes(), reference.read_bytes())

            provenance = json.loads((run_root / "provenance.json").read_text())
            self.assertEqual(provenance["references"][0]["sha256"], sha256_file(reference))
            self.assertEqual(provenance["references"][0]["license"], "Public Domain")
            frozen_license = run_root / "licenses" / "shotgun_side.json"
            self.assertEqual(
                provenance["references"][0]["license_snapshot_sha256"],
                sha256_file(frozen_license),
            )

            state = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state["stage"], "awaiting_concept_candidates")
            self.assertTrue(state["gates"]["references_frozen"])
            self.assertFalse(state["gates"]["concept_approved"])
            self.assertFalse(state["gates"]["high_poly_approved"])
            self.assertFalse(state["gates"]["runtime_approved"])

    def test_create_art_run_refuses_to_overwrite_existing_run(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            root = Path(temp)
            brief, _reference = self.write_brief(root)
            config = self.make_config(root)
            create_art_run(config, brief, run_id="immutable-run")
            with self.assertRaisesRegex(ArtRunError, "immutable"):
                create_art_run(config, brief, run_id="immutable-run")
    def test_stage_and_approve_concept_requires_a_real_immutable_candidate(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            root = Path(temp)
            brief, _reference = self.write_brief(root)
            config = self.make_config(root)
            create_art_run(config, brief, run_id="concept-run")
            image = root / "projects" / "benchmark" / "concept-01.png"
            image.write_bytes(b"concept-image")
            metadata = {
                "provider": "fixture-provider",
                "model": "fixture-model-v1",
                "prompt_sha256": "1" * 64,
                "workflow_sha256": "2" * 64,
                "seed": 42,
                "license_snapshot": "provider-terms-2026-07-22",
            }

            staged = stage_concept_candidate(
                config,
                "concept-run",
                "candidate-01",
                image,
                metadata,
            )
            staged_path = Path(staged["path"])
            self.assertEqual(staged_path.read_bytes(), image.read_bytes())
            self.assertEqual(staged["sha256"], sha256_file(image))

            with self.assertRaisesRegex(ArtRunError, "duplicate"):
                stage_concept_candidate(
                    config,
                    "concept-run",
                    "candidate-01",
                    image,
                    metadata,
                )

            approval = approve_concept(
                config,
                "concept-run",
                "candidate-01",
                approved_by="user",
                evidence="Explicit visual approval in benchmark review",
            )
            self.assertEqual(approval["candidate_sha256"], sha256_file(image))
            run_root = root / "reports" / "art-runs" / "concept-run"
            state = json.loads((run_root / "state.json").read_text())
            self.assertEqual(state["stage"], "concept_approved")
            self.assertTrue(state["gates"]["concept_approved"])
            gate = json.loads((run_root / "gates" / "concept-approval.json").read_text())
            self.assertEqual(gate["candidate_id"], "candidate-01")
            self.assertEqual(gate["candidate_sha256"], sha256_file(image))

    def test_concept_approval_refuses_unknown_candidate(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            root = Path(temp)
            brief, _reference = self.write_brief(root)
            config = self.make_config(root)
            create_art_run(config, brief, run_id="missing-candidate-run")
            with self.assertRaisesRegex(ArtRunError, "unknown concept candidate"):
                approve_concept(
                    config,
                    "missing-candidate-run",
                    "candidate-missing",
                    approved_by="user",
                    evidence="none",
                )


if __name__ == "__main__":
    unittest.main()
