from __future__ import annotations

import json
import struct
from pathlib import Path

from .blender import run_blender_script
from .config import FactoryConfig
from .style_contract import StyleContract

SCRIPT = Path(__file__).resolve().parent / "scripts" / "retro_pass.py"
CANONICAL_GENERATOR = "BlenderAssetFactory retro_pass"


class RetroError(RuntimeError):
    pass


def canonical_glb_bytes(path: Path) -> bytes:
    """Return GLB bytes with volatile metadata normalized.

    Blender writes its own version into asset.generator, which differs between
    installs. Everything else in the file must be reproducible.

    The returned bytes are a valid, self-consistent GLB container (not merely
    a comparable digest input): the 12-byte header's total-length field
    matches the real length of the rebuilt buffer, the JSON chunk is padded
    to a 4-byte boundary with spaces (0x20) per the glTF spec, and the BIN
    chunk -- including its own 8-byte chunk header -- is carried over
    unmodified.
    """
    data = path.read_bytes()
    json_length = struct.unpack_from("<I", data, 12)[0]
    document = json.loads(data[20 : 20 + json_length].decode("utf-8"))
    document.setdefault("asset", {})["generator"] = CANONICAL_GENERATOR
    document["asset"].pop("copyright", None)
    normalized = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    normalized += b" " * ((4 - len(normalized) % 4) % 4)
    # Everything after the JSON chunk's data, which is exactly the BIN
    # chunk's own 8-byte header (length + type) followed by its data. Taken
    # verbatim: the BIN payload is not touched by canonicalisation, and it
    # already carries whatever padding the exporter gave it.
    binary = data[20 + json_length :]
    total_length = 12 + 8 + len(normalized) + len(binary)
    header = struct.pack("<III", 0x46546C67, 2, total_length)
    return header + struct.pack("<II", len(normalized), 0x4E4F534A) + normalized + binary


def retro_pass(
    config: FactoryConfig,
    source: Path,
    contract: StyleContract,
    role: str,
    output: Path,
    report_path: Path,
) -> dict:
    try:
        contract.band_for(role)
    except Exception as error:
        raise RetroError(str(error)) from error
    payload = {
        "source": str(source),
        "output": str(output),
        "role": role,
        "palette": str(contract.palette),
        "contract": contract.as_payload(),
    }
    report = run_blender_script(config, SCRIPT, payload, report_path)
    if not report.get("ok"):
        raise RetroError(f"retro pass failed: {report.get('error')}")
    if not output.is_file():
        raise RetroError(f"retro pass reported success but {output} does not exist")
    report["contract_digest"] = contract.digest()
    return report
