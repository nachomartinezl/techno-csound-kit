import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jsonschema import Draft7Validator, RefResolver
from assemble_track import assemble
from build_contracts import STAGES, generated_files
from compile_track import InvalidTrack, RNG, check_destinations, expand, load_track, validate
from contract import ROOT, SCHEMA, audit_gemini, gemini_schema, openapi_document, ramp_bounds


def fixture():
    return json.loads((ROOT / "examples/example.track.json").read_text())


def plan_path(name):
    return ROOT / ("examples" if name == "example.track.json" else "tests/fixtures") / name


class ContractTests(unittest.TestCase):
    def test_generated_artifacts_match(self):
        for name, text in generated_files().items():
            with self.subTest(file=name):
                self.assertEqual((ROOT / name).read_text(), text)

    def test_schema_document_and_examples(self):
        Draft7Validator.check_schema(SCHEMA)
        light = gemini_schema()
        Draft7Validator.check_schema(light)
        audit_gemini(light)
        # A JSON property named 'pattern' or 'title' is not a schema keyword.
        self.assertEqual(light["properties"]["title"]["type"], "string")
        self.assertEqual(light["properties"]["clips"]["items"]["properties"]["pattern"]["type"], "string")
        oas = openapi_document()
        resolver = RefResolver.from_schema(oas)
        strict_oas = Draft7Validator(oas["components"]["schemas"]["TrackPlan"], resolver=resolver)
        for name in ("example.track.json", "track_1.json", "track_2.json"):
            with self.subTest(file=name):
                data = load_track(plan_path(name))
                Draft7Validator(light).validate(data)
                strict_oas.validate(data)
                expand(data)

    def test_api_schema_uses_only_openapi30_keywords(self):
        def walk(node):
            if "$ref" in node:
                target = node["$ref"].rsplit("/", 1)[-1]
                self.assertIn(target, oas["components"]["schemas"])
                self.assertEqual(set(node), {"$ref"})
                return
            self.assertNotIn("const", node)
            self.assertNotIn("$schema", node)
            self.assertNotIn("definitions", node)
            self.assertIn("type", node)
            if "required" in node:
                self.assertLessEqual(set(node["required"]), set(node["properties"]))
            for child in node.get("properties", {}).values():
                walk(child)
            for child in node.get("oneOf", []):
                walk(child)
            if "items" in node:
                walk(node["items"])
        oas = openapi_document()
        self.assertEqual(oas["openapi"], "3.0.3")
        for schema in oas["components"]["schemas"].values():
            walk(schema)

    def test_stage_merge_preserves_exact_plan_and_events(self):
        data = fixture()
        parts = [{key: copy.deepcopy(data[key]) for key in keys} for keys in STAGES.values()]
        merged = assemble(parts)
        self.assertEqual(merged, data)
        self.assertEqual(expand(merged), expand(data))
        for name, part in zip(STAGES, parts):
            schema = json.loads((ROOT / f"schemas/gemini-stages/{name}.schema.json").read_text())
            Draft7Validator(schema).validate(part)
        with self.assertRaisesRegex(InvalidTrack, "Duplicate stage"):
            assemble(parts + [parts[0]])

    def test_scalar_fields_not_lost_when_exporting(self):
        def compare(strict, light):
            if "$ref" in strict:
                strict = SCHEMA["definitions"][strict["$ref"].rsplit("/", 1)[-1]]
            self.assertEqual(strict["type"], light["type"])
            if "properties" in strict:
                self.assertEqual(set(strict["properties"]), set(light["properties"]))
                self.assertEqual(strict["required"], light["required"])
                for key in strict["properties"]:
                    compare(strict["properties"][key], light["properties"][key])
            if "items" in strict:
                compare(strict["items"], light["items"])
        compare(SCHEMA, gemini_schema())

    def test_production_tracks_preserve_previous_event_values(self):
        # Golden expanded events predate the review; no regeneration in this test.
        goldens = json.loads((ROOT / "tests/fixtures/event-goldens.json").read_text())
        for plan, old in goldens.items():
            new = expand(load_track(plan_path(plan)))
            with self.subTest(plan=plan):
                digest = hashlib.sha256(json.dumps(new["events"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                self.assertEqual(old["events_sha256"], digest)
                self.assertEqual(old["render_seconds"], new["render_seconds"])

    def test_sends_and_fractional_drive_supported_consistently(self):
        data = fixture()
        data["tracks"][0]["drive"] = .35
        data["tracks"][2]["mix"]["room_send"] = .8
        data["tracks"][2]["mix"]["delay_send"] = .8
        clip = next(c for c in data["clips"] if c["track"] == "closed")
        clip["ramps"] = [{"parameter": name, "from": .35, "to": .8} for name in ("room_send", "delay_send")]
        validate(data)
        for name in ("room_send", "delay_send"):
            self.assertEqual(ramp_bounds(name), (0, .8))
        oas = openapi_document()
        Draft7Validator(oas["components"]["schemas"]["TrackPlan"], resolver=RefResolver.from_schema(oas)).validate(data)

    def test_range_errors_identify_all_endpoints(self):
        data = fixture()
        data["clips"][0]["ramps"] = [{"parameter": "room_send", "from": -.1, "to": .81},
                                     {"parameter": "delay_send", "from": .9, "to": 2}]
        with self.assertRaises(InvalidTrack) as caught:
            validate(data)
        errors = [e for e in caught.exception.issues if e["code"] == "range"]
        self.assertEqual(len(errors), 4)
        self.assertIn("/clips/0/ramps/1/to", [e["path"] for e in errors])

    def test_no_flattened_room_bounds_on_filter_or_gain(self):
        data = fixture()
        clip = next(c for c in data["clips"] if c["track"] == "hook")
        clip["ramps"] = [{"parameter": "lowpass_hz", "from": 1200, "to": 6000},
                         {"parameter": "gain_db", "from": -12, "to": 0}]
        validate(data)

    def test_both_filter_ramps_are_checked_together(self):
        data = fixture()
        clip = next(c for c in data["clips"] if c["track"] == "hook")
        clip["ramps"] = [{"parameter": "highpass_hz", "from": 200, "to": 1600},
                         {"parameter": "lowpass_hz", "from": 2000, "to": 1000}]
        with self.assertRaisesRegex(InvalidTrack, "highpass_hz"):
            validate(data)
        clip["ramps"][1]["to"] = 3000
        validate(data)

    def test_highpass_only_cannot_cross_static_lowpass(self):
        data = fixture()
        clip = next(c for c in data["clips"] if c["track"] == "hook")
        clip["ramps"] = [{"parameter": "highpass_hz", "from": 300, "to": 4000}]
        with self.assertRaisesRegex(InvalidTrack, "highpass_hz"):
            validate(data)

    def test_partial_pattern_repeat_and_clip_end(self):
        data = fixture()
        data["bars"] = 9
        data["sections"] = [{"name": "test", "start_bar": 0, "bars": 9, "intent": "partial pattern"}]
        data["tracks"] = data["tracks"][:1]
        pattern = data["patterns"][0]
        pattern["bars"] = 2
        pattern["events"] = [{"step": 0, "duration_steps": 64, "midi": 31, "velocity": .8, "probability": 1},
                             {"step": 20, "duration_steps": 1, "midi": 31, "velocity": .8, "probability": 1}]
        data["patterns"] = [pattern]
        data["clips"] = [dict(data["clips"][0], bars=9)]
        result = expand(data)
        self.assertEqual(len(result["events"]), 9)  # four full pairs, one partial event
        self.assertTrue(all(e["pfields"][1] + e["pfields"][2] <= result["music_seconds"] + 1e-9 for e in result["events"]))

    def test_swing_only_moves_odd_steps(self):
        data = fixture()
        data["swing"] = 0
        straight = expand(data)["events"]
        data["swing"] = .2
        swung = expand(data)["events"]
        keyed = lambda events: {(e["clip_index"], e["repeat"], e["event_index"]): e["pfields"] for e in events}
        a, b = keyed(straight), keyed(swung)
        patterns = {p["id"]: p for p in data["patterns"]}
        for key, fields in a.items():
            ci, rep, ei = key
            step = patterns[data["clips"][ci]["pattern"]]["events"][ei]["step"]
            self.assertAlmostEqual(b[key][1] - fields[1], (.2 * 60 / 140 / 4) if step % 2 else 0)

    def test_rng_known_uint32_values(self):
        rng = RNG(0)
        self.assertEqual(rng.uniform(), 1013904223 / 4294967296)
        self.assertEqual(rng.uniform(), 1196435762 / 4294967296)

    def test_nonfinite_duplicate_keys_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            for text in ('{"seed":1,"seed":2}', '{"seed":NaN}', '{"seed":1e999}', '```json\n{}\n```'):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(InvalidTrack):
                    validate(load_track(path))
            result = subprocess.run([sys.executable, str(ROOT / "compile_track.py"), str(Path(tmp) / "missing.json"), "--check"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)

    def test_safe_paths_and_failed_validation_preserve_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, output, report, repair = (Path(tmp) / n for n in ("input.json", "output.csd", "report.json", "repair.txt"))
            for outputs in ([source], [output, output], [ROOT / "engine.orc"]):
                with self.assertRaises(InvalidTrack):
                    check_destinations([source], outputs)
            data = fixture()
            data["clips"][0]["ramps"] = [{"parameter": "room_send", "from": .9, "to": 1.1}]
            source.write_text(json.dumps(data))
            output.write_text("previous valid output")
            result = subprocess.run([sys.executable, str(ROOT / "compile_track.py"), str(source), str(output), "--report", str(report), "--repair-prompt", str(repair)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(), "previous valid output")
            self.assertEqual(len(json.loads(report.read_text())["errors"]), 2)
            self.assertIn("/clips/0/ramps/0/to", repair.read_text())

    def test_semantic_failure_cases(self):
        def duplicate_track(d): d["tracks"].append(copy.deepcopy(d["tracks"][0]))
        def bad_ref(d): d["clips"][0]["pattern"] = "missing"
        def overlap(d): d["clips"].append(copy.deepcopy(d["clips"][0]))
        def zero_drive(d): d["tracks"][0]["drive"] = 0
        def phase_pan(d): d["tracks"][0]["mix"]["pan"] = .2
        def bad_end(d): d["sections"][-1]["bars"] += 1
        def extra_field(d): d["tracks"][0]["resonance"] = .5
        def no_kicks(d):
            for event in d["patterns"][0]["events"]: event["probability"] = 0
        def over_step(d): d["patterns"][0]["events"][0]["step"] = 16
        def scale_duplicate(d): d["tonality"]["scale_intervals"].append(0)
        for mutate in (duplicate_track, bad_ref, overlap, zero_drive, phase_pan, bad_end, extra_field, no_kicks, over_step, scale_duplicate):
            data = fixture()
            mutate(data)
            with self.subTest(case=mutate.__name__), self.assertRaises(InvalidTrack):
                expand(data)

    def test_resource_caps_before_render(self):
        data = fixture()
        data["tracks"] = data["tracks"][:1]
        data["patterns"] = data["patterns"][:1]
        data["patterns"][0]["events"] = [copy.deepcopy(data["patterns"][0]["events"][0]) for _ in range(129)]
        data["clips"] = [data["clips"][0]]
        with self.assertRaisesRegex(InvalidTrack, "simultaneous"):
            expand(data)
        data["patterns"][0]["events"] *= 8
        data["bars"] = 256
        data["sections"] = [{"name": "long", "start_bar": 0, "bars": 256, "intent": "limit test"}]
        data["clips"][0]["bars"] = 256
        with self.assertRaisesRegex(InvalidTrack, "candidate"):
            expand(data)


if __name__ == "__main__":
    unittest.main()
