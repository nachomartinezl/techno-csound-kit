import array
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_pipeline import prepare, mix, run
from compile_track import load_track, expand, make_csd


@unittest.skipUnless(all(shutil.which(t) for t in ('csound', 'ffmpeg', 'ffprobe')), 'audio tools unavailable')
class AudioPipelineTests(unittest.TestCase):
    def test_stems_recombine_and_master_safely(self):
        data = load_track(ROOT/'examples/example.track.json')
        events = expand(data)
        events['events'] = [e for e in events['events'] if e['pfields'][1] < 8]
        events['render_seconds'] = 12
        with tempfile.TemporaryDirectory(prefix='stem regression ') as tmp:
            root = Path(tmp)
            csd_path = root/'track.csd'
            csd, directory = prepare(make_csd(data, events, root/'track.wav'), data, events, csd_path)
            csd_path.write_text(csd)
            run(['csound', str(csd_path)])
            manifest = json.loads((directory/'stems.json').read_text())
            self.assertEqual(len(manifest['stems']), len(data['tracks'])+2)
            recipe = directory/'mix.json'
            original = recipe.read_bytes()
            prepare(make_csd(data, events, root/'track.wav'), data, events, csd_path)
            self.assertEqual(recipe.read_bytes(), original)
            mix(directory)
            def samples(path):
                values = array.array('f')
                values.frombytes(subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-f','f32le','-']))
                return values
            direct, rebuilt = samples(root/'track.wav'), samples(directory/'mix.wav')
            self.assertEqual(len(direct), len(rebuilt))
            self.assertLess(max(abs(a-b) for a,b in zip(direct,rebuilt)), 1e-6)
            report = json.loads((directory/'mastering.json').read_text())
            self.assertLessEqual(report['final']['true_peak_dbtp'], -1.2)
            self.assertEqual(report['final']['nan_samples'], 0)
            # A broken recipe must fail before it can produce an approved master.
            settings = json.loads(original)
            settings['stem_gains_db']['missing'] = 0
            recipe.write_text(json.dumps(settings))
            with self.assertRaises(ValueError):
                mix(directory)
            self.assertFalse((directory/'mastering.json').exists())
