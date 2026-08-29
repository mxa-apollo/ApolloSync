"""Thread-safe lifecycle management for Apollo Sync configuration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Lock, Timer

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .config import Config
from .logger import get_logger
from .utils import config_path as default_config_path

__all__ = ["ConfigManager"]

logger = get_logger(__name__)


class ConfigManager:
    """Own, watch, and safely replace the application's active configuration."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        on_reload_error: Callable[[Exception, Config], None] | None = None,
    ) -> None:
        """Load the initial configuration and prepare external-file watching."""
        self._path = _resolve_config_path(path)
        self._config = Config.load(self._path)
        self._on_reload_error = on_reload_error
        self._lock = Lock()
        self._subscribers: list[Callable[[Config, Config], None]] = []
        self._observer: Observer | None = None
        self._timer: Timer | None = None
        self._stopping = False

    @property
    def current(self) -> Config:
        """Return the last known-good configuration snapshot."""
        with self._lock:
            return self._config

    @property
    def path(self) -> Path:
        """Return the exact external configuration file being monitored."""
        return self._path

    def reload(self) -> Config:
        """Load, validate, atomically activate, and publish a new configuration."""
        try:
            new_config = Config.load(self._path)
        except Exception as exc:
            logger.error(
                "Configuration reload failed (%s): %s", type(exc).__name__, exc
            )
            old_config = self.current
            if self._on_reload_error is not None:
                try:
                    self._on_reload_error(exc, old_config)
                except Exception:
                    logger.exception("Configuration reload error callback failed.")
            return old_config

        with self._lock:
            if self._stopping:
                return self._config
            old_config = self._config
            self._config = new_config
            subscribers = tuple(self._subscribers)

        if old_config == new_config:
            return new_config
        logger.info("Configuration reloaded.")
        for callback in subscribers:
            try:
                callback(old_config, new_config)
            except Exception:
                logger.exception("Configuration subscriber failed.")
        return new_config

    def subscribe(self, callback: Callable[[Config, Config], None]) -> None:
        """Register a callback invoked after a valid configuration replacement."""
        if not callable(callback):
            raise TypeError("Configuration subscriber must be callable.")
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def start(self) -> None:
        """Start watching only the directory containing the external config file."""
        with self._lock:
            if self._observer is not None:
                return
            self._stopping = False
            observer = Observer()
            observer.schedule(_ConfigEventHandler(self._queue_reload), str(self._path.parent), recursive=False)
            observer.start()
            self._observer = observer

    def stop(self) -> None:
        """Stop watching and cancel any pending debounced reload."""
        with self._lock:
            self._stopping = True
            observer = self._observer
            self._observer = None
            timer = self._timer
            self._timer = None
        if timer is not None:
            timer.cancel()
        if observer is not None:
            observer.stop()
            observer.join()

    def _queue_reload(self) -> None:
        """Replace the pending reload timer for a burst of config events."""
        with self._lock:
            if self._stopping or self._observer is None:
                return
            if self._timer is not None:
                self._timer.cancel()
            timer = Timer(self._config.debounce_ms / 1_000, self._run_reload)
            timer.daemon = True
            self._timer = timer
            timer.start()

    def _run_reload(self) -> None:
        """Run one debounced reload unless shutdown has started."""
        with self._lock:
            self._timer = None
            if self._stopping:
                return
        self.reload()


class _ConfigEventHandler(FileSystemEventHandler):
    """Filter watchdog events down to the one configured external file."""

    def __init__(self, queue_reload: Callable[[], None]) -> None:
        super().__init__()
        self._queue_reload = queue_reload

    def on_created(self, event: FileSystemEvent) -> None:
        self._consider(event.src_path, event.is_directory)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._consider(event.src_path, event.is_directory)

    def on_closed(self, event: FileSystemEvent) -> None:
        self._consider(event.src_path, event.is_directory)

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._consider(event.src_path, event.is_directory)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._consider(getattr(event, "dest_path", ""), event.is_directory)

    def _consider(self, path: str, is_directory: bool) -> None:
        """Queue only events whose filename is exactly config.json."""
        if not is_directory and Path(path).name.casefold() == "config.json":
            self._queue_reload()


def _resolve_config_path(path: Path | str | None) -> Path:
    """Resolve the manager's path using the existing external config rules."""
    if path is None:
        return default_config_path()
    candidate = Path(path)
    return candidate if candidate.is_absolute() else default_config_path().parent / candidate
