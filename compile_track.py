#!/usr/bin/env python3
"""Validate a techno plan and compile Csound; --check diagnoses without writing code."""
import argparse
import heapq
import json
import math
import os
import re
import tempfile
from pathlib import Path
from jsonschema import Draft7Validator
from presets import COMPILER_VERSION, PRESET_VERSION, parameters, variants
from contract import (CONTRACT_REVISION, LEVELS, MAX_EVENTS, MAX_INPUT_BYTES,
                      MAX_POLYPHONY, ROOT, SCHEMA, VOICES, ramp_bounds)


class InvalidTrack(ValueError):
    def __init__(self, issues):
        if isinstance(issues, str):
            issues = [{"path": "$", "code": "invalid", "message": issues}]
        self.issues = issues
        super().__init__("\n".join(f'{e["path"]}: {e["message"]}' for e in issues))


def pointer(parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts) if parts else "$"


def load_track(path):
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise InvalidTrack(f"Input exceeds {MAX_INPUT_BYTES} bytes; use reusable patterns.")

    def unique_keys(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise InvalidTrack(f"Duplicate JSON object key {key!r}; keep exactly one value.")
            obj[key] = value
        return obj

    def constant(value):
        raise InvalidTrack(f"{value} is not a valid finite JSON number.")

    try:
        return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_keys, parse_constant=constant)
    except InvalidTrack:
        raise
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InvalidTrack(f"Invalid JSON: {exc}. Save the complete object without Markdown fences.") from exc


def validate(d):
    issues = []

    def issue(path, message, code="semantic"):
        issues.append({"path": path, "code": code, "message": message})

    def finite(value, parts=()):
        if len(parts) > 32:
            issue(pointer(parts), "JSON is nested too deeply.", "depth")
            return
        if isinstance(value, float) and not math.isfinite(value):
            issue(pointer(parts), "Use a finite number.", "nonfinite")
        elif isinstance(value, dict):
            for key, child in value.items():
                finite(child, parts + (key,))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                finite(child, parts + (index,))

    finite(d)
    if issues:
        raise InvalidTrack(issues)
    for error in Draft7Validator(SCHEMA).iter_errors(d):
        issue(pointer(error.path), error.message, "schema")
    if issues:
        raise InvalidTrack(issues)

    def index_by_id(items, label):
        lookup = {}
        for i, item in enumerate(items):
            if item["id"] in lookup:
                issue(f"/{label}/{i}/id", f'Duplicate ID {item["id"]!r}.', "duplicate_id")
            lookup[item["id"]] = item
        return lookup

    tracks = index_by_id(d["tracks"], "tracks")
    patterns = index_by_id(d["patterns"], "patterns")
    if sum(t["voice"] == "kick" for t in d["tracks"]) != 1:
        issue("/tracks", "Declare exactly one kick track.")
    if 0 not in d["tonality"]["scale_intervals"]:
        issue("/tonality/scale_intervals", "Include interval 0 (the root).")
    end = 0
    for i, section in enumerate(d["sections"]):
        if section["start_bar"] != end:
            issue(f"/sections/{i}/start_bar", f"Expected {end}; sections must be ordered and contiguous.")
        end = section["start_bar"] + section["bars"]
    if end != d["bars"]:
        issue("/sections", f'Sections end at bar {end}; expected {d["bars"]}.')
    for i, track in enumerate(d["tracks"]):
        if track.get("variant", "classic") not in variants(track["voice"]):
            issue(f"/tracks/{i}/variant", f'For {track["voice"]}, choose: {", ".join(variants(track["voice"]))}.', "variant")
        mix = track["mix"]
        if mix["highpass_hz"] >= mix["lowpass_hz"]:
            issue(f"/tracks/{i}/mix", "highpass_hz must be less than lowpass_hz.")
        if track["voice"] in ("kick", "bass") and mix["pan"] != 0:
            issue(f"/tracks/{i}/mix/pan", "Keep kick and bass centered: pan = 0.")
    for i, pattern in enumerate(d["patterns"]):
        for j, event in enumerate(pattern["events"]):
            if event["step"] >= 16 * pattern["bars"]:
                issue(f"/patterns/{i}/events/{j}/step", f'Must be below {16 * pattern["bars"]}.')

    intervals = {key: [] for key in tracks}
    total = 0
    for i, clip in enumerate(d["clips"]):
        path = f"/clips/{i}"
        if clip["track"] not in tracks:
            issue(path + "/track", f'Unknown track {clip["track"]!r}.', "reference")
        if clip["pattern"] not in patterns:
            issue(path + "/pattern", f'Unknown pattern {clip["pattern"]!r}.', "reference")
        if clip["track"] not in tracks or clip["pattern"] not in patterns:
            continue
        track, pattern = tracks[clip["track"]], patterns[clip["pattern"]]
        mix = track["mix"]
        end = clip["start_bar"] + clip["bars"]
        if end > d["bars"]:
            issue(path + "/bars", f'Clip ends at {end}, after track bar {d["bars"]}.')
        for start, stop, previous in intervals[clip["track"]]:
            if clip["start_bar"] < stop and end > start:
                issue(path, f'Overlaps clips[{previous}] on track {clip["track"]!r}.')
        intervals[clip["track"]].append((clip["start_bar"], end, i))
        ramps = {}
        for j, ramp in enumerate(clip["ramps"]):
            name = ramp["parameter"]
            if name in ramps:
                issue(f"{path}/ramps/{j}/parameter", f"Duplicate ramp for {name}.")
            ramps[name] = ramp
            low, high = ramp_bounds(name)
            for side in ("from", "to"):
                if not low <= ramp[side] <= high:
                    issue(f"{path}/ramps/{j}/{side}", f'{name} must be {low}..{high}; received {ramp[side]}.', "range")
            if name == "pan" and track["voice"] in ("kick", "bass") and any(ramp[s] != 0 for s in ("from", "to")):
                issue(f"{path}/ramps/{j}", "Kick/bass pan ramps must remain at 0.")
        # Both filters are affine: checking their difference at each endpoint
        # catches every crossing, including simultaneous HP and LP ramps.
        for side in ("from", "to"):
            hp = ramps.get("highpass_hz", {}).get(side, mix["highpass_hz"])
            lp = ramps.get("lowpass_hz", {}).get(side, mix["lowpass_hz"])
            if hp >= lp:
                issue(path + "/ramps", f"{side}: highpass_hz ({hp}) must be below lowpass_hz ({lp}).")
            gain = ramps.get("gain_db", {}).get(side, clip["gain_db"])
            if gain + mix["gain_db"] > SCHEMA["definitions"]["mix"]["properties"]["gain_db"]["maximum"]:
                issue(path + "/gain_db", "Combined track and clip gain must not exceed +6 dB.")
        for j, event in enumerate(pattern["events"]):
            note = event["midi"] + clip["transpose"]
            event_path = f'{path}/pattern({clip["pattern"]})/events/{j}'
            if not 0 <= note <= 127:
                issue(event_path, f"Transposition produces MIDI {note}; expected 0..127.")
            if track["voice"] == "kick" and not 24 <= note <= 48:
                issue(event_path, f"Kick MIDI {note} must be 24..48.")
            if track["voice"] in ("bass", "stab") and (note - d["tonality"]["root_pitch_class"]) % 12 not in d["tonality"]["scale_intervals"]:
                issue(event_path, f"MIDI {note} is outside the declared scale after transposition.")
        # Odd section lengths may use a final partial pattern repetition.
        full, remainder = divmod(int(clip["bars"]), int(pattern["bars"]))
        total += full * len(pattern["events"]) + sum(e["step"] < remainder * 16 for e in pattern["events"])
    if total > MAX_EVENTS:
        issue("/clips", f"{total} candidate events exceeds {MAX_EVENTS}; simplify the patterns.", "capacity")
    if issues:
        raise InvalidTrack(issues)
    return tracks, patterns


class RNG:
    """LCG32; identical score decisions in Python and uint32_t C arithmetic."""
    def __init__(self, seed):
        self.state = int(seed)

    def uniform(self):
        self.state = (1664525 * self.state + 1013904223) & 0xffffffff
        return self.state / 4294967296.0


def expand(d):
    tracks, patterns = validate(d)
    rng, events = RNG(d["seed"]), []
    step_s = 60 / d["bpm"] / 4
    for ci, clip in enumerate(d["clips"]):
        track, pattern = tracks[clip["track"]], patterns[clip["pattern"]]
        span, origin = clip["bars"] * 16, clip["start_bar"] * 16
        for repeat in range(math.ceil(clip["bars"] / pattern["bars"])):
            for ei, event in enumerate(pattern["events"]):
                local = repeat * pattern["bars"] * 16 + event["step"]
                if local >= span:
                    continue  # Not a candidate: consume no random draw.
                draw = rng.uniform()  # Consume even for probability 0 or 1.
                if draw >= event["probability"]:
                    continue
                absolute = origin + local
                offset = d["swing"] if absolute % 2 else 0
                progress = local / span  # Nominal onset, before swing.
                mix, clip_gain = track["mix"].copy(), clip["gain_db"]
                for ramp in clip["ramps"]:
                    value = ramp["from"] + (ramp["to"] - ramp["from"]) * progress
                    if ramp["parameter"] == "gain_db":
                        clip_gain = value
                    else:
                        mix[ramp["parameter"]] = value
                duration = min(event["duration_steps"], span - local - offset) * step_s
                amp = LEVELS[track["voice"]] * event["velocity"] * 10 ** ((mix["gain_db"] + clip_gain) / 20)
                fields = [VOICES[track["voice"]], (absolute + offset) * step_s, duration, amp,
                          event["midi"] + clip["transpose"], mix["pan"], track["tone"], track["drive"],
                          mix["highpass_hz"], mix["lowpass_hz"], mix["room_send"], mix["delay_send"], mix["duck"]]
                events.append({"track": track["id"], "clip_index": ci, "repeat": repeat,
                               "event_index": ei, "pfields": fields})
    events.sort(key=lambda e: (e["pfields"][1], e["pfields"][0], e["clip_index"], e["repeat"], e["event_index"]))
    if not any(e["pfields"][0] == 1 for e in events):
        raise InvalidTrack("No kick events survived; include an active kick clip with probability 1.")
    active, peak = [], 0
    for event in events:
        fields = event["pfields"]
        if not all(math.isfinite(v) for v in fields) or fields[2] <= 0:
            raise InvalidTrack("Expansion produced a nonfinite value or nonpositive duration.")
        while active and active[0] <= fields[1]:
            heapq.heappop(active)
        heapq.heappush(active, fields[1] + fields[2])
        peak = max(peak, len(active))
    if peak > MAX_POLYPHONY:
        raise InvalidTrack(f"{peak} simultaneous notes exceeds {MAX_POLYPHONY}; reduce overlapping notes.")
    music = d["bars"] * 4 * 60 / d["bpm"]
    return {"format_version": "techno-csound-events-1", "contract_revision": CONTRACT_REVISION,
            "compiler_version": COMPILER_VERSION, "preset_version": PRESET_VERSION,
            "track_variants": {t["id"]: t.get("variant", "classic") for t in d["tracks"]},
            "bpm": d["bpm"], "music_seconds": music, "render_seconds": music + d["master"]["tail_seconds"],
            "peak_polyphony": peak, "events": events}


def quality_warnings(d):
    """Advisory checks; never silently clamp or rewrite creative choices."""
    warnings = []
    used = {c["track"] for c in d["clips"]}
    patterns = {p["id"]: p for p in d["patterns"]}
    for i, track in enumerate(d["tracks"]):
        if track["id"] not in used:
            warnings.append(f'/tracks/{i}: unused track {track["id"]!r}.')
        if track["voice"] == "kick" and track["drive"] < 1:
            warnings.append(f'/tracks/{i}/drive: {track["drive"]} attenuates the kick; drive is linear, not a 0..1 intensity.')
        if track["voice"] == "kick":
            for clip in d["clips"]:
                if clip["track"] == track["id"] and any(e["probability"] < 1 for e in patterns[clip["pattern"]]["events"]):
                    warnings.append(f'/tracks/{i}: probabilistic kick hits may weaken the intended pulse.')
                    break
    return warnings


def make_csd(d, expanded, output_wav=None):
    if output_wav is None:
        output_wav = re.sub(r"[^A-Za-z0-9_-]+", "-", d["title"]).strip("-") or "track"
        output_wav += ".wav"
    output_wav = str(output_wav)
    if any(c in output_wav for c in ('"', '\n', '\r', '\\', '<', '>')):
        raise InvalidTrack("WAV path contains characters unsupported in Csound options.")
    fx = d["effects"]
    tokens = {"SR": 48000, "SEED": int(d["seed"]) % 2147483646 + 1,
              "ROOM_FEEDBACK": fx["room_feedback"], "ROOM_DAMPING": fx["room_damping_hz"],
              "ROOM_GAIN": 10 ** (fx["room_return_db"] / 20), "DELAY_SECONDS": fx["delay_beats"] * 60 / d["bpm"],
              "ECHO_DECAY": fx["echo_decay"], "DELAY_GAIN": 10 ** (fx["delay_return_db"] / 20),
              "MASTER_GAIN": 10 ** (d["master"]["gain_db"] / 20)}
    orc = (ROOT / "engine.orc").read_text()
    for key, value in tokens.items():
        orc = orc.replace("@" + key + "@", format(value, ".12g"))
    if "@" in orc:
        raise InvalidTrack("Engine contains an unresolved substitution token.")
    def line(fields):
        return "i " + " ".join(format(v, ".12g") for v in fields)
    score = ["; Times are seconds; no tempo statement. Contract " + CONTRACT_REVISION,
             f"; Compiler {COMPILER_VERSION}; presets {PRESET_VERSION}"]
    tracks = {t["id"]: t for t in d["tracks"]}
    score += [line(e["pfields"] + [0] + parameters(tracks[e["track"]])) for e in expanded["events"]]
    score += [line([90, 0, expanded["render_seconds"]]), line([99, 0, expanded["render_seconds"]]), "e"]
    return ('<CsoundSynthesizer>\n<CsOptions>\n-d -m0 -W -f -o "' + output_wav + '"\n</CsOptions>\n<CsInstruments>\n' + orc +
            "\n</CsInstruments>\n<CsScore>\n" + "\n".join(score) + "\n</CsScore>\n</CsoundSynthesizer>\n")


def atomic_text(path, text):
    """Replace one destination only after its content has been written."""
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temp = Path(handle.name)
            handle.write(text)
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def check_destinations(inputs, outputs):
    protected = {p.resolve() for p in inputs}
    protected |= {p.resolve() for p in ROOT.iterdir() if p.suffix in (".py", ".orc", ".md") or p.name.endswith("schema.json") or p.name == "track.openapi.json"}
    for folder in ("schemas", "prompts", "examples", "tests", "docs"):
        protected.update(p.resolve() for p in (ROOT / folder).rglob("*") if p.is_file())
    resolved = [p.resolve() for p in outputs if p is not None]
    if len(resolved) != len(set(resolved)) or any(p in protected for p in resolved):
        raise InvalidTrack("Output paths must be distinct and must not overwrite inputs, schemas, or kit source files.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version",
                        version=f"Techno Csound Kit {COMPILER_VERSION}; contract {CONTRACT_REVISION}; presets {PRESET_VERSION}")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--events", type=Path)
    parser.add_argument("--check", action="store_true", help="validate and expand without writing Csound or event files")
    parser.add_argument("--compile-only", action="store_true", help="write CSD and stem routing without rendering or mastering")
    parser.add_argument("--report", type=Path, help="write structured errors, warnings, and timings")
    parser.add_argument("--repair-prompt", type=Path, help="on failure, write all errors for an LLM repair pass")
    args = parser.parse_args()
    if not args.check and args.output is None:
        parser.error("output is required unless --check is used")
    if args.check and (args.output is not None or args.events is not None):
        parser.error("--check does not take output paths except --report and --repair-prompt")
    events_path = args.events or (args.output.with_suffix(".events.json") if args.output else None)
    report = {"contract_revision": CONTRACT_REVISION, "input": str(args.input.resolve()), "valid": False, "errors": [], "warnings": []}
    try:
        check_destinations([args.input], [args.output, events_path, args.report, args.repair_prompt,
                                         args.output.with_suffix(".wav") if args.output else None])
    except InvalidTrack as exc:
        parser.exit(2, f"compile_track.py: error: {exc}\n")
    try:
        data = load_track(args.input)
        expanded = expand(data)
        report.update(valid=True, warnings=quality_warnings(data), events=len(expanded["events"]),
                      music_seconds=expanded["music_seconds"], render_seconds=expanded["render_seconds"], peak_polyphony=expanded["peak_polyphony"])
        if not args.check:
            csd = make_csd(data, expanded, args.output.resolve().with_suffix(".wav"))
            from audio_pipeline import prepare
            try:
                csd, audio_directory = prepare(csd, data, expanded, args.output)
            except ValueError as exc:
                raise InvalidTrack(str(exc)) from exc
            event_json = json.dumps(expanded, indent=2, allow_nan=False) + "\n"
            atomic_text(events_path, event_json)
            atomic_text(args.output, csd)
        if args.report:
            atomic_text(args.report, json.dumps(report, indent=2) + "\n")
    except (InvalidTrack, OSError) as exc:
        report["valid"] = False
        report["errors"] = exc.issues if isinstance(exc, InvalidTrack) else [{"path": "$", "code": "io", "message": str(exc)}]
        try:
            if args.report:
                atomic_text(args.report, json.dumps(report, indent=2) + "\n")
            if args.repair_prompt:
                atomic_text(args.repair_prompt,
                            "Repair the attached track JSON using the system contract. Preserve the composition and all unaffected values. "
                            "Correct ALL errors below. Do not add fields or change validator limits. "
                            "Return the complete corrected JSON object only.\n\n" + json.dumps(report["errors"], indent=2) + "\n")
        except OSError as writing_error:
            parser.exit(2, f"compile_track.py: error: {exc}\nCould not save diagnostics: {writing_error}\n")
        parser.exit(2, f"compile_track.py: error (contract {CONTRACT_REVISION}):\n{exc}\n")
    for warning in report["warnings"]:
        print("Warning:", warning)
    print(f'{report["events"]} events; music {report["music_seconds"]:.3f} s + tail '
          f'{data["master"]["tail_seconds"]:.3f} s = {report["render_seconds"]:.3f} s; '
          + ("validation passed" if args.check else f"wrote {args.output} and {events_path}"))
    if not args.check and not args.compile_only:
        from audio_pipeline import run, mix
        try:
            print("Rendering premix and aligned stems…", flush=True)
            run(["csound", str(args.output.resolve())])
            mix(audio_directory)
        except (RuntimeError, ValueError, OSError, AssertionError) as exc:
            parser.exit(2, f"Audio pipeline failed: {exc}\nCSD is saved; fix the issue before using the audio exports.\n")


if __name__ == "__main__":
    main()
