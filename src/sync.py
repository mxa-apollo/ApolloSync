"""Reliable playlist synchronization policy.

The engine owns queueing, safe reads, conversion, atomic replacement, and
notifications. It deliberately knows nothing about filesystem event detection.
"""

from __future__ import annotations

import os
import queue
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread, current_thread
from typing import Callable

from .config import Config
from .converter import convert_playlist
from .logger import get_logger
from .notifier import notify

logger = get_logger(__name__)


@dataclass
class _WorkItem:
    """One queued playlist and an optional completion signal."""

    path: Path
    completed: Event | None = None


class SyncEngine:
    """Process playlists safely with serialized work and per-path coalescing."""

    def __init__(
        self,
        config: Config,
        *,
        notifier: Callable[[str, str], None] = notify,
    ) -> None:
        """Create and start the single background processing worker."""
        self._config = config
        self._config_lock = Lock()
        self._notifier = notifier
        self._queue: queue.Queue[_WorkItem | None] = queue.Queue()
        self._lock = Lock()
        self._active: set[Path] = set()
        self._queued: set[Path] = set()
        self._pending: set[Path] = set()
        self._accepting = True
        self._worker = Thread(target=self._run, name="apollo-sync-worker", daemon=True)
        self._worker.start()

    def update_config(self, config: Config) -> None:
        """Atomically replace the configuration used by future processing."""
        with self._config_lock:
            self._config = config

    def submit(self, playlist_path: Path | str) -> bool:
        """Queue a playlist without blocking the filesystem observer thread.

        Returns ``False`` when shutdown has begun or when the path is already
        queued. A change arriving while the path is active is remembered as one
        pending follow-up pass.
        """
        path = Path(playlist_path).absolute()
        with self._lock:
            if not self._accepting:
                return False
            if path in self._active:
                self._pending.add(path)
                return True
            if path in self._queued:
                return False
            self._active.add(path)
            self._queued.add(path)
            self._queue.put(_WorkItem(path))
            return True

    def process_now(self, playlist_path: Path | str) -> None:
        """Process one playlist through the same worker pipeline and wait for it."""
        path = Path(playlist_path).absolute()
        completed = Event()
        with self._lock:
            if not self._accepting:
                return
            if path in self._active:
                self._pending.add(path)
                return
            self._active.add(path)
            self._queued.add(path)
            self._queue.put(_WorkItem(path, completed))
        completed.wait()

    def scan(self, playlist_paths: list[Path]) -> None:
        """Process a manual scan using the same queued pipeline as watcher events."""
        completions: list[Event] = []
        for path in playlist_paths:
            path = Path(path).absolute()
            completed = Event()
            with self._lock:
                if not self._accepting:
                    break
                if path in self._active:
                    self._pending.add(path)
                    continue
                self._active.add(path)
                self._queued.add(path)
                self._queue.put(_WorkItem(path, completed))
            completions.append(completed)
        for completed in completions:
            completed.wait()

    def stop(self) -> None:
        """Stop accepting work and let queued/active atomic writes finish."""
        with self._lock:
            self._accepting = False
            self._pending.clear()
        self._queue.put(None)
        if current_thread() is not self._worker:
            self._worker.join()

    def _run(self) -> None:
        """Run queued work until the shutdown sentinel is reached."""
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            try:
                self._process(item.path)
            except Exception:
                logger.exception("Unexpected playlist processing failure: %s", item.path)
            finally:
                if item.completed is not None:
                    item.completed.set()
                with self._lock:
                    self._active.discard(item.path)
                    self._queued.discard(item.path)
                    if item.path in self._pending and self._accepting:
                        self._pending.remove(item.path)
                        self._active.add(item.path)
                        self._queued.add(item.path)
                        self._queue.put(_WorkItem(item.path))
                        logger.info("Follow-up playlist processing queued: %s", item.path)
                self._queue.task_done()

    def _process(self, playlist_path: Path) -> None:
        """Read, convert, and atomically replace one playlist when necessary."""
        if not playlist_path.is_file():
            logger.warning("Playlist disappeared before processing: %s", playlist_path)
            return

        logger.info("Playlist processing started: %s", playlist_path)
        with self._config_lock:
            config = self._config

        try:
            raw = playlist_path.read_bytes()
            text, encoding = _decode_playlist(raw)
        except (OSError, UnicodeError) as exc:
            logger.error("Failed reading playlist %s (%s): %s", playlist_path, type(exc).__name__, exc)
            self._send_failure(playlist_path)
            return

        try:
            result = convert_playlist(text, config.music_root, playlist_path)
        except Exception as exc:
            logger.error("Failed converting playlist %s (%s): %s", playlist_path, type(exc).__name__, exc)
            self._send_failure(playlist_path)
            return

        if not result.changed:
            logger.info("Playlist already up to date: %s", playlist_path)
            return

        try:
            _atomic_write(playlist_path, result.converted_text.encode(encoding))
        except (OSError, UnicodeError) as exc:
            logger.error("Failed writing playlist %s (%s): %s", playlist_path, type(exc).__name__, exc)
            self._send_failure(playlist_path)
            return

        logger.info("Playlist successfully synced: %s", playlist_path)
        if config.notifications:
            try:
                self._notifier("Playlist synced", playlist_path.name)
            except Exception:
                logger.exception("Notification failed for playlist: %s", playlist_path)

    def _send_failure(self, playlist_path: Path) -> None:
        """Send a best-effort failure notification."""
        with self._config_lock:
            notifications_enabled = self._config.notifications
        if not notifications_enabled:
            return
        try:
            self._notifier("Playlist sync failed", playlist_path.name)
        except Exception:
            logger.exception("Notification failed for playlist: %s", playlist_path)


def _decode_playlist(data: bytes) -> tuple[str, str]:
    """Decode UTF-8, preserving UTF-8 BOMs, with cp1252 fallback."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8-sig"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252"), "cp1252"


def _atomic_write(path: Path, data: bytes) -> None:
    """Write bytes beside *path*, fsync them, then atomically replace *path*."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(data)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not clean up temporary playlist file: %s", temporary_path)
