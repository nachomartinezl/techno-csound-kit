# Changelog

## 1.1.0

- Added `new_track.py` to import generated text/JSON into an isolated local project
  and run the complete pipeline.
- Optional per-track semantic variants for kick, closed hat, open hat, and clap.
- Three new presets per family with fixed, calibrated output compensation.
- Original `classic` sound retained for omitted variants and all other voices.
- Compact schema/prompt updates with voice-specific local validation.
- Versioned preset tables, synthesis provenance, and repeatable audio comparisons.

Plan format: `techno-csound-1`. Contract revision: `1.2.0`. Presets: `1.0.0`.
The prior stable commit is preserved as Git tag `v1.0.0`.

## 1.0.0

- Structured validation and deterministic event expansion for eight voices.
- Generated Gemini/OpenAPI schemas, system instructions, and staged assembly.
- Csound rendering with aligned track stems and shared wet returns.
- Editable balance, shared mix bus, and measured fixed-gain mastering.
- Fixed regression fixtures, stem recombination tests, and render verification.
- Source, prompts, schemas, documentation, and local music organized separately.

Plan format: `techno-csound-1`. Contract revision: `1.1.0`.
