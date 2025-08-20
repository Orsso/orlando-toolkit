from __future__ import annotations

"""Session-scoped temporary storage manager.

Provides a single on-disk workspace for the current app session to store
preview artifacts and edited images. Ensures easy cleanup at the end of the
session to avoid orphaned temp files.

Public API:
- get_session_storage() -> SessionStorage singleton for the process
- SessionStorage.base_dir: Path to the session directory
- SessionStorage.get_image_path(filename: str) -> Path
- SessionStorage.ensure_image_written(filename: str, data: bytes) -> Path
- SessionStorage.cleanup() -> None
"""

from pathlib import Path
from typing import Optional
import atexit
import os
import shutil
import tempfile
import uuid

__all__ = ["get_session_storage", "SessionStorage"]


class SessionStorage:
    """Session-scoped temp storage rooted in a unique base directory.

    The base directory is created under the OS temp folder with a unique
    name so multiple app instances do not collide.
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        if base_dir is None:
            root = Path(tempfile.gettempdir()) / "orlando_toolkit"
            # Ensure a unique session folder to prevent cross-run collisions
            uniq = f"session_{os.getpid()}_{uuid.uuid4().hex[:8]}"
            base_dir = root / uniq
        self._base_dir = Path(base_dir)
        # Create base directory upfront (no subfolders for images)
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    # No subfolders: images are stored directly under base_dir

    def get_image_path(self, filename: str) -> Path:
        """Map an image filename to its session file path under base_dir."""
        safe = filename.replace(os.sep, "_")
        return self._base_dir / safe

    def ensure_image_written(self, filename: str, data: bytes) -> Path:
        """Ensure the given image is written to disk; return its path."""
        path = self.get_image_path(filename)
        if not path.exists():
            try:
                path.write_bytes(data)
            except Exception:
                pass
        return path

    def cleanup(self) -> None:
        """Delete the entire session directory tree, ignoring errors."""
        try:
            if self._base_dir.exists():
                shutil.rmtree(self._base_dir, ignore_errors=True)
        except Exception:
            # Ignore cleanup issues; folder lives under OS temp
            pass


_SESSION: Optional[SessionStorage] = None


def get_session_storage() -> SessionStorage:
    global _SESSION
    if _SESSION is None:
        _SESSION = SessionStorage()
        try:
            atexit.register(_SESSION.cleanup)
        except Exception:
            pass
    return _SESSION


