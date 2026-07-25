# Immutable Art Runs

The art-run layer prevents technically valid but visually unapproved assets from reaching production.

## Create a run

An asset brief must include:

- target use and style profile;
- recognizable required parts;
- forbidden details;
- source and runtime budgets;
- diagnostic camera views;
- retry limits;
- local reference images;
- source URL, creator, license URL, and a frozen license-evidence file for every reference.

```bash
PYTHONPATH=. python3 -m factory art init \
  --brief specs/assets/benchmark-shotgun-v1.json \
  --run-id benchmark-shotgun-v1 \
  --json
```

Creation freezes the brief, all reference files, all license snapshots, and their SHA-256 hashes under:

```text
reports/art-runs/<run-id>/
  brief.json
  provenance.json
  state.json
  references/
  licenses/
```

An existing run ID is immutable and cannot be overwritten.

## Stage a generated concept

The candidate metadata contract records provider, pinned model, prompt hash, workflow hash, seed, and provider-terms snapshot.

```bash
PYTHONPATH=. python3 -m factory art stage-concept \
  --run-id benchmark-shotgun-v1 \
  --candidate-id concept-01 \
  --image projects/.../concept-01.png \
  --metadata projects/.../concept-01-metadata.json \
  --json
```

Duplicate candidate IDs are rejected.

## Approve the concept gate

Only use this command after the user explicitly accepts one candidate visually:

```bash
PYTHONPATH=. python3 -m factory art approve-concept \
  --run-id benchmark-shotgun-v1 \
  --candidate-id concept-01 \
  --approved-by user \
  --evidence "Explicit visual approval in benchmark review" \
  --json
```

The approval is immutable and binds the selected candidate's SHA-256 hash. The run then advances from `awaiting_concept_candidates` to `concept_approved`.

No 3D reconstruction should begin before that gate exists.

## Benchmark generator

The current benchmark uses the pinned `flux-2-pro` endpoint rather than a preview model:

```bash
PYTHONPATH=. python3 scripts/generate_benchmark_concepts.py --count 8
```

It uses eight rights-tracked public reference URLs, fixed seeds, persisted prompts, raw provider records, immutable candidate staging, and a contact sheet. API keys are read only from environment variables and are never persisted in reports.
