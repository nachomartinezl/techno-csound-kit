#!/usr/bin/env python3
"""Generate Gemini/OpenAPI/prompt artifacts from the authoritative local contract."""
import argparse
import hashlib
import json
from contract import (CONTRACT_REVISION, ROOT, SCHEMA, audit_gemini,
                      gemini_schema, openapi_document, range_guide)

STAGES = {
    "structure": [key for key in SCHEMA["properties"] if key not in ("tracks", "patterns", "clips")],
    "tracks": ["tracks"], "patterns": ["patterns"], "clips": ["clips"],
}


def generated_files():
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    pretty = lambda value: json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    schema = gemini_schema()
    files = {"schemas/gemini-response-schema.json": compact(schema),
             "schemas/track.openapi.json": pretty(openapi_document())}
    metrics = {"full": audit_gemini(schema)}
    for name, keys in STAGES.items():
        stage = {"type": "object", "properties": {key: schema["properties"][key] for key in keys}, "required": keys}
        files[f"schemas/gemini-stages/{name}.schema.json"] = compact(stage)
        metrics[name] = audit_gemini(stage)
    prompt = (ROOT / "prompts/SYSTEM_PROMPT_SOURCE.txt").read_text().replace("{FIELD_LIMITS}", range_guide())
    files["prompts/SYSTEM_PROMPT.txt"] = prompt
    manifest = {"contract_revision": CONTRACT_REVISION,
                "source_sha256": hashlib.sha256((ROOT / "schemas/track.schema.json").read_bytes()).hexdigest(),
                "schemas": metrics,
                "note": "Node/depth statistics are local regression metrics, NOT Google's undocumented decoder budget.",
                "generated_sha256": {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()}}
    files["schemas/contract-manifest.json"] = pretty(manifest)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if any generated artifact is stale")
    args = parser.parse_args()
    stale = []
    for name, text in generated_files().items():
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        parser.exit(1, "Stale contract artifacts: " + ", ".join(stale) + ". Run python3 build_contracts.py.\n")
    print("Contract artifacts match authoritative source." if args.check else "Generated contracts, system instructions, and staged Gemini schemas.")


if __name__ == "__main__":
    main()
