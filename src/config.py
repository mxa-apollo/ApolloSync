"""Loading and validation for ApolloSync's JSON configuration.

This module deliberately has no dependency on the rest of the application so
that configuration can be loaded before services such as logging or the tray
application are started.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Mapping

from .utils import config_path


class ConfigError(ValueError):
    """Base exception raised when ApolloSync configuration is unusable."""


class ConfigFileError(ConfigError):
    """Raised when the configuration file cannot be read or parsed."""


@dataclass(frozen=True, slots=True)
class Config:
    """Validated application settings loaded from a JSON file.

    Attributes:
        music_root: Root directory containing the music library.
        playlist_folder: Playlist directory. A relative path is interpreted
            relative to :attr:`music_root`; an absolute path is used as given.
        notifications: Whether desktop notifications are enabled.
        start_with_windows: Whether Windows startup integration is enabled.
        debounce_ms: Delay in milliseconds used to coalesce file changes.
        log_level: Standard logging level name to use when logging is added.
    """

    music_root: Path
    playlist_folder: Path
    notifications: bool = True
    start_with_windows: bool = False
    debounce_ms: int = 500
    log_level: str = "INFO"

    DEFAULT_FILE_NAME: ClassVar[str] = "config.json"
    _VALID_LOG_LEVELS: ClassVar[frozenset[str]] = frozenset(
        {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
    )

    def __post_init__(self) -> None:
        """Normalize and validate values supplied directly to the dataclass.

        This makes ``Config(...)`` as safe to use as :meth:`load`, including
        when callers build a configuration programmatically in tests.
        """
        music_root = self._coerce_path("music_root", self.music_root)
        playlist_folder = self._coerce_path("playlist_folder", self.playlist_folder)

        if not isinstance(self.notifications, bool):
            raise ConfigError("'notifications' must be a boolean.")
        if not isinstance(self.start_with_windows, bool):
            raise ConfigError("'start_with_windows' must be a boolean.")
        if isinstance(self.debounce_ms, bool) or not isinstance(self.debounce_ms, int):
            raise ConfigError("'debounce_ms' must be an integer greater than zero.")
        if self.debounce_ms <= 0:
            raise ConfigError("'debounce_ms' must be greater than zero.")
        if not isinstance(self.log_level, str):
            raise ConfigError("'log_level' must be a string.")

        log_level = self.log_level.upper()
        if log_level not in self._VALID_LOG_LEVELS:
            levels = ", ".join(sorted(self._VALID_LOG_LEVELS))
            raise ConfigError(f"'log_level' must be one of: {levels}.")

        object.__setattr__(self, "music_root", music_root)
        object.__setattr__(self, "playlist_folder", playlist_folder)
        object.__setattr__(self, "log_level", log_level)

    @property
    def playlist_path(self) -> Path:
        """Return the effective playlist directory as a :class:`Path`.

        ``playlist_folder`` remains the value expressed by configuration. This
        property resolves relative values against the configured music root.
        """
        if self.playlist_folder.is_absolute():
            return self.playlist_folder
        return self.music_root / self.playlist_folder

    @classmethod
    def load(cls, path: Path | str | None = None) -> "Config":
        """Load configuration from *path*.

        Args:
            path: JSON configuration file. When omitted, the external
                ``config.json`` beside the source project or executable is used.

        Raises:
            ConfigFileError: If the file is missing, unreadable, malformed, or
                its JSON root is not an object.
            ConfigError: If a required setting is missing or any setting has
                an invalid value.
        """
        config_file_path = config_path() if path is None else Path(path)
        if not config_file_path.is_absolute():
            config_file_path = config_path().parent / config_file_path
        try:
            with config_file_path.open("r", encoding="utf-8") as config_file:
                data = json.load(config_file)
        except FileNotFoundError as exc:
            raise ConfigFileError(f"Configuration file not found: {config_file_path}") from exc
        except OSError as exc:
            raise ConfigFileError(
                f"Could not read configuration file '{config_file_path}': {exc}"
            ) from exc
        except UnicodeDecodeError as exc:
            raise ConfigFileError(
                f"Configuration file '{config_file_path}' must be UTF-8 encoded."
            ) from exc
        except json.JSONDecodeError as exc:
            raise ConfigFileError(
                f"Configuration file '{config_file_path}' contains invalid JSON: {exc.msg} "
                f"(line {exc.lineno}, column {exc.colno})."
            ) from exc

        if not isinstance(data, Mapping):
            raise ConfigFileError(
                f"Configuration file '{config_file_path}' must contain a JSON object."
            )

        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Config":
        """Create a configuration from JSON-compatible mapping data.

        ``music_root`` is required. All remaining supported settings have
        defaults, making a minimal configuration easy to maintain.

        Args:
            data: Mapping of configuration setting names to values.

        Raises:
            ConfigError: If a required key is missing or a value is invalid.
        """
        if "music_root" not in data:
            raise ConfigError("Missing required configuration key: 'music_root'.")

        return cls(
            music_root=data["music_root"],
            playlist_folder=data.get("playlist_folder", "Playlists"),
            notifications=data.get("notifications", True),
            start_with_windows=data.get("start_with_windows", False),
            debounce_ms=data.get("debounce_ms", 500),
            log_level=data.get("log_level", "INFO"),
        )

    @staticmethod
    def _coerce_path(name: str, value: Path | str) -> Path:
        """Return a non-empty path value or raise a clear configuration error."""
        if not isinstance(value, (Path, str)):
            raise ConfigError(f"'{name}' must be a path string.")
        if isinstance(value, str) and not value.strip():
            raise ConfigError(f"'{name}' must not be empty.")
        return Path(value).expanduser()
