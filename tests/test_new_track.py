import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from compile_track import InvalidTrack
from new_track import adopt_existing, import_plan, project_name


class NewTrackTests(unittest.TestCase):
    def test_import_accepts_txt_normalizes_and_consumes_inbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            source = kit / "track_11.txt"
            shutil.copy2(ROOT / "examples/example.track.json", source)
            destination, plan, consumed = import_plan(
                source, projects_root=kit / "projects", inbox_root=kit
            )
            self.assertEqual(destination, kit / "projects/track_11")
            self.assertTrue(consumed)
            self.assertFalse(source.exists())
            self.assertEqual(json.loads(plan.read_text()),
                             json.loads((ROOT / "examples/example.track.json").read_text()))

    def test_external_input_is_preserved_and_existing_project_refused(self):
        with tempfile.TemporaryDirectory() as source_tmp, tempfile.TemporaryDirectory() as projects_tmp:
            source = Path(source_tmp) / "idea.txt"
            shutil.copy2(ROOT / "examples/example.track.json", source)
            destination, _, consumed = import_plan(source, "my_track", Path(projects_tmp))
            self.assertFalse(consumed)
            self.assertTrue(source.exists())
            with self.assertRaisesRegex(InvalidTrack, "already exists"):
                import_plan(source, "my_track", Path(projects_tmp))
            self.assertTrue(destination.exists())

    def test_invalid_input_creates_nothing_and_bad_names_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bad.txt"
            source.write_text("not json")
            with self.assertRaises(InvalidTrack):
                import_plan(source, projects_root=root / "projects", inbox_root=root)
            self.assertTrue(source.exists())
            self.assertFalse((root / "projects/bad").exists())
            for name in ("../escape", "Track!", "_track", "a" * 65):
                with self.subTest(name=name), self.assertRaises(InvalidTrack):
                    project_name(name)

    def test_adopt_moves_complete_output_and_updates_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            kit = Path(tmp)
            (kit / "projects").mkdir()
            shutil.copy2(ROOT / "examples/example.track.json", kit / "track_10.json")
            old = str(kit / "track_10")
            (kit / "track_10.csd").write_text(f'output "{old}.wav"\n')
            audio = kit / "track_10.audio"
            audio.mkdir()
            (audio / "stems.json").write_text(json.dumps({"csd": old + ".csd"}))
            destination, moved = adopt_existing("track_10", kit)
            self.assertEqual(len(moved), 3)
            self.assertFalse((kit / "track_10.json").exists())
            self.assertIn(str(destination / "track_10.wav"),
                          (destination / "track_10.csd").read_text())
            self.assertIn(str(destination / "track_10.csd"),
                          (destination / "track_10.audio/stems.json").read_text())
