"""Small first-run setup wizard and testable configuration helpers.

The graphical portion is intentionally thin. Validation and file creation are
kept in ordinary functions so they can be tested without a Windows desktop.
"""

from __future__ import annotations

import json
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import Config, ConfigError
from .logger import get_logger

__all__ = ["SetupValues", "create_config", "run_setup_wizard", "validate_setup"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SetupValues:
    """Values collected by the first-run wizard."""

    music_root: Path
    playlist_folder: Path
    notifications: bool = True
    start_with_windows: bool = False


def validate_setup(values: SetupValues) -> Config:
    """Validate wizard values and return a normal application :class:`Config`.

    The music library and effective playlist directory must already exist and
    be directories. This prevents the watcher from starting against a typo.
    Relative playlist folders are interpreted relative to ``music_root``.
    """
    if not str(values.music_root).strip():
        raise ConfigError("Select a music library folder before continuing.")
    if not str(values.playlist_folder).strip():
        raise ConfigError("Select a playlist folder before continuing.")
    config = Config(
        values.music_root,
        values.playlist_folder,
        notifications=values.notifications,
        start_with_windows=values.start_with_windows,
    )
    if not config.music_root.is_dir():
        raise ConfigError("The music library folder must already exist. Choose an existing folder.")
    if not config.playlist_path.is_dir():
        raise ConfigError(
            "The playlist folder must already exist. Choose an existing folder containing your M3U/M3U8 files."
        )
    return config


def create_config(path: Path | str, values: SetupValues) -> Config:
    """Validate values and create a new external ``config.json`` safely.

    The file is opened in exclusive-create mode, so an existing configuration
    can never be overwritten accidentally. The caller owns handling any
    ``FileExistsError`` or other filesystem error.
    """
    config = validate_setup(values)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "music_root": str(config.music_root),
        "playlist_folder": str(config.playlist_folder),
        "notifications": config.notifications,
        "start_with_windows": config.start_with_windows,
        "debounce_ms": config.debounce_ms,
        "log_level": config.log_level,
    }
    with target.open("x", encoding="utf-8") as config_file:
        json.dump(payload, config_file, indent=4)
        config_file.write("\n")
    return config


def run_setup_wizard(config_path: Path | str) -> bool:
    """Show the first-run wizard and create configuration on explicit success.

    Returns ``True`` only when configuration was created successfully. Cancel
    or any validation/write failure returns ``False`` and leaves an existing
    file untouched.
    """
    target = Path(config_path)
    result: list[bool] = [False]
    root = tk.Tk()
    root.title("ApolloSync Setup")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=18)
    frame.grid()
    ttk.Label(frame, text="Welcome to ApolloSync", font=("Segoe UI", 14, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w"
    )
    ttk.Label(
        frame,
        text="ApolloSync keeps M3U/M3U8 playlists portable by converting\n"
        "absolute music paths into relative paths. It monitors your playlist folder\n"
        "and updates playlists only when a conversion is needed.",
    ).grid(row=1, column=0, columnspan=3, pady=(6, 14), sticky="w")

    music_var = tk.StringVar()
    playlist_var = tk.StringVar(value="Playlists")
    notifications_var = tk.BooleanVar(value=True)
    startup_var = tk.BooleanVar(value=False)

    music_entry = _path_row(
        frame,
        2,
        "Music library *",
        "Folder containing your music files.",
        music_var,
        choose_directory=True,
    )
    playlist_entry = _path_row(
        frame,
        4,
        "Playlist folder *",
        "Folder containing the M3U/M3U8 files ApolloSync will monitor.",
        playlist_var,
        choose_directory=True,
    )
    ttk.Label(
        frame,
        text="A relative folder is resolved under the music library; Browse may select an absolute folder.",
        wraplength=430,
    ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(0, 4))
    ttk.Checkbutton(frame, text="Show desktop notifications", variable=notifications_var).grid(
        row=7, column=0, columnspan=3, sticky="w", pady=(8, 0)
    )
    ttk.Checkbutton(frame, text="Start ApolloSync with Windows", variable=startup_var).grid(
        row=8, column=0, columnspan=3, sticky="w"
    )
    ttk.Label(frame, text="Cancel closes setup without creating a configuration file.").grid(
        row=9, column=0, columnspan=3, sticky="w", pady=(8, 0)
    )

    def finish() -> None:
        try:
            music_text = music_var.get().strip()
            playlist_text = playlist_var.get().strip()
            if not music_text:
                raise ConfigError("Select a music library folder before continuing.")
            if not playlist_text:
                raise ConfigError("Select a playlist folder before continuing.")
            values = SetupValues(
                Path(music_text),
                Path(playlist_text),
                notifications_var.get(),
                startup_var.get(),
            )
            create_config(target, values)
        except (ConfigError, OSError, ValueError) as exc:
            messagebox.showerror("Setup could not be completed", str(exc), parent=root)
            return
        result[0] = True
        root.destroy()

    def cancel() -> None:
        root.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=10, column=0, columnspan=3, pady=(8, 0), sticky="e")
    ttk.Button(buttons, text="Cancel", command=cancel).pack(side="left", padx=(0, 8))
    start_button = ttk.Button(buttons, text="Start ApolloSync", command=finish)
    start_button.pack(side="left")
    root.protocol("WM_DELETE_WINDOW", cancel)

    def submit_from_entry(_event: object) -> str:
        start_button.invoke()
        return "break"

    music_entry.bind("<Return>", submit_from_entry)
    playlist_entry.bind("<Return>", submit_from_entry)
    root.bind("<Escape>", lambda _event: cancel())
    root.after_idle(music_entry.focus_set)
    root.mainloop()
    return result[0]


def _path_row(
    parent: ttk.Frame,
    row: int,
    label: str,
    helper: str,
    variable: tk.StringVar,
    *,
    choose_directory: bool,
) -> ttk.Entry:
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
    entry = ttk.Entry(parent, textvariable=variable, width=42)
    entry.grid(row=row, column=1, padx=8, pady=4)
    ttk.Label(parent, text=helper, wraplength=430).grid(
        row=row + 1, column=0, columnspan=3, sticky="w", pady=(0, 4)
    )

    def browse() -> None:
        selected = filedialog.askdirectory(title=f"Choose {label}") if choose_directory else ""
        if selected:
            variable.set(selected)

    ttk.Button(parent, text="Browse...", command=browse).grid(row=row, column=2, pady=4)
    return entry
