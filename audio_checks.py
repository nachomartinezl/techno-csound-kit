"""Shared subprocess execution and final stereo audio verification."""
import json
import math
import re
import subprocess


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"Command failed: {command}\n{result.stdout}\n{result.stderr}")
    return result.stdout + result.stderr


def inspect_audio(wav, expected_seconds):
    metadata = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(wav)]))["streams"][0]
    log = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af",
               "ebur128=peak=true,astats=metadata=0:reset=0", "-f", "null", "-"])
    def metric(pattern):
        matches = re.findall(pattern, log)
        if not matches:
            raise RuntimeError(f"Missing audio metric: {pattern}")
        value = float(matches[-1])
        if not math.isfinite(value):
            raise RuntimeError(f"Nonfinite metric: {pattern}")
        return value
    values = {"duration_seconds": float(metadata["duration"]), "sample_rate": int(metadata["sample_rate"]),
              "channels": metadata["channels"], "codec": metadata["codec_name"],
              "sample_peak_dbfs": metric(r"Peak level dB:\s+(\S+)"),
              "rms_dbfs": metric(r"RMS level dB:\s+(\S+)"),
              "nan_samples": metric(r"Number of NaNs:\s+(\S+)"),
              "infinite_samples": metric(r"Number of Infs:\s+(\S+)"),
              "integrated_lufs": metric(r"Integrated loudness:\s+I:\s+(\S+)"),
              "true_peak_dbtp": metric(r"True peak:\s+Peak:\s+(\S+)")}
    assert abs(values["duration_seconds"] - expected_seconds) < .002, values
    assert values["sample_rate"] == 48000 and values["channels"] == 2, values
    assert values["nan_samples"] == values["infinite_samples"] == 0, values
    assert values["sample_peak_dbfs"] < 0 and values["true_peak_dbtp"] < 0, values
    assert values["rms_dbfs"] > -80, values
    values["full_scale_samples"] = 0  # Established by the measured maximum below 0 dBFS.
    return values
