#!/usr/bin/env python3
"""Run contract tests and, with --render, verify complete Csound renders using FFmpeg."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
from compile_track import atomic_text, expand, load_track, make_csd
from contract import CONTRACT_REVISION, ROOT
from audio_checks import run, inspect_audio



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/verification.json")
    args = parser.parse_args()
    results = {"contract_revision": CONTRACT_REVISION, "gemini_live_tested": False,
               "note": "Local schema checks cannot prove acceptance by Google's remote decoder.", "renders": {}}
    print(run([sys.executable, str(ROOT / "build_contracts.py"), "--check"]).strip(), flush=True)
    log = run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"])
    print(log, flush=True)
    results["regression_tests"] = "passed"
    if args.render:
        for command in ("csound", "ffmpeg", "ffprobe"):
            if not shutil.which(command):
                parser.error(f"{command} is required for --render")
        with tempfile.TemporaryDirectory(prefix="techno-kit-verify-") as directory:
            tmp = Path(directory)
            for name in ("example.track.json", "track_1.json", "track_2.json"):
                print("Rendering", name, flush=True)
                data = load_track(ROOT / ("examples" if name == "example.track.json" else "tests/fixtures") / name)
                events = expand(data)
                csd, wav = tmp / "test.csd", tmp / "test.wav"
                csd.write_text(make_csd(data, events))
                run(["csound", "--syntax-check-only", str(csd)])
                rendered = run(["csound", "-W", "-f", "-o", str(wav), str(csd)])
                if "0 errors in performance" not in rendered:
                    raise RuntimeError(rendered)
                audio = inspect_audio(wav, events["render_seconds"])
                results["renders"][name] = {"event_count": len(events["events"]),
                                           "peak_polyphony": events["peak_polyphony"], **audio}
                print(json.dumps(results["renders"][name]), flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(args.report, json.dumps(results, indent=2) + "\n")
    print("Wrote", args.report)


if __name__ == "__main__":
    main()
