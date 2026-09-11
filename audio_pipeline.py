"""Aligned track stems, editable balance, shared glue, and measured fixed-gain mastering."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
from audio_checks import run, inspect_audio
from presets import COMPILER_VERSION, PRESET_VERSION


def quoted(path):
    value = str(Path(path).resolve())
    if any(c in value for c in ('"', '\\', '\n', '\r', '<', '>')):
        raise ValueError('Unsupported character in audio path')
    return '"' + value + '"'


def prepare(csd, data, expanded, output):
    for hook in ('giSine ftgen', ' gaL = gaL+aL', '\nendin\n\n; Shared stereo glue', 'instr 99\n'):
        if csd.count(hook) != 1:
            raise ValueError(f'Engine routing changed; cannot safely insert stems: {hook}')
    directory = output.resolve().with_suffix('.audio')
    directory.mkdir(exist_ok=True)
    stems = directory / 'stems'
    stems.mkdir(exist_ok=True)
    tracks = {t['id']: i for i, t in enumerate(data['tracks'])}
    entries = [{'id': t['id'], 'voice': t['voice'], 'file': f'stems/{i+1:02d}-{t["voice"]}.wav', 'gain_db': 0}
               for i, t in enumerate(data['tracks'])]
    entries += [{'id': '__room', 'file': 'stems/room.wav', 'gain_db': 0},
                {'id': '__delay', 'file': 'stems/delay.wav', 'gain_db': 0}]
    globals_text = '\n'.join(f'gaStem{i}L init 0\ngaStem{i}R init 0' for i in range(len(tracks)))
    csd = csd.replace('giSine ftgen', globals_text+'\ngiSine ftgen')
    routing = '\n'.join(f' if p14 == {i} then\n gaStem{i}L = gaStem{i}L+aL\n gaStem{i}R = gaStem{i}R+aR\n endif' for i in range(len(tracks)))
    csd = csd.replace(' gaL = gaL+aL', routing+'\n gaL = gaL+aL', 1)
    # Capture the exact post-return-gain, post-duck wet contributions before summing.
    wet_lines = 0
    for line in csd.splitlines():
        if line.startswith(' gaL = gaL+((aWetL') or line.startswith(' gaR = gaR+((aWetR'):
            wet_lines += 1
            side = 'L' if 'gaL =' in line else 'R'
            expression = line.split(' = ', 1)[1].split('+', 1)[1]
            # Split the room and echo at their explicit sum in the fixed engine.
            room, echo = expression[1:].rsplit(')*aDuck', 1)[0].split('+(aE1', 1)
            replacement = f' aRoom{side} = {room}*aDuck\n aDelay{side} = (aE1{echo}*aDuck\n ga{side} = ga{side}+aRoom{side}+aDelay{side}'
            csd = csd.replace(line, replacement)
    if wet_lines != 2:
        raise ValueError('Engine wet routing changed; cannot safely extract returns')
    wet = '\n'.join(f' fout {quoted(directory / e["file"])}, 16, a{kind}L, a{kind}R' for e, kind in zip(entries[-2:], ('Room', 'Delay')))
    csd = csd.replace('\nendin\n\n; Shared stereo glue', '\n'+wet+'\nendin\n\n; Shared stereo glue')
    writes = '\n'.join(f' fout {quoted(directory / e["file"])}, 16, gaStem{i}L, gaStem{i}R\n clear gaStem{i}L,gaStem{i}R' for i, e in enumerate(entries[:-2]))
    csd = csd.replace('instr 99\n', 'instr 99\n'+writes+'\n')
    before, rest = csd.split('<CsScore>')
    score, after = rest.split('</CsScore>')
    lines = score.splitlines()
    event_iter = iter(expanded['events'])
    for i, line in enumerate(lines):
        if line.startswith('i ') and int(float(line.split()[1])) in range(1, 9):
            fields = line.split()
            fields[14] = str(tracks[next(event_iter)['track']])
            lines[i] = ' '.join(fields)
    csd = before+'<CsScore>'+'\n'.join(lines)+'\n</CsScore>'+after
    manifest = {'version': 1, 'compiler_version': COMPILER_VERSION, 'preset_version': PRESET_VERSION,
                'track_variants': {t['id']: t.get('variant', 'classic') for t in data['tracks']},
                'csd': str(output.resolve()), 'duration_seconds': expanded['render_seconds'], 'stems': entries}
    (directory/'stems.json').write_text(json.dumps(manifest, indent=2)+'\n')
    recipe = directory/'mix.json'
    if not recipe.exists():
        recipe.write_text(json.dumps({'stem_gains_db': {e['id']: 0 for e in entries}, 'target_lufs': -11,
                                     'true_peak_dbtp': -1.3, 'limiter_release_ms': 70,
                                     'limiter_drive_db': 4}, indent=2)+'\n')
    return csd, directory


def loudness(path):
    log = run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(path), '-af',
               'loudnorm=I=-11:TP=-1.3:LRA=20:print_format=json', '-f', 'null', '-'])
    m = json.loads(re.findall(r'\{\s*"input_i".*?\}', log, re.S)[-1])
    result = {k: float(m[k]) for k in ('input_i', 'input_tp', 'input_lra')}
    if not all(math.isfinite(v) for v in result.values()):
        raise ValueError('Silent or nonfinite mix cannot be mastered')
    return result


def mix(directory):
    directory = directory.resolve()
    manifest = json.loads((directory/'stems.json').read_text())
    recipe = json.loads((directory/'mix.json').read_text())
    # A previous success report must never describe a failed new run.
    (directory/'mastering.json').unlink(missing_ok=True)
    gains = recipe['stem_gains_db']
    if set(gains) != {e['id'] for e in manifest['stems']}:
        raise ValueError('mix.json stem IDs differ from stems.json; update the recipe explicitly')
    def bounded(value, lo, hi):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f'Invalid recipe value {value}: expected {lo}..{hi}')
        return value
    for value in gains.values():
        bounded(value, -60, 18)
    target = bounded(recipe['target_lufs'], -24, -9)
    ceiling = bounded(recipe['true_peak_dbtp'], -6, -1)
    release = bounded(recipe['limiter_release_ms'], 10, 300)
    push = bounded(recipe.get('limiter_drive_db', 4), 0, 6)
    recipe['limiter_drive_db'] = push
    # Sum pre-master stems into the same glue bus as the synthesis engine.
    source = Path(manifest['csd']).read_text()
    orchestra = source.split('<CsInstruments>')[1].split('</CsInstruments>')[0]
    # Stem writers must not run during remixing.
    orchestra = '\n'.join(line for line in orchestra.splitlines() if not line.lstrip().startswith('fout '))
    inputs = []
    for i, entry in enumerate(manifest['stems']):
        path = directory/entry['file']
        info = json.loads(run(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))['streams'][0]
        if int(info['sample_rate']) != 48000 or info['channels'] != 2 or abs(float(info['duration'])-manifest['duration_seconds']) > .002:
            raise ValueError(f'Stem is not aligned stereo 48 kHz: {path}')
        inputs += [f'aL{i},aR{i} diskin2 {quoted(path)},1,0,0',
                   f'gaL = gaL+aL{i}*{10**(gains[entry["id"]]/20):.12g}',
                   f'gaR = gaR+aR{i}*{10**(gains[entry["id"]]/20):.12g}']
    premix = directory/'mix.wav'
    mix_csd = '<CsoundSynthesizer>\n<CsOptions>\n-d -m0 -W -f -o '+quoted(premix)+'\n</CsOptions>\n<CsInstruments>\n'+orchestra+'\ninstr 89\n'+'\n'.join(inputs)+'\nendin\n</CsInstruments>\n<CsScore>\ni 89 0 '+str(manifest['duration_seconds'])+'\ni 99 0 '+str(manifest['duration_seconds'])+'\ne\n</CsScore>\n</CsoundSynthesizer>\n'
    (directory/'mix.csd').write_text(mix_csd)
    print('Summing stems through shared glue…', flush=True)
    run(['csound', str(directory/'mix.csd')])
    measured = loudness(premix)
    # A constant input gain, never a moving loudness envelope. Modest extra drive
    # allows transient limiting; final gain is constrained by measured true peak.
    drive = target-measured['input_i']+push
    with tempfile.TemporaryDirectory(prefix='techno-master-') as tmp:
        limited = Path(tmp)/'limited.wav'
        filters = (f'volume={drive}dB,aresample=192000:resampler=soxr:precision=28,'
                   f'apad=pad_dur=0.003,alimiter=limit={10**((ceiling-.3)/20)}:attack=3:release={release}:level=false,'
                   'atrim=start=0.003,asetpts=PTS-STARTPTS,aresample=48000:resampler=soxr:precision=28')
        print('Mastering with fixed gain and oversampled peak limiting…', flush=True)
        run(['ffmpeg','-y','-v','error','-i',str(premix),'-af',filters,'-c:a','pcm_f32le',str(limited)])
        post = loudness(limited)
        gain = min(target-post['input_i'], ceiling-.1-post['input_tp'])
        master = directory/'master.pending.wav'
        run(['ffmpeg','-y','-v','error','-i',str(limited),'-af',f'volume={gain}dB,aresample=48000:resampler=soxr:osf=s32:output_sample_bits=24:dither_method=triangular','-c:a','pcm_s24le',str(master)])
    final = inspect_audio(master, manifest['duration_seconds'])
    if final['true_peak_dbtp'] > ceiling+.1:
        raise ValueError('Delivered master exceeds requested true-peak ceiling')
    master.replace(directory/'master.wav')
    master = directory/'master.wav'
    report = {'recipe': recipe, 'premix': measured, 'limiter_input_gain_db': drive,
              'synthesis': {key: manifest.get(key, 'legacy/unrecorded') for key in ('compiler_version', 'preset_version', 'track_variants')},
              'post_limiter': post, 'final_gain_db': gain, 'final': final,
              'target_reached': abs(final['integrated_lufs']-target) <= .3,
              'note': 'Peak safety takes priority over loudness. No dynamic loudness normalization.',
              'source_sha256': {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in [directory/'mix.json',directory/'stems.json',directory/'mix.csd']+[directory/e['file'] for e in manifest['stems']]},
              'tools': {t: run([t,'--version'] if t == 'csound' else [t,'-version']).splitlines()[0] for t in ('csound','ffmpeg')}}
    (directory/'mastering.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'Wrote {master}: {final["integrated_lufs"]} LUFS, {final["true_peak_dbtp"]} dBTP',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='Track .audio directory containing stems.json and mix.json')
    args = parser.parse_args()
    mix(args.directory)
