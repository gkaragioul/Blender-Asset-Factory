"""A report from a PREVIOUS run must never be returned as this run's result.

`run_blender_script` decides that Blender succeeded by testing
`report_path.is_file()`. Without deleting the path first, a Blender that dies
before its script writes -- a Cycles segfault, an OOM kill, an addon failure
under --factory-startup -- leaves the previous run's report sitting there, and
it is returned as though it described the run that just crashed.

The consequence is not a confusing error message, it is a false certificate.
`factory/retro.py` only checks `output.is_file()`, which the previous run's
.glb also satisfies, and then stamps the CURRENT contract digest onto the
stale report. Edit the palette, re-run the pack into the same directory, have
one asset crash Cycles, and the run report certifies `verdict: pass` with the
new contract digest for a GLB built under the old contract.

These tests need no Blender: they drive `run_blender_script` with the
subprocess stubbed out, which is exactly the condition being modelled -- a
launch that returns without writing a report.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from factory.blender import BlenderError, run_blender_script
from factory.config import FactoryConfig
from tests.temp_paths import temporary_root

STALE = {"ok": True, "run": "previous", "triangles_out": 1}
FRESH = {"ok": True, "run": "current", "triangles_out": 2}


class _Completed:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout = "stubbed blender stdout"
        self.stderr = "stubbed blender stderr"


class StaleReportTest(unittest.TestCase):
    def setUp(self):
        self.config = FactoryConfig.load()
        work = temporary_root() / "blender-report"
        work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.report_path = self.path / "report.json"
        # A stand-in for "some Blender exists"; the subprocess never runs.
        self.executable = self.path / "blender.exe"
        self.executable.write_bytes(b"")

    def _run(self, writer):
        with mock.patch(
            "factory.blender.discover_blender", return_value=self.executable
        ), mock.patch("factory.blender.subprocess.run", side_effect=writer):
            return run_blender_script(
                self.config,
                self.path / "script.py",
                {"source": "irrelevant"},
                self.report_path,
            )

    def test_a_stale_report_is_not_returned_when_blender_writes_nothing(self):
        self.report_path.write_text(json.dumps(STALE), encoding="utf-8")

        def crashes(*_args, **_kwargs):
            # Models a Blender that dies before its script writes anything.
            return _Completed(returncode=-11)

        with self.assertRaises(BlenderError) as caught:
            self._run(crashes)
        self.assertIn("Blender produced no report", str(caught.exception))
        self.assertFalse(
            self.report_path.is_file(),
            "the previous run's report survived the launch, so a crashed "
            "Blender would have had it returned as its own result",
        )

    def test_a_report_written_by_this_run_is_returned(self):
        # The control: with the same stale report present, a Blender that DOES
        # write must have its own report returned, not be broken by the
        # deletion.
        self.report_path.write_text(json.dumps(STALE), encoding="utf-8")

        def writes(*_args, **_kwargs):
            self.report_path.write_text(json.dumps(FRESH), encoding="utf-8")
            return _Completed(returncode=0)

        self.assertEqual(self._run(writes), FRESH)

    def test_the_payload_is_written_where_the_script_is_told_to_look(self):
        # Deleting the report must not disturb the payload sitting beside it.
        seen = {}

        def writes(command, **_kwargs):
            seen["command"] = list(command)
            self.report_path.write_text(json.dumps(FRESH), encoding="utf-8")
            return _Completed(returncode=0)

        self._run(writes)
        command = seen["command"]
        payload_path = Path(command[command.index("--payload") + 1])
        self.assertTrue(payload_path.is_file())
        self.assertEqual(
            json.loads(payload_path.read_text(encoding="utf-8")),
            {"source": "irrelevant"},
        )


if __name__ == "__main__":
    unittest.main()
