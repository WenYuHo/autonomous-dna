# Release Branch Export

This repo is internal. End users should only receive the `release` branch.
The `release` branch is produced by CI using `tools/export_release.py` with
`release_manifest.json` to exclude internal/agent files.

## How it works
- Pushes to `dev` or `main` trigger the Release Export workflow.
- The workflow builds `dist/release` and force-updates the `release` branch.
- The `release` branch has its own history (no internal commits).

## Customize what ships
Edit `release_manifest.json`:
- `exclude`: list of paths or globs to omit (relative to repo root).
- `rename`: map of `source` -> `destination` paths in the export.

Example: ship a client README by editing `README.release.md`.

## Run locally
```bash
python tools/export_release.py --out dist/release --config release_manifest.json
```
