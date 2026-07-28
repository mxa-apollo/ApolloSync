"""Filesystem monitoring for playlist files.

This module deliberately only detects stable playlist changes. It delegates all
application behaviour to a callback supplied by its caller.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import RLock, Timer

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

__all__ = ["PlaylistWatcher"]

_PLAYLIST_EXTENSIONS = frozenset({".m3u", ".m3u8"})
_IGNORED_SUFFIXES = frozenset({".bak", ".backup", ".part", ".swp", ".swo", ".tmp", ".temp"})


class PlaylistWatcher(FileSystemEventHandler):
    """Watch one playlist directory and debounce playlist change callbacks.

    The watcher observes only direct children of ``playlist_folder``. For each
    playlist, a burst of created, modified, moved, or closed events produces at
    most one callback after ``debounce_ms`` has elapsed without another event
    for that path.

    Temporary and backup names are ignored, as are non-playlist files and
    directory events. A file moved into the folder is evaluated using its
    destination name, so an editor's atomic-save rename is handled correctly.

    Args:
        playlist_folder: Directory whose direct playlist files are monitored.
        on_playlist_changed: Called with a playlist path after the debounce
            interval. The callback is executed on a background timer thread.
        debounce_ms: Positive quiet period, in milliseconds, before invoking
            the callback for a changed playlist.

    Examples:
        >>> received: list[Path] = []
        >>> watcher = PlaylistWatcher(
        ...     "D:/Music/Playlists", received.append, debounce_ms=500
        ... )
        >>> watcher.is_running
        False
        >>> watcher.stop()  # Safe before start and safe to call repeatedly.
    """

    def __init__(
        self,
        playlist_folder: Path | str,
        on_playlist_changed: Callable[[Path], None],
        *,
        debounce_ms: int = 500,
    ) -> None:
        """Initialize a watcher without starting its observer thread."""
        super().__init__()
        if not isinstance(playlist_folder, (Path, str)):
            raise TypeError("'playlist_folder' must be a pathlib.Path or string.")
        if not callable(on_playlist_changed):
            raise TypeError("'on_playlist_changed' must be callable.")
        if isinstance(debounce_ms, bool) or not isinstance(debounce_ms, int):
            raise TypeError("'debounce_ms' must be an integer greater than zero.")
        if debounce_ms <= 0:
            raise ValueError("'debounce_ms' must be greater than zero.")

        self._playlist_folder = Path(playlist_folder).expanduser().absolute()
        self._on_playlist_changed = on_playlist_changed
        self._debounce_seconds = debounce_ms / 1_000
        self._lock = RLock()
        self._observer: Observer | None = None
        self._timers: dict[Path, Timer] = {}

    @property
    def is_running(self) -> bool:
        """Return whether the observer has been started and not yet stopped."""
        with self._lock:
            return self._observer is not None and self._observer.is_alive()

    def start(self) -> None:
        """Start observing the configured playlist directory.

        Raises:
            RuntimeError: If this watcher is already running.
            OSError: If watchdog cannot observe the configured directory.
        """
        with self._lock:
            if self._observer is not None:
                raise RuntimeError("PlaylistWatcher is already running.")

            observer = Observer()
            observer.schedule(self, str(self._playlist_folder), recursive=False)
            try:
                observer.start()
            except Exception:
                observer.unschedule_all()
                raise
            self._observer = observer

    def stop(self) -> None:
        """Stop observing and cancel callbacks that have not fired yet.

        The method is idempotent. It waits for the observer thread to finish,
        but does not attempt to interrupt a callback already in progress.
        """
        with self._lock:
            observer = self._observer
            self._observer = None
            timers = tuple(self._timers.values())
            self._timers.clear()

        for timer in timers:
            timer.cancel()

        if observer is not None:
            observer.stop()
            observer.join()

    def on_created(self, event: FileSystemEvent) -> None:
        """Queue a callback when a playlist is created."""
        self._queue_event_path(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Queue a callback when a playlist is modified."""
        self._queue_event_path(event)

    def on_closed(self, event: FileSystemEvent) -> None:
        """Queue a callback when a playlist is closed after writing."""
        self._queue_event_path(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Queue a callback for a playlist moved into the watched directory."""
        if event.is_directory:
            return
        destination = getattr(event, "dest_path", None)
        if destination is not None:
            self._queue_path(Path(destination))

    def _queue_event_path(self, event: FileSystemEvent) -> None:
        """Extract a non-directory event path and queue it for debouncing."""
        if not event.is_directory:
            self._queue_path(Path(event.src_path))

    def _queue_path(self, path: Path) -> None:
        """Replace the pending timer for one eligible playlist path."""
        path = path.absolute()
        if not self._is_eligible_playlist(path):
            return

        with self._lock:
            if self._observer is None:
                return

            previous_timer = self._timers.pop(path, None)
            if previous_timer is not None:
                previous_timer.cancel()

            timer = Timer(self._debounce_seconds, self._deliver_callback, args=(path,))
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _deliver_callback(self, path: Path) -> None:
        """Remove a completed timer and invoke the caller's callback once."""
        with self._lock:
            if self._observer is None:
                return
            self._timers.pop(path, None)

        self._on_playlist_changed(path)

    def _is_eligible_playlist(self, path: Path) -> bool:
        """Return whether *path* is a direct, non-temporary playlist child."""
        if path.parent != self._playlist_folder:
            return False
        if path.suffix.lower() not in _PLAYLIST_EXTENSIONS:
            return False
        return not _is_temporary_or_backup(path.name)


def _is_temporary_or_backup(filename: str) -> bool:
    """Identify common temporary and backup filenames without filesystem access."""
    name = filename.casefold()
    return (
        name.startswith("~$")
        or name.startswith(".")
        or name.endswith("~")
        or Path(name).suffix in _IGNORED_SUFFIXES
        or any(
            marker in name
            for marker in (".bak.", ".backup.", ".part.", ".swp.", ".swo.", ".tmp.", ".temp.")
        )
    )
