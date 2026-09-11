# Controlled timbral variation

## Using variants

Add one optional field to an existing track object:

```json
{
  "id": "kick_main",
  "voice": "kick",
  "variant": "tight",
  "role": "Firm, compact pulse",
  "tone": 0.5,
  "drive": 1.4,
  "mix": {
    "gain_db": -8,
    "pan": 0,
    "highpass_hz": 25,
    "lowpass_hz": 12000,
    "room_send": 0,
    "delay_send": 0,
    "duck": 0
  }
}
```

This is a track object inside `tracks`, not a complete plan. The rest of the
JSON-to-master workflow is unchanged. Variants are static per track, not event
fields or automation targets. Unknown names and wrong voice/name pairs fail with
a `/tracks/N/variant` error. The semantic choice does not change note events,
arrangement timing, probability draws, pitch, or user-specified mix controls.

| Voice | Variant | Intended character |
| --- | --- | --- |
| kick | subby | Rounded pitch sweep and longer body |
| kick | punchy | Stronger, faster pitch transient and click |
| kick | tight | Shorter body for dense grooves |
| closed_hat | crisp | Short, bright filtered noise |
| closed_hat | dark | Softer upper spectrum and fuller lower noise band |
| closed_hat | metallic | Fixed inharmonic partials mixed with noise |
| open_hat | airy | Longer, bright noise decay |
| open_hat | dark | Restrained brightness and shorter decay |
| open_hat | metallic | Ringing partials with a noise component |
| clap | dry | Compact envelope and closely spaced pulses |
| clap | sharp | Higher presence band and fast envelope |
| clap | wide | More separated pulses and a 4 ms right-channel offset |

Every voice also supports `classic`, which retains the original signal path.
Omitted variants behave exactly like `classic`. Bass, stab, percussion, and noise
currently support only `classic`; no snare voice or new instrument type was added.

Choose a coherent palette. A dark, dense warehouse brief can use a tight kick,
dark hats, and dry clap. More variants at once does not inherently improve a mix.
Existing bounded tone/drive controls remain available, but the model cannot supply
arbitrary preset decay, partial frequencies, click gains, or other raw DSP fields.

## Schema and compiler ownership

`presets.py` owns the versioned parameter mappings and fixed compensation gains.
The optional schema enum contains the compact union of names. The compiler enforces
the voice/name relationship locally, avoiding a larger conditional Gemini schema.
The generated system instructions list the valid vocabulary by voice.

New CSDs carry a reserved p14 stem index and compiler-owned p15–p27 controls.
`FIELDS` in `presets.py` defines that order. Portable event pfields remain the
original thirteen fields; `track_variants`, `compiler_version`, and `preset_version`
are recorded alongside the events and in stem manifests. CSDs embed resolved
numeric controls, so rendering an existing CSD does not consult a newer preset table.
Mastering reports retain the synthesis versions recorded in the stem manifest.

## Levels and repeatability

Preset-specific output compensation is fixed at compile time. It was calibrated
against `classic` on `examples/timbral-comparison.track.json`, not normalized
independently on every generated note. This keeps rendering deterministic and
preserves velocity/arrangement dynamics.

Compensation is approximate: different MIDI notes, lengths, tone, drive, filters,
and arrangements can change the relative balance. The final master still performs
its own peak checks; audition your track instead of assuming every valid setting
combination has identical loudness.
Shorter, sharper sounds can have higher crest factors at similar premix LUFS and
therefore produce a quieter peak-constrained master. Check the actual mastering
report instead of assuming that matched preset loudness guarantees a −11 LUFS export.

The comparison harness keeps one groove and seed fixed and changes one variant
at a time. It renders each setting twice and verifies decoded samples for the
full mix and all stems. Csound WAV headers can contain wall-clock timestamps;
container hashes may therefore differ even when audio samples are identical.
Audio repeatability assumes the same compiler, presets, Csound/FFmpeg builds,
and platform. No new uncontrolled random source is introduced by the presets.

## Comparison renders

```bash
python compare_presets.py
python compare_presets.py --voice kick --output reports/kick-comparisons
```

Open `reports/preset-comparisons/index.html` in a browser. Each row offers the full
unmastered mix and its isolated target stem. These use the same composition and
gain staging, including preset compensation. The page does not play multiple
versions in sync; stop one before starting another. `metrics.json` records:

- duration, sample/true peaks, RMS, LUFS, and nonfinite sample counts;
- decoded-sample hashes and repeatability results;
- differences from each family's classic reference;
- pairwise waveform correlations and explicit failures.

Checks allow at most 2 LU stem loudness difference, 3 dB stem RMS difference,
1.5 LU full-mix difference, and absolute pairwise correlation below 0.98. Every
render must have safe measured peaks and the expected length. These are focused
regression bounds, not universal psychoacoustic guarantees. The listening page is
provided for subjective evaluation; no monitored listening claim is made.

`--measure-only` collects calibration results without enforcing relative-level or
distinction thresholds. It still checks audio validity and writes any failures;
do not use it as the release acceptance command.

## Versioning

- Stable pre-change baseline: Git tag `v1.0.0`, commit `acaa16f`.
- Current compiler/release: `1.1.0`.
- Track contract revision: `1.2.0`; JSON format remains `techno-csound-1`.
- Preset table version: `1.0.0`.

`python compile_track.py --version` prints all three current version numbers.

A source archive, hash manifest, and Git bundle were also saved before editing in
the parent `archive/techno-kit-v1.0.0-20260910-232925/` directory. Ignored music
projects remain in place; they were not rerendered or included in that source archive.

To inspect the original source without overwriting current work:

```bash
git worktree add ../techno-csound-kit-v1.0.0 v1.0.0
```
