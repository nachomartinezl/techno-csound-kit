import copy
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_pipeline import prepare
from compile_track import InvalidTrack, expand, load_track, make_csd
from contract import SCHEMA, gemini_schema
from presets import BASE, FIELDS, PRESETS, parameters, variants, vocabulary
import tempfile


class PresetTests(unittest.TestCase):
    def setUp(self):
        self.plan = load_track(ROOT/'examples/timbral-comparison.track.json')

    def test_optional_classic_and_schema_vocabulary(self):
        strict = SCHEMA['definitions']['track']
        light = gemini_schema()['properties']['tracks']['items']
        self.assertNotIn('variant', strict['required'])
        self.assertNotIn('variant', light['required'])
        self.assertEqual(strict['properties']['variant']['enum'], vocabulary())
        self.assertEqual(light['properties']['variant']['enum'], vocabulary())
        original = expand(self.plan)
        original_csd = make_csd(self.plan, original)
        for track in self.plan['tracks']:
            track['variant'] = 'classic'
        self.assertEqual(original, expand(self.plan))
        self.assertEqual(original_csd, make_csd(self.plan, expand(self.plan)))

    def test_variants_change_only_synthesis_controls(self):
        events = expand(self.plan)['events']
        for voice in PRESETS:
            for name in variants(voice):
                with self.subTest(voice=voice, variant=name):
                    data = copy.deepcopy(self.plan)
                    track = next(t for t in data['tracks'] if t['voice'] == voice)
                    track['variant'] = name
                    expanded = expand(data)
                    self.assertEqual(expanded['events'], events)
                    self.assertEqual(expanded['track_variants'][track['id']], name)
                    csd = make_csd(data, expanded)
                    lines = [l.split() for l in csd.splitlines() if l.startswith('i ') and int(float(l.split()[1])) < 9]
                    self.assertTrue(all(len(line) == 28 for line in lines))
                    self.assertIn(parameters(track)[0], (0, 1))

    def test_reject_wrong_voice_unknown_and_raw_controls(self):
        for field, value in [('variant', 'invented'), ('variant', 'metallic'), ('pitch_decay', .03), ('variant', 2)]:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.plan)
                data['tracks'][0][field] = value
                with self.assertRaises(InvalidTrack):
                    expand(data)
        data = load_track(ROOT/'examples/example.track.json')
        next(t for t in data['tracks'] if t['voice'] == 'bass')['variant'] = 'subby'
        with self.assertRaisesRegex(InvalidTrack, 'For bass, choose: classic'):
            expand(data)

    def test_preset_tables_are_bounded(self):
        limits = {'decay_ratio': (.3, 1), 'amp_curve': (-8, -1), 'pitch_ratio': (1, 6),
                  'pitch_decay_s': (.005, .08), 'click_gain': (0, 2), 'drive_scale': (.5, 1.5),
                  'highpass_hz': (2000, 9000), 'lowpass_hz': (6000, 18000), 'metal_mix': (0, .8),
                  'clap_center_hz': (800, 4000), 'clap_spread_s': (.005, .045), 'output_gain_db': (-12, 12)}
        for voice, family in PRESETS.items():
            self.assertTrue(3 <= len(family) <= 5)
            for name, settings in family.items():
                self.assertLessEqual(set(settings), set(FIELDS))
                values = {**BASE, **settings}
                for key, (lo, hi) in limits.items():
                    self.assertTrue(math.isfinite(values[key]) and lo <= values[key] <= hi, (voice, name, key))

    def test_stem_index_does_not_shift_preset_controls(self):
        for track in self.plan['tracks']:
            track['variant'] = next(iter(PRESETS[track['voice']]))
        events = expand(self.plan)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'test.csd'
            direct = make_csd(self.plan, events)
            routed, directory = prepare(direct, self.plan, events, path)
            before = [l.split() for l in direct.splitlines() if l.startswith('i ') and int(float(l.split()[1])) < 9]
            after = [l.split() for l in routed.splitlines() if l.startswith('i ') and int(float(l.split()[1])) < 9]
            mapping = {t['id']: i for i, t in enumerate(self.plan['tracks'])}
            for a, b, event in zip(before, after, events['events']):
                self.assertEqual(a[:14], b[:14])
                self.assertEqual(a[15:], b[15:])
                self.assertEqual(int(b[14]), mapping[event['track']])
            manifest = json.loads((directory/'stems.json').read_text())
            self.assertEqual(manifest['track_variants'], events['track_variants'])
