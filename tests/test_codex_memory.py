import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CodexMemoryContractTest(unittest.TestCase):
    def test_agents_requires_durable_startup_and_closeout(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        for phrase in (
            "knowledge/START_HERE.md",
            "factory.ps1 doctor",
            "knowledge/active-project.json",
            "Do not modify trusted bridge safety boundaries through learning",
            "factory.ps1 learn closeout",
        ):
            self.assertIn(phrase, text)

    def test_readme_documents_portable_entry_points(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for command in (
            "bootstrap\\setup.ps1",
            "factory.ps1 doctor",
            "factory.ps1 resume",
            "factory.ps1 verify",
        ):
            self.assertIn(command, text)


if __name__ == "__main__":
    unittest.main()
