import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.cli import run
from factory.config import FactoryConfig
from factory.transfer import TransferError, index_models
from tests.temp_paths import temporary_root


class TransferTest(unittest.TestCase):
    def test_model_index_is_sorted_and_relative(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            model_root = Path(temp)
            (model_root / "checkpoints").mkdir()
            (model_root / "vae").mkdir()
            (model_root / "vae" / "b.safetensors").write_bytes(b"b")
            (model_root / "checkpoints" / "a.safetensors").write_bytes(b"a")
            root = Path(__file__).resolve().parents[1]
            config = FactoryConfig(
                root,
                model_root,
                root / ".tooling",
                root / "reports",
                "http://127.0.0.1:9876",
                (),
            )
            index = index_models(config, hash_files=True)
        paths = [entry["relative_path"] for entry in index["models"]]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(
            paths, ["checkpoints/a.safetensors", "vae/b.safetensors"]
        )
        self.assertTrue(
            all(len(entry["sha256"]) == 64 for entry in index["models"])
        )

    def test_symlinks_outside_model_root_are_rejected(self):
        with tempfile.TemporaryDirectory(
            dir=temporary_root()
        ) as model_temp, tempfile.TemporaryDirectory(dir=temporary_root()) as outside_temp:
            model_root = Path(model_temp)
            outside = Path(outside_temp) / "outside.safetensors"
            outside.write_bytes(b"outside")
            link = model_root / "escaped.safetensors"
            try:
                link.symlink_to(outside)
            except OSError as error:
                self.skipTest(f"Windows symlink permission unavailable: {error}")
            root = Path(__file__).resolve().parents[1]
            config = FactoryConfig(
                root,
                model_root,
                root / ".tooling",
                root / "reports",
                "http://127.0.0.1:9876",
                (),
            )
            with self.assertRaisesRegex(TransferError, "escapes model root"):
                index_models(config, hash_files=True)

    def test_index_models_cli_writes_external_manifest(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            model_root = Path(temp)
            (model_root / "checkpoints").mkdir()
            (model_root / "checkpoints" / "fixture.safetensors").write_bytes(
                b"fixture"
            )
            root = Path(__file__).resolve().parents[1]
            config = FactoryConfig(
                root,
                model_root,
                root / ".tooling",
                root / "reports",
                "http://127.0.0.1:9876",
                (),
            )
            with patch("factory.config.FactoryConfig.load", return_value=config):
                code, result, _json_output = run(["index-models", "--json"])
            self.assertEqual(code, 0, result)
            self.assertTrue(result["ok"])
            self.assertEqual(
                Path(result["data"]["index_path"]),
                model_root / "manifests" / "model-index.json",
            )


if __name__ == "__main__":
    unittest.main()
