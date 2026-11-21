# Installation and build guide

## End users

There is no accepted installer yet. Only use a future release artifact whose GitHub release, checksum,
and clean-machine test result are published. The installer is designed to be per-user and to leave research
projects untouched during uninstall. The recognition model is installed separately. On the first start,
KurrentScholar explains that transcription cannot work without it and offers the one-time download.

## Source setup

Install Git and `uv`; no global Python is required because `uv` can provision the pinned Python version.

```powershell
uv python install 3.11
uv sync --extra dev
uv run pytest -m "not real_model"
uv run kurrentscholar
```

Each model download needs about 1.34 GB plus temporary/cache headroom (the app requires 1.8 GB free per
new installation). If interrupted, choose Install model again; Hugging Face Hub reuses completed files.

KurrentScholar verifies the expected file sizes and the pinned weights checksum before marking the model
ready. If installation fails, retry from **Install model** and inspect
`%LOCALAPPDATA%\KurrentScholar\Logs\kurrentscholar.log` for the recorded technical cause. Windows' trust
store is used for HTTPS, which supports ordinary institutional certificate deployments without disabling
certificate verification.

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

