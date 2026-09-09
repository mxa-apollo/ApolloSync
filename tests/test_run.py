"""Focused tests for startup UX and event-based shutdown waiting."""

from __future__ import annotations

import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from run import _show_config_error_dialog
from src.main import ApolloSyncApp


class StartupUxTests(unittest.TestCase):
    def test_invalid_config_dialog_is_concise_and_preserves_location(self) -> None:
        config_file = Path("C:/ApolloSync/config.json")
        with patch("tkinter.messagebox.showerror") as showerror:
            _show_config_error_dialog(config_file, ValueError("invalid JSON"))
        title, message = showerror.call_args.args
        self.assertEqual(title, "ApolloSync — Configuration Error")
        self.assertIn("was not changed", message)
        self.assertIn(str(config_file), message)
        self.assertNotIn("invalid JSON", message)

    def test_shutdown_wait_returns_after_request(self) -> None:
        app = ApolloSyncApp()
        finished = threading.Event()
        thread = threading.Thread(target=lambda: (app.wait_for_shutdown(), finished.set()))
        thread.start()
        self.assertFalse(finished.wait(0.05))
        app.request_exit()
        self.assertTrue(finished.wait(1))
        thread.join(1)


if __name__ == "__main__":
    unittest.main()
