# Local projects

Use one folder per composition, containing its plan JSON, CSD, event export,
premix, and `.audio` directory. These folders are ignored by Git; back them up
separately to preserve your music.

The v1 cleanup moved `track_1` through `track_9` here and updated absolute paths
in generated text files. WAVs were preserved. Older review artifacts are outside
the repository in the parent `archive/techno-kit-pre-v1/` directory.

From the repository root:

```bash
python compile_track.py projects/track_9/track_9.json --check
python audio_pipeline.py projects/track_9/track_9.audio
```

Create a new folder for each new track. The root README explains the full workflow.
