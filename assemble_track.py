#!/usr/bin/env python3
"""Assemble staged Gemini responses; validate the complete result before saving."""
import argparse
import json
from pathlib import Path
from compile_track import InvalidTrack, atomic_text, check_destinations, expand, load_track
from contract import SCHEMA


def assemble(parts):
    result = {}
    for part in parts:
        if not isinstance(part, dict):
            raise InvalidTrack("Each stage must return a JSON object.")
        for key, value in part.items():
            if key not in SCHEMA["properties"]:
                raise InvalidTrack(f"Unknown stage field {key!r}.")
            if key in ("tracks", "patterns", "clips"):
                if not isinstance(value, list):
                    raise InvalidTrack(f"{key} must be an array.")
                result.setdefault(key, []).extend(value)
            elif key in result:
                raise InvalidTrack(f"Duplicate stage field {key!r}; provide metadata once.")
            else:
                result[key] = value
    expand(result)  # Includes ranges, references, unique IDs and scheduling checks.
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--part", type=Path, action="append", required=True)
    args = parser.parse_args()
    try:
        check_destinations(args.part, [args.output])
        result = assemble([load_track(path) for path in args.part])
        atomic_text(args.output, json.dumps(result, indent=2, allow_nan=False) + "\n")
    except (InvalidTrack, OSError) as exc:
        parser.exit(2, f"assemble_track.py: error: {exc}\n")
    print("Validated and wrote", args.output)


if __name__ == "__main__":
    main()
