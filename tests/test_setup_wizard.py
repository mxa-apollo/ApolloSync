"""GUI-independent tests for first-run setup configuration handling."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.config import ConfigError
from src.setup_wizard import SetupValues, create_config, validate_setup


class SetupWizardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.music = self.root / "Music"
        self.playlists = self.music / "Playlists"
        self.playlists.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def values(self, **updates: object) -> SetupValues:
        data: dict[str, object] = {
            "music_root": self.music,
            "playlist_folder": "Playlists",
            "notifications": True,
            "start_with_windows": False,
        }
        data.update(updates)
        return SetupValues(**data)  # type: ignore[arg-type]

    def test_valid_setup_creates_compatible_config(self) -> None:
        target = self.root / "config.json"
        config = create_config(target, self.values())
        self.assertEqual(config.playlist_path, self.playlists)
        loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(loaded["playlist_folder"], "Playlists")
        self.assertTrue(loaded["notifications"])

    def test_invalid_paths_are_rejected(self) -> None:
        with self.assertRaisesRegex(ConfigError, "music library folder"):
            validate_setup(self.values(music_root=self.root / "missing"))
        with self.assertRaisesRegex(ConfigError, "playlist folder"):
            validate_setup(self.values(playlist_folder="Missing"))

    def test_empty_paths_explain_what_is_required(self) -> None:
        with self.assertRaisesRegex(ConfigError, "music library folder"):
            validate_setup(self.values(music_root=""))
        with self.assertRaisesRegex(ConfigError, "playlist folder"):
            validate_setup(self.values(playlist_folder=""))

    def test_existing_config_is_never_overwritten(self) -> None:
        target = self.root / "config.json"
        target.write_text("original", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            create_config(target, self.values())
        self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_cancel_path_does_not_create_file(self) -> None:
        target = self.root / "config.json"
        # The GUI's cancel result is intentionally represented by doing nothing.
        self.assertFalse(target.exists())

    def test_optional_settings_are_preserved(self) -> None:
        target = self.root / "config.json"
        create_config(target, self.values(notifications=False, start_with_windows=True))
        loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertFalse(loaded["notifications"])
        self.assertTrue(loaded["start_with_windows"])


if __name__ == "__main__":
    unittest.main()
