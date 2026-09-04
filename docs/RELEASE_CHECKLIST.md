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
- M20 packaged-app validation completed manually by the developer using the fresh
  M20 build; application behavior was reported working correctly.
- M20.1 release tooling and clean-package preparation completed.
- M20.1 tooling verified: pytest 9.1.1 and PyInstaller 6.22.2 are available in the
  active Python 3.12.14 environment.
- M20.1 fresh build and package audit completed in isolated `dist_m20/` output;
  executable and icon are present without external config or runtime logs.
- Automated pytest verification: 24 tests passed (with an environment cache warning).

## Pending

- The existing ignored `dist/ApolloSync` directory contains prior runtime `config.json`
  and `logs/` and must not be distributed as-is; use the fresh build output instead.
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
