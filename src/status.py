"""Thread-safe, in-memory application status for tray diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from threading import RLock

from .logger import get_logger

__all__ = ["ApplicationStatus", "StatusSnapshot"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    """Immutable point-in-time view of the application's session status."""

    state: str = "stopped"
    watching: bool = False
    last_sync_time: datetime | None = None
    last_processed_playlist: Path | None = None
    total_processed: int = 0
    total_synced: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    last_error: str | None = None


StatusListener = Callable[[StatusSnapshot], None]


class ApplicationStatus:
    """Own mutable session status while exposing only immutable snapshots.

    Updates notify listeners after releasing the lock, so a tray refresh or
    other slow observer cannot block status reads or synchronization work.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._snapshot = StatusSnapshot()
        self._listeners: list[StatusListener] = []

    @property
    def current(self) -> StatusSnapshot:
        """Return an immutable, point-in-time status snapshot."""
        with self._lock:
            return self._snapshot

    def subscribe(self, callback: StatusListener) -> None:
        """Register a listener for status changes, without duplicate entries."""
        if not callable(callback):
            raise TypeError("Status listener must be callable.")
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def set_starting(self) -> None:
        """Mark application startup as in progress."""
        self._update(state="starting", watching=False)

    def set_watching(self, watching: bool = True) -> None:
        """Set whether filesystem watching is active."""
        self._update(state="watching" if watching else "stopped", watching=watching)

    def set_error(self, message: str) -> None:
        """Record an application-level startup/runtime error."""
        self._update(state="error", watching=False, last_error=_short_error(message))

    def set_stopped(self) -> None:
        """Mark the application as stopped."""
        self._update(state="stopped", watching=False)

    def processing_started(self, playlist: Path) -> None:
        """Record one actual processing operation beginning."""
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                last_processed_playlist=playlist,
                total_processed=self._snapshot.total_processed + 1,
            )
            snapshot, listeners = self._snapshot, tuple(self._listeners)
        self._notify(snapshot, listeners)

    def processing_succeeded(self, playlist: Path, *, changed: bool) -> None:
        """Record a successful changed or no-change processing result."""
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                state="watching" if self._snapshot.watching else self._snapshot.state,
                last_processed_playlist=playlist,
                last_sync_time=datetime.now().astimezone() if changed else self._snapshot.last_sync_time,
                total_synced=self._snapshot.total_synced + (1 if changed else 0),
                total_skipped=self._snapshot.total_skipped + (0 if changed else 1),
                last_error=None,
            )
            snapshot, listeners = self._snapshot, tuple(self._listeners)
        self._notify(snapshot, listeners)

    def processing_failed(self, playlist: Path, error: BaseException | str) -> None:
        """Record a failed or unavailable processing operation."""
        message = _short_error(error)
        with self._lock:
            self._snapshot = replace(
                self._snapshot,
                state="error",
                last_processed_playlist=playlist,
                total_failed=self._snapshot.total_failed + 1,
                last_error=message,
            )
            snapshot, listeners = self._snapshot, tuple(self._listeners)
        self._notify(snapshot, listeners)

    def _update(self, **changes: object) -> None:
        with self._lock:
            self._snapshot = replace(self._snapshot, **changes)
            snapshot, listeners = self._snapshot, tuple(self._listeners)
        self._notify(snapshot, listeners)

    @staticmethod
    def _notify(snapshot: StatusSnapshot, listeners: tuple[StatusListener, ...]) -> None:
        for callback in listeners:
            try:
                callback(snapshot)
            except Exception:
                logger.exception("Status listener failed.")


def _short_error(error: BaseException | str) -> str:
    """Return a compact error suitable for a tray menu."""
    if isinstance(error, BaseException):
        text = f"{type(error).__name__}: {error}"
    else:
        text = str(error)
    return text[:240]
