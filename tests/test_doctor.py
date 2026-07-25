import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.config import FactoryConfig
from factory.doctor import _probe_bridge, probe
from tests.temp_paths import temporary_root


class DoctorTest(unittest.TestCase):
    def test_bridge_probe_uses_read_only_json_socket_command(self):
        sent = []

        class FakeSocket:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def sendall(self, payload):
                sent.append(payload)

            def recv(self, _size):
                return b'{"status":"success","result":{}}'

        with patch(
            "factory.doctor.socket.create_connection",
            return_value=FakeSocket(),
        ):
            ok, detail = _probe_bridge("http://127.0.0.1:9876")

        request = json.loads(sent[0].decode("utf-8"))
        self.assertTrue(ok)
        self.assertEqual(request["type"], "get_scene_info")
        self.assertEqual(request["params"], {})
        self.assertEqual(detail, "get_scene_info succeeded")

    def test_finds_blender_candidate_and_reports_missing_optionals(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            blender = Path(temp) / "blender.exe"
            blender.write_bytes(b"fixture")
            config = FactoryConfig(
                root=Path(__file__).resolve().parents[1],
                model_root=Path(r"G:\LLMs"),
                tooling_root=Path(temp),
                reports_root=Path(__file__).resolve().parents[1] / "reports",
                bridge_url="http://127.0.0.1:9876",
                blender_candidates=(blender,),
            )
            with patch(
                "factory.doctor._probe_bridge",
                return_value=(False, "connection refused"),
            ), patch(
                "factory.doctor._run_version",
                return_value="Blender 5.2.0",
            ):
                report = probe(config)
        self.assertEqual(
            report["capabilities"]["blender"]["status"], "available"
        )
        self.assertEqual(
            report["capabilities"]["bridge"]["status"], "unavailable"
        )
        self.assertIn(
            report["capabilities"]["comfyui"]["status"],
            {"unavailable", "degraded"},
        )

    def test_doctor_does_not_create_missing_model_root(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            missing = Path(temp) / "missing-model-root"
            base = FactoryConfig.load()
            config = FactoryConfig(
                root=base.root,
                model_root=missing,
                tooling_root=base.tooling_root,
                reports_root=base.reports_root,
                bridge_url=base.bridge_url,
                blender_candidates=base.blender_candidates,
            )
            probe(config)
            self.assertFalse(missing.exists())

    def test_release_runtime_is_probed_from_pinned_files(self):
        with tempfile.TemporaryDirectory(dir=temporary_root()) as temp:
            tooling = Path(temp)
            node = tooling / "node.exe"
            gltfpack = tooling / "gltfpack.exe"
            node_modules = tooling / "release-node" / "node_modules"
            for package, version in (("gltf-validator", "2.0.0-dev.3.10"), ("three", "0.185.1"), ("playwright-core", "1.61.1")):
                package_dir = node_modules / package
                package_dir.mkdir(parents=True, exist_ok=True)
                (package_dir / "package.json").write_text(json.dumps({"name": package, "version": version}))
            node.write_bytes(b"node")
            gltfpack.write_bytes(b"gltfpack")
            (tooling / "release-runtime.json").write_text(json.dumps({
                "node": str(node),
                "gltfpack": str(gltfpack),
                "gltfpack_version": "1.2",
                "node_modules": str(node_modules),
            }))
            base = FactoryConfig.load()
            config = FactoryConfig(base.root, base.model_root, tooling, base.reports_root, base.bridge_url, base.blender_candidates)
            with patch("factory.doctor._probe_bridge", return_value=(False, "offline")), patch("factory.doctor._run_version", return_value="v24.17.0"):
                report = probe(config)
        self.assertEqual(report["capabilities"]["node"]["version"], "v24.17.0")
        self.assertEqual(report["capabilities"]["gltfpack"]["version"], "1.2")
        self.assertEqual(report["capabilities"]["gltf_validator"]["version"], "2.0.0-dev.3.10")
        self.assertEqual(report["capabilities"]["playwright_core"]["version"], "1.61.1")

    def test_linux_browser_can_be_discovered_from_path(self):
        base = FactoryConfig.load()
        with patch("factory.doctor.shutil.which", return_value="/usr/bin/google-chrome"), patch("factory.doctor.Path.is_file", return_value=True), patch("factory.doctor._probe_bridge", return_value=(False, "offline")):
            report = probe(base)
        self.assertEqual(report["capabilities"]["browser"]["status"], "available")
        self.assertEqual(report["capabilities"]["browser"]["path"], "/usr/bin/google-chrome")


if __name__ == "__main__":
    unittest.main()
