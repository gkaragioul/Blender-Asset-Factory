from __future__ import annotations

import unittest
import zipfile
from pathlib import Path

from tests.temp_paths import temporary_root

ARCHIVE_CANDIDATES = (
    Path(__file__).resolve().parents[2] / ".hermes" / "desktop-attachments" / "m1897-trenchgun.zip",
    Path(__file__).resolve().parents[1] / ".hermes" / "desktop-attachments" / "m1897-trenchgun.zip",
)


class FixtureUnavailable(unittest.SkipTest):
    pass


def trenchgun_fbx() -> Path:
    destination = temporary_root() / "fixtures" / "m1897-trenchgun"
    target = destination / "source" / "trenchgun.fbx"
    if target.is_file():
        return target
    archive = next((path for path in ARCHIVE_CANDIDATES if path.is_file()), None)
    if archive is None:
        raise FixtureUnavailable(
            "m1897-trenchgun.zip was not found; looked in "
            + ", ".join(str(path) for path in ARCHIVE_CANDIDATES)
        )
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(destination)
    if not target.is_file():
        raise FixtureUnavailable(f"{archive} does not contain source/trenchgun.fbx")
    return target
