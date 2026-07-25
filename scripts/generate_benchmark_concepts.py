from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

from factory.art_runs import stage_concept_candidate
from factory.config import FactoryConfig
from factory.io import atomic_write_json, atomic_write_text, sha256_file
from factory.providers.bfl import BFLClient


RUN_ID = "benchmark-shotgun-v1"
PROJECT_RELATIVE = Path(
    "projects/ww2_lowpoly_frontline_pack/benchmark-shotgun-v1"
)
REFERENCE_URLS = [
    "https://upload.wikimedia.org/wikipedia/commons/e/ec/Nakhjir_2_Double_Barrel_Shotgun_2.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/9/9c/Nakhjir_2_Double_Barrel_Shotgun_3.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/1/19/Nakhjir_2_Double_Barrel_Shotgun_4.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/2/2b/Nakhjir_2_Double_Barrel_Shotgun_5.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/9/90/Nakhjir_2_Double_Barrel_Shotgun_6.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/e/e8/Break-action_shotgun_close-up_01.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/d/d6/Shotgun_%28PSF%29.png",
    "https://upload.wikimedia.org/wikipedia/commons/1/1c/Double-barreled_Shotgun_MET_sfsb55.218_006.jpg",
]
SEEDS = [17321, 29633, 41047, 53861, 64927, 78139, 89231, 94349]
VARIATIONS = [
    "balanced service-grade field weapon with restrained practical construction",
    "rugged arsenal-refurbished field weapon with robust receiver shoulders",
    "elegant pre-war sporting gun adapted for austere wartime field service",
    "compact and purposeful guard weapon while retaining believable full-length anatomy",
    "heavily used rural hunting gun requisitioned for wartime defense",
    "plain utilitarian military-contract interpretation with minimal decoration",
    "slender lightweight field gun with especially clear stock-receiver-barrel rhythm",
    "stout durable field gun emphasizing readable hinge, fore-end, and twin muzzles",
]


BASE_PROMPT = """Create one polished professional game-asset concept render of a fictionalized 1930s-1940s side-by-side break-action shotgun. Use the reference images only to preserve real shotgun anatomy and proportions. Images 1 through 5 show one consistent real object from disassembled, receiver, stock/tang, muzzle/chamber, and full-side views. Image 6 shows the break-action hinge and open chambers. Image 7 supplies a clean side silhouette. Image 8 supplies historical wood-and-steel proportion language.

The result must depict exactly one complete shotgun in a clean left-facing three-quarter side view, fully inside frame from butt to both muzzles. It must unmistakably have two barrels arranged horizontally side-by-side, two circular muzzle openings, a central barrel rib, attached wooden fore-end, coherent break-action receiver and hinge, top lever and tang, two triggers inside one trigger guard, a narrow wrist, realistic stock comb and butt, and a tiny front bead sight. Use aged dark walnut and restrained blued steel with purposeful material separation. Preserve believable mechanical transitions and a strong readable silhouette.

Do not copy any manufacturer, model, logo, marking, decorative engraving, sling, ammunition, case, human hand, text, labels, watermark, modern optic, rail, magazine, over-under barrel arrangement, floating part, exploded view, extra weapon, or background prop. Do not make a low-detail primitive model. Render a high-quality untextured-design-quality source concept on a uniform neutral light-gray studio background with soft shadow and crisp form definition. This is the high-quality source stage; PS1 simplification happens later.

Design variation: {variation}."""


def build_contact_sheet(paths: list[Path], output: Path) -> None:
    cell_width, cell_height = 640, 450
    columns = 2
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (cell_width * columns, cell_height * rows), (28, 30, 34))
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail((cell_width - 24, cell_height - 48), Image.Resampling.LANCZOS)
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        sheet.paste(image, (x + (cell_width - image.width) // 2, y + 8))
        draw.text((x + 12, y + cell_height - 30), path.stem, fill=(245, 245, 245))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=94)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.count < 1 or args.count > len(SEEDS):
        raise SystemExit(f"--count must be between 1 and {len(SEEDS)}")

    config = FactoryConfig.load()
    project_root = config.root / PROJECT_RELATIVE
    output_root = project_root / "concepts" / "raw"
    prompt_root = project_root / "concepts" / "prompts"
    terms_path = project_root / "provider-terms" / "bfl-flux-api-service-terms.html"
    if not terms_path.is_file():
        raise RuntimeError(f"provider terms snapshot missing: {terms_path}")
    terms_sha256 = sha256_file(terms_path)
    plan = []
    for index in range(args.count):
        candidate_id = f"concept-{index + 1:02d}"
        prompt = BASE_PROMPT.format(variation=VARIATIONS[index])
        plan.append(
            {
                "candidate_id": candidate_id,
                "seed": SEEDS[index],
                "prompt": prompt,
                "output": str(output_root / f"{candidate_id}.png"),
            }
        )
    atomic_write_json(project_root / "concepts" / "generation-plan.json", plan)
    if args.dry_run:
        print(json.dumps({"ok": True, "dry_run": True, "candidate_count": len(plan)}))
        return 0

    api_key = os.environ.get("BFL_API_KEY", "")
    client = BFLClient(api_key, model="flux-2-pro")
    completed_paths: list[Path] = []
    run_root = config.reports_root / "art-runs" / RUN_ID
    provider_results = run_root / "concepts" / "provider-results"
    for item in plan:
        candidate_id = item["candidate_id"]
        prompt = item["prompt"]
        prompt_path = prompt_root / f"{candidate_id}.txt"
        output_path = Path(item["output"])
        atomic_write_text(prompt_path, prompt + "\n")
        result = client.generate(
            prompt=prompt,
            reference_urls=REFERENCE_URLS,
            output_path=output_path,
            seed=item["seed"],
            width=1536,
            height=1024,
            timeout_seconds=600,
        )
        atomic_write_json(provider_results / f"{candidate_id}.json", result)
        stage_concept_candidate(
            config,
            RUN_ID,
            candidate_id,
            output_path,
            {
                "provider": result["provider"],
                "model": result["model"],
                "prompt_sha256": result["prompt_sha256"],
                "workflow_sha256": result["workflow_sha256"],
                "seed": result["seed"],
                "license_snapshot": (
                    f"{terms_path.relative_to(config.root).as_posix()}#sha256={terms_sha256}"
                ),
            },
        )
        completed_paths.append(output_path)
        print(json.dumps({"candidate": candidate_id, "request_id": result["request_id"], "sha256": result["output_sha256"]}))

    contact_sheet = project_root / "concepts" / "benchmark-concept-contact-sheet.jpg"
    build_contact_sheet(completed_paths, contact_sheet)
    print(json.dumps({"ok": True, "candidate_count": len(completed_paths), "contact_sheet": str(contact_sheet), "contact_sheet_sha256": sha256_file(contact_sheet)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
