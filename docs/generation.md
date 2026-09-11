# Structured generation and repair

## If Gemini says “Constraint is too tall”

This is a server-side schema-decoding complexity failure before a plan is produced.
The `58881 vs 58880` message reports the point at which a threshold was exceeded; it
does **not** establish that the complete grammar is only one unit too large. JSON
file byte size, whitespace, requested track duration, and output-token budget are
not measurements of that internal grammar.

The supplied Gemini profile retains only explicit types, properties, required lists,
array items, and small string enums. Numeric and array-size limits stay in the
generated system instructions and local validator. This is a conservative profile
for the AI Studio errors encountered here: Google's current JSON Schema API supports
more features, but support depends on the surface/API/model. Google documents schema
complexity limits and recommends simplifying deeply nested or large schemas; it also
requires application-level validation of semantic values.
See [Google's structured-output documentation](https://ai.google.dev/gemini-api/docs/structured-output).

If replacing the complete schema still fails, use the smaller stage schemas. Keep
the same system instructions and artistic brief; change the response schema per pass:

| Pass | Response schema | User instruction |
|---|---|---|
| 1 | `../schemas/gemini-stages/structure.schema.json` | Plan metadata, tonality, effects, master, and contiguous sections. |
| 2 | `../schemas/gemini-stages/tracks.schema.json` | Given the structure, define the palette and mix; return only tracks. |
| 3 | `../schemas/gemini-stages/patterns.schema.json` | Given structure and tracks, define reusable note patterns; return only patterns. |
| 4 | `../schemas/gemini-stages/clips.schema.json` | Given all previous parts, schedule pattern IDs on track IDs; return only clips. |

Supply the previously generated parts as context in each subsequent pass. If a long
pattern or clip response is truncated, request smaller batches with disjoint IDs or
time ranges and save each complete JSON object separately. The assembler supports
multiple pattern/clip part files; it detects duplicate IDs, overlaps and bad references.

```bash
python3 assemble_track.py generated-track.json \
  --part structure.json --part tracks.json --part patterns.json --part clips.json
python3 compile_track.py generated-track.json generated-track.csd
```

Assembly validates the complete result before saving. It does not invent defaults,
repair notes, clamp sends, or rewrite arrangement decisions. Local tests verify the
stage schemas and exact assembly round-trip. Acceptance by Google's live decoder
has not been tested in this session and cannot be guaranteed by a local schema check.


Commands shown here run from the repository root; schema paths in the table are relative to this document.
