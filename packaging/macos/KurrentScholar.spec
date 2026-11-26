# Native macOS application bundle. Build separately on Apple Silicon and Intel.
import os
from pathlib import Path
import tomllib

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

root = Path(SPECPATH).parent.parent
signing = {
    "codesign_identity": os.environ.get("APPLE_CODESIGN_IDENTITY") or None,
    "entitlements_file": str(root / "packaging" / "macos" / "entitlements.plist"),
}
version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

datas = (
    collect_data_files("transformers")
    + collect_data_files("pypdfium2")
    + collect_data_files("certifi")
    + copy_metadata("huggingface-hub")
    + copy_metadata("transformers")
    # Application icon and stylesheet images (spin box arrows).
    + [(str(root / "src" / "kurrentscholar" / "assets"), "kurrentscholar/assets")]
)
binaries = collect_dynamic_libs("torch") + collect_dynamic_libs("pypdfium2")
hiddenimports = [
    "transformers.models.trocr",
    "transformers.models.vit",
    "transformers.models.roberta",
    "openpyxl",
    "pypdfium2._helpers",
] + collect_submodules("huggingface_hub")

a = Analysis(
    [str(root / "src" / "kurrentscholar" / "app.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    runtime_hooks=[str(root / "packaging" / "runtime_hook.py")],
    excludes=["tkinter", "matplotlib", "IPython", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KurrentScholar",
    console=False,
    disable_windowed_traceback=False,
    **signing,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KurrentScholar",
    **signing,
)
app = BUNDLE(
    coll,
    name="KurrentScholar.app",
    icon=str(root / "assets" / "branding" / "kurrentscholar.icns"),
    bundle_identifier="de.kit.kurrentscholar",
    **signing,
    info_plist={
        "CFBundleDisplayName": "KurrentScholar",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSApplicationCategoryType": "public.app-category.education",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    },
)
