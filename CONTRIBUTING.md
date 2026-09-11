# Contributing

## Scope of v1

This repository owns JSON-to-audio compilation. LLM generation is external.
Keep CLI entry points at the root and local music under `projects/`. Do not commit
rendered audio, environments, caches, review backups, or private track projects.
An explicit curated plan belongs in `examples/`.

The release is v1.0.0; contract revision is 1.1.0; plan format is `techno-csound-1`.
These version numbers describe different things.

## Contracts

Edit `schemas/track.schema.json` for definitions and
`prompts/SYSTEM_PROMPT_SOURCE.txt` for wording. Then run:

```bash
python build_contracts.py
python build_contracts.py --check
```

Commit generated exports, system prompt, and manifest with their sources. Do not
hand-edit generated artifacts. OpenAPI is 3.0.3 with entry point
`components.schemas.TrackPlan`; Gemini uses a smaller standalone schema. Local
validation enforces semantic relationships omitted from that schema.
See [the format reference](docs/format.md) for timing and event ordering.

## Verification

```bash
python -m unittest discover -s tests -v
python verify_system.py --render
```

Tests use checked-in examples and fixtures, never local projects.
`tests/fixtures/event-goldens.json` stores hashes of event lists captured before
v1 organization: UTF-8 JSON with sorted keys and compact separators. Change these
only for intentional, reviewed event behavior changes, not merely to pass a test.

The short audio test checks alignment, near-null recombination, recipe preservation,
and mastering. Full verification renders three fixed plans and writes
`reports/verification.json`; temporary audio is deleted. Google's remote decoder
is not tested by this suite.

## First commit

Run the checks and inspect the files being added. From this directory:

```bash
git init -b main
git add .
git diff --cached --stat
git diff --cached --check
git status --short
git commit -m "Add v1 JSON-to-Csound stem and mastering pipeline"
```

Ignore rules exclude projects and render artifacts. Back up local music separately.
No remote or publishing step is required. A project license has not been selected.
