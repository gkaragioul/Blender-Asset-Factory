import unittest

from factory.config import FactoryConfig
from factory.doctor import probe
from factory.transfer import build_transfer_manifest


class ReleaseContinuityTest(unittest.TestCase):
    def test_doctor_proves_release_runtime_capabilities(self):
        capabilities = probe(FactoryConfig.load())["capabilities"]
        for name in ("browser", "node", "gltf_validator", "gltfpack", "playwright_core", "three", "threejs_viewer"):
            self.assertEqual(capabilities[name]["status"], "available", f"{name}: {capabilities[name]}")

    def test_transfer_manifest_inventories_release_dependencies(self):
        manifest = build_transfer_manifest(FactoryConfig.load())
        names = {entry["name"] for entry in manifest["entries"]}
        self.assertTrue({"node", "gltfpack", "gltf_validator", "playwright_core", "three"}.issubset(names))


if __name__ == "__main__":
    unittest.main()
