# Controlled Timbral Variation — Implementation Instruction

## Goal

Introduce **controlled timbral variation** into the current techno-generation system without changing the overall architecture or sacrificing determinism.

The current pipeline already produces predictable results:

- LLM generates structured JSON
- Python compiler converts JSON into Csound/CSD
- Csound renders audio
- Python post-processing/mastering produces the final WAV

Preserve that architecture.

The next improvement is to let the model choose among multiple **production-ready sound variants** for each instrument while keeping output deterministic, bounded, mix-safe, and semantically simple.

---

## Core Principle

Do **not** expose raw synthesis/DSP parameters directly to the LLM.

Instead, expose a small semantic preset vocabulary such as:

```json
{
  "kick": {
    "variant": "punchy"
  },
  "closed_hat": {
    "variant": "crisp"
  },
  "open_hat": {
    "variant": "metallic"
  }
}
```

The compiler should translate each semantic variant into a known, tested set of Csound parameters.

The model chooses **intent**.

The compiler owns **sound design implementation**.

---

## Requirements

### 1. Preserve existing architecture

Do not redesign the generation system.

Keep the existing:

- structured-output contract
- JSON schema
- compiler flow
- Csound rendering flow
- mastering pipeline
- deterministic seed behavior

Only extend the instrument representation enough to support sound variants.

---

### 2. Add a small preset vocabulary per instrument

Start with a limited number of clearly differentiated variants.

Example initial vocabulary:

#### Kick

- `subby`
- `punchy`
- `hard`
- `tight`
- `soft`

#### Closed hi-hat

- `crisp`
- `dark`
- `metallic`
- `short`
- `noisy`

#### Open hi-hat

- `airy`
- `metallic`
- `bright`
- `dark`
- `short`

#### Clap / snare

- `dry`
- `wide`
- `sharp`
- `noisy`
- `deep`

Do not add dozens of variants initially.

Prefer **3–5 strong, recognizably different presets** per instrument.

---

### 3. Keep variants deterministic

The exact same:

- JSON
- seed
- compiler version
- preset version

must produce the same result.

If a preset internally uses randomized micro-variation, all randomness must be derived from the existing deterministic seed.

Never introduce uncontrolled randomness.

---

### 4. Implement variants as compiler-owned presets

Each semantic variant should map to a concrete bounded parameter set.

Conceptually:

```python
KICK_PRESETS = {
    "subby": {
        "start_freq": ...,
        "end_freq": ...,
        "pitch_decay": ...,
        "amp_decay": ...,
        "drive": ...,
        "click_amount": ...
    },
    "punchy": {
        ...
    }
}
```

The exact implementation can follow the existing project style.

The important rule is:

> The LLM selects a named preset. The compiler determines the DSP.

Do not allow arbitrary values like:

```json
{
  "kick": {
    "pitch_decay": 0.0317,
    "drive": 1.832,
    "filter_q": 6.91
  }
}
```

unless those parameters are already part of a carefully bounded existing schema.

---

### 5. Normalize perceived level across variants

A different preset should change the **character**, not accidentally change the entire mix balance.

Variants must be gain-staged so their perceived level is reasonably consistent.

At minimum:

- avoid clipping
- avoid major RMS/LUFS jumps
- keep peaks within expected bounds
- make sure one preset does not dominate solely because it is louder

Where necessary, include preset-specific output compensation.

Example:

```python
"hard": {
    "drive": 1.8,
    "output_gain_db": -2.5
}
```

The target is not mathematically identical loudness.

The target is **mix-compatible loudness**.

---

### 6. Make the variants meaningfully different

Do not create five presets that are technically different but perceptually almost identical.

For every preset family, verify that the variants are audibly distinct.

For example, kick presets might intentionally vary:

- fundamental / body frequency
- pitch envelope depth
- pitch decay
- amplitude decay
- transient click
- saturation / distortion
- tail length
- noise/transient content

Hi-hat presets might vary:

- metallic partial structure
- noise balance
- high-pass frequency
- decay
- brightness
- transient sharpness
- stereo treatment, if supported

Keep these differences bounded and musically useful.

---

### 7. Update the JSON schema

Add preset selection in the smallest clean extension possible.

Example:

```json
{
  "instruments": {
    "kick": {
      "variant": "punchy"
    },
    "closed_hat": {
      "variant": "crisp"
    }
  }
}
```

Use enums wherever possible.

Example conceptual schema:

```json
{
  "variant": {
    "type": "string",
    "enum": ["subby", "punchy", "hard", "tight", "soft"]
  }
}
```

Invalid preset names should fail validation or cleanly fall back to a documented default.

Do not silently interpret arbitrary strings.

---

### 8. Update the assistant/system prompt

Teach the composing model to select variants intentionally.

The prompt should communicate something like:

> Choose instrument variants according to the musical role, arrangement, density, genre, and requested character. Do not vary presets merely for novelty. Maintain sonic coherence across the track.

Examples:

- dense warehouse techno → `tight` or `hard` kick
- hypnotic low-end-heavy track → `subby` kick
- aggressive percussion → `metallic` hats
- darker restrained mix → `dark` hats
- sparse groove → potentially longer or more characterful sounds

The model should understand that presets are part of **production direction**, not random decoration.

---

### 9. Prefer coherence over random diversity

Do not make every instrument choose a random preset independently.

A generated track should sound like one coherent production.

Preset decisions should be influenced by:

- track description
- energy
- density
- arrangement
- tempo
- scale/melodic material
- requested style
- other instrument choices

For example, if the overall brief is:

> dark, dry, hypnotic, stripped Berlin warehouse techno

then the model should consistently favor sounds that reinforce that direction.

---

## Testing

Add a focused test harness for preset variation.

Use one fixed composition and change **only one instrument variant at a time**.

Example:

```text
track_A = same arrangement + kick=subby
track_B = same arrangement + kick=punchy
track_C = same arrangement + kick=hard
```

Everything else should remain identical.

Verify:

1. All variants render successfully.
2. Outputs are deterministic.
3. Variants are audibly distinguishable.
4. Peak levels stay within acceptable bounds.
5. Overall loudness stays reasonably close.
6. No variant unexpectedly destroys the mix.
7. Existing tracks without a `variant` field still compile using the default behavior.

---

## Suggested evaluation output

For each rendered preset test, collect basic metrics such as:

```text
preset
peak_dbfs
rms_dbfs
integrated_lufs
duration
render_hash
```

Optionally generate a comparison folder:

```text
preset_tests/
  kick_subby.wav
  kick_punchy.wav
  kick_hard.wav
  kick_tight.wav
  metrics.json
```

This will make later sound-design iteration much faster.

---

## Backward compatibility

Existing JSON without explicit variants should continue working.

Example:

```json
{
  "kick": {}
}
```

should behave as the current/default kick.

Do not break existing prompts or fixtures unless absolutely necessary.

---

## Initial Scope

For the first implementation, do not try to solve every instrument.

Start with the most perceptually important percussion voices:

1. kick
2. closed hi-hat
3. open hi-hat
4. clap/snare

Once the mechanism is stable, it can later be extended to:

- bass
- rumble
- stab
- pad
- noise
- percussion
- rides
- FX

---

## Deliverable

Implement the preset system end-to-end:

1. inspect the current schema and compiler
2. define a compact preset vocabulary
3. implement compiler-side preset mappings
4. update structured-output schema
5. update assistant/composer instructions
6. preserve deterministic behavior
7. add loudness/gain compensation where needed
8. create comparison renders/tests
9. document the preset vocabulary
10. keep existing behavior backward-compatible

Do not redesign unrelated parts of the project.

The objective of this iteration is simple:

> **Increase sonic variety without decreasing predictability.**

The result should allow the LLM to make musically meaningful choices like:

> “Use a tight punchy kick with dark short hats”

while the compiler remains responsible for translating those semantic choices into safe, deterministic, production-ready Csound parameters.
