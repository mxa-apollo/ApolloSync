# Public Release Checklist

## Completed

- Security audit and public-content review completed.
- `config.example.json` added as the safe public configuration template.
- Runtime `config.json` documented as local-only.
- Personalized `config.json` removed from reachable Git history.
- Historical config content sanitized from `main`.
- Release tags `v0.1.0`, `v0.2.0`, and `v0.3.0` rewritten and pushed.
- Git history verified with `git fsck --full`.
- MIT License added.
- M14–M18 automated test suite passes.

## Pending

- Final source review and packaged executable test on a clean Windows user profile.
- Review tracked files, logs, and dependency licenses for release contents.
- Build the PyInstaller one-folder package.
- Verify external `config.json`, tray icon, logs, startup, and shutdown in the packaged build.
- Perform final real-world Windows testing.
- Confirm final release version.
- Create the final release commit and push it.
- Create the GitHub Release and upload only the intended distribution archive.
- Verify the release asset.
- Change repository visibility to Public when approved.