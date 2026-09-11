#!/usr/bin/env python3
"""Render a fixed groove, changing one voice variant at a time; compare and measure."""
import argparse
import array
import copy
import hashlib
import html
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from audio_checks import inspect_audio, run
from audio_pipeline import prepare
from compile_track import expand, load_track, make_csd
from contract import ROOT
from presets import COMPILER_VERSION, PRESET_VERSION, PRESETS, variants


def samples(path):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'f32le', '-'])
    values = array.array('f')
    values.frombytes(raw)
    return values, hashlib.sha256(raw).hexdigest()


def compare(left, right):
    if len(left) != len(right):
        raise ValueError('Variant changed rendered duration')
    dot = sum(a*b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a*a for a in left)*sum(b*b for b in right))
    return dot/denominator if denominator else 0


def evaluate(output, voices=None, enforce=True):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = load_track(ROOT/'examples/timbral-comparison.track.json')
    base_events = expand(plan)
    results = {'compiler_version': COMPILER_VERSION, 'preset_version': PRESET_VERSION,
               'presets_sha256': hashlib.sha256((ROOT/'presets.py').read_bytes()).hexdigest(),
               'engine_sha256': hashlib.sha256((ROOT/'engine.orc').read_bytes()).hexdigest(),
               'composition_sha256': hashlib.sha256((ROOT/'examples/timbral-comparison.track.json').read_bytes()).hexdigest(),
               'thresholds': {'stem_lufs_delta': 2, 'stem_rms_delta_db': 3, 'mix_lufs_delta': 1.5, 'max_pair_correlation': .98},
               'note': 'Measured distinction is not a substitute for listening; no monitored listening claim.',
               'variants': {}, 'failures': []}
    with tempfile.TemporaryDirectory(prefix='preset-comparison-') as tmp:
        tmp = Path(tmp)
        for voice in voices or PRESETS:
            family = {}
            for name in variants(voice):
                label = f'{voice}-{name}'
                print('Comparing', label, flush=True)
                d = copy.deepcopy(plan)
                track = next(t for t in d['tracks'] if t['voice'] == voice)
                track['variant'] = name
                events = expand(d)
                if events['events'] != base_events['events']:
                    raise ValueError('Variant changed note events')
                csd_path, wav = tmp/'track.csd', tmp/'track.wav'
                csd, directory = prepare(make_csd(d, events, wav), d, events, csd_path)
                csd_path.write_text(csd)
                run(['csound', str(csd_path)])
                manifest = json.loads((directory/'stems.json').read_text())
                stem = directory/next(e['file'] for e in manifest['stems'] if e['id'] == track['id'])
                stem_values, stem_hash = samples(stem)
                _, mix_hash = samples(wav)
                record = {'stem': inspect_audio(stem, events['render_seconds']),
                          'mix': inspect_audio(wav, events['render_seconds']),
                          'render_hash': mix_hash, 'stem_hash': stem_hash}
                # Identical CSD/seed/tool run twice, including all wet and dry stems.
                # fout WAV headers can carry wall-clock PEAK-chunk timestamps.
                # Reproducibility is defined over decoded samples, not container bytes.
                first_hashes = {e['file']: samples(directory/e['file'])[1] for e in manifest['stems']}
                run(['csound', str(csd_path)])
                record['deterministic'] = samples(wav)[1] == mix_hash and all(
                    samples(directory/file)[1] == digest for file, digest in first_hashes.items())
                if not record['deterministic']:
                    results['failures'].append(label+': nondeterministic render')
                shutil.copy2(wav, output/(label+'.wav'))
                shutil.copy2(stem, output/(label+'-stem.wav'))
                family[name] = stem_values
                results['variants'][label] = record
            reference = results['variants'][f'{voice}-classic']
            for name in variants(voice):
                label = f'{voice}-{name}'
                record = results['variants'][label]
                for bus, key, limit in [('stem','integrated_lufs',2), ('stem','rms_dbfs',3), ('mix','integrated_lufs',1.5)]:
                    delta = record[bus][key]-reference[bus][key]
                    record[f'{bus}_{key}_delta'] = delta
                    if abs(delta) > limit:
                        results['failures'].append(f'{label}: {bus} {key} delta {delta:.2f} exceeds {limit}')
                record['pair_correlations'] = {other: compare(family[name], values) for other, values in family.items() if other != name}
                if any(abs(c) > .98 for c in record['pair_correlations'].values()):
                    results['failures'].append(label+': insufficient waveform distinction')
    (output/'metrics.json').write_text(json.dumps(results, indent=2)+'\n')
    rows = []
    for label, record in results['variants'].items():
        rows.append(f'<tr><th>{html.escape(label)}</th><td><audio controls preload="none" src="{label}.wav"></audio></td>'
                    f'<td><audio controls preload="none" src="{label}-stem.wav"></audio></td>'
                    f'<td>{record["stem"]["integrated_lufs"]:.1f}</td><td>{record["mix"]["integrated_lufs"]:.1f}</td></tr>')
    (output/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Controlled timbre comparisons</title>'
        '<style>body{font:16px sans-serif;margin:2rem;background:#16181c;color:#eee}td,th{padding:.6rem;text-align:left}audio{width:250px}</style>'
        '<h1>Controlled timbre comparisons</h1><p>Same groove and seed. One track variant changes per render. '
        'Compare both the complete premix and the isolated stem; levels include fixed preset compensation. '
        'These are unmastered comparisons. Stop playback before starting another row.</p>'
        '<table><tr><th>Variant</th><th>Full mix</th><th>Isolated stem</th><th>Stem LUFS</th><th>Mix LUFS</th></tr>'
        +''.join(rows)+'</table>')
    if enforce and results['failures']:
        raise RuntimeError('\n'.join(results['failures']))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reports/preset-comparisons')
    parser.add_argument('--voice', choices=list(PRESETS), action='append')
    parser.add_argument('--measure-only', action='store_true', help='collect measurements during preset calibration without enforcing level/distinction thresholds')
    args = parser.parse_args()
    evaluate(args.output, args.voice, not args.measure_only)
    print('Wrote comparisons and metrics:', args.output)
