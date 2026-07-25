from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .catalog import Catalog
from .config import FactoryConfig
from .gates import gate1, gate2, verdict
from .gltf_validation import validate_glb
from .io import atomic_write_json
from .retro import retro_pass
from .silhouette import compare, effective_radius, mask_from_png, render_masks
from .style_contract import StyleContract


class PackError(RuntimeError):
    pass


def _asset_record(identifier: str) -> dict:
    return {
        "id": identifier,
        "verdict": "reject",
        "error": None,
        "triangles": None,
        "gate1": None,
        "gate2": None,
        "silhouette": None,
        "output": None,
    }


def build_pack(
    config: FactoryConfig,
    catalog: Catalog,
    contract: StyleContract,
    sources: dict[str, Path],
    output_root: Path,
    validate: bool = True,
) -> dict:
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%S.%fZ")
    records: list[dict] = []

    for entry in catalog.entries:
        record = _asset_record(entry.id)
        asset_dir = output_root / entry.id
        try:
            source = sources.get(entry.id)
            if source is None or not Path(source).is_file():
                raise PackError(f"no source mesh was supplied for {entry.id!r}")
            source = Path(source)

            work = asset_dir / "work"
            work.mkdir(parents=True, exist_ok=True)
            output = asset_dir / f"{entry.id}.glb"

            retro_report = retro_pass(
                config, source, contract, entry.role, output, work / "retro.json"
            )
            record["triangles"] = retro_report["triangles_out"]
            record["output"] = str(output)

            raw_report_path = work / "masks-raw.json"
            raw_paths = render_masks(
                config, source, work / "masks-raw", raw_report_path
            )
            # Frame the converted render with the same radius the raw render
            # used, so a converted mesh with slightly different bounds is not
            # penalized (or flattered) by a different zoom level -- see
            # render_masks' docstring and test_silhouette.py's own use of
            # effective_radius for why the centre is deliberately NOT shared
            # while the radius is.
            shared_radius = effective_radius(raw_report_path)
            ps1_paths = render_masks(
                config, output, work / "masks-ps1", work / "masks-ps1.json",
                radius=shared_radius,
            )
            raw_masks = [mask_from_png(path.read_bytes())[1] for path in raw_paths]
            ps1_masks = [mask_from_png(path.read_bytes())[1] for path in ps1_paths]
            comparison = compare(raw_masks, ps1_masks)
            record["silhouette"] = comparison

            validator_ok = True
            if validate:
                validation = validate_glb(config, output, work / "validation.json")
                validator_ok = bool(validation.get("ok", False))

            first = gate1(
                output.read_bytes(),
                contract,
                entry.role,
                triangles=retro_report["triangles_out"],
                validator_ok=validator_ok,
                preview_ok=True,
            )
            second = gate2(comparison)
            record["gate1"] = first
            record["gate2"] = second
            record["verdict"] = verdict(first, second)
        except Exception as error:
            record["error"] = f"{type(error).__name__}: {error}"
        records.append(record)

    report = {
        "schema_version": 1,
        "pack_id": catalog.pack_id,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "contract_digest": contract.digest(),
        "ok": all(item["verdict"] == "pass" for item in records),
        # gate2()/verdict() only ever produce "pass" or "reject" -- see
        # gates.verdict's docstring: there is no "flag" outcome any more,
        # since gate2 dropped the absolute quality threshold that used to
        # produce a middle judgement call. Counting a "flag" bucket that can
        # never be populated would misrepresent what this run measured.
        "counts": {
            name: sum(1 for item in records if item["verdict"] == name)
            for name in ("pass", "reject")
        },
        "assets": records,
    }
    report_path = config.reports_root / "packs" / catalog.pack_id / run_id / "pack.json"
    report["report_path"] = str(report_path)
    atomic_write_json(report_path, report)
    return report
