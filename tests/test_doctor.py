import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from factory.config import FactoryConfig
from factory.doctor import _probe_bridge, probe


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
                return b'{"id":"doctor","success":true,"result":{}}\n'

        with patch(
            "factory.doctor.socket.create_connection",
            return_value=FakeSocket(),
        ):
            ok, detail = _probe_bridge("http://127.0.0.1:9876")

        request = json.loads(sent[0].decode("utf-8"))
        self.assertTrue(ok)
        self.assertEqual(request["command"], "scene.get_info")
        self.assertEqual(request["params"], {})
        self.assertEqual(detail, "scene.get_info succeeded")

    def test_finds_blender_candidate_and_reports_missing_optionals(self):
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
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
        with tempfile.TemporaryDirectory(dir="G:\\") as temp:
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


if __name__ == "__main__":
    unittest.main()
