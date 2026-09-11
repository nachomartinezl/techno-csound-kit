"""Versioned, compiler-owned percussion presets; never raw LLM DSP controls."""
PRESET_VERSION = "1.0.0"
COMPILER_VERSION = "1.1.0"

# CSD-only fields p15..p27. p14 is reserved for the stem index. The classic
# branch ignores these controls and retains the original signal path exactly.
FIELDS = ("enabled", "decay_ratio", "amp_curve", "pitch_ratio", "pitch_decay_s",
          "click_gain", "drive_scale", "highpass_hz", "lowpass_hz", "metal_mix",
          "clap_center_hz", "clap_spread_s", "output_gain_db")
BASE = dict(zip(FIELDS, (1, 1, -5, 3.5, .055, 1, 1, 4500, 16000, 0, 2200, .022, 0)))

PRESETS = {
    "kick": {
        "subby": {"decay_ratio": 1, "amp_curve": -2.2, "pitch_ratio": 2,
                  "pitch_decay_s": .035, "click_gain": .25, "drive_scale": .85, "output_gain_db": 1.5},
        "punchy": {"decay_ratio": .85, "amp_curve": -3, "pitch_ratio": 4.8,
                   "pitch_decay_s": .026, "click_gain": 1.4, "drive_scale": 1.1, "output_gain_db": 1.1},
        "tight": {"decay_ratio": .55, "amp_curve": -4, "pitch_ratio": 3.2,
                  "pitch_decay_s": .018, "click_gain": .7, "drive_scale": 1.2, "output_gain_db": 3.1},
    },
    "closed_hat": {
        "crisp": {"decay_ratio": .8, "amp_curve": -5, "highpass_hz": 6500, "lowpass_hz": 17000, "output_gain_db": 1.1},
        "dark": {"decay_ratio": 1, "amp_curve": -3, "highpass_hz": 3200, "lowpass_hz": 8500, "output_gain_db": .7},
        "metallic": {"decay_ratio": .9, "amp_curve": -4, "highpass_hz": 4500, "lowpass_hz": 15000, "metal_mix": .65, "output_gain_db": .6},
    },
    "open_hat": {
        "airy": {"decay_ratio": 1, "amp_curve": -2.5, "highpass_hz": 7500, "lowpass_hz": 18000, "output_gain_db": -1.2},
        "dark": {"decay_ratio": .85, "amp_curve": -3, "highpass_hz": 3000, "lowpass_hz": 8000, "output_gain_db": 1},
        "metallic": {"decay_ratio": 1, "amp_curve": -3.5, "highpass_hz": 4500, "lowpass_hz": 15000, "metal_mix": .7, "output_gain_db": -1},
    },
    "clap": {
        "dry": {"decay_ratio": .6, "amp_curve": -5, "clap_center_hz": 1900, "clap_spread_s": .012, "output_gain_db": 3.1},
        "sharp": {"decay_ratio": .75, "amp_curve": -6, "clap_center_hz": 3400, "clap_spread_s": .018, "output_gain_db": .9},
        "wide": {"decay_ratio": 1, "amp_curve": -3.5, "clap_center_hz": 2200, "clap_spread_s": .038, "output_gain_db": -1},
    },
}


def variants(voice):
    return ("classic", *PRESETS.get(voice, {}))


def parameters(track):
    name = track.get("variant", "classic")
    if name not in variants(track["voice"]):
        raise ValueError(f'Unsupported {track["voice"]} variant {name!r}')
    values = {**BASE, **PRESETS.get(track["voice"], {}).get(name, {})}
    values["enabled"] = int(name != "classic")
    return [values[key] for key in FIELDS]


def vocabulary():
    return ["classic", *dict.fromkeys(name for family in PRESETS.values() for name in family)]


def guide():
    return "\n".join(f'- {voice}: ' + ', '.join(variants(voice)) for voice in PRESETS)
