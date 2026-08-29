"""Persistent tests for live configuration management."""

from __future__ import annotations

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.config import Config
from src.config_manager import ConfigManager, _ConfigEventHandler


class _FakeTimer:
    instances: list["_FakeTimer"] = []

    def __init__(self, _delay: float, callback: object) -> None:
        self.callback = callback
        self.cancelled = False
        self.daemon = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        return

    def cancel(self) -> None:
        self.cancelled = True


class _FakeObserver:
    def __init__(self) -> None:
        self.handler: object | None = None
        self.stopped = False
        self.joined = False

    def schedule(self, handler: object, _path: str, recursive: bool = False) -> None:
        assert recursive is False
        self.handler = handler

    def start(self) -> None:
        return

    def stop(self) -> None:
        self.stopped = True

    def join(self) -> None:
        self.joined = True


class ConfigManagerTests(unittest.TestCase):
    """Exercise safe reload and event lifecycle behavior."""

    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.config_file = self.root / "config.json"
        self.write_config(log_level="INFO")

    def tearDown(self) -> None:
        self.directory.cleanup()

    def write_config(self, **updates: object) -> None:
        values: dict[str, object] = {
            "music_root": str(self.root / "Music"),
            "playlist_folder": "Playlists",
            "notifications": True,
            "start_with_windows": False,
            "debounce_ms": 500,
            "log_level": "INFO",
        }
        values.update(updates)
        import json

        self.config_file.write_text(json.dumps(values), encoding="utf-8")

    def manager(self, **kwargs: object) -> ConfigManager:
        return ConfigManager(self.config_file, **kwargs)

    def test_initial_loading_and_valid_reload(self) -> None:
        manager = self.manager()
        self.assertEqual(manager.current.log_level, "INFO")
        self.write_config(log_level="DEBUG")
        manager.reload()
        self.assertEqual(manager.current.log_level, "DEBUG")

    def test_invalid_json_values_and_missing_file_retain_last_good(self) -> None:
        manager = self.manager()
        original = manager.current
        self.config_file.write_text("{", encoding="utf-8")
        self.assertEqual(manager.reload(), original)
        self.write_config(music_root=123)
        self.assertEqual(manager.reload(), original)
        self.config_file.unlink()
        self.assertEqual(manager.reload(), original)

    def test_valid_recreation_is_applied_and_subscribers_receive_both_configs(self) -> None:
        received: list[tuple[Config, Config]] = []
        manager = self.manager()
        manager.subscribe(lambda old, new: received.append((old, new)))
        self.config_file.unlink()
        self.write_config(log_level="DEBUG")
        manager.reload()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0].log_level, "INFO")
        self.assertEqual(received[0][1].log_level, "DEBUG")

    def test_subscriber_failure_does_not_break_other_subscribers(self) -> None:
        manager = self.manager()
        received: list[Config] = []
        manager.subscribe(lambda _old, _new: (_ for _ in ()).throw(RuntimeError("bad")))
        manager.subscribe(lambda _old, new: received.append(new))
        self.write_config(log_level="DEBUG")
        manager.reload()
        self.assertEqual(received[0].log_level, "DEBUG")

    def test_only_config_filename_is_accepted_by_event_handler(self) -> None:
        queued: list[bool] = []
        handler = _ConfigEventHandler(lambda: queued.append(True))
        handler._consider(str(self.root / "other.json"), False)
        handler._consider(str(self.root / "config.json"), False)
        handler._consider(str(self.root / "config.json"), True)
        self.assertEqual(queued, [True])

    def test_rapid_events_replace_one_pending_timer(self) -> None:
        _FakeTimer.instances.clear()
        manager = self.manager()
        fake_observer = _FakeObserver()
        with patch("src.config_manager.Observer", return_value=fake_observer), patch(
            "src.config_manager.Timer", _FakeTimer
        ):
            manager.start()
            assert isinstance(fake_observer.handler, _ConfigEventHandler)
            handler = fake_observer.handler
            handler.on_modified(type("Event", (), {"src_path": str(self.config_file), "is_directory": False})())
            handler.on_modified(type("Event", (), {"src_path": str(self.config_file), "is_directory": False})())
            self.assertEqual(len(_FakeTimer.instances), 2)
            self.assertTrue(_FakeTimer.instances[0].cancelled)
            manager.stop()

    def test_stop_cancels_pending_reload_and_observer(self) -> None:
        _FakeTimer.instances.clear()
        manager = self.manager()
        fake_observer = _FakeObserver()
        with patch("src.config_manager.Observer", return_value=fake_observer), patch(
            "src.config_manager.Timer", _FakeTimer
        ):
            manager.start()
            manager._queue_reload()
            manager.stop()
        self.assertTrue(_FakeTimer.instances[0].cancelled)
        self.assertTrue(fake_observer.stopped)
        self.assertTrue(fake_observer.joined)

    def test_config_access_is_safe_during_reload(self) -> None:
        manager = self.manager()
        failures: list[Exception] = []

        def read_current() -> None:
            try:
                for _ in range(100):
                    _ = manager.current.log_level
            except Exception as exc:
                failures.append(exc)

        reader = threading.Thread(target=read_current)
        reader.start()
        self.write_config(log_level="DEBUG")
        manager.reload()
        reader.join()
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
