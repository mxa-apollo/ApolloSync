"""Application orchestration for Apollo Sync's MVP."""

from __future__ import annotations

from pathlib import Path
from threading import Lock

from .config import Config
from .converter import convert_playlist
from .logger import get_logger
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

    def __init__(self, config_path: Path | str = Config.DEFAULT_FILE_NAME) -> None:
        """Create an application instance without loading configuration yet."""
        self._config_path = Path(config_path)
        self._config: Config | None = None
        self._watcher: PlaylistWatcher | None = None
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

    def stop(self) -> None:
        """Stop filesystem monitoring and cancel pending playlist callbacks.

        Calling this method repeatedly is safe. A playlist processing operation
        already in progress is allowed to finish rather than being interrupted
        during a file write.
        """
        with self._state_lock:
            watcher = self._watcher
            self._watcher = None

        if watcher is not None:
            watcher.stop()

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
