"""Application orchestration for Apollo Sync's MVP."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Event, Lock

from .config import Config
from .logger import get_logger
from .startup import apply_startup_setting
from .sync import SyncEngine
from .tray import ApolloSyncTray
from .utils import logs_directory
from .watcher import PlaylistWatcher

__all__ = ["ApolloSyncApp"]

logger = get_logger(__name__)


class ApolloSyncApp:
    """Coordinate configuration, playlist watching, and playlist conversion.

    The application owns the watcher because it supplies the callback that
    turns a filesystem event into the complete read-convert-write workflow.
    Conversion and event detection remain in their dedicated modules.

    Args:
        config_path: Path to the application's JSON configuration file.

    Examples:
        >>> app = ApolloSyncApp("config.json")
        >>> app.is_running
        False
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        """Create an application instance without loading configuration yet."""
        self._config_path = config_path
        self._config: Config | None = None
        self._watcher: PlaylistWatcher | None = None
        self._tray: ApolloSyncTray | None = None
        self._sync: SyncEngine | None = None
        self._shutdown_requested = Event()
        self._state_lock = Lock()

    @property
    def is_running(self) -> bool:
        """Return whether the application's playlist watcher is running."""
        with self._state_lock:
            return self._watcher is not None and self._watcher.is_running

    def start(self) -> None:
        """Load configuration and begin monitoring the playlist directory.

        Raises:
            RuntimeError: If the application is already running.
            ConfigError: If configuration cannot be loaded or validated.
            OSError: If the playlist directory cannot be watched.
        """
        with self._state_lock:
            if self._watcher is not None:
                raise RuntimeError("ApolloSyncApp is already running.")

            config = Config.load(self._config_path)
            logger.info("Configuration loaded.")
            apply_startup_setting(config.start_with_windows)
            watcher = PlaylistWatcher(
                config.playlist_path,
                self.process_playlist,
                debounce_ms=config.debounce_ms,
            )
            # Set configuration before starting the observer so a fast event
            # can always be processed with a fully initialized application.
            self._config = config
            self._sync = SyncEngine(config)
            try:
                watcher.start()
            except Exception:
                sync = self._sync
                self._sync = None
                try:
                    if sync is not None:
                        sync.stop()
                except Exception:
                    logger.exception("Failed cleaning up after watcher startup failure.")
                raise
            self._watcher = watcher
            try:
                tray = ApolloSyncTray(
                    open_music_folder=self.open_music_folder,
                    open_playlists_folder=self.open_playlists_folder,
                    open_logs_folder=self.open_logs_folder,
                    run_scan_now=self.run_scan_now,
                    exit_callback=self.request_exit,
                )
                self._tray = tray
                tray.start()
            except Exception:
                failed_watcher = self._watcher
                failed_sync = self._sync
                failed_tray = self._tray
                self._watcher = None
                self._sync = None
                self._tray = None
                for component, cleanup in (
                    ("tray", failed_tray.stop if failed_tray is not None else None),
                    ("watcher", failed_watcher.stop if failed_watcher is not None else None),
                    ("sync", failed_sync.stop if failed_sync is not None else None),
                ):
                    if cleanup is None:
                        continue
                    try:
                        cleanup()
                    except Exception:
                        logger.exception("Failed cleaning up %s after startup failure.", component)
                raise

    def stop(self) -> None:
        """Stop filesystem monitoring and cancel pending playlist callbacks.

        Calling this method repeatedly is safe. A playlist processing operation
        already in progress is allowed to finish rather than being interrupted
        during a file write.
        """
        with self._state_lock:
            watcher = self._watcher
            tray = self._tray
            sync = self._sync
            self._watcher = None
            self._tray = None
            self._sync = None

        if watcher is not None:
            watcher.stop()
        if sync is not None:
            sync.stop()
        if tray is not None:
            tray.stop()

    @property
    def shutdown_requested(self) -> bool:
        """Return whether the tray Exit action requested application shutdown."""
        return self._shutdown_requested.is_set()

    def request_exit(self) -> None:
        """Request clean shutdown from a non-main thread such as the tray UI."""
        self._shutdown_requested.set()

    def open_music_folder(self) -> None:
        """Open the configured music directory in Windows Explorer."""
        self._open_folder(self._require_config().music_root)

    def open_playlists_folder(self) -> None:
        """Open the configured playlist directory in Windows Explorer."""
        self._open_folder(self._require_config().playlist_path)

    def open_logs_folder(self) -> None:
        """Open Apollo Sync's log directory in Windows Explorer."""
        self._open_folder(logs_directory())

    def run_scan_now(self) -> None:
        """Process every direct M3U playlist in the configured playlist folder."""
        config = self._require_config()
        logger.info("Manual playlist scan started.")
        try:
            playlist_paths = tuple(
                path
                for pattern in ("*.m3u", "*.m3u8")
                for path in config.playlist_path.glob(pattern)
            )
        except OSError:
            logger.exception("Failed listing playlist folder for manual scan.")
            return

        sync = self._sync
        if sync is not None:
            sync.scan(playlist_paths)
            logger.info("Manual playlist scan completed: %d playlists.", len(playlist_paths))

    def _require_config(self) -> Config:
        """Return startup configuration or fail clearly before the app starts."""
        if self._config is None:
            raise RuntimeError("ApolloSyncApp has not been started.")
        return self._config

    @staticmethod
    def _open_folder(path: Path) -> None:
        """Open *path* with Windows Explorer and report failures through logging."""
        try:
            os.startfile(path)  # type: ignore[attr-defined]  # Windows-only API.
        except (AttributeError, OSError):
            logger.exception("Failed opening folder: %s", path)

    def process_playlist(self, playlist_path: Path) -> None:
        """Queue one changed playlist for the shared synchronization pipeline."""
        sync = self._sync
        if sync is not None:
            sync.submit(playlist_path)
