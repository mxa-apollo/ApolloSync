"""Tests for user-facing application status and synchronization statistics."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from src.config import Config
from src.status import ApplicationStatus
from src.sync import SyncEngine


class StatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.music = root / "Music"
        self.playlists = root / "Playlists"
        self.music.mkdir()
        self.playlists.mkdir()
        track = self.music / "song.flac"
        track.touch()
        self.config = Config(self.music, self.playlists, notifications=False)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def playlist(self, name: str, content: str | None = None) -> Path:
        path = self.playlists / name
        path.write_text(content if content is not None else str(self.music / "song.flac") + "\n", encoding="utf-8")
        return path

    def test_initial_status(self) -> None:
        status = ApplicationStatus().current
        self.assertFalse(status.watching)
        self.assertEqual(status.total_processed, 0)
        self.assertIsNone(status.last_error)

    def test_lifecycle_transitions(self) -> None:
        status = ApplicationStatus()
        status.set_starting()
        self.assertEqual(status.current.state, "starting")
        status.set_watching()
        self.assertTrue(status.current.watching)
        status.set_stopped()
        self.assertEqual(status.current.state, "stopped")

    def test_success_and_no_change_statistics(self) -> None:
        path = self.playlist("one.m3u")
        status = ApplicationStatus()
        engine = SyncEngine(self.config, status=status)
        try:
            engine.process_now(path)
            engine.process_now(path)
            snapshot = status.current
            self.assertEqual(snapshot.total_processed, 2)
            self.assertEqual(snapshot.total_synced, 1)
            self.assertEqual(snapshot.total_skipped, 1)
            self.assertEqual(snapshot.total_failed, 0)
            self.assertEqual(snapshot.last_processed_playlist, path.absolute())
            self.assertIsNotNone(snapshot.last_sync_time)
        finally:
            engine.stop()

    def test_failure_updates_error_statistics(self) -> None:
        path = self.playlist("missing.m3u")
        status = ApplicationStatus()
        engine = SyncEngine(self.config, status=status)
        try:
            path.unlink()
            engine.process_now(path)
            snapshot = status.current
            self.assertEqual(snapshot.total_processed, 1)
            self.assertEqual(snapshot.total_failed, 1)
            self.assertIn("unavailable", snapshot.last_error or "")
        finally:
            engine.stop()

    def test_multiple_operations_and_manual_scan_share_statistics(self) -> None:
        first = self.playlist("one.m3u")
        second = self.playlist("two.m3u8")
        status = ApplicationStatus()
        engine = SyncEngine(self.config, status=status)
        try:
            engine.scan([first, second])
            self.assertEqual(status.current.total_processed, 2)
            self.assertEqual(status.current.total_synced, 2)
        finally:
            engine.stop()

    def test_status_reads_are_safe_during_updates(self) -> None:
        status = ApplicationStatus()
        playlist = self.playlists / "x.m3u"
        errors: list[BaseException] = []

        def writer() -> None:
            try:
                for _ in range(500):
                    status.processing_started(playlist)
                    status.processing_succeeded(playlist, changed=False)
            except BaseException as exc:  # pragma: no cover - diagnostic guard
                errors.append(exc)

        thread = threading.Thread(target=writer)
        thread.start()
        while thread.is_alive():
            snapshot = status.current
            self.assertGreaterEqual(snapshot.total_processed, snapshot.total_skipped)
        thread.join()
        self.assertFalse(errors)


if __name__ == "__main__":
    unittest.main()
