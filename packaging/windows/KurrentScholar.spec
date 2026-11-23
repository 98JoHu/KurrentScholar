# PyInstaller specification for a CPU-only Windows one-directory distribution.
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

root = Path(SPECPATH).parent.parent

datas = (
    collect_data_files("transformers")
    + collect_data_files("pypdfium2")
    + collect_data_files("certifi")
    + copy_metadata("huggingface-hub")
    + copy_metadata("transformers")
    + [(str(root / "src" / "kurrentscholar" / "assets" / "kurrentscholar-logo.png"), "kurrentscholar/assets")]
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
    # PyTorch imports both torch.distributed and torch.testing during ordinary
    # local CPU inference, so neither namespace may be excluded here.
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
    icon=str(root / "assets" / "branding" / "kurrentscholar.ico"),
    version=str(root / "packaging" / "windows" / "version_info.txt"),
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="KurrentScholar",
)

