# Techno Csound Kit — v1.1

Turn a structured musical plan into a Csound arrangement, aligned stems, and a
measured stereo master. Any LLM can supply the JSON; generation happens outside
this repository. Rendering needs no API keys, network calls, samples, or plugins.

**Prompt → JSON → validation → Csound → stems → mix → master**

## Install

Required: Python 3.10+, Csound, FFmpeg and FFprobe with libsoxr support. The local
v1 verification environment uses Python 3.10 and Csound 6.17.

Run commands from this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 1. Generate or choose a plan

In AI Studio, use:

| Input | File |
| --- | --- |
| System instructions | [SYSTEM_PROMPT.txt](prompts/SYSTEM_PROMPT.txt) |
| Structured output schema | [gemini-response-schema.json](schemas/gemini-response-schema.json) |
| Example artistic brief | [USER_PROMPT_EXAMPLE.txt](prompts/USER_PROMPT_EXAMPLE.txt) |

Paste the schema object itself into the schema editor. The easiest workflow accepts
either a `.txt` or `.json` drop file; its content must be plain JSON:

```bash
python new_track.py track_11.txt
```

This validates the plan, creates `projects/track_11/`, normalizes it to
`track_11.json`, and runs the full render/master pipeline. A valid source dropped
directly in the kit root is consumed after its project copy is safely written,
keeping the root clean. An external source is preserved. Override the derived name
with `--name nocturnal_pressure`. Existing project folders are never merged or
replaced. To try the included example without changing it:

```bash
python new_track.py examples/example.track.json --name my_track
```

For your own music, replace `track.json` with the generated plan. See
[generation and repair](docs/generation.md) if Gemini rejects the schema or
truncates a response. Live Gemini acceptance is not part of local verification.

## 2. Validate

```bash
python compile_track.py projects/my-track/track.json --check \
  --report projects/my-track/validation.json \
  --repair-prompt projects/my-track/repair.txt
```

On failure, give the model the JSON and repair instructions, save its corrected
JSON, and validate again. Repair files are written only on failure; ignore an old
repair file after a successful check. Invalid plans do not replace compiled files.

## 3. Render the complete track

```bash
python compile_track.py projects/my-track/track.json projects/my-track/track.csd
```

Compilation automatically renders stems, mixes, masters, and checks the delivered
audio. **Listen to `projects/my-track/track.audio/master.wav`.**

| Output within the project folder | Purpose |
| --- | --- |
| `track.csd` | Synthesizer, score, and stem routing |
| `track.events.json` | Expanded portable event list |
| `track.wav` | Original stereo float premix |
| `track.audio/stems/` | One stereo float file per track, plus room and delay |
| `track.audio/stems.json` | Track IDs, stem filenames, duration, and CSD path |
| `track.audio/mix.json` | Editable balance and mastering settings |
| `track.audio/mix.csd`, `mix.wav` | Rebuilt mix through the shared master bus |
| `track.audio/master.wav` | 48 kHz, 24-bit listening master |
| `track.audio/mastering.json` | Actual measurements, settings, and provenance |

Use `--compile-only` to stop before rendering. Then run `csound` on the CSD to
render the premix and stems, followed by the mixing command below.

## 4. Refine the mix

Edit `track.audio/mix.json`. Stem gains are additional decibels: `1` raises a
stem by 1 dB; `-2` lowers it by 2 dB. Rebuild without resynthesizing:

```bash
python audio_pipeline.py projects/my-track/track.audio
```

For changes to notes, arrangement, synthesis, sends, or ducking, edit the plan and
compile again. Existing mix recipes are preserved; update their IDs if you change
the palette. See [mixing and mastering](docs/audio.md) for routing and controls.

Rerunning a project replaces its generated exports. Keep a copy before experimenting
to preserve a version. Generated CSDs use absolute paths: recompile after moving a
project. An old master may remain after a failed run; a successful new
`mastering.json` verifies the new mix/master run.

## Repository layout

```text
compile_track.py       Validation and complete render entry point
new_track.py           Import generated JSON into a self-contained project
audio_pipeline.py     Stem routing, remixing, and mastering
audio_checks.py       Shared audio measurements and subprocess checks
assemble_track.py     Assemble staged LLM responses
contract.py           Contract access and schema projections
build_contracts.py    Regenerate schemas and system instructions
verify_system.py      Regression and full-render verification
engine.orc            Fixed eight-voice Csound engine
schemas/              Authoritative schema and generated API exports
prompts/              Prompt source, generated prompt, artistic brief
examples/             Small runnable plan
tests/                Tests and fixed regression fixtures
docs/                 Generation, audio, and format references
projects/             Local compositions and audio (ignored by Git)
reports/              Local verification output (ignored by Git)
```

Existing local tracks are kept under `projects/track_N/`. They are not required by
the software or included in the source commit.

## Verify and develop

```bash
python build_contracts.py --check
python -m unittest discover -s tests -v
python verify_system.py --render
```

The audio regression test renders a short excerpt and checks stem recombination
and mastering. It skips when audio tools are absent. `--render` requires those
tools and also renders three full fixed plans into temporary files.
See [contributing](CONTRIBUTING.md) for contract changes and first-commit checks.

v1 preserves generated balance and offers repeatable controls; it does not infer a
professional mix automatically. Mastering targets −11 LUFS while prioritizing a
−1.3 dBTP ceiling. Inspect the actual results and audition before release.

## Controlled timbral variation

Tracks can optionally select a compiler-owned sound preset with `"variant"`:
kick supports `subby`, `punchy`, `tight`; closed hat supports `crisp`, `dark`,
`metallic`; open hat supports `airy`, `dark`, `metallic`; clap supports `dry`,
`sharp`, `wide`. Other voices support `classic` only. Omit the field or use
`classic` to preserve the original v1.0 sound. Use the regenerated prompt/schema
when generating new plans. See [preset vocabulary and evaluation](docs/presets.md).

```bash
python compare_presets.py
```

This renders a fixed groove twice per variant, measures isolated stems and full
mixes, and creates `reports/preset-comparisons/index.html` for listening.
The known baseline is tagged `v1.0.0`; see [versioning](docs/presets.md#versioning).
