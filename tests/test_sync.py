"""Focused regression tests for the Milestone 12 synchronization engine."""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from src.config import Config
from src.converter import convert_playlist
from src.sync import SyncEngine, _atomic_write


class SyncEngineTests(unittest.TestCase):
    """Exercise processing, atomic writes, notifications, and concurrency."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.music = self.root / "Music"
        self.playlists = self.root / "Playlists"
        self.music.mkdir()
        self.playlists.mkdir()
        self.track = self.music / "Songs" / "Artist" / "Track.flac"
        self.track.parent.mkdir(parents=True)
        self.track.touch()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _config(self, notifications: bool = False) -> Config:
        return Config(self.music, self.playlists, notifications=notifications)

    def _playlist(self, name: str = "library.m3u", content: bytes | None = None) -> Path:
        path = self.playlists / name
        path.write_bytes(content if content is not None else (str(self.track) + "\n").encode())
        return path

    def test_absolute_paths_are_atomically_converted_and_not_rewritten_when_current(self) -> None:
        path = self._playlist()
        engine = SyncEngine(self._config())
        try:
            engine.process_now(path)
            converted = path.read_text(encoding="utf-8")
            self.assertNotIn(str(self.track), converted)
            self.assertIn("..\\Music\\Songs\\Artist\\Track.flac", converted)
            timestamp = path.stat().st_mtime_ns
            engine.process_now(path)
            self.assertEqual(timestamp, path.stat().st_mtime_ns)
        finally:
            engine.stop()

    def test_m3u8_and_utf8_bom_are_supported(self) -> None:
        path = self._playlist("library.m3u8", b"\xef\xbb\xbf" + str(self.track).encode() + b"\n")
        engine = SyncEngine(self._config())
        try:
            engine.process_now(path)
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        finally:
            engine.stop()

    def test_failed_replace_leaves_original_and_cleans_temp(self) -> None:
        path = self._playlist(content=b"original")
        original_replace = os.replace
        with patch("src.sync.os.replace", side_effect=OSError("blocked")):
            with self.assertRaises(OSError):
                _atomic_write(path, b"new")
        os.replace = original_replace
        self.assertEqual(path.read_bytes(), b"original")
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_deleted_playlist_and_bad_bytes_do_not_stop_worker(self) -> None:
        deleted = self._playlist("deleted.m3u")
        bad = self._playlist("bad.m3u", b"\xff\xfe\xfd\n")
        valid = self._playlist("valid.m3u", b"relative\\track.flac\n")
        engine = SyncEngine(self._config())
        try:
            deleted.unlink()
            engine.process_now(deleted)
            engine.process_now(bad)
            engine.process_now(valid)
            self.assertEqual(valid.read_bytes(), b"relative\\track.flac\n")
        finally:
            engine.stop()

    def test_changes_during_processing_coalesce_to_one_follow_up(self) -> None:
        path = self._playlist()
        engine = SyncEngine(self._config())
        entered = threading.Event()
        release = threading.Event()
        calls: list[Path] = []

        def process(item: Path) -> None:
            calls.append(item)
            entered.set()
            release.wait(2)

        engine._process = process  # type: ignore[method-assign]
        first = threading.Thread(target=engine.process_now, args=(path,))
        first.start()
        self.assertTrue(entered.wait(1))
        engine.submit(path)
        engine.submit(path)
        release.set()
        first.join(2)
        engine.stop()
        self.assertEqual(calls, [path.absolute(), path.absolute()])

    def test_different_playlists_queue_without_state_corruption(self) -> None:
        first = self._playlist("a.m3u")
        second = self._playlist("b.m3u8")
        engine = SyncEngine(self._config())
        try:
            engine.scan([first, second])
            self.assertNotEqual(first.read_text(), str(self.track) + "\n")
            self.assertNotEqual(second.read_text(), str(self.track) + "\n")
        finally:
            engine.stop()

    def test_relative_scan_path_is_normalized(self) -> None:
        path = self._playlist()
        engine = SyncEngine(self._config())
        try:
            with contextlib.chdir(self.playlists):
                engine.scan([Path(path.name)])
            self.assertNotIn(str(self.track), path.read_text())
        finally:
            engine.stop()

    def test_notification_success_and_failure_are_best_effort(self) -> None:
        path = self._playlist()
        sent: list[tuple[str, str]] = []
        engine = SyncEngine(self._config(notifications=True), notifier=lambda title, message: sent.append((title, message)))
        try:
            engine.process_now(path)
            self.assertEqual(sent[0][0], "Playlist synced")
        finally:
            engine.stop()

        failing = self._playlist("failing.m3u")
        engine = SyncEngine(self._config(notifications=True), notifier=lambda _title, _message: (_ for _ in ()).throw(RuntimeError("offline")))
        try:
            engine.process_now(failing)
        finally:
            engine.stop()

    def test_stop_from_worker_skips_self_join(self) -> None:
        path = self._playlist()
        engine = SyncEngine(self._config())
        finished = threading.Event()

        def process(_item: Path) -> None:
            engine.stop()
            finished.set()

        engine._process = process  # type: ignore[method-assign]
        engine.submit(path)
        self.assertTrue(finished.wait(2))
        engine._worker.join(2)
        self.assertFalse(engine._worker.is_alive())


class ConverterRegressionTests(unittest.TestCase):
    """Confirm the pure converter remains unchanged in behavior."""

    def test_relative_and_comments_remain_unchanged(self) -> None:
        text = "#EXTM3U\nrelative\\track.flac\nhttps://example.test/stream\n"
        result = convert_playlist(text, r"D:\Music", r"D:\Music\Playlists\x.m3u")
        self.assertFalse(result.changed)
        self.assertEqual(result.converted_text, text)


if __name__ == "__main__":
    unittest.main()
