import json
import tempfile
import unittest
from pathlib import Path

from factory.blender import discover_blender
from factory.config import FactoryConfig
from tests.temp_paths import temporary_root


def _config_with_candidates(temp: Path, candidates: list[str]) -> FactoryConfig:
    root = temp / "repo"
    (root / "factory").mkdir(parents=True)
    (root / "models").mkdir()
    (root / ".tooling").mkdir()
    (root / "reports").mkdir()
    path = root / "factory" / "config.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "root": ".",
                "model_root": "models",
                "tooling_root": ".tooling",
                "reports_root": "reports",
                "bridge_url": "http://127.0.0.1:9876",
                "blender_candidates": candidates,
            }
        ),
        encoding="utf-8",
    )
    return FactoryConfig.load(path)


class BlenderDiscoveryTest(unittest.TestCase):
    def test_finds_literal_candidate(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            installed = temp_path / "bin" / "blender"
            installed.parent.mkdir(parents=True)
            installed.write_text("#!/bin/sh\n", encoding="utf-8")
            config = _config_with_candidates(temp_path, [str(installed)])
            self.assertEqual(discover_blender(config), installed)

    def test_expands_glob_candidate_and_prefers_highest_version(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            base = temp_path / "Blender Foundation"
            for version in ("Blender 4.2", "Blender 4.10", "Blender 4.9"):
                target = base / version
                target.mkdir(parents=True)
                (target / "blender.exe").write_text("stub", encoding="utf-8")
            config = _config_with_candidates(
                temp_path, [str(base / "*" / "blender.exe")]
            )
            found = discover_blender(config)
            self.assertEqual(found.parent.name, "Blender 4.10")

    def test_returns_none_when_nothing_matches(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            temp_path = Path(temp)
            config = _config_with_candidates(
                temp_path, [str(temp_path / "absent" / "blender")]
            )
            self.assertIsNone(discover_blender(config))


if __name__ == "__main__":
    unittest.main()
