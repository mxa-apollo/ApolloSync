"""Application orchestration for Apollo Sync's MVP."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Event, Lock

from .config import Config
from .converter import convert_playlist
from .logger import get_logger
from .startup import apply_startup_setting
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
        self._shutdown_requested = Event()
        self._state_lock = Lock()
        self._processing_lock = Lock()

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
            watcher.start()
            self._watcher = watcher
            tray = ApolloSyncTray(
                open_music_folder=self.open_music_folder,
                open_playlists_folder=self.open_playlists_folder,
                open_logs_folder=self.open_logs_folder,
                run_scan_now=self.run_scan_now,
                exit_callback=self.request_exit,
            )
            self._tray = tray
            tray.start()

    def stop(self) -> None:
        """Stop filesystem monitoring and cancel pending playlist callbacks.

        Calling this method repeatedly is safe. A playlist processing operation
        already in progress is allowed to finish rather than being interrupted
        during a file write.
        """
        with self._state_lock:
            watcher = self._watcher
            tray = self._tray
            self._watcher = None
            self._tray = None

        if watcher is not None:
            watcher.stop()
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
        try:
            playlist_paths = tuple(
                path
                for pattern in ("*.m3u", "*.m3u8")
                for path in config.playlist_path.glob(pattern)
            )
        except OSError:
            logger.exception("Failed listing playlist folder for manual scan.")
            return

        for playlist_path in playlist_paths:
            self.process_playlist(playlist_path)

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
        """Convert one changed playlist, reporting failures without stopping the app.

        The watcher invokes this method on a background timer thread. The
        process-wide lock serializes reads and writes so a long-running callback
        cannot overlap another conversion operation.
        """
        try:
            with self._processing_lock:
                self._process_playlist(playlist_path)
        except Exception:
            logger.exception("Unexpected callback exception.")

    def _process_playlist(self, playlist_path: Path) -> None:
        """Perform the read-convert-write workflow for one playlist path."""
        config = self._config
        if config is None:
            raise RuntimeError("ApolloSyncApp has not been started.")

        try:
            raw_playlist = playlist_path.read_bytes()
        except OSError:
            logger.exception("Failed reading playlist: %s", playlist_path)
            return

        playlist_text, encoding = _decode_playlist_text(raw_playlist)
        result = convert_playlist(playlist_text, config.music_root, playlist_path)
        logger.info("Playlist processed: %s", playlist_path)
        if result.changed:
            try:
                playlist_path.write_bytes(result.converted_text.encode(encoding))
            except OSError:
                logger.exception("Failed writing playlist: %s", playlist_path)
                return
            logger.info("Playlist updated: %s", playlist_path)


def _decode_playlist_text(data: bytes) -> tuple[str, str]:
    """Decode playlist bytes as UTF-8, falling back to Windows cp1252.

    The returned encoding is the exact encoding used for a later write, so
    conversion does not silently change the playlist's character encoding.
    """
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252"), "cp1252"
