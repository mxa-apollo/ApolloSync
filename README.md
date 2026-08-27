# Apollo Sync

## Packaging

Apollo Sync can be built as a Windows one-folder executable with PyInstaller.
The build intentionally leaves `config.json` external so users can configure
the music root and playlist folder without rebuilding the application.

From the repository root, install the runtime dependencies and PyInstaller,
then run:

```powershell
pyinstaller --clean --noconfirm ApolloSync.spec
```

The packaged application is produced under `dist/ApolloSync/`:

```text
dist/ApolloSync/
    ApolloSync.exe
    config.json       # copy this from the repository root
    assets/
    logs/              # created automatically on first run
```

To distribute Apollo Sync, provide the complete `dist/ApolloSync/` folder,
including `ApolloSync.exe`, `config.json`, and the generated `assets/`
directory. Users start `ApolloSync.exe`; the executable must remain beside
`config.json`. The application creates `logs/` beside the executable when it
starts. Do not distribute PyInstaller's `build/` directory or the `.spec`
file as runtime requirements.
