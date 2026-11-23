# Installation and build guide

## End users

Download the current Windows installer from the
[latest GitHub Release](https://github.com/98JoHu/KurrentScholar/releases/latest) or use the
[direct installer link](https://github.com/98JoHu/KurrentScholar/releases/latest/download/KurrentScholar-Setup-Windows-x64.exe).
Compare its SHA-256 with `SHA256SUMS.txt` from the same release. The installer is per-user and leaves
research projects untouched during uninstall. It is currently unsigned, so Windows may show an
unknown-publisher warning; do not disable system security. The recognition model is installed separately.
On first start, KurrentScholar explains that transcription cannot work without it and offers the one-time
download.

## Source setup

Install Git and `uv`; no global Python is required because `uv` can provision the pinned Python version.

```powershell
uv python install 3.11
uv sync --extra dev
uv run pytest -m "not real_model"
uv run kurrentscholar
```

Each recognition-model download needs about 1.34 GB plus temporary/cache headroom. The Model Manager
calculates the remaining download plus a 512 MiB safety
margin. If interrupted, choose Install / repair; Hugging Face Hub reuses completed files.

KurrentScholar verifies the expected file sizes and the pinned weights checksum before marking the model
ready. If installation fails, retry from **Models > Model Manager** and inspect
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

The GitHub Actions workflow performs native Windows build/test/installer/checksum jobs and publishes the
installer plus checksum on `v*` tags. A tagged release must still be installed, started, used for a smoke
project, and uninstalled in a clean VM as the final human acceptance check.

## macOS builds

Use the architecture-specific DMG from the latest release: Apple Silicon for M1/M2/M3/M4 and later, Intel
for x86-64 Macs. KurrentScholar declares macOS 12 as its minimum. Install it by dragging the application to
Applications. Models and projects are user data and are not bundled into the application.

The native build recipe is in `packaging/macos/` and the release job is
`.github/workflows/macos-release.yml`. It runs the same tests, creates a native `.app`, signs it with a
Developer ID Application certificate, submits its DMG to Apple's notary service, staples the approval, and
only then attaches it to the release. Required protected secrets and clean-machine checks are documented in
`packaging/macos/README.md`. A Windows host cannot validate this native signing pipeline.

