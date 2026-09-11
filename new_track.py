#!/usr/bin/env python3
"""Import generated JSON into projects/<name>/ and run the track pipeline."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from compile_track import InvalidTrack, atomic_text, expand, load_track
from contract import ROOT


PROJECT_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def project_name(value):
    name = value.strip().lower().replace(" ", "_")
    if not PROJECT_NAME.fullmatch(name):
        raise InvalidTrack(
            "Project name must start with a lowercase letter and contain only "
            "lowercase letters, digits, underscores, or hyphens (maximum 64 characters)."
        )
    return name


def import_plan(source, name=None, projects_root=None, inbox_root=None):
    """Validate and normalize a generated .txt/.json plan into a new project."""
    source = source.resolve()
    projects_root = (projects_root or ROOT / "projects").resolve()
    inbox_root = (inbox_root or ROOT).resolve()
    name = project_name(name or source.stem)
    destination = projects_root / name
    plan = destination / f"{name}.json"
    if destination.exists():
        raise InvalidTrack(
            f"Project {name!r} already exists at {destination}. Choose another name; "
            "use compile_track.py to rebuild an existing project."
        )
    data = load_track(source)
    expand(data)
    destination.mkdir(parents=True)
    atomic_text(plan, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    # Root files act as inbox items. Consume only after the project copy is safe.
    consumed = source.parent == inbox_root and source != plan.resolve()
    if consumed:
        source.unlink()
    return destination, plan, consumed


def adopt_existing(name, kit_root=None):
    """Move outputs made by the old root workflow into a project without rendering."""
    kit_root = (kit_root or ROOT).resolve()
    name = project_name(name)
    destination = kit_root / "projects" / name
    if destination.exists():
        raise InvalidTrack(f"Project {name!r} already exists at {destination}.")
    plan = kit_root / f"{name}.json"
    data = load_track(plan)
    expand(data)
    candidates = [kit_root / f"{name}{suffix}" for suffix in
                  (".json", ".csd", ".events.json", ".validation.json", ".repair.txt", ".wav", ".audio")]
    present = [path for path in candidates if path.exists()]
    destination.mkdir(parents=True)
    for path in present:
        shutil.move(str(path), destination / path.name)

    old_prefix = str(kit_root / name)
    new_prefix = str(destination / name)
    for path in destination.rglob("*"):
        if path.is_file() and path.suffix in (".json", ".csd", ".txt"):
            text = path.read_text()
            updated = text.replace(old_prefix, new_prefix)
            if updated != text:
                atomic_text(path, updated)

    report = destination / f"{name}.audio" / "mastering.json"
    if report.exists():
        details = json.loads(report.read_text())
        for relative in details.get("source_sha256", {}):
            artifact = report.parent / relative
            if artifact.is_file() and artifact.suffix != ".wav":
                details["source_sha256"][relative] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        details["relocation_note"] = (
            "Paths and text-provenance hashes updated when the existing root output "
            "was adopted into projects; audio files were moved without rendering."
        )
        atomic_text(report, json.dumps(details, indent=2) + "\n")
    return destination, present


def main():
    parser = argparse.ArgumentParser(
        description="Create a self-contained project from generated JSON and render it."
    )
    parser.add_argument("source", nargs="?", type=Path,
                        help="generated JSON file; .txt is accepted because content is parsed as JSON")
    parser.add_argument("--name", help="project/output basename; defaults to the source filename")
    parser.add_argument("--compile-only", action="store_true", help="create CSD and stem configuration without rendering")
    parser.add_argument("--adopt-existing", metavar="NAME",
                        help="move an existing root NAME.json and its outputs into projects/NAME without rerendering")
    args = parser.parse_args()
    try:
        if args.adopt_existing:
            if args.source or args.name or args.compile_only:
                parser.error("--adopt-existing cannot be combined with source, --name, or --compile-only")
            destination, moved = adopt_existing(args.adopt_existing)
            print(f"Adopted {len(moved)} existing artifacts without rendering: {destination}")
            return
        if not args.source:
            parser.error("source is required unless --adopt-existing is used")
        destination, plan, consumed = import_plan(args.source, args.name)
    except (InvalidTrack, OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"new_track.py: error: {exc}\n")

    output = destination / f"{destination.name}.csd"
    command = [sys.executable, str(ROOT / "compile_track.py"), str(plan), str(output)]
    if args.compile_only:
        command.append("--compile-only")
    print(f"Created project: {destination}", flush=True)
    if consumed:
        print(f"Consumed root inbox file: {args.source}", flush=True)
    result = subprocess.run(command)
    if result.returncode:
        parser.exit(result.returncode,
                    f"Compilation failed; the validated plan remains at {plan}.\n")
    if not args.compile_only:
        print(f"Master: {destination / (destination.name + '.audio') / 'master.wav'}")


if __name__ == "__main__":
    main()
