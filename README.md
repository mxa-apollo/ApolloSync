# Apollo Sync

Apollo Sync is a small Windows tray utility that keeps `.m3u` and `.m3u8`
playlists portable. It converts Windows absolute music paths to paths relative
to the configured music library while preserving comments, blank lines, order,
URLs, and already-relative paths.

## How it works

At startup Apollo Sync loads the external `config.json`, starts a debounced
watcher for the playlist folder, and processes changes on one background worker.
Changed files are written through a temporary file, flush, and atomic replacement.
The tray displays session statistics and the most recent error.

## Installation and packaged use

For development, run `python run.py` from the repository root. For packaged use,
distribute the complete `dist/ApolloSync/` folder:

```text
ApolloSync/
    ApolloSync.exe
    config.json
    assets/
    logs/                 # created automatically
```

Build with PyInstaller (after installing dependencies):

```powershell
pyinstaller --clean --noconfirm ApolloSync.spec
```

`config.json` is deliberately external and must remain beside the executable.

## First-time setup and config.json

Copy `config.example.json` to `config.json` (or create a JSON file) beside
`run.py` or `ApolloSync.exe`. The required `music_root` setting identifies the
music library. If the file is missing or invalid, Apollo Sync never creates or
overwrites it; startup stops with a clear error and the expected path is logged.
Keep personalized `config.json` files local and distribute the example instead.

Supported settings:

```json
{
  "music_root": "D:\\Music",
  "playlist_folder": "Playlists",
  "notifications": true,
  "start_with_windows": false,
  "debounce_ms": 500,
  "log_level": "INFO"
}
```

`playlist_folder` may be relative to `music_root` or absolute. `debounce_ms` is
the delay used to coalesce rapid saves. `notifications` controls desktop sync
notifications. `log_level` accepts `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or
`DEBUG`. `start_with_windows` creates or removes a per-user Startup shortcut in
packaged mode. Configuration changes are validated and applied live; an invalid
edit leaves the last valid configuration active.

## Automatic synchronization

Only the configured playlist folder is watched. Temporary, backup, and
unsupported files are ignored. Multiple save events are debounced and coalesced
so one playlist is not processed concurrently.

## Manual Scan Playlists

Choose **Scan Playlists** in the tray menu to process eligible playlists in the
configured folder using the same safe pipeline as watcher events.

## Notifications and logs

When enabled, notifications are shown for a successful sync or failed sync.
Notification backend failures are logged and never stop synchronization. Logs are
written to `logs/apollosync.log`, rotated at 1 MB, and retain five backups. Use
**Open Logs** in the tray menu for the log directory.

## Windows startup

With `start_with_windows` enabled in a packaged build, Apollo Sync maintains an
`ApolloSync.lnk` shortcut in the current user's Startup folder. It requires no
administrator rights and is updated if the executable moves. Source execution
does not create a shortcut. Disabling the setting removes Apollo Sync's shortcut.

## Troubleshooting

- If startup stops immediately, check that `config.json` exists beside the
  executable and that `music_root` is a valid path string.
- If playlists are unchanged, confirm their extension is `.m3u` or `.m3u8` and
  that absolute paths are inside `music_root`.
- Check `logs/apollosync.log` for detailed read, conversion, write, watcher, or
  startup errors.
- If the tray icon or notifications are unavailable, synchronization continues;
  the condition is recorded in the log.

## Current limitations

Apollo Sync has no settings window, persistent history, database, cloud sync,
installer, updater, or registry-based startup integration. Session statistics
reset when the application exits.
