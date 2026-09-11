# Track format and engine

## Timing, sound and portability

One bar is four beats / sixteen steps. Music seconds = `bars * 4 * 60 / bpm`.
Render seconds add `master.tail_seconds`: 105 bars at 140 BPM give 180 seconds of music;
`track_2` adds a 4.5-second tail for 184.5 seconds total.

Clips repeat their pattern and may end with a partial repetition. Notes are shortened
at the clip end. Ramps are evaluated at the nominal note onset, before swing, and
held for that note; their `to` value is at the clip boundary. They do not continuously
sweep an already sounding note. Track gain plus clip gain (or its ramp) sets level.
Role/section intent fields are descriptive and do not trigger additional synthesis.

Eight fixed voice IDs exist: 1 kick, 2 bass, 3 closed hat, 4 open hat, 5 clap,
6 percussion, 7 stab, 8 noise. An arp is a pattern of stab events; pads, sample loading,
independent resonance, portamento and additional synth types are not exposed in v1.
The engine maps external pan −1..+1 into Csound `pan2`'s 0..1 range. Kick/bass pan is
validated at 0. Room and finite echo returns share a stereo bus; per-note `follow2`
ducking reads the kick envelope. `compress2` uses a shared high-passed mid signal for
stereo glue. Final bounded saturation is not a true-peak limiter or loudness target.
The Python pipeline masters this premix separately. Successful validation does not establish
professional sound quality. See [Csound's CSD format](https://csound.com/manual/invoke/the-csd-file-format/),
[pan2](https://csound.com/docs/manual/pan2.html), and [compress2](https://csound.com/docs/manual/compress2.html).

`*.events.json` contains the portable event list. The `pfields` array is:

```text
[voice, onset_seconds, duration_seconds, amplitude, midi, pan, tone, drive,
 highpass_hz, lowpass_hz, room_send, delay_send, duck]
```

Probability uses LCG32, traversing clips in JSON order, then repetitions, then pattern
events in JSON order. Consume exactly one draw for each candidate even at probability
0 or 1; consume none for an event outside the final partial repetition.

```c
uint32_t next_u32(uint32_t *state) {
    *state = 1664525u * (*state) + 1013904223u;
    return *state;
}
double uniform01(uint32_t *state) { return next_u32(state) / 4294967296.0; }
```

Accept when `uniform01 < probability`. Sort expanded events by onset, voice,
clip index, repeat index, event index. Matching this produces identical score events
in C and Python; bit-identical synthesized audio across Csound versions/platforms is
not promised. Caps are 100,000 candidate events and 128 simultaneous source notes.


For field types and bounds, see [the authoritative schema](../schemas/track.schema.json).
The generated CSD adds an internal p14 stem index and p15–p27 preset controls;
the portable event array above remains unchanged. Optional `tracks[].variant`
selects a compiler-owned percussion preset. See [presets](presets.md) for the
vocabulary, defaults, versions, and compensation policy.
