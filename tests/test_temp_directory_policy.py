import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TemporaryDirectoryPolicyTest(unittest.TestCase):
    def test_tests_do_not_create_temporary_directories_at_drive_root(self):
        offenders = []
        for path in sorted((ROOT / "tests").glob("test_*.py")):
            source = path.read_text(encoding="utf-8")
            if 'TemporaryDirectory(dir="G:\\\\")' in source:
                offenders.append(path.name)

        self.assertEqual(
            offenders,
            [],
            "Tests must use the project temporary directory, not the root of G:.",
        )


if __name__ == "__main__":
    unittest.main()
