# Mixing and mastering

## Stem routing

All stems start at zero, use stereo 48 kHz / 32-bit float WAV, and share the same
length including the effects tail. `stems.json` maps numbered filenames to track
IDs. Multiple tracks using the same voice still have separate stems.

Track stems include synthesis, filters, panning, level automation, and kick ducking.
They exclude the master bus and shared ambience. Room and delay are separate wet
returns, already return-gained and ducked. Import all stems at zero into a DAW.
Csound's [`fout`](https://csound.com/docs/manual/fout.html) writes the float files.

Rebalancing a dry stem does not alter its contribution to the recorded wet returns.
Change sends in the source plan and recompile to change that relationship. The
same applies to baked ducking. These are mix-ready stems, not raw oscillators.

The remix sums stems through the same low-frequency stereo control, shared
compression, gentle saturation, and final fade as the direct render. At zero
additional gain, tests require recombination to match within floating-point tolerance.

## Recipe

`mix.json` is preserved across recompilation. Its track IDs must exactly match
`stems.json`; missing or extra IDs produce an error.

| Setting | Default | Allowed | Meaning |
| --- | ---: | ---: | --- |
| Each `stem_gains_db` value | 0 | −60 to +18 | Additional stem gain |
| `target_lufs` | −11 | −24 to −9 | Requested integrated loudness |
| `true_peak_dbtp` | −1.3 | −6 to −1 | Delivered true-peak ceiling |
| `limiter_release_ms` | 70 | 10 to 300 | Limiter release |
| `limiter_drive_db` | 4 | 0 to 6 | Extra drive above estimated target gain |

Lower limiter drive for gentler transient reduction. Raising it can reduce punch;
use listening and the report to decide.

## Mastering sequence

1. Measure the rebuilt premix.
2. Apply fixed gain based on measured loudness and recipe drive.
3. Upsample to 192 kHz and apply stereo peak limiting with 3 ms lookahead and
   configured release. Compensate for lookahead and return to 48 kHz.
4. Measure again and apply constant gain that respects the peak ceiling.
5. Export with 24-bit triangular dither and check the delivered file.

This follows the earlier warehouse remix's fixed-gain approach. There is no dynamic
loudness normalization lifting quiet breaks. If loudness and peak targets cannot
both be met, peak safety wins; `target_reached` reports the result. The report also
records actual duration, loudness, peaks, nonfinite sample counts, recipe, source
hashes, and tool versions.

Only a master passing final checks replaces `master.wav`. A failed remix removes
the prior success report; an older master can still exist. Failed rendering can
leave partial premixes or stems, so rerun successfully before using those files.

## Reproducibility

Preserve the plan, recipe, CSD, stems, and report. The CSD contains the engine and
score snapshot. Keep the same Python, Csound, and FFmpeg versions when comparing
renders; bit-identical audio across versions or platforms is not guaranteed.

Changing `csound -o` redirects only the premix. Stem paths remain embedded in the
CSD. Recompile into another project directory for a complete alternate render.
