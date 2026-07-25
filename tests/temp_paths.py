from pathlib import Path


def temporary_root() -> Path:
    root = Path(__file__).resolve().parents[1] / "tmp" / "factory" / "tests"
    root.mkdir(parents=True, exist_ok=True)
    return root
