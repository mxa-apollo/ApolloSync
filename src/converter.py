"""Pure, in-memory conversion of Windows playlist paths.

The module neither accesses the filesystem nor depends on application services.
It converts absolute Windows media paths to paths relative to the playlist file
only when the media path belongs to the configured music root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from .logger import get_logger

__all__ = ["ConversionResult", "convert_playlist"]

_SUPPORTED_EXTENSIONS = frozenset({".m3u", ".m3u8"})

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """The result of converting one playlist's text.

    Attributes:
        converted_text: The playlist text after eligible paths are converted.
        changed: ``True`` only if at least one line was changed.
        converted_path_count: Number of absolute paths converted.
    """

    converted_text: str
    changed: bool
    converted_path_count: int


def convert_playlist(
    playlist_text: str,
    music_root: Path | str,
    playlist_path: Path | str,
) -> ConversionResult:
    """Convert eligible absolute Windows paths in M3U playlist text.

    ``playlist_path`` identifies where the playlist would be stored; no file is
    read or written. Its parent directory is used as the base for the resulting
    relative paths. Both ``.m3u`` and ``.m3u8`` playlist names are supported.

    Only absolute Windows paths contained by ``music_root`` are converted.
    Comments, blank lines, URLs, relative paths, ordering, and line endings are
    retained exactly. Paths outside the root remain unchanged.

    Examples:
        >>> result = convert_playlist(
        ...     "#EXTM3U\\nD:\\\\Music\\\\Songs\\\\Artist\\\\Track.flac\\n",
        ...     "D:\\\\Music",
        ...     "D:\\\\Music\\\\Playlists\\\\favourites.m3u",
        ... )
        >>> result.converted_text
        '#EXTM3U\\n..\\\\Songs\\\\Artist\\\\Track.flac\\n'
        >>> result.changed, result.converted_path_count
        (True, 1)

        >>> unchanged = convert_playlist(
        ...     "https://example.test/stream\\nSongs\\\\Artist\\\\Track.flac\\n",
        ...     "D:\\\\Music",
        ...     "D:\\\\Music\\\\Playlists\\\\radio.m3u8",
        ... )
        >>> unchanged.changed
        False
        >>> unchanged.converted_text
        'https://example.test/stream\\nSongs\\\\Artist\\\\Track.flac\\n'

    Args:
        playlist_text: UTF-8-decoded text from a playlist file.
        music_root: Absolute Windows path that bounds eligible media paths.
        playlist_path: Absolute Windows path of the playlist file.

    Raises:
        TypeError: If ``playlist_text`` is not text.
        ValueError: If either path is not an absolute Windows path, or if the
            playlist extension is not ``.m3u`` or ``.m3u8``.
    """
    if not isinstance(playlist_text, str):
        raise TypeError("'playlist_text' must be a string.")

    root = _absolute_windows_path("music_root", music_root)
    destination = _absolute_windows_path("playlist_path", playlist_path)
    if destination.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        logger.warning("Unsupported playlist format ignored.")
        extensions = ", ".join(sorted(_SUPPORTED_EXTENSIONS))
        raise ValueError(f"'playlist_path' must have one of these extensions: {extensions}.")

    converted_lines: list[str] = []
    converted_path_count = 0
    for line in playlist_text.splitlines(keepends=True):
        body, line_ending = _split_line_ending(line)
        converted_body = _convert_path_if_eligible(body, root, destination.parent)
        if converted_body != body:
            converted_path_count += 1
        converted_lines.append(converted_body + line_ending)

    converted_text = "".join(converted_lines)
    return ConversionResult(
        converted_text=converted_text,
        changed=converted_path_count > 0,
        converted_path_count=converted_path_count,
    )


def _absolute_windows_path(name: str, value: Path | str) -> PureWindowsPath:
    """Validate *value* and return it as an absolute Windows path."""
    if not isinstance(value, (Path, str)):
        raise TypeError(f"'{name}' must be a pathlib.Path or string.")
    if isinstance(value, str) and not value.strip():
        raise ValueError(f"'{name}' must not be empty.")

    path = PureWindowsPath(value)
    if not path.is_absolute():
        raise ValueError(f"'{name}' must be an absolute Windows path: {value!s}")
    return path


def _split_line_ending(line: str) -> tuple[str, str]:
    """Separate a playlist line from its original CRLF, LF, or CR ending."""
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[:-1], line[-1]
    return line, ""


def _convert_path_if_eligible(
    line: str,
    music_root: PureWindowsPath,
    playlist_directory: PureWindowsPath,
) -> str:
    """Return a converted path line, or the original line when it is ineligible."""
    if not line or line.startswith("#"):
        return line

    candidate = PureWindowsPath(line)
    if not candidate.is_absolute():
        return line

    try:
        candidate.relative_to(music_root)
    except ValueError:
        logger.warning("Playlist path outside music root ignored.")
        return line

    # Windows has no relative path syntax across drives or UNC shares.
    if candidate.drive.casefold() != playlist_directory.drive.casefold():
        return line

    logger.debug("Converted an absolute playlist path to a relative path.")
    return str(_relative_windows_path(candidate, playlist_directory))


def _relative_windows_path(
    target: PureWindowsPath, start: PureWindowsPath
) -> PureWindowsPath:
    """Compute a Windows relative path without touching the filesystem."""
    target_parts = target.parts
    start_parts = start.parts
    common_length = 0
    for target_part, start_part in zip(target_parts, start_parts):
        if target_part.casefold() != start_part.casefold():
            break
        common_length += 1

    relative_parts = ("..",) * (len(start_parts) - common_length) + target_parts[common_length:]
    return PureWindowsPath(*relative_parts) if relative_parts else PureWindowsPath(".")
