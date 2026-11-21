"""What the removed local AI feature (0.9 to 0.10) may have left on this PC, and deleting it on request.

The feature stored speech models in ``%LOCALAPPDATA%\\Babarify\\Frame\\models`` and generated subtitles in
``%APPDATA%\\Babarify\\Frame\\subtitles``, indexed in the library database. Both folders belong to Babarify
alone. Nothing is deleted unless the person asks; media files and their own subtitles are never touched.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path

from babarify_frame.library.database import LibraryDatabase


def models_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Babarify" / "Frame" / "models"


def generated_dir() -> Path:
    base = os.environ.get("BABARIFY_CONFIG_DIR") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Babarify" / "Frame" / "subtitles"


def _folder_size(folder: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            with contextlib.suppress(OSError):
                total += os.path.getsize(os.path.join(root, name))
    return total


def leftover_bytes(db: LibraryDatabase) -> int:
    """Disk space the old feature still uses; 0 when nothing is left (the database index counts as 1 byte)."""
    size = _folder_size(models_dir()) + _folder_size(generated_dir())
    if size == 0 and db.transcripts():
        return 1
    return size


def delete_leftovers(db: LibraryDatabase) -> None:
    for transcript in db.delete_all_transcripts():
        srt = Path(transcript.srt_path)
        if srt.suffix.lower() == ".srt" and generated_dir() in srt.parents:
            srt.unlink(missing_ok=True)
    for folder in (models_dir(), generated_dir()):
        shutil.rmtree(folder, ignore_errors=True)
