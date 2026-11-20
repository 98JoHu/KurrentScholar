# Installation and build guide

## End users

There is no accepted installer yet. Only use a future release artifact whose GitHub release, checksum,
and clean-machine test result are published. The installer is designed to be per-user and to leave research
projects untouched during uninstall. The recognition model is installed separately on first request.

## Source setup

Install Git and `uv`; no global Python is required because `uv` can provision the pinned Python version.

```powershell
uv python install 3.11
uv sync --extra dev
uv run pytest -m "not real_model"
uv run kurrentscholar
```

The model download needs 1,340,570,347 bytes plus temporary/cache headroom (the app requires 1.8 GB free).
If interrupted, choose Install model again; Hugging Face Hub reuses completed files.

## Windows one-directory build

```powershell
uv run pyinstaller packaging/windows/KurrentScholar.spec --noconfirm --clean
```

Install Inno Setup 6, then compile `packaging/windows/KurrentScholar.iss`. Expected paths, only after a
successful local build, are `dist/KurrentScholar/` and `dist/installer/KurrentScholar-Setup-Windows-x64.exe`.
The installer is unsigned unless a maintainer explicitly adds a protected CI signing step. Never instruct
users to disable system-wide security; publish a checksum and explain the unsigned warning.

The GitHub Actions workflow performs native Windows build/test/installer/checksum jobs. A tagged release
must still be installed, started, used for a smoke project, and uninstalled in a clean VM before promotion.

